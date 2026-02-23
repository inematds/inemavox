"""Gerenciador de Jobs - fila, subprocess, monitoramento, stats."""

import asyncio
import json
import os
import re
import signal
import subprocess
import time
import shutil
import sys
import uuid
from pathlib import Path
from typing import Optional

from api.stats_tracker import STAGES, estimate_remaining, record_job_complete, format_eta

JOBS_DIR = Path(os.environ.get("JOBS_DIR", "jobs"))
PIPELINE_SCRIPT = os.environ.get("PIPELINE_SCRIPT", "dublar_pro_v5.py")
PYTHON_BIN = os.environ.get("PYTHON_BIN", sys.executable or shutil.which("python3") or "python3")
DOCKER_GPU_IMAGE = os.environ.get("DOCKER_GPU_IMAGE", "inemavox:gpu")
PROJECT_DIR = Path(__file__).parent.parent.resolve()

# Stages para jobs de corte manual (3 etapas)
STAGES_CUT_MANUAL = [
    {"num": 1, "id": "download", "name": "Download", "icon": "⬇"},
    {"num": 2, "id": "cutting", "name": "Cortando clips", "icon": "✂"},
    {"num": 3, "id": "zip", "name": "Criando ZIP", "icon": "📦"},
]

# Stages para jobs de corte viral (6 etapas)
STAGES_CUT_VIRAL = [
    {"num": 1, "id": "download", "name": "Download", "icon": "⬇"},
    {"num": 2, "id": "extraction", "name": "Extracao de audio", "icon": "🔊"},
    {"num": 3, "id": "transcription", "name": "Transcricao", "icon": "📝"},
    {"num": 4, "id": "analysis", "name": "Analise viral", "icon": "🔥"},
    {"num": 5, "id": "cutting", "name": "Cortando clips", "icon": "✂"},
    {"num": 6, "id": "zip", "name": "Criando ZIP", "icon": "📦"},
]

# Stages para jobs de transcricao (4 etapas)
STAGES_TRANSCRIPTION = [
    {"num": 1, "id": "download", "name": "Download", "icon": "⬇"},
    {"num": 2, "id": "extraction", "name": "Extracao de audio", "icon": "🔊"},
    {"num": 3, "id": "transcription", "name": "Transcricao", "icon": "📝"},
    {"num": 4, "id": "export", "name": "Exportando legendas", "icon": "💾"},
]

# Stages para jobs de download (1 etapa)
STAGES_DOWNLOAD = [
    {"num": 1, "id": "download", "name": "Baixando video", "icon": "⬇"},
]

# Stages para jobs de TTS / Voice Clone (1 etapa)
STAGES_TTS = [
    {"num": 1, "id": "generating", "name": "Gerando audio", "icon": "🔊"},
]


