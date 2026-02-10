"""Rastreador de estatisticas - aprende tempos por etapa para calcular ETAs."""

import json
import time
from pathlib import Path
from typing import Optional

STATS_FILE = Path(__file__).parent.parent / "jobs" / "pipeline_stats.json"

# Etapas do pipeline com nomes e descricoes
STAGES = [
    {"num": 1, "id": "download", "name": "Download", "icon": "↓"},
    {"num": 2, "id": "extraction", "name": "Extrai Audio", "icon": "♪"},
    {"num": 3, "id": "transcription", "name": "Transcricao", "icon": "✎"},
    {"num": 4, "id": "translation", "name": "Traducao", "icon": "⇄"},
    {"num": 5, "id": "split", "name": "Split", "icon": "✂"},
    {"num": 6, "id": "tts", "name": "TTS", "icon": "🔊"},
    {"num": 7, "id": "sync", "name": "Sincronizacao", "icon": "⟳"},
    {"num": 8, "id": "concat", "name": "Concatenacao", "icon": "⊕"},
    {"num": 9, "id": "postprocess", "name": "Pos-Processo", "icon": "⚙"},
    {"num": 10, "id": "mux", "name": "Mux Final", "icon": "▶"},
]


def _load_stats() -> dict:
    """Carrega historico de estatisticas."""
    if STATS_FILE.exists():
        try:
            return json.loads(STATS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"jobs_completed": 0, "stage_times": {}, "total_times": []}


def _save_stats(stats: dict):
    """Salva estatisticas em disco."""
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(stats, indent=2))


def record_job_complete(job_config: dict, stage_times: dict, total_time: float, device: str):
    """Registra um job completo para aprendizado.

    stage_times: {"download": 5.2, "transcription": 120.3, ...}
    """
    stats = _load_stats()
    stats["jobs_completed"] = stats.get("jobs_completed", 0) + 1

    # Chave unica por combinacao de engine + device
    tts = job_config.get("tts_engine", "edge")
    trans = job_config.get("translation_engine", "m2m100")
    whisper = job_config.get("whisper_model", "large-v3")
    profile_key = f"{tts}_{trans}_{whisper}_{device}"

    if "stage_times" not in stats:
        stats["stage_times"] = {}
    if profile_key not in stats["stage_times"]:
        stats["stage_times"][profile_key] = {}

    profile = stats["stage_times"][profile_key]
    for stage_id, duration in stage_times.items():
        if stage_id not in profile:
            profile[stage_id] = {"samples": [], "avg": 0}
        # Manter ultimos 10 samples
        samples = profile[stage_id]["samples"]
        samples.append(round(duration, 1))
        if len(samples) > 10:
            samples.pop(0)
        profile[stage_id]["avg"] = round(sum(samples) / len(samples), 1)

    # Tempo total
    if "total_times" not in stats:
        stats["total_times"] = []
    stats["total_times"].append({
        "profile": profile_key,
        "total": round(total_time, 1),
        "timestamp": time.time(),
    })
    if len(stats["total_times"]) > 50:
        stats["total_times"] = stats["total_times"][-50:]

    _save_stats(stats)


def estimate_remaining(job_config: dict, current_stage: int, stage_elapsed: float, device: str) -> Optional[dict]:
    """Estima tempo restante baseado em historico.

    Retorna: {"eta_seconds": 300, "confidence": "medium", "stage_estimates": {...}}
    """
    stats = _load_stats()

    tts = job_config.get("tts_engine", "edge")
    trans = job_config.get("translation_engine", "m2m100")
    whisper = job_config.get("whisper_model", "large-v3")
    profile_key = f"{tts}_{trans}_{whisper}_{device}"

    profile = stats.get("stage_times", {}).get(profile_key)

    if not profile:
        # Sem dados historicos - usar estimativas default
        return _default_estimate(job_config, current_stage, device)

    remaining = 0.0
    stage_estimates = {}
    for stage in STAGES:
        sid = stage["id"]
        if stage["num"] <= current_stage:
            stage_estimates[sid] = {"status": "done"}
            continue
        avg = profile.get(sid, {}).get("avg")
        if avg:
            stage_estimates[sid] = {"status": "pending", "est_seconds": avg}
            remaining += avg
        else:
            # Usar default para stages sem dados
            default = _default_stage_time(sid, job_config, device)
            stage_estimates[sid] = {"status": "pending", "est_seconds": default}
            remaining += default

    return {
        "eta_seconds": round(remaining),
        "confidence": "high" if len(profile) >= 5 else "medium",
        "stage_estimates": stage_estimates,
    }


def _default_estimate(job_config: dict, current_stage: int, device: str) -> dict:
    """Estimativa default sem dados historicos."""
    remaining = 0.0
    stage_estimates = {}
    for stage in STAGES:
        sid = stage["id"]
        if stage["num"] <= current_stage:
            stage_estimates[sid] = {"status": "done"}
            continue
        est = _default_stage_time(sid, job_config, device)
        stage_estimates[sid] = {"status": "pending", "est_seconds": est}
        remaining += est

    return {
        "eta_seconds": round(remaining),
        "confidence": "low",
        "stage_estimates": stage_estimates,
    }


def _default_stage_time(stage_id: str, config: dict, device: str) -> float:
    """Tempos default por etapa (em segundos) para video de ~10min."""
    is_gpu = device == "cuda"
    tts = config.get("tts_engine", "edge")

    defaults = {
        "download": 30,
        "extraction": 5,
        "transcription": 120 if not is_gpu else 30,
        "translation": 60 if config.get("translation_engine") != "ollama" else 180,
        "split": 5,
        "tts": _tts_default(tts, is_gpu),
        "sync": 15,
        "concat": 10,
        "postprocess": 10,
        "mux": 10,
    }
    return defaults.get(stage_id, 30)


def _tts_default(engine: str, is_gpu: bool) -> float:
    """Estimativa TTS - a etapa mais variavel."""
    if engine == "edge":
        return 120  # online, depende da rede
    elif engine == "bark":
        return 60 if is_gpu else 600  # GPU vs CPU enorme diferenca
    elif engine == "xtts":
        return 120 if is_gpu else 900
    elif engine == "piper":
        return 30
    return 120


def get_stats_summary() -> dict:
    """Retorna resumo das estatisticas para a API."""
    stats = _load_stats()
    return {
        "jobs_completed": stats.get("jobs_completed", 0),
        "profiles": list(stats.get("stage_times", {}).keys()),
        "stages": STAGES,
    }


def format_eta(seconds: int) -> str:
    """Formata ETA em texto legivel."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        m = seconds // 60
        s = seconds % 60
        return f"{m}min {s}s"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}min"
