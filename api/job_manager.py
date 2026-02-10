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
DOCKER_GPU_IMAGE = os.environ.get("DOCKER_GPU_IMAGE", "dublar-pro:gpu")
PROJECT_DIR = Path(__file__).parent.parent.resolve()


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


# Detectar capacidades ao iniciar
DOCKER_GPU_AVAILABLE = _detect_docker_gpu()
DEVICE = _detect_device()

# Log de inicializacao
_mode = "Docker GPU" if DOCKER_GPU_AVAILABLE else f"Local ({DEVICE})"
print(f"[JobManager] Modo: {_mode} | Device: {DEVICE} | Image: {DOCKER_GPU_IMAGE}")


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

    def to_dict(self) -> dict:
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

    def _calc_progress(self, checkpoint: dict) -> dict:
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
            if job_id in self.jobs:
                continue
            try:
                config = json.loads(config_path.read_text())
                job = Job(job_id, config)
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
                    # output.log e criado quando o job inicia
                    job.started_at = log_stat.st_mtime  # aprox (sera sobrescrito se tiver dado melhor)
                    # Se stage_times existir, calcular duracao real
                    if job.stage_times:
                        total_dur = sum(job.stage_times.values())
                        job.started_at = job.created_at  # aprox
                        job.finished_at = job.created_at + total_dur

                dublado_dir = job_dir / "dublado"
                has_output = dublado_dir.exists() and any(dublado_dir.glob("*.mp4"))
                log_path = job_dir / "output.log"
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
        job.workdir.mkdir(parents=True, exist_ok=True)
        (job.workdir / "dub_work").mkdir(exist_ok=True)
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

        if DOCKER_GPU_AVAILABLE:
            cmd = self._build_docker_command(job)
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
                # (a ultima etapa pode ter sido muito rapida e nao capturada no polling)
                checkpoint = job._read_checkpoint()
                job._calc_progress(checkpoint)

                # Registrar tempo da ultima etapa
                if job._last_stage_num > 0 and job._last_stage_num <= len(STAGES):
                    last_sid = STAGES[job._last_stage_num - 1]["id"]
                    job.stage_times[last_sid] = round(job.finished_at - job._last_stage_start, 1)

                # Persistir stage_times em disco (sobrevive a restarts)
                try:
                    times_path = job.workdir / "stage_times.json"
                    times_path.write_text(json.dumps(job.stage_times, indent=2))
                except Exception:
                    pass

                if exit_code == 0:
                    job.status = "completed"
                    # Salvar estatisticas para aprendizado
                    record_job_complete(job.config, job.stage_times, job.duration, job.device)
                elif exit_code == -signal.SIGTERM or exit_code == -signal.SIGKILL:
                    job.status = "cancelled"
                else:
                    job.status = "failed"
                    # Tentar capturar erro do log
                    error_msg = f"Exit code: {exit_code}"
                    try:
                        lines = log_path.read_text().splitlines()
                        # Pegar ultimas linhas com erro
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
            "--name", f"dublarv5-{job.id}",
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