def _detect_docker_gpu() -> bool:
    """Verifica se a imagem Docker GPU existe e Docker esta disponivel."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", DOCKER_GPU_IMAGE],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _detect_device() -> str:
    """Detecta se GPU CUDA esta disponivel (local ou Docker)."""
    # Se temos Docker GPU, reportar como cuda
    if DOCKER_GPU_AVAILABLE:
        return "cuda"
    # Tentar localmente
    try:
        result = subprocess.run(
            [PYTHON_BIN, "-c", "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else "cpu"
    except Exception:
        return "cpu"


def _detect_chatterbox_device() -> str:
    """Detecta se o ambiente Chatterbox tem GPU CUDA disponivel."""
    chatterbox_python = os.environ.get(
        "CHATTERBOX_PYTHON",
        "/home/nmaldaner/miniconda3/envs/chatterbox/bin/python3",
    )
    try:
        result = subprocess.run(
            [chatterbox_python, "-c", "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')"],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout.strip() if result.returncode == 0 else "cpu"
    except Exception:
        return "cpu"


# Detectar capacidades ao iniciar
DOCKER_GPU_AVAILABLE = _detect_docker_gpu()
DEVICE = _detect_device()
CHATTERBOX_DEVICE = _detect_chatterbox_device()

# Log de inicializacao
_mode = "Docker GPU" if DOCKER_GPU_AVAILABLE else f"Local ({DEVICE})"
print(f"[JobManager] Modo: {_mode} | Device: {DEVICE} | Chatterbox: {CHATTERBOX_DEVICE} | Image: {DOCKER_GPU_IMAGE}")


class Job:
    def __init__(self, job_id: str, config: dict):
        self.id = job_id
        self.config = config
        self.status = "queued"
        self.created_at = time.time()
        self.started_at = None
        self.finished_at = None
        self.process: Optional[subprocess.Popen] = None
        self.workdir = JOBS_DIR / job_id
        self.error = None
        self.device = DEVICE
        self.stage_times: dict[str, float] = {}
        self._last_stage_num = 0
        self._last_stage_start = 0.0

    @property
    def duration(self) -> float:
        if self.started_at is None:
            return 0
        end = self.finished_at or time.time()
        return end - self.started_at

    def _get_stages(self) -> list:
        """Retorna a lista de stages corretos baseado no tipo de job."""
        job_type = self.config.get("job_type", "dubbing")
        if job_type == "cutting":
            mode = self.config.get("mode", "manual")
            if mode == "viral" and not self.config.get("split_equal"):
                return STAGES_CUT_VIRAL
            return STAGES_CUT_MANUAL
        elif job_type == "transcription":
            return STAGES_TRANSCRIPTION
        elif job_type == "download":
            return STAGES_DOWNLOAD
        elif job_type in ("tts_generate", "voice_clone"):
            return STAGES_TTS
        else:
            return STAGES

    def _recover_if_output_exists(self):
        """Se marcado como failed mas arquivos de saida existem, recuperar para completed."""
        if self.status != "failed":
            return
        job_type = self.config.get("job_type", "dubbing")
        if job_type == "transcription":
            td = self.workdir / "transcription"
            if td.exists() and any(td.glob("transcript.*")):
                self.status = "completed"
                self.error = None
        elif job_type == "cutting":
            cd = self.workdir / "clips"
            if cd.exists() and any(cd.glob("clip_*.mp4")):
                self.status = "completed"
                self.error = None
        elif job_type == "download":
            dd = self.workdir / "download"
            if dd.exists() and any(dd.glob("video.*")):
                self.status = "completed"
                self.error = None
        elif job_type in ("tts_generate", "voice_clone"):
            ao = self.workdir / "audio_out"
            if ao.exists() and any(ao.glob("generated.*")):
                self.status = "completed"
                self.error = None
        else:
            dd = self.workdir / "dublado"
            if dd.exists() and any(dd.glob("*.mp4")):
                self.status = "completed"
                self.error = None

    def to_dict(self) -> dict:
        self._recover_if_output_exists()
        checkpoint = self._read_checkpoint()
        progress = self._calc_progress(checkpoint)
        return {
            "id": self.id,
            "status": self.status,
            "config": self.config,
            "device": self.device,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": round(self.duration, 1),
            "error": self.error,
            "checkpoint": checkpoint,
            "progress": progress,
            "stage_times": self.stage_times,
        }

    def _read_checkpoint(self) -> dict:
        cp_path = self.workdir / "dub_work" / "checkpoint.json"
        if cp_path.exists():
            try:
                return json.loads(cp_path.read_text())
            except Exception:
                pass
        return {}

    def _calc_progress_simple(self, checkpoint: dict) -> dict:
        """Calculo de progresso simplificado para jobs nao-dubbing (sem ETA)."""
        stages = self._get_stages()
        current_step = checkpoint.get("last_step_num", 0)
        total = len(stages)
        percent = round((current_step / total) * 100) if total > 0 else 0

        # Trackear tempo das etapas
        if current_step != self._last_stage_num and current_step > 0:
            now = time.time()
            start_time = self._last_stage_start if self._last_stage_start > 0 else (self.started_at or now)
            elapsed = round(now - start_time, 1)

            stages_completed = current_step - self._last_stage_num
            if stages_completed > 0:
                per_stage = round(elapsed / stages_completed, 1)
                for i in range(self._last_stage_num, current_step):
                    if i < len(stages):
                        self.stage_times[stages[i]["id"]] = per_stage

            self._last_stage_num = current_step
            self._last_stage_start = now
        elif self._last_stage_num == 0 and self.started_at:
            self._last_stage_start = self.started_at

        current_stage_elapsed = round(time.time() - self._last_stage_start, 1) if self._last_stage_start > 0 else 0

        # Montar info das stages
        stages_info = []
        for stage in stages:
            snum = stage["num"]
            sid = stage["id"]
            if snum < current_step + 1:
                st = {**stage, "status": "done", "time": self.stage_times.get(sid)}
            elif snum == current_step + 1:
                st = {**stage, "status": "running", "elapsed": current_stage_elapsed}
                log_progress = self._parse_log_progress()
                if log_progress:
                    st["log_progress"] = log_progress
            else:
                st = {**stage, "status": "pending"}
            stages_info.append(st)

        stage_name = stages[current_step]["name"] if current_step < total else "Concluido"
        stage_id = stages[current_step]["id"] if current_step < total else "done"

        return {
            "current_stage": current_step,
            "next_stage": current_step + 1,
            "total_stages": total,
            "percent": percent,
            "stage_name": stage_name,
            "stage_id": stage_id,
            "stages": stages_info,
            "device": self.device,
            "eta_seconds": None,
            "eta_text": None,
            "eta_confidence": "low",
            "elapsed_s": round(self.duration, 1),
        }

    def _calc_progress(self, checkpoint: dict) -> dict:
        job_type = self.config.get("job_type", "dubbing")
        if job_type != "dubbing":
            return self._calc_progress_simple(checkpoint)

        current_step = checkpoint.get("last_step_num", 0)
        total = len(STAGES)
        percent = round((current_step / total) * 100) if total > 0 else 0

        # Trackear tempo das etapas
        if current_step != self._last_stage_num and current_step > 0:
            now = time.time()
            start_time = self._last_stage_start if self._last_stage_start > 0 else (self.started_at or now)
            elapsed = round(now - start_time, 1)

            # Quantas etapas completaram desde o ultimo check
            stages_completed = current_step - self._last_stage_num
            if stages_completed > 0:
                per_stage = round(elapsed / stages_completed, 1)
                for i in range(self._last_stage_num, current_step):
                    if i < len(STAGES):
                        self.stage_times[STAGES[i]["id"]] = per_stage

            self._last_stage_num = current_step
            self._last_stage_start = now
        elif self._last_stage_num == 0 and self.started_at:
            self._last_stage_start = self.started_at

        # Calcular ETA
        eta = estimate_remaining(self.config, current_step, 0, self.device)
        eta_text = format_eta(eta["eta_seconds"]) if eta else "?"

        # Tempo na etapa atual
        current_stage_elapsed = round(time.time() - self._last_stage_start, 1) if self._last_stage_start > 0 else 0

        # Mapa de ferramenta por etapa baseado na config do job
        cfg = self.config
        asr_label = cfg.get("asr_engine", "whisper")
        if asr_label == "whisper":
            asr_label = f"whisper {cfg.get('whisper_model', 'large-v3')}"
        else:
            pm = cfg.get("parakeet_model", "nvidia/parakeet-tdt-1.1b")
            asr_label = f"parakeet {pm.split('/')[-1]}"
        trad_label = cfg.get("translation_engine", "m2m100")
        if trad_label == "ollama" and cfg.get("ollama_model"):
            trad_label = f"ollama ({cfg['ollama_model']})"
        stage_tools = {
            "download": "yt-dlp",
            "extraction": "ffmpeg",
            "transcription": asr_label,
            "translation": trad_label,
            "split": "ffmpeg",
            "tts": cfg.get("tts_engine", "edge"),
            "sync": cfg.get("sync_mode", "smart"),
            "concat": "ffmpeg",
            "postprocess": "rubberband",
            "mux": "ffmpeg",
        }

        # Montar info das stages
        stages_info = []
        for stage in STAGES:
            snum = stage["num"]
            sid = stage["id"]
            tool = stage_tools.get(sid, "")
            if snum < current_step + 1:
                st = {**stage, "status": "done", "time": self.stage_times.get(sid), "tool": tool}
            elif snum == current_step + 1:
                st = {**stage, "status": "running", "elapsed": current_stage_elapsed, "tool": tool}
                # Adicionar progresso detalhado do log (ex: yt-dlp %)
                log_progress = self._parse_log_progress()
                if log_progress:
                    st["log_progress"] = log_progress
            else:
                est = eta["stage_estimates"].get(sid, {}).get("est_seconds") if eta else None
                st = {**stage, "status": "pending", "estimate": est, "tool": tool}
            stages_info.append(st)

        return {
            "current_stage": current_step,
            "next_stage": current_step + 1,
            "total_stages": total,
            "percent": percent,
            "stage_name": STAGES[current_step]["name"] if current_step < total else "Concluido",
            "stage_id": STAGES[current_step]["id"] if current_step < total else "done",
            "stages": stages_info,
            "device": self.device,
            "eta_seconds": eta["eta_seconds"] if eta else None,
            "eta_text": eta_text,
            "eta_confidence": eta["confidence"] if eta else "low",
            "elapsed_s": round(self.duration, 1),
        }

    def _parse_log_progress(self) -> dict | None:
        """Extrai progresso do yt-dlp ou outras ferramentas do output.log."""
        log_path = self.workdir / "output.log"
        if not log_path.exists():
            return None
        try:
            # Ler ultimos 4KB do log (suficiente para a linha mais recente)
            with open(log_path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 4096))
                tail = f.read().decode("utf-8", errors="replace")
            # yt-dlp: "[download]  52.3% of  371.95MiB at    5.38MiB/s ETA 00:32"
            match = re.search(
                r"\[download\]\s+([\d.]+)%\s+of\s+~?([\d.]+\S+)\s+at\s+([\d.]+\S+)\s+ETA\s+(\S+)",
                tail,
            )
            if match:
                return {
                    "type": "download",
                    "percent": float(match.group(1)),
                    "size": match.group(2),
                    "speed": match.group(3),
                    "eta": match.group(4),
                }
            # ffmpeg merge: "[Merger] Merging formats into ..."
            if "[Merger]" in tail or "Merging formats" in tail:
                return {"type": "download", "percent": 99, "detail": "Mesclando audio+video..."}
        except Exception:
            pass
        return None

    def read_logs(self, last_n: int = 50) -> list:
        log_path = self.workdir / "output.log"
        if not log_path.exists():
            return []
        try:
            lines = log_path.read_text().splitlines()
            return lines[-last_n:]
        except Exception:
            return []


class JobManager:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._subscribers: dict[str, list] = {}
        JOBS_DIR.mkdir(exist_ok=True)

    def start(self):
        self._load_existing_jobs()
        self._worker_task = asyncio.create_task(self._worker())

    def _load_existing_jobs(self):
        """Recarrega jobs existentes do disco (sobrevive a restarts/reloads)."""
        if not JOBS_DIR.exists():
            return
        loaded = 0
        for job_dir in sorted(JOBS_DIR.iterdir()):
            if not job_dir.is_dir():
                continue
            config_path = job_dir / "config.json"
            if not config_path.exists():
                continue
            job_id = job_dir.name
            # Re-avaliar jobs que estavam em estado terminal mas podem ter
            # concluido durante um reload (Docker container continuou rodando)
            existing = self.jobs.get(job_id)
            if existing and existing.status in ("completed", "running", "queued"):
                continue
            if existing and existing.status in ("failed", "cancelled"):
                # Re-checar se os arquivos de saida existem agora
                existing_config = existing.config
                existing_type = existing_config.get("job_type", "dubbing")
                if existing_type == "cutting":
                    clips_dir = job_dir / "clips"
                    if clips_dir.exists() and any(clips_dir.glob("clip_*.mp4")):
                        existing.status = "completed"
                        existing.error = None
                elif existing_type == "transcription":
                    transcript_dir = job_dir / "transcription"
                    if transcript_dir.exists() and any(transcript_dir.glob("transcript.*")):
                        existing.status = "completed"
                        existing.error = None
                elif existing_type == "download":
                    dl_dir = job_dir / "download"
                    if dl_dir.exists() and any(dl_dir.glob("video.*")):
                        existing.status = "completed"
                        existing.error = None
                else:
                    dublado_dir = job_dir / "dublado"
                    if dublado_dir.exists() and any(dublado_dir.glob("*.mp4")):
                        existing.status = "completed"
                        existing.error = None
                continue
            try:
                config = json.loads(config_path.read_text())
                job = Job(job_id, config)
                job_type = config.get("job_type", "dubbing")

                # Aplicar device correto para jobs de Chatterbox
                if config.get("engine") in ("chatterbox", "chatterbox-vc") or (
                    job_type == "dubbing" and config.get("tts_engine") == "chatterbox"
                ):
                    job.device = CHATTERBOX_DEVICE

                # Transcricao usa Whisper GPU via conda env quando CUDA disponivel
                if job_type == "transcription" and CHATTERBOX_DEVICE == "cuda":
                    job.device = CHATTERBOX_DEVICE

                # Restaurar created_at real (mtime do config.json = momento da criacao)
                job.created_at = config_path.stat().st_mtime
                # Restaurar stage_times se existir
                times_path = job_dir / "stage_times.json"
                if times_path.exists():
                    try:
                        job.stage_times = json.loads(times_path.read_text())
                    except Exception:
                        pass
                # Determinar status pelo que existe no disco
                checkpoint = job._read_checkpoint()
                # Sincronizar _last_stage_num com checkpoint para evitar
                # que _calc_progress recalcule e sobrescreva stage_times
                if checkpoint.get("last_step_num"):
                    job._last_stage_num = checkpoint["last_step_num"]

                # Restaurar started_at e finished_at a partir dos arquivos
                log_path = job_dir / "output.log"
                if log_path.exists():
                    log_stat = log_path.stat()
                    job.started_at = log_stat.st_mtime
                    if job.stage_times:
                        total_dur = sum(job.stage_times.values())
                        job.started_at = job.created_at
                        job.finished_at = job.created_at + total_dur

                # Detectar conclusao por tipo de job
                if job_type == "cutting":
                    clips_dir = job_dir / "clips"
                    has_output = clips_dir.exists() and any(clips_dir.glob("clip_*.mp4"))
                elif job_type == "transcription":
                    transcript_dir = job_dir / "transcription"
                    has_output = transcript_dir.exists() and any(
                        transcript_dir.glob("transcript.*")
                    )
                elif job_type == "download":
                    dl_dir = job_dir / "download"
                    has_output = dl_dir.exists() and any(dl_dir.glob("video.*"))
                else:
                    dublado_dir = job_dir / "dublado"
                    has_output = dublado_dir.exists() and any(dublado_dir.glob("*.mp4"))

                if has_output:
                    job.status = "completed"
                elif log_path.exists():
                    log_text = log_path.read_text()
                    if "Traceback" in log_text or "Error" in log_text[-500:]:
                        job.status = "failed"
                        for line in reversed(log_text.splitlines()[-20:]):
                            if "error" in line.lower() or "exception" in line.lower():
                                job.error = line.strip()
                                break
                    elif checkpoint:
                        job.status = "failed"
                        job.error = f"Interrompido na etapa {checkpoint.get('last_step', '?')}"
                    else:
                        job.status = "failed"
                else:
                    job.status = "queued"
                self.jobs[job_id] = job
                loaded += 1
            except Exception as e:
                print(f"[JobManager] Erro ao carregar job {job_id}: {e}")
        if loaded:
            print(f"[JobManager] {loaded} jobs carregados do disco")

    async def _worker(self):
        while True:
            job_id = await self.queue.get()
            job = self.jobs.get(job_id)
            if job and job.status == "queued":
                await self._run_job(job)
            self.queue.task_done()

    async def create_job(self, config: dict) -> Job:
        job_id = str(uuid.uuid4())[:8]
        job = Job(job_id, config)
        job_type = config.get("job_type", "dubbing")

        # Jobs de Chatterbox rodam no env conda com CUDA
        if config.get("engine") in ("chatterbox", "chatterbox-vc") or (
            job_type == "dubbing" and config.get("tts_engine") == "chatterbox"
        ):
            job.device = CHATTERBOX_DEVICE

        # Transcricao usa Whisper GPU via conda env quando CUDA disponivel
        if job_type == "transcription" and CHATTERBOX_DEVICE == "cuda":
            job.device = CHATTERBOX_DEVICE

        job.workdir.mkdir(parents=True, exist_ok=True)
        (job.workdir / "dub_work").mkdir(exist_ok=True)

        if job_type == "cutting":
            (job.workdir / "clips").mkdir(exist_ok=True)
        elif job_type == "transcription":
            (job.workdir / "transcription").mkdir(exist_ok=True)
        elif job_type == "download":
            (job.workdir / "download").mkdir(exist_ok=True)
        elif job_type in ("tts_generate", "voice_clone"):
            (job.workdir / "audio_out").mkdir(exist_ok=True)
        else:
            (job.workdir / "dublado").mkdir(exist_ok=True)

        self.jobs[job_id] = job
        (job.workdir / "config.json").write_text(json.dumps(config, indent=2))

        await self.queue.put(job_id)
        await self._notify(job_id, {"event": "created", "job": job.to_dict()})
        return job

    async def _run_job(self, job: Job):
        job.status = "running"
        job.started_at = time.time()
        job._last_stage_start = job.started_at
        await self._notify(job.id, {"event": "started", "job": job.to_dict()})

        job_type = job.config.get("job_type", "dubbing")

        if DOCKER_GPU_AVAILABLE:
            if job_type == "cutting":
                cmd = self._build_docker_cut_command(job)
            elif job_type == "transcription":
                cmd = self._build_docker_transcribe_command(job)
            elif job_type == "download":
                cmd = self._build_docker_download_command(job)
            elif job_type in ("tts_generate", "voice_clone"):
                cmd = self._build_local_tts_command(job)
            else:
                cmd = self._build_docker_command(job)
        else:
            if job_type == "cutting":
                cmd = self._build_local_cut_command(job)
            elif job_type == "transcription":
                cmd = self._build_local_transcribe_command(job)
            elif job_type == "download":
                cmd = self._build_local_download_command(job)
            elif job_type in ("tts_generate", "voice_clone"):
                cmd = self._build_local_tts_command(job)
            else:
                cmd = self._build_local_command(job)

        log_path = job.workdir / "output.log"

        try:
            env = os.environ.copy()
            if not DOCKER_GPU_AVAILABLE:
                python_dir = os.path.dirname(PYTHON_BIN)
                if python_dir not in env.get("PATH", ""):
                    env["PATH"] = python_dir + ":" + env.get("PATH", "")

            with open(log_path, "w") as log_file:
                # Docker roda do project dir, local roda do workdir
                cwd = str(PROJECT_DIR) if DOCKER_GPU_AVAILABLE else str(job.workdir)

                job.process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    cwd=cwd,
                    env=env,
                )

                while job.process.poll() is None:
                    await asyncio.sleep(2)
                    await self._notify(job.id, {
                        "event": "progress",
                        "job": job.to_dict(),
                    })

                exit_code = job.process.returncode
                job.finished_at = time.time()

                # Processar todas as transicoes de etapa pendentes
                checkpoint = job._read_checkpoint()
                job._calc_progress(checkpoint)

                # Registrar tempo da ultima etapa
                stages = job._get_stages()
                if job._last_stage_num > 0 and job._last_stage_num <= len(stages):
                    last_sid = stages[job._last_stage_num - 1]["id"]
                    job.stage_times[last_sid] = round(job.finished_at - job._last_stage_start, 1)

                # Persistir stage_times em disco (sobrevive a restarts)
                try:
                    times_path = job.workdir / "stage_times.json"
                    times_path.write_text(json.dumps(job.stage_times, indent=2))
                except Exception:
                    pass

                if exit_code == 0:
                    job.status = "completed"
                    # Salvar estatisticas para aprendizado (apenas dubbing)
                    if job_type == "dubbing":
                        record_job_complete(job.config, job.stage_times, job.duration, job.device)
                elif exit_code == -signal.SIGTERM or exit_code == -signal.SIGKILL:
                    job.status = "cancelled"
                else:
                    job.status = "failed"
                    error_msg = f"Exit code: {exit_code}"
                    try:
                        lines = log_path.read_text().splitlines()
                        for line in reversed(lines[-20:]):
                            if "error" in line.lower() or "traceback" in line.lower() or "exception" in line.lower():
                                error_msg = line.strip()
                                break
                    except Exception:
                        pass
                    job.error = error_msg

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.finished_at = time.time()

        await self._notify(job.id, {"event": "finished", "job": job.to_dict()})

    def _build_docker_cut_command(self, job: Job) -> list:
        """Monta comando Docker para corte de clips."""
        config = job.config
        workdir_abs = str(job.workdir.resolve())
        script_path = str(PROJECT_DIR / "clipar_v1.py")
        hf_cache = str(Path.home() / ".cache" / "huggingface")
        whisper_cache = str(Path.home() / ".cache" / "whisper")

        Path(hf_cache).mkdir(parents=True, exist_ok=True)
        Path(whisper_cache).mkdir(parents=True, exist_ok=True)

        cmd = [
            "docker", "run", "--rm",
            "--gpus", "all",
            "--ipc=host",
            "--name", f"inemavox-{job.id}",
            "--ulimit", "memlock=-1",
            "--ulimit", "stack=67108864",
            "--network", "host",
            # Script montado como volume read-only
            "-v", f"{script_path}:/app/clipar_v1.py:ro",
            # Dirs de trabalho
            "-v", f"{workdir_abs}/dub_work:/app/dub_work",
            "-v", f"{workdir_abs}/clips:/app/clips",
            # Cache de modelos
            "-v", f"{hf_cache}:/root/.cache/huggingface",
            "-v", f"{whisper_cache}:/root/.cache/whisper",
            # Sobrescrever entrypoint para rodar nosso script
            "--entrypoint", "python",
            DOCKER_GPU_IMAGE,
            "/app/clipar_v1.py",
        ]

        input_val = config["input"]
        if not input_val.startswith("http") and os.path.exists(input_val):
            input_abs = str(Path(input_val).resolve())
            cmd.insert(-3, "-v")
            cmd.insert(-3, f"{input_abs}:/app/input_video{Path(input_val).suffix}")
            input_val = f"/app/input_video{Path(input_val).suffix}"

        cmd.extend(["--in", input_val])
        cmd.extend(["--outdir", "/app/clips"])
        cmd.extend(["--mode", config.get("mode", "manual")])

        if config.get("mode") == "manual" and config.get("timestamps"):
            cmd.extend(["--timestamps", config["timestamps"]])
        elif config.get("mode") == "viral":
            if config.get("num_clips"):
                cmd.extend(["--num-clips", str(config["num_clips"])])
            if config.get("split_equal"):
                cmd.append("--split-equal")
            else:
                if config.get("ollama_model"):
                    cmd.extend(["--ollama-model", config["ollama_model"]])
                if config.get("min_duration"):
                    cmd.extend(["--min-duration", str(config["min_duration"])])
                if config.get("max_duration"):
                    cmd.extend(["--max-duration", str(config["max_duration"])])
                if config.get("whisper_model"):
                    cmd.extend(["--whisper-model", config["whisper_model"]])
                if config.get("llm_provider") and config["llm_provider"] != "ollama":
                    cmd.extend(["--llm-provider", config["llm_provider"]])
                if config.get("llm_model"):
                    cmd.extend(["--llm-model", config["llm_model"]])
                if config.get("llm_api_key"):
                    cmd.extend(["--llm-api-key", config["llm_api_key"]])
                if config.get("llm_base_url"):
                    cmd.extend(["--llm-base-url", config["llm_base_url"]])
                if config.get("system_prompt"):
                    cmd.extend(["--system-prompt", config["system_prompt"]])
                if config.get("user_prompt"):
                    cmd.extend(["--user-prompt", config["user_prompt"]])

        return cmd

    def _build_local_cut_command(self, job: Job) -> list:
        """Monta comando local para corte de clips."""
        config = job.config
        script_path = str(PROJECT_DIR / "clipar_v1.py")
        cmd = [PYTHON_BIN, script_path]

        cmd.extend(["--in", config["input"]])
        cmd.extend(["--outdir", str(job.workdir.resolve() / "clips")])
        cmd.extend(["--mode", config.get("mode", "manual")])

        if config.get("mode") == "manual" and config.get("timestamps"):
            cmd.extend(["--timestamps", config["timestamps"]])
        elif config.get("mode") == "viral":
            if config.get("num_clips"):
                cmd.extend(["--num-clips", str(config["num_clips"])])
            if config.get("split_equal"):
                cmd.append("--split-equal")
            else:
                if config.get("ollama_model"):
                    cmd.extend(["--ollama-model", config["ollama_model"]])
                if config.get("min_duration"):
                    cmd.extend(["--min-duration", str(config["min_duration"])])
                if config.get("max_duration"):
                    cmd.extend(["--max-duration", str(config["max_duration"])])
                if config.get("whisper_model"):
                    cmd.extend(["--whisper-model", config["whisper_model"]])
                if config.get("llm_provider") and config["llm_provider"] != "ollama":
                    cmd.extend(["--llm-provider", config["llm_provider"]])
                if config.get("llm_model"):
                    cmd.extend(["--llm-model", config["llm_model"]])
                if config.get("llm_api_key"):
                    cmd.extend(["--llm-api-key", config["llm_api_key"]])
                if config.get("llm_base_url"):
                    cmd.extend(["--llm-base-url", config["llm_base_url"]])
                if config.get("system_prompt"):
                    cmd.extend(["--system-prompt", config["system_prompt"]])
                if config.get("user_prompt"):
                    cmd.extend(["--user-prompt", config["user_prompt"]])

        return cmd

    def _build_docker_transcribe_command(self, job: Job) -> list:
        """Monta comando Docker para transcricao."""
        config = job.config
        workdir_abs = str(job.workdir.resolve())
        script_path = str(PROJECT_DIR / "transcrever_v1.py")
        hf_cache = str(Path.home() / ".cache" / "huggingface")
        whisper_cache = str(Path.home() / ".cache" / "whisper")

        Path(hf_cache).mkdir(parents=True, exist_ok=True)
        Path(whisper_cache).mkdir(parents=True, exist_ok=True)

        cmd = [
            "docker", "run", "--rm",
            "--gpus", "all",
            "--ipc=host",
            "--name", f"inemavox-{job.id}",
            "--ulimit", "memlock=-1",
            "--ulimit", "stack=67108864",
            "--network", "host",
            "-v", f"{script_path}:/app/transcrever_v1.py:ro",
            "-v", f"{workdir_abs}/dub_work:/app/dub_work",
            "-v", f"{workdir_abs}/transcription:/app/transcription",
            "-v", f"{hf_cache}:/root/.cache/huggingface",
            "-v", f"{whisper_cache}:/root/.cache/whisper",
            "--entrypoint", "python",
            DOCKER_GPU_IMAGE,
            "/app/transcrever_v1.py",
        ]

        input_val = config["input"]
        if not input_val.startswith("http") and os.path.exists(input_val):
            input_abs = str(Path(input_val).resolve())
            cmd.insert(-3, "-v")
            cmd.insert(-3, f"{input_abs}:/app/input_video{Path(input_val).suffix}")
            input_val = f"/app/input_video{Path(input_val).suffix}"

        cmd.extend(["--in", input_val])
        cmd.extend(["--outdir", "/app/transcription"])

        asr = config.get("asr_engine", "whisper")
        cmd.extend(["--asr", asr])
        if config.get("whisper_model"):
            cmd.extend(["--whisper-model", config["whisper_model"]])
        if config.get("src_lang"):
            cmd.extend(["--src", config["src_lang"]])

        return cmd

    def _build_local_transcribe_command(self, job: Job) -> list:
        """Monta comando local para transcricao."""
        config = job.config
        script_path = str(PROJECT_DIR / "transcrever_v1.py")
        cmd = [PYTHON_BIN, script_path]

        cmd.extend(["--in", config["input"]])
        cmd.extend(["--outdir", str(job.workdir.resolve() / "transcription")])

        asr = config.get("asr_engine", "whisper")
        cmd.extend(["--asr", asr])
        if config.get("whisper_model"):
            cmd.extend(["--whisper-model", config["whisper_model"]])
        if config.get("src_lang"):
            cmd.extend(["--src", config["src_lang"]])

        return cmd

    def _build_docker_download_command(self, job: Job) -> list:
        """Monta comando Docker para download de video."""
        config = job.config
        workdir_abs = str(job.workdir.resolve())
        script_path = str(PROJECT_DIR / "baixar_v1.py")

        cmd = [
            "docker", "run", "--rm",
            "--gpus", "all",
            "--ipc=host",
            "--name", f"inemavox-{job.id}",
            "--ulimit", "memlock=-1",
            "--ulimit", "stack=67108864",
            "--network", "host",
            "-v", f"{script_path}:/app/baixar_v1.py:ro",
            "-v", f"{workdir_abs}/dub_work:/app/dub_work",
            "-v", f"{workdir_abs}/download:/app/download",
            "--entrypoint", "python",
            DOCKER_GPU_IMAGE,
            "/app/baixar_v1.py",
            "--outdir", "/app/download",
        ]

        if config.get("local_file"):
            local_abs = str(Path(config["local_file"]).resolve())
            cmd.insert(-3, "-v")
            cmd.insert(-3, f"{local_abs}:/app/local_input{Path(config['local_file']).suffix}")
            cmd.extend(["--local-file", f"/app/local_input{Path(config['local_file']).suffix}"])
        else:
            cmd.extend(["--url", config["url"]])

        if config.get("quality"):
            cmd.extend(["--quality", config["quality"]])

        return cmd

    def _build_local_download_command(self, job: Job) -> list:
        """Monta comando local para download de video ou processamento de arquivo local."""
        config = job.config
        script_path = str(PROJECT_DIR / "baixar_v1.py")

        cmd = [
            PYTHON_BIN, script_path,
            "--outdir", str(job.workdir.resolve() / "download"),
        ]

        if config.get("local_file"):
            cmd.extend(["--local-file", config["local_file"]])
        else:
            cmd.extend(["--url", config["url"]])

        if config.get("quality"):
            cmd.extend(["--quality", config["quality"]])

        return cmd

    def _build_local_tts_command(self, job: Job) -> list:
        """Monta comando local para geracao de audio (TTS / Voice Clone)."""
        config = job.config
        script_path = str(PROJECT_DIR / "tts_direct.py")
        outdir = str(job.workdir.resolve() / "audio_out")

        cmd = [
            PYTHON_BIN, script_path,
            "--text", config["text"],
            "--lang", config.get("lang", "pt"),
            "--engine", config.get("engine", "edge"),
            "--outdir", outdir,
        ]
        if config.get("voice"):
            cmd.extend(["--voice", config["voice"]])
        if config.get("ref_audio") and Path(config["ref_audio"]).exists():
            cmd.extend(["--ref", config["ref_audio"]])
        if config.get("cfg_weight") is not None:
            cmd.extend(["--cfg-weight", str(config["cfg_weight"])])
        if config.get("exaggeration") is not None:
            cmd.extend(["--exaggeration", str(config["exaggeration"])])
        if config.get("temperature") is not None:
            cmd.extend(["--temperature", str(config["temperature"])])

        return cmd

    def _build_docker_command(self, job: Job) -> list:
        """Monta comando para rodar pipeline dentro do Docker com GPU."""
        config = job.config
        workdir_abs = str(job.workdir.resolve())
        hf_cache = str(Path.home() / ".cache" / "huggingface")
        whisper_cache = str(Path.home() / ".cache" / "whisper")

        # Garantir que os dirs de cache existam no host
        Path(hf_cache).mkdir(parents=True, exist_ok=True)
        Path(whisper_cache).mkdir(parents=True, exist_ok=True)

        cmd = [
            "docker", "run", "--rm",
            "--gpus", "all",
            "--ipc=host",
            "--name", f"inemavox-{job.id}",
            "--ulimit", "memlock=-1",
            "--ulimit", "stack=67108864",
            # Network host para acessar Ollama no localhost:11434
            "--network", "host",
            # Montar workdir do job (checkpoint, logs, output)
            "-v", f"{workdir_abs}/dub_work:/app/dub_work",
            "-v", f"{workdir_abs}/dublado:/app/dublado",
            # Cache de modelos HuggingFace (evitar re-download)
            "-v", f"{hf_cache}:/root/.cache/huggingface",
            # Cache OpenAI Whisper (evitar re-download do modelo ~3GB)
            "-v", f"{whisper_cache}:/root/.cache/whisper",
            # Imagem
            DOCKER_GPU_IMAGE,
        ]

        # Argumentos do pipeline (passados ao ENTRYPOINT)
        input_val = config["input"]

        # Se input e um arquivo local, montar no container
        if not input_val.startswith("http") and os.path.exists(input_val):
            input_abs = str(Path(input_val).resolve())
            cmd.insert(-1, "-v")
            cmd.insert(-1, f"{input_abs}:/app/input_video{Path(input_val).suffix}")
            input_val = f"/app/input_video{Path(input_val).suffix}"

        cmd.extend(["--in", input_val])

        if config.get("src_lang"):
            cmd.extend(["--src", config["src_lang"]])
        cmd.extend(["--tgt", config.get("tgt_lang", "pt")])

        cmd.extend(["--outdir", "/app/dublado"])

        asr = config.get("asr_engine", "whisper")
        cmd.extend(["--asr", asr])
        if config.get("whisper_model"):
            cmd.extend(["--whisper-model", config["whisper_model"]])
        if asr == "parakeet" and config.get("parakeet_model"):
            cmd.extend(["--parakeet-model", config["parakeet_model"]])

        tradutor = config.get("translation_engine", "m2m100")
        cmd.extend(["--tradutor", tradutor])
        if tradutor == "ollama" and config.get("ollama_model"):
            cmd.extend(["--modelo", config["ollama_model"]])
        if config.get("large_model"):
            cmd.append("--large-model")

        tts = config.get("tts_engine", "edge")
        cmd.extend(["--tts", tts])
        if config.get("voice"):
            cmd.extend(["--voice", config["voice"]])
        if config.get("tts_rate"):
            cmd.extend(["--rate", config["tts_rate"]])

        if config.get("sync_mode"):
            cmd.extend(["--sync", config["sync_mode"]])
        if config.get("maxstretch"):
            cmd.extend(["--maxstretch", str(config["maxstretch"])])
        if config.get("tolerance"):
            cmd.extend(["--tolerance", str(config["tolerance"])])
        if config.get("no_truncate"):
            cmd.append("--no-truncate")
        if config.get("use_rubberband") is False:
            cmd.append("--no-rubberband")

        if config.get("diarize"):
            cmd.append("--diarize")
            if config.get("num_speakers"):
                cmd.extend(["--num-speakers", str(config["num_speakers"])])

        if config.get("clone_voice"):
            cmd.append("--clonar-voz")

        if config.get("maxdur"):
            cmd.extend(["--maxdur", str(config["maxdur"])])
        if config.get("seed"):
            cmd.extend(["--seed", str(config["seed"])])

        return cmd

    def _build_local_command(self, job: Job) -> list:
        """Monta comando para rodar pipeline localmente (CPU)."""
        config = job.config
        cmd = [PYTHON_BIN, os.path.abspath(PIPELINE_SCRIPT)]

        cmd.extend(["--in", config["input"]])

        if config.get("src_lang"):
            cmd.extend(["--src", config["src_lang"]])
        cmd.extend(["--tgt", config.get("tgt_lang", "pt")])

        cmd.extend(["--outdir", str(job.workdir.resolve() / "dublado")])

        asr = config.get("asr_engine", "whisper")
        cmd.extend(["--asr", asr])
        if config.get("whisper_model"):
            cmd.extend(["--whisper-model", config["whisper_model"]])
        if asr == "parakeet" and config.get("parakeet_model"):
            cmd.extend(["--parakeet-model", config["parakeet_model"]])

        tradutor = config.get("translation_engine", "m2m100")
        cmd.extend(["--tradutor", tradutor])
        if tradutor == "ollama" and config.get("ollama_model"):
            cmd.extend(["--modelo", config["ollama_model"]])
        if config.get("large_model"):
            cmd.append("--large-model")

        tts = config.get("tts_engine", "edge")
        cmd.extend(["--tts", tts])
        if config.get("voice"):
            cmd.extend(["--voice", config["voice"]])
        if config.get("tts_rate"):
            cmd.extend(["--rate", config["tts_rate"]])

        if config.get("sync_mode"):
            cmd.extend(["--sync", config["sync_mode"]])
        if config.get("maxstretch"):
            cmd.extend(["--maxstretch", str(config["maxstretch"])])
        if config.get("tolerance"):
            cmd.extend(["--tolerance", str(config["tolerance"])])
        if config.get("no_truncate"):
            cmd.append("--no-truncate")
        if config.get("use_rubberband") is False:
            cmd.append("--no-rubberband")

        if config.get("diarize"):
            cmd.append("--diarize")
            if config.get("num_speakers"):
                cmd.extend(["--num-speakers", str(config["num_speakers"])])

        if config.get("clone_voice"):
            cmd.append("--clonar-voz")

        if config.get("maxdur"):
            cmd.extend(["--maxdur", str(config["maxdur"])])
        if config.get("seed"):
            cmd.extend(["--seed", str(config["seed"])])

        return cmd

    async def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        if job.process and job.process.poll() is None:
            job.process.terminate()
            try:
                job.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                job.process.kill()
            job.status = "cancelled"
            job.finished_at = time.time()
            await self._notify(job_id, {"event": "cancelled", "job": job.to_dict()})
            return True
        return False

    async def delete_job(self, job_id: str) -> bool:
        """Cancela (se rodando/na fila) e deleta arquivos + entrada do job."""
        job = self.jobs.get(job_id)
        if not job:
            return False
        # Cancelar processo se ativo
        if job.status == "running" and job.process and job.process.poll() is None:
            job.process.terminate()
            try:
                job.process.wait(timeout=5)
            except Exception:
                job.process.kill()
        # Remover da fila se queued
        job.status = "deleted"
        # Deletar arquivos do disco
        if job.workdir.exists():
            shutil.rmtree(job.workdir, ignore_errors=True)
        # Remover da memória
        self.jobs.pop(job_id, None)
        return True

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def list_jobs(self) -> list:
        return [j.to_dict() for j in sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)]

    def subscribe(self, job_id: str, ws):
        if job_id not in self._subscribers:
            self._subscribers[job_id] = []
        self._subscribers[job_id].append(ws)

    def unsubscribe(self, job_id: str, ws):
        if job_id in self._subscribers:
            self._subscribers[job_id] = [w for w in self._subscribers[job_id] if w != ws]

    async def _notify(self, job_id: str, data: dict):
        subscribers = self._subscribers.get(job_id, [])
        dead = []
        for ws in subscribers:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unsubscribe(job_id, ws)
