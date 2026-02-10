"""Dublar Pro API - FastAPI server com WebSocket para progresso em tempo real."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.job_manager import JobManager
from api.model_manager import get_ollama_models, get_ollama_status, unload_ollama_model, get_all_options
from api.system_monitor import get_system_status
from api.stats_tracker import get_stats_summary

JOBS_DIR = Path(os.environ.get("JOBS_DIR", "jobs"))
UPLOAD_DIR = JOBS_DIR / "uploads"

job_manager = JobManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown."""
    JOBS_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    job_manager.start()
    yield


app = FastAPI(
    title="Dublar v5 API",
    version="5.1.0",
    description="API para pipeline de dublagem automatica de videos",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- System ---

@app.get("/api/system/status")
async def system_status():
    """Status completo do sistema (GPU, CPU, RAM, disco)."""
    status = get_system_status()
    status["ollama"] = await get_ollama_status()
    return status


# --- Models ---

@app.get("/api/models/options")
async def get_options():
    """Todas as opcoes disponiveis (TTS, ASR, traducao, idiomas, etc)."""
    options = get_all_options()
    options["ollama_models"] = await get_ollama_models()
    return options


@app.get("/api/models/ollama")
async def list_ollama_models():
    """Lista modelos Ollama disponiveis."""
    return await get_ollama_models()


@app.post("/api/models/ollama/unload")
async def unload_model(model: str):
    """Descarrega modelo Ollama para liberar VRAM."""
    success = await unload_ollama_model(model)
    return {"success": success, "model": model}


# --- Jobs ---

@app.post("/api/jobs")
async def create_job(config: dict):
    """Criar novo job de dublagem."""
    if "input" not in config or "tgt_lang" not in config:
        raise HTTPException(400, "Campos obrigatorios: input, tgt_lang")
    job = await job_manager.create_job(config)
    return job.to_dict()


@app.post("/api/jobs/upload")
async def create_job_with_upload(
    file: UploadFile = File(...),
    config_json: str = Form(...),
):
    """Criar job com upload de video."""
    import json
    config = json.loads(config_json)

    # Salvar arquivo
    upload_path = UPLOAD_DIR / f"{file.filename}"
    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)

    config["input"] = str(upload_path.absolute())
    job = await job_manager.create_job(config)
    return job.to_dict()


@app.get("/api/jobs")
async def list_jobs():
    """Listar todos os jobs."""
    return job_manager.list_jobs()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Status de um job."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/logs")
async def get_job_logs(job_id: str, last_n: int = 100):
    """Ultimas linhas de log de um job."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")
    return {"logs": job.read_logs(last_n)}


@app.get("/api/jobs/{job_id}/download")
async def download_job(job_id: str):
    """Baixar video dublado."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")
    if job.status != "completed":
        raise HTTPException(400, "Job nao concluido")

    # Procurar video de saida
    dublado_dir = job.workdir / "dublado"
    if dublado_dir.exists():
        videos = list(dublado_dir.glob("*.mp4"))
        if videos:
            return FileResponse(
                videos[0],
                media_type="video/mp4",
                filename=videos[0].name,
            )

    raise HTTPException(404, "Video dublado nao encontrado")


@app.get("/api/jobs/{job_id}/subtitles")
async def download_subtitles(job_id: str, lang: str = "trad"):
    """Baixar legendas (original ou traduzida)."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")

    srt_name = "asr_trad.srt" if lang == "trad" else "asr.srt"
    srt_path = job.workdir / "dub_work" / srt_name
    if srt_path.exists():
        return FileResponse(srt_path, media_type="text/plain", filename=srt_name)
    raise HTTPException(404, "Legendas nao encontradas")


@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancelar ou remover job."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")

    if job.status == "running":
        await job_manager.cancel_job(job_id)
        return {"status": "cancelled"}
    return {"status": job.status}


# --- WebSocket ---

@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_progress(websocket: WebSocket, job_id: str):
    """WebSocket para progresso em tempo real de um job."""
    await websocket.accept()

    job = job_manager.get_job(job_id)
    if not job:
        await websocket.send_json({"error": "Job nao encontrado"})
        await websocket.close()
        return

    # Enviar estado atual
    await websocket.send_json({"event": "connected", "job": job.to_dict()})

    # Inscrever para updates
    job_manager.subscribe(job_id, websocket)

    try:
        while True:
            # Manter conexao aberta, receber pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        job_manager.unsubscribe(job_id, websocket)


# --- Health ---

@app.get("/api/stats")
async def pipeline_stats():
    """Estatisticas do pipeline (tempos medios, ETAs aprendidos)."""
    return get_stats_summary()


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "5.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
