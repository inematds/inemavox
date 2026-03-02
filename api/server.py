"""inemaVOX API - FastAPI server com WebSocket para progresso em tempo real."""

import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.job_manager import JobManager
from api.model_manager import get_ollama_models, get_ollama_status, unload_ollama_model, start_ollama, stop_ollama, pull_ollama_model, get_all_options
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


APP_VERSION = "1.9.2"

app = FastAPI(
    title="inemaVOX API",
    version=APP_VERSION,
    description="inemaVOX - Suite de voz com IA local: dublagem, transcricao, corte e download de videos",
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
    status["version"] = APP_VERSION
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


@app.post("/api/ollama/start")
async def api_start_ollama():
    """Inicia o servico Ollama."""
    return await start_ollama()


@app.post("/api/ollama/stop")
async def api_stop_ollama():
    """Para o servico Ollama."""
    return await stop_ollama()


@app.get("/api/ollama/status")
async def api_ollama_status():
    """Status do Ollama (online, modelos)."""
    status = await get_ollama_status()
    if status["online"]:
        status["models"] = await get_ollama_models()
    return status


@app.post("/api/ollama/pull")
async def api_pull_model(body: dict):
    """Baixa um modelo no Ollama."""
    model = body.get("model", "")
    if not model:
        raise HTTPException(400, "Campo 'model' obrigatorio")
    result = await pull_ollama_model(model)
    return result


# --- Jobs: Specific routes BEFORE {job_id} to avoid conflicts ---

@app.post("/api/jobs/cut")
async def create_cut_job(config: dict):
    """Criar job de corte de clips."""
    if "input" not in config:
        raise HTTPException(400, "Campo obrigatorio: input")
    config["job_type"] = "cutting"
    if "mode" not in config:
        config["mode"] = "manual"
    if config["mode"] == "manual" and not config.get("timestamps"):
        raise HTTPException(400, "Modo manual requer campo 'timestamps'")
    job = await job_manager.create_job(config)
    return job.to_dict()


@app.post("/api/jobs/cut/upload")
async def create_cut_job_with_upload(
    file: UploadFile = File(...),
    config_json: str = Form(...),
):
    """Criar job de corte com upload de video."""
    config = json.loads(config_json)
    suffix = Path(file.filename).suffix or ".mp4"
    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(file.filename).stem}{suffix}"
    upload_path = UPLOAD_DIR / safe_name
    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)
    config["input"] = str(upload_path.absolute())
    config["job_type"] = "cutting"
    if "mode" not in config:
        config["mode"] = "manual"
    job = await job_manager.create_job(config)
    return job.to_dict()


@app.post("/api/jobs/tts")
async def create_tts_job(config: dict):
    """Criar job de geracao de audio a partir de texto."""
    if "text" not in config:
        raise HTTPException(400, "Campo obrigatorio: text")
    config["job_type"] = "tts_generate"
    if "engine" not in config:
        config["engine"] = "edge"
    if "lang" not in config:
        config["lang"] = "pt"
    job = await job_manager.create_job(config)
    return job.to_dict()


@app.post("/api/jobs/tts/upload")
async def create_tts_job_with_ref(
    file: UploadFile = File(...),
    config_json: str = Form(...),
):
    """Criar job TTS Chatterbox com audio de referencia para voice clone."""
    config = json.loads(config_json)
    if "text" not in config:
        raise HTTPException(400, "Campo obrigatorio: text")
    suffix = Path(file.filename).suffix or ".wav"
    safe_name = f"{uuid.uuid4().hex[:8]}_ref{suffix}"
    upload_path = UPLOAD_DIR / safe_name
    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)
    config["ref_audio"] = str(upload_path.absolute())
    config["engine"] = "chatterbox"
    config["job_type"] = "tts_generate"
    if "lang" not in config:
        config["lang"] = "pt"
    job = await job_manager.create_job(config)
    return job.to_dict()


@app.post("/api/jobs/voice-clone")
async def create_voice_clone_job(
    file: UploadFile = File(...),
    config_json: str = Form(...),
):
    """Criar job de voice clone com upload de audio de referencia."""
    config = json.loads(config_json)
    if "text" not in config:
        raise HTTPException(400, "Campo obrigatorio: text")
    suffix = Path(file.filename).suffix or ".wav"
    safe_name = f"{uuid.uuid4().hex[:8]}_ref{suffix}"
    upload_path = UPLOAD_DIR / safe_name
    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)
    config["ref_audio"] = str(upload_path.absolute())
    config["engine"] = "chatterbox"
    config["job_type"] = "voice_clone"
    if "lang" not in config:
        config["lang"] = "pt"
    job = await job_manager.create_job(config)
    return job.to_dict()


