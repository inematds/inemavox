"""Gerenciador de Jobs - fila, subprocess, monitoramento."""

import asyncio
import json
import os
import signal
import subprocess
import time
import shutil
import sys
import uuid
from pathlib import Path
from typing import Optional

JOBS_DIR = Path(os.environ.get("JOBS_DIR", "jobs"))
PIPELINE_SCRIPT = os.environ.get("PIPELINE_SCRIPT", "dublar_pro_v4.py")
# Use the same python that's running the API, or find python3
PYTHON_BIN = os.environ.get("PYTHON_BIN", sys.executable or shutil.which("python3") or "python3")
USE_DOCKER = os.environ.get("USE_DOCKER", "0") == "1"


class Job:
    def __init__(self, job_id: str, config: dict):
        self.id = job_id
        self.config = config
        self.status = "queued"  # queued, running, completed, failed, cancelled
        self.created_at = time.time()
        self.started_at = None
        self.finished_at = None
        self.process: Optional[subprocess.Popen] = None
        self.workdir = JOBS_DIR / job_id
        self.error = None

    @property
    def duration(self) -> float:
        if self.started_at is None:
            return 0
        end = self.finished_at or time.time()
        return end - self.started_at

    def to_dict(self) -> dict:
        checkpoint = self._read_checkpoint()
        return {
            "id": self.id,
            "status": self.status,
            "config": self.config,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": round(self.duration, 1),
            "error": self.error,
            "checkpoint": checkpoint,
            "progress": self._calc_progress(checkpoint),
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
        stages = [
            "download", "extraction", "transcription", "translation",
            "split", "tts", "fade", "sync", "concat", "mux"
        ]
        last_step = checkpoint.get("last_step_num", 0)
        total = len(stages)
        return {
            "current_stage": last_step,
            "total_stages": total,
            "percent": round((last_step / total) * 100),
            "stage_name": stages[last_step] if last_step < total else "completed",
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
        self._worker_task = asyncio.create_task(self._worker())

    async def _worker(self):
        """Processa jobs da fila, um por vez."""
        while True:
            job_id = await self.queue.get()
            job = self.jobs.get(job_id)
            if job and job.status == "queued":
                await self._run_job(job)
            self.queue.task_done()

    async def create_job(self, config: dict) -> Job:
        """Cria novo job de dublagem."""
        job_id = str(uuid.uuid4())[:8]
        job = Job(job_id, config)
        job.workdir.mkdir(parents=True, exist_ok=True)
        (job.workdir / "dub_work").mkdir(exist_ok=True)
        (job.workdir / "dublado").mkdir(exist_ok=True)

        self.jobs[job_id] = job

        # Salvar config
        (job.workdir / "config.json").write_text(json.dumps(config, indent=2))

        # Adicionar a fila
        await self.queue.put(job_id)
        await self._notify(job_id, {"event": "created", "job": job.to_dict()})
        return job

    async def _run_job(self, job: Job):
        """Executa o pipeline como subprocess."""
        job.status = "running"
        job.started_at = time.time()
        await self._notify(job.id, {"event": "started", "job": job.to_dict()})

        cmd = self._build_command(job)
        log_path = job.workdir / "output.log"

        try:
            # Herdar PATH do processo atual (venv) para que yt-dlp, ffmpeg etc. sejam encontrados
            env = os.environ.copy()
            # Garantir que o diretorio bin do venv esta no PATH
            python_dir = os.path.dirname(PYTHON_BIN)
            if python_dir not in env.get("PATH", ""):
                env["PATH"] = python_dir + ":" + env.get("PATH", "")

            with open(log_path, "w") as log_file:
                job.process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    cwd=str(job.workdir),
                    env=env,
                )

                # Monitorar o processo
                while job.process.poll() is None:
                    await asyncio.sleep(2)
                    await self._notify(job.id, {
                        "event": "progress",
                        "job": job.to_dict(),
                    })

                exit_code = job.process.returncode
                job.finished_at = time.time()

                if exit_code == 0:
                    job.status = "completed"
                elif exit_code == -signal.SIGTERM or exit_code == -signal.SIGKILL:
                    job.status = "cancelled"
                else:
                    job.status = "failed"
                    job.error = f"Exit code: {exit_code}"

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.finished_at = time.time()

        await self._notify(job.id, {"event": "finished", "job": job.to_dict()})

    def _build_command(self, job: Job) -> list:
        """Constroi comando do pipeline a partir da config."""
        config = job.config
        cmd = [PYTHON_BIN, os.path.abspath(PIPELINE_SCRIPT)]

        # Input
        cmd.extend(["--in", config["input"]])

        # Idiomas
        if config.get("src_lang"):
            cmd.extend(["--src", config["src_lang"]])
        cmd.extend(["--tgt", config.get("tgt_lang", "pt")])

        # Output
        cmd.extend(["--outdir", str(job.workdir.resolve() / "dublado")])

        # ASR
        asr = config.get("asr_engine", "whisper")
        cmd.extend(["--asr", asr])
        if config.get("whisper_model"):
            cmd.extend(["--whisper-model", config["whisper_model"]])

        # Traducao
        tradutor = config.get("translation_engine", "m2m100")
        cmd.extend(["--tradutor", tradutor])
        if tradutor == "ollama" and config.get("ollama_model"):
            cmd.extend(["--modelo", config["ollama_model"]])
        if config.get("large_model"):
            cmd.append("--large-model")

        # TTS
        tts = config.get("tts_engine", "edge")
        cmd.extend(["--tts", tts])
        if config.get("voice"):
            cmd.extend(["--voice", config["voice"]])
        if config.get("tts_rate"):
            cmd.extend(["--rate", config["tts_rate"]])

        # Sincronizacao
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

        # Diarizacao
        if config.get("diarize"):
            cmd.append("--diarize")
            if config.get("num_speakers"):
                cmd.extend(["--num-speakers", str(config["num_speakers"])])

        # Voice cloning
        if config.get("clone_voice"):
            cmd.append("--clonar-voz")

        # Outros
        if config.get("maxdur"):
            cmd.extend(["--maxdur", str(config["maxdur"])])
        if config.get("seed"):
            cmd.extend(["--seed", str(config["seed"])])

        return cmd

    async def cancel_job(self, job_id: str) -> bool:
        """Cancela um job em execucao."""
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

    # WebSocket subscribers
    def subscribe(self, job_id: str, ws):
        if job_id not in self._subscribers:
            self._subscribers[job_id] = []
        self._subscribers[job_id].append(ws)

    def unsubscribe(self, job_id: str, ws):
        if job_id in self._subscribers:
            self._subscribers[job_id] = [w for w in self._subscribers[job_id] if w != ws]

    async def _notify(self, job_id: str, data: dict):
        """Envia update para todos os subscribers do job."""
        subscribers = self._subscribers.get(job_id, [])
        dead = []
        for ws in subscribers:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unsubscribe(job_id, ws)