@app.post("/api/jobs/voice-clone/url")
async def create_voice_clone_job_url(config: dict):
    """Criar job de voice clone baixando audio de referencia a partir de uma URL."""
    import asyncio

    ref_url = config.pop("ref_url", None)
    if not ref_url:
        raise HTTPException(400, "Campo obrigatorio: ref_url")
    if "text" not in config:
        raise HTTPException(400, "Campo obrigatorio: text")

    ref_id = uuid.uuid4().hex[:8]
    out_path = UPLOAD_DIR / f"{ref_id}_ref.mp3"

    try:
        import yt_dlp  # type: ignore
    except ImportError:
        raise HTTPException(500, "yt-dlp nao instalado")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(UPLOAD_DIR / f"{ref_id}_ref.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "quiet": True,
        "no_warnings": True,
    }

    def do_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([ref_url])

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, do_download)
    except Exception as e:
        raise HTTPException(500, f"Erro ao baixar referencia: {e}")

    downloaded = list(UPLOAD_DIR.glob(f"{ref_id}_ref.*"))
    if not downloaded:
        raise HTTPException(500, "Falha ao baixar referencia — arquivo nao encontrado apos download")

    config["ref_audio"] = str(downloaded[0].absolute())
    config["engine"] = "chatterbox"
    config["job_type"] = "voice_clone"
    if "lang" not in config:
        config["lang"] = "pt"
    job = await job_manager.create_job(config)
    return job.to_dict()


@app.get("/api/jobs/{job_id}/audio")
async def download_audio(job_id: str):
    """Baixar audio gerado (TTS ou Voice Clone)."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")
    if job.status != "completed":
        raise HTTPException(400, "Job nao concluido")
    audio_dir = job.workdir / "audio_out"
    for ext in ("wav", "mp3", "ogg"):
        p = audio_dir / f"generated.{ext}"
        if p.exists():
            media = "audio/wav" if ext == "wav" else f"audio/{ext}"
            return FileResponse(p, media_type=media, filename=f"audio_{job_id}.{ext}")
    raise HTTPException(404, "Audio nao encontrado")


@app.post("/api/jobs/download")
async def create_download_job(config: dict):
    """Criar job de download de video (YouTube, TikTok, Instagram, etc.)."""
    if "url" not in config:
        raise HTTPException(400, "Campo obrigatorio: url")
    config["job_type"] = "download"
    if "quality" not in config:
        config["quality"] = "best"
    job = await job_manager.create_job(config)
    return job.to_dict()


@app.post("/api/jobs/download/upload")
async def create_download_job_with_upload(
    file: UploadFile = File(...),
    config_json: str = Form(...),
):
    """Criar job de conversao/extracao de audio a partir de arquivo local."""
    config = json.loads(config_json)
    suffix = Path(file.filename).suffix or ".mp4"
    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(file.filename).stem}{suffix}"
    upload_path = UPLOAD_DIR / safe_name
    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)
    config["local_file"] = str(upload_path.absolute())
    config["job_type"] = "download"
    if "quality" not in config:
        config["quality"] = "best"
    job = await job_manager.create_job(config)
    return job.to_dict()


@app.post("/api/jobs/transcribe")
async def create_transcription_job(config: dict):
    """Criar job de transcricao."""
    if "input" not in config:
        raise HTTPException(400, "Campo obrigatorio: input")
    config["job_type"] = "transcription"
    job = await job_manager.create_job(config)
    return job.to_dict()


@app.post("/api/jobs/transcribe/upload")
async def create_transcription_job_with_upload(
    file: UploadFile = File(...),
    config_json: str = Form(...),
):
    """Criar job de transcricao com upload de video."""
    config = json.loads(config_json)
    suffix = Path(file.filename).suffix or ".mp4"
    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(file.filename).stem}{suffix}"
    upload_path = UPLOAD_DIR / safe_name
    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)
    config["input"] = str(upload_path.absolute())
    config["job_type"] = "transcription"
    job = await job_manager.create_job(config)
    return job.to_dict()


# --- Jobs: General endpoints ---

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
    """Criar job de dublagem com upload de video."""
    config = json.loads(config_json)

    # Salvar arquivo com nome unico para evitar conflitos
    suffix = Path(file.filename).suffix or ".mp4"
    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(file.filename).stem}{suffix}"
    upload_path = UPLOAD_DIR / safe_name
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


@app.get("/api/jobs/{job_id}/download-file")
async def download_file(job_id: str):
    """Baixar arquivo de video de um job de download."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")
    if job.config.get("job_type") != "download":
        raise HTTPException(400, "Job nao e do tipo download")
    if job.status != "completed":
        raise HTTPException(400, "Job nao concluido")

    dl_dir = job.workdir / "download"
    if dl_dir.exists():
        files = list(dl_dir.glob("video.*"))
        if files:
            f = files[0]
            ext = f.suffix.lstrip(".")
            media_type = "audio/mpeg" if ext == "mp3" else "video/mp4"
            return FileResponse(f, media_type=media_type, filename=f.name)

    raise HTTPException(404, "Arquivo baixado nao encontrado")


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


def _parse_ts_str(s: str) -> float:
    """Converte 'HH:MM:SS', 'MM:SS' ou 'SS' para segundos."""
    parts = s.strip().split(":")
    if len(parts) == 1:
        return float(parts[0])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def _build_clips_metadata(config: dict, clips_dir: Path) -> dict:
    """Gera clips_metadata.json a partir da config do job (retroativo)."""
    import re
    metadata = {}
    mode = config.get("mode", "manual")

    if mode == "manual" and config.get("timestamps"):
        timestamps = []
        for part in re.split(r"[,;\r\n]+", str(config["timestamps"])):
            part = part.strip()
            m = re.match(r"^([\d:]+)\s*-\s*([\d:]+)$", part)
            if m:
                try:
                    start = _parse_ts_str(m.group(1))
                    end = _parse_ts_str(m.group(2))
                    if end > start:
                        timestamps.append((start, end))
                except Exception:
                    pass
        for i, (start, end) in enumerate(timestamps, 1):
            metadata[f"clip_{i:02d}.mp4"] = {"title": f"Clip {i}", "start": start, "end": end}
    else:
        # Viral ou sem timestamps: titulo pelo indice
        for i, clip in enumerate(sorted(clips_dir.glob("clip_*.mp4")), 1):
            metadata[clip.name] = {"title": f"Clip {i}"}

    return metadata


@app.get("/api/jobs/{job_id}/clips")
async def list_clips(job_id: str):
    """Lista os clips disponíveis para um job de corte."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")
    if job.config.get("job_type") != "cutting":
        raise HTTPException(400, "Job nao e do tipo corte")

    clips_dir = job.workdir / "clips"
    if not clips_dir.exists():
        return []

    # Carrega metadados; gera e salva on-the-fly se nao existir (retroativo)
    meta_path = clips_dir / "clips_metadata.json"
    metadata = {}
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    else:
        metadata = _build_clips_metadata(job.config, clips_dir)
        try:
            meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    clips = []
    for clip in sorted(clips_dir.glob("clip_*.mp4")):
        clip_meta = metadata.get(clip.name, {})
        clips.append({
            "name": clip.name,
            "size_bytes": clip.stat().st_size,
            "url": f"/api/jobs/{job_id}/clips/{clip.name}",
            "title": clip_meta.get("title", clip.name),
            "description": clip_meta.get("description"),
            "start": clip_meta.get("start"),
            "end": clip_meta.get("end"),
        })
    return clips


@app.get("/api/jobs/{job_id}/clips/zip")
async def download_clips_zip(job_id: str):
    """Download do ZIP com todos os clips."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")

    zip_path = job.workdir / "clips" / "clips.zip"
    if not zip_path.exists():
        raise HTTPException(404, "ZIP nao encontrado")

    return FileResponse(zip_path, media_type="application/zip", filename=f"clips_{job_id}.zip")


@app.get("/api/jobs/{job_id}/clips/{clip_name}")
async def download_clip(job_id: str, clip_name: str):
    """Download de um clip individual."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")

    # Validar nome do clip para evitar path traversal
    if ".." in clip_name or "/" in clip_name:
        raise HTTPException(400, "Nome de clip invalido")

    clip_path = job.workdir / "clips" / clip_name
    if not clip_path.exists():
        raise HTTPException(404, "Clip nao encontrado")

    return FileResponse(clip_path, media_type="video/mp4", filename=clip_name)


def _build_transcript_summary(job) -> dict:
    """Gera transcript_summary.json a partir dos arquivos existentes (retroativo)."""
    transcript_dir = job.workdir / "transcription"
    config = job.config
    input_val = config.get("input", "")

    # Titulo: info.json do yt-dlp ou nome do arquivo
    title = ""
    info_path = job.workdir / "dub_work" / "source.info.json"
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            title = str(info.get("title", "") or "")
        except Exception:
            pass
    if not title and not input_val.startswith("http"):
        title = Path(input_val).stem

    # Descricao: ler transcript.json ou transcript.txt
    segments = []
    json_path = transcript_dir / "transcript.json"
    if json_path.exists():
        try:
            segments = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if segments:
        full_text = " ".join(seg.get("text", "") for seg in segments)
        duration_s = round(float(segments[-1].get("end", 0)), 1) if segments else 0
    else:
        # Fallback: ler txt
        txt_path = transcript_dir / "transcript.txt"
        full_text = ""
        if txt_path.exists():
            try:
                full_text = txt_path.read_text(encoding="utf-8")
            except Exception:
                pass
        duration_s = 0

    description = full_text[:500].strip()
    if len(full_text) > 500:
        last_space = description.rfind(" ")
        if last_space > 0:
            description = description[:last_space] + "..."

    return {
        "title": title,
        "description": description,
        "total_segments": len(segments),
        "duration_s": duration_s,
    }


@app.get("/api/jobs/{job_id}/transcript-summary")
async def get_transcript_summary(job_id: str):
    """Retorna titulo e descricao (preview) da transcricao. Gera on-the-fly para jobs antigos."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")

    summary_path = job.workdir / "transcription" / "transcript_summary.json"
    if summary_path.exists():
        try:
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Gerar retroativamente a partir dos arquivos existentes
    transcript_dir = job.workdir / "transcription"
    if not transcript_dir.exists():
        return {"title": "", "description": "", "total_segments": 0, "duration_s": 0}

    result = _build_transcript_summary(job)

    # Salvar para proximas chamadas
    try:
        summary_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    return result


@app.get("/api/jobs/{job_id}/video-summary")
async def get_video_summary(job_id: str):
    """Retorna titulo e descricao do video para jobs de dublagem."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")

    config = job.config
    input_val = config.get("input", "")

    # Derivar titulo do input
    title = ""
    info_path = job.workdir / "dub_work" / "source.info.json"
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            title = str(info.get("title", "") or "")
        except Exception:
            pass
    if not title:
        if not input_val.startswith("http"):
            title = Path(input_val).stem
        else:
            title = input_val

    # Derivar descricao das legendas traduzidas (primeiros segmentos)
    description = ""
    for srt_name in ["asr_trad.srt", "asr.srt"]:
        srt_path = job.workdir / "dub_work" / srt_name
        if srt_path.exists():
            try:
                srt_text = srt_path.read_text(encoding="utf-8")
                lines = []
                for line in srt_text.splitlines():
                    line = line.strip()
                    if not line or line.isdigit() or "-->" in line:
                        continue
                    lines.append(line)
                    if sum(len(l) for l in lines) > 450:
                        break
                full = " ".join(lines)
                description = full[:450].strip()
                if len(full) > 450:
                    last_space = description.rfind(" ")
                    if last_space > 0:
                        description = description[:last_space] + "..."
            except Exception:
                pass
            break

    return {"title": title, "description": description}


@app.get("/api/jobs/{job_id}/transcript")
async def download_transcript(job_id: str, format: str = "srt"):
    """Download da transcricao em diferentes formatos (srt, txt, json)."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")
    if job.config.get("job_type") != "transcription":
        raise HTTPException(400, "Job nao e do tipo transcricao")

    valid_formats = {"srt": "text/plain", "txt": "text/plain", "json": "application/json"}
    if format not in valid_formats:
        raise HTTPException(400, f"Formato invalido. Use: {', '.join(valid_formats.keys())}")

    transcript_path = job.workdir / "transcription" / f"transcript.{format}"
    if not transcript_path.exists():
        raise HTTPException(404, f"Transcricao em formato {format} nao encontrada")

    return FileResponse(
        transcript_path,
        media_type=valid_formats[format],
        filename=f"transcript_{job_id}.{format}",
    )


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    """Cria um novo job com a mesma config de um job falho/cancelado."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")
    if job.status not in ("failed", "cancelled"):
        raise HTTPException(400, f"Somente jobs failed/cancelled podem ser re-tentados (status atual: {job.status})")
    new_job = await job_manager.create_job(dict(job.config))
    return {"id": new_job.id, "status": new_job.status}


@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str, delete: bool = False):
    """Cancelar job (running/queued). Com ?delete=true, remove arquivos e entrada."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nao encontrado")

    if delete:
        ok = await job_manager.delete_job(job_id)
        return {"status": "deleted" if ok else "not_found"}

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
    return {"status": "ok", "version": APP_VERSION}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
