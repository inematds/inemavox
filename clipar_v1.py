#!/usr/bin/env python3
"""Clipar v1 - Corte de clips de video por timestamps manuais ou analise viral via LLM."""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Prompts padrão para análise viral
DEFAULT_SYSTEM_PROMPT = (
    "You are an expert video editor and social media strategist specializing in "
    "viral short-form content. Your goal is to identify the most engaging, "
    "shareable moments from video transcripts."
)

DEFAULT_USER_PROMPT = (
    "Analyze this video transcript and identify the {num_clips} most engaging/viral segments.\n\n"
    "Requirements:\n"
    "- Each clip must be between {min_dur} and {max_dur} seconds long\n"
    "- Choose complete thoughts/stories, never cut mid-sentence\n"
    "- Prioritize: hooks, surprising facts, emotional moments, actionable tips, controversial opinions\n"
    "- Clips must not overlap\n\n"
    "Transcript:\n{transcript}\n\n"
    "Respond ONLY with a valid JSON array (no extra text, no markdown):\n"
    '[\n  {{"start": 10.5, "end": 75.2, "reason": "Strong hook about..."}},\n'
    '  {{"start": 120.0, "end": 195.0, "reason": "Viral moment: ..."}}\n]'
)

# Base URLs para providers OpenAI-compativeis
PROVIDER_BASE_URLS = {
    "openai":     "https://api.openai.com",
    "groq":       "https://api.groq.com/openai",
    "deepseek":   "https://api.deepseek.com",
    "together":   "https://api.together.xyz",
    "openrouter": "https://openrouter.ai/api",
}


def write_checkpoint(workdir: Path, step_num: int, step_id: str, step_name: str):
    """Escreve checkpoint no mesmo formato do dublar_pro_v5.py."""
    cp = {
        "last_step_num": step_num,
        "last_step": step_id,
        "last_step_name": step_name,
        "timestamp": time.time(),
    }
    cp_path = workdir / "dub_work" / "checkpoint.json"
    cp_path.parent.mkdir(parents=True, exist_ok=True)
    cp_path.write_text(json.dumps(cp, indent=2))
    print(f"[checkpoint] etapa {step_num}: {step_name}", flush=True)


def download_input(input_val: str, workdir: Path) -> Path:
    """Baixa video se for URL, ou retorna o path local."""
    if input_val.startswith("http"):
        print(f"[download] Baixando: {input_val}", flush=True)
        out_template = workdir / "dub_work" / "source.%(ext)s"
        cmd = [
            "yt-dlp",
            # acodec!=none garante que o formato tenha audio (evita video-only)
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[acodec!=none][ext=mp4]/best[acodec!=none]/best",
            "--merge-output-format", "mp4",
            "--output", str(out_template),
            "--no-playlist",
            input_val,
        ]
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp falhou com codigo {result.returncode}")
        files = list((workdir / "dub_work").glob("source.*"))
        files = [f for f in files if f.suffix not in (".json", ".txt", ".part")]
        if not files:
            raise RuntimeError("yt-dlp nao gerou arquivo de saida")
        return sorted(files)[-1]
    else:
        p = Path(input_val)
        if not p.exists():
            raise FileNotFoundError(f"Arquivo nao encontrado: {input_val}")
        return p


def parse_time_str(s: str) -> float:
    """Converte 'HH:MM:SS', 'HH:MM:SS,mmm', 'MM:SS' ou 'SS' para segundos float."""
    # Substituir vírgula de milissegundos (formato SRT) por ponto
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    if len(parts) == 1:
        return float(parts[0])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    else:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def parse_timestamps(timestamps_str: str) -> list[tuple[float, float]]:
    """Parseia timestamps em lista de (start, end).

    Formatos aceitos:
      - Padrão:  00:30-02:15, 05:00-07:30
      - SRT:     00:00:00,080 --> 00:00:24,079
    Separadores entre pares: vírgula, ponto-e-vírgula ou nova linha.
    """
    clips = []
    # Dividir em pares de timestamps: usa newline como separador primário para SRT
    for part in re.split(r"[;\r\n]+", timestamps_str):
        part = part.strip()
        if not part:
            continue

        # Formato SRT: "HH:MM:SS,mmm --> HH:MM:SS,mmm"
        srt_match = re.match(
            r"^([\d]{1,2}:[\d]{2}:[\d]{2}[,.][\d]+)\s*-->\s*([\d]{1,2}:[\d]{2}:[\d]{2}[,.][\d]+)$",
            part,
        )
        if srt_match:
            start_s = parse_time_str(srt_match.group(1))
            end_s = parse_time_str(srt_match.group(2))
            if end_s > start_s:
                clips.append((start_s, end_s))
            else:
                print(f"[warn] Clip invalido (start >= end): {part}", flush=True)
            continue

        # Formato padrão: "HH:MM:SS-HH:MM:SS" ou "MM:SS-MM:SS"
        # Suporta múltiplos pares separados por vírgula na mesma linha
        for subpart in re.split(r",", part):
            subpart = subpart.strip()
            if not subpart:
                continue
            match = re.match(r"^([\d:]+)\s*-\s*([\d:]+)$", subpart)
            if not match:
                print(f"[warn] Timestamp invalido ignorado: {subpart}", flush=True)
                continue
            start_s = parse_time_str(match.group(1))
            end_s = parse_time_str(match.group(2))
            if end_s <= start_s:
                print(f"[warn] Clip invalido (start >= end): {subpart}", flush=True)
                continue
            clips.append((start_s, end_s))

    return clips


def cut_clips(source: Path, timestamps: list[tuple[float, float]], clips_dir: Path) -> list[Path]:
    """Corta clips usando ffmpeg sem re-encodar."""
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_files = []
    for i, (start, end) in enumerate(timestamps, 1):
        duration = end - start
        out_path = clips_dir / f"clip_{i:02d}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", str(source),
            "-t", str(duration),
            "-c", "copy",
            str(out_path),
        ]
        print(f"[cutting] Clip {i:02d}: {start:.1f}s - {end:.1f}s ({duration:.1f}s)", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[warn] ffmpeg erro no clip {i}: {result.stderr[-300:]}", flush=True)
        else:
            clip_files.append(out_path)
            print(f"[cutting] Clip {i:02d} salvo: {out_path.name}", flush=True)
    return clip_files


def save_clips_metadata(clips_dir: Path, timestamps: list[tuple[float, float]], descriptions: list[str] | None = None):
    """Salva metadados dos clips (titulo, timestamps, descricao) em clips_metadata.json."""
    metadata = {}
    for i, (start, end) in enumerate(timestamps, 1):
        clip_name = f"clip_{i:02d}.mp4"
        entry: dict = {
            "title": f"Clip {i}",
            "start": start,
            "end": end,
        }
        if descriptions and i <= len(descriptions) and descriptions[i - 1]:
            entry["description"] = descriptions[i - 1]
        metadata[clip_name] = entry
    meta_path = clips_dir / "clips_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[metadata] Metadados de {len(metadata)} clips salvos", flush=True)


def create_zip(clips_dir: Path) -> Path | None:
    """Cria ZIP com todos os clips."""
    import zipfile
    zip_path = clips_dir / "clips.zip"
    clips = sorted(clips_dir.glob("clip_*.mp4"))
    if not clips:
        print("[warn] Nenhum clip para zipar", flush=True)
        return None
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for clip in clips:
            zf.write(clip, clip.name)
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"[zip] ZIP criado: {zip_path.name} ({size_mb:.1f}MB, {len(clips)} clips)", flush=True)
    return zip_path


def extract_audio(source: Path, workdir: Path) -> Path:
    """Extrai audio como WAV mono 16kHz para analise."""
    print("[extraction] Extraindo audio...", flush=True)
    audio_path = workdir / "dub_work" / "audio.wav"
    cmd = [
        "ffmpeg", "-y", "-i", str(source),
        "-ac", "1", "-ar", "16000", "-vn",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou: {result.stderr[-500:]}")
    return audio_path


def _has_cuda() -> bool:
    """Verifica se CUDA esta disponivel no PyTorch E no CTranslate2 (mesmo check do dublar_pro_v5.py)."""
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        import ctranslate2
        ctranslate2.get_supported_compute_types("cuda")  # lanca ValueError se sem CUDA
        return True
    except Exception:
        return False


def transcribe_for_viral(audio_path: Path, model: str = "large-v3") -> list[dict]:
    """Transcreve com faster-whisper para analise viral."""
    print(f"[transcription] Transcrevendo para analise viral (modelo: {model})...", flush=True)
    from faster_whisper import WhisperModel

    device = "cuda" if _has_cuda() else "cpu"
    compute = "float16" if device == "cuda" else "int8"

    wm = WhisperModel(model, device=device, compute_type=compute)
    segments_iter, info = wm.transcribe(str(audio_path), vad_filter=True)

    results = []
    for seg in segments_iter:
        results.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
        })

    print(f"[transcription] {len(results)} segmentos, idioma: {info.language}", flush=True)
    return results


def _build_prompts(
    segments: list[dict],
    num_clips: int,
    min_dur: int,
    max_dur: int,
    custom_system: str | None = None,
    custom_user: str | None = None,
) -> tuple[str, str]:
    """Retorna (system_prompt, user_prompt) com suporte a customização."""
    transcript_text = "\n".join(
        f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}"
        for seg in segments
    )
    system = (custom_system or DEFAULT_SYSTEM_PROMPT).strip()
    user_template = (custom_user or DEFAULT_USER_PROMPT).strip()
    user = user_template.format(
        num_clips=num_clips,
        min_dur=min_dur,
        max_dur=max_dur,
        transcript=transcript_text,
    )
    return system, user


def _parse_llm_response(content: str, provider: str) -> list[dict]:
    """Parseia a resposta do LLM extraindo o array JSON."""
    # JSON direto
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    # Bloco markdown ```json ... ```
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", content)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # Array solto na resposta
    m = re.search(r"\[[\s\S]*\]", content)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    raise RuntimeError(f"Nao foi possivel parsear resposta do LLM ({provider}): {content[:300]}")


def _call_ollama(system: str, user: str, model: str, ollama_url: str) -> str:
    """Chama Ollama com streaming. timeout=None = sem limite (modelo pode demorar horas)."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "options": {"temperature": 0.3},
    }
    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    parts = []
    with urllib.request.urlopen(req, timeout=None) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            chunk = json.loads(line)
            parts.append(chunk.get("message", {}).get("content", ""))
            if chunk.get("done"):
                break
    return "".join(parts)


def _call_openai_compat(system: str, user: str, model: str, api_key: str, base_url: str) -> str:
    """Chama API compativel com OpenAI (OpenAI, Groq, DeepSeek, Together, Custom) com streaming SSE."""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    parts = []
    with urllib.request.urlopen(req, timeout=None) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[len("data:"):].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0].get("delta", {}).get("content", "")
                if delta:
                    parts.append(delta)
            except Exception:
                continue
    return "".join(parts)


def _call_anthropic(system: str, user: str, model: str, api_key: str) -> str:
    """Chama Anthropic API com streaming SSE."""
    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "stream": True,
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    parts = []
    with urllib.request.urlopen(req, timeout=None) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line or not line.startswith("data:"):
                continue
            try:
                chunk = json.loads(line[len("data:"):].strip())
                if chunk.get("type") == "content_block_delta":
                    parts.append(chunk.get("delta", {}).get("text", ""))
            except Exception:
                continue
    return "".join(parts)


def get_video_duration(video_path: Path) -> float:
    """Retorna duração do vídeo em segundos via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video_path)],
        capture_output=True, text=True,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def split_equal_parts(source: Path, num_parts: int, clips_dir: Path) -> list[tuple[float, float]]:
    """Divide o vídeo em num_parts partes iguais usando ffmpeg."""
    duration = get_video_duration(source)
    part_dur = duration / num_parts
    timestamps = []
    for i in range(num_parts):
        start = i * part_dur
        end = min((i + 1) * part_dur, duration)
        timestamps.append((round(start, 3), round(end, 3)))
        print(f"[split] Parte {i+1}/{num_parts}: {start:.1f}s - {end:.1f}s ({part_dur:.1f}s)", flush=True)
    return timestamps


def analyze_viral(
    segments: list[dict],
    num_clips: int,
    min_dur: int,
    max_dur: int,
    provider: str = "ollama",
    ollama_model: str = "qwen2.5:7b",
    ollama_url: str = "http://localhost:11434",
    llm_model: str = "",
    llm_api_key: str = "",
    llm_base_url: str = "",
    system_prompt: str | None = None,
    user_prompt: str | None = None,
) -> list[dict]:
    """Identifica os segmentos mais virais usando o provider LLM configurado."""
    model_label = llm_model if provider != "ollama" else ollama_model
    print(f"[analysis] Analisando com {provider}/{model_label} ({num_clips} clips, {min_dur}-{max_dur}s)...", flush=True)

    system, user = _build_prompts(segments, num_clips, min_dur, max_dur, system_prompt, user_prompt)

    try:
        if provider == "ollama":
            content = _call_ollama(system, user, ollama_model, ollama_url)
        elif provider == "anthropic":
            content = _call_anthropic(system, user, llm_model, llm_api_key)
        else:  # openai, groq, deepseek, together, custom
            base = llm_base_url or PROVIDER_BASE_URLS.get(provider, "")
            if not base:
                raise ValueError(f"Base URL nao definida para provider '{provider}'")
            content = _call_openai_compat(system, user, llm_model, llm_api_key, base)
    except Exception as e:
        raise RuntimeError(f"Erro ao chamar {provider}: {e}")

    print(f"[analysis] Resposta do LLM recebida ({len(content)} chars)", flush=True)
    return _parse_llm_response(content, provider)


def main():
    parser = argparse.ArgumentParser(description="Clipar v1 - Corte de clips de video")
    parser.add_argument("--in", dest="input", required=True, help="URL ou caminho do arquivo")
    parser.add_argument("--outdir", required=True, help="Diretorio de saida para clips")
    parser.add_argument("--mode", default="manual", choices=["manual", "viral"])
    parser.add_argument("--timestamps", default="", help="Ex: 00:30-02:15,05:00-07:30")
    parser.add_argument("--ollama-model", default="qwen2.5:7b", dest="ollama_model")
    parser.add_argument("--num-clips", type=int, default=5, dest="num_clips")
    parser.add_argument("--min-duration", type=int, default=30, dest="min_duration")
    parser.add_argument("--max-duration", type=int, default=120, dest="max_duration")
    parser.add_argument("--whisper-model", default="large-v3", dest="whisper_model")
    parser.add_argument("--ollama-url", default="http://localhost:11434", dest="ollama_url")
    # Providers externos
    parser.add_argument("--llm-provider", default="ollama",
                        choices=["ollama", "openai", "anthropic", "groq", "deepseek", "together", "openrouter", "custom"],
                        dest="llm_provider")
    parser.add_argument("--llm-model", default="", dest="llm_model",
                        help="Modelo para providers externos (ex: gpt-4o, claude-opus-4-5)")
    parser.add_argument("--llm-api-key", default="", dest="llm_api_key",
                        help="API key para providers externos")
    parser.add_argument("--llm-base-url", default="", dest="llm_base_url",
                        help="Base URL para provider custom (compativel com OpenAI)")
    parser.add_argument("--split-equal", action="store_true", dest="split_equal",
                        help="Dividir em partes iguais sem usar IA (ignora LLM e transcricao)")
    parser.add_argument("--system-prompt", default="", dest="system_prompt",
                        help="System prompt customizado para o LLM")
    parser.add_argument("--user-prompt", default="", dest="user_prompt",
                        help="User prompt customizado para o LLM (use {transcript}, {num_clips}, {min_dur}, {max_dur})")
    args = parser.parse_args()

    clips_dir = Path(args.outdir)
    workdir = clips_dir.parent  # dub_work fica no pai de clips/

    (workdir / "dub_work").mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Checkpoint escrito APOS cada etapa (semantica: "etapa N concluida")
        # Assim o progresso mostra a etapa N como done e N+1 como running

        if args.mode == "manual":
            # Etapa 1: Download
            source = download_input(args.input, workdir)
            write_checkpoint(workdir, 1, "download", "Download")

            # Etapa 2: Cutting
            timestamps = parse_timestamps(args.timestamps)
            if not timestamps:
                raise ValueError(
                    f"Nenhum timestamp valido em: {repr(args.timestamps)!r}. "
                    "Use o formato: 00:30-02:15,05:00-07:30 (virgula, ponto-e-virgula ou nova linha como separador)"
                )
            cut_clips(source, timestamps, clips_dir)
            write_checkpoint(workdir, 2, "cutting", "Cortando clips")
            save_clips_metadata(clips_dir, timestamps)

            # Etapa 3: ZIP
            create_zip(clips_dir)
            write_checkpoint(workdir, 3, "zip", "Criando ZIP")

        else:  # viral
            # Etapa 1: Download
            source = download_input(args.input, workdir)
            write_checkpoint(workdir, 1, "download", "Download")

            if args.split_equal:
                # Modo: dividir em partes iguais (sem IA)
                print(f"[split] Dividindo em {args.num_clips} partes iguais...", flush=True)
                timestamps = split_equal_parts(source, args.num_clips, clips_dir)
                descriptions = [f"Parte {i+1}" for i in range(len(timestamps))]

                # Etapa 2: Cutting
                cut_clips(source, timestamps, clips_dir)
                write_checkpoint(workdir, 2, "cutting", "Cortando clips")
                save_clips_metadata(clips_dir, timestamps, descriptions)

                # Etapa 3: ZIP
                create_zip(clips_dir)
                write_checkpoint(workdir, 3, "zip", "Criando ZIP")

            else:
                # Modo: análise viral com LLM
                # Etapa 2: Extraction
                audio = extract_audio(source, workdir)
                write_checkpoint(workdir, 2, "extraction", "Extracao de audio")

                # Etapa 3: Transcription
                segments = transcribe_for_viral(audio, args.whisper_model)
                if not segments:
                    raise RuntimeError("Nenhum segmento de fala detectado no audio")
                write_checkpoint(workdir, 3, "transcription", "Transcricao")

                # Etapa 4: Analysis
                viral_clips = analyze_viral(
                    segments,
                    args.num_clips,
                    args.min_duration,
                    args.max_duration,
                    provider=args.llm_provider,
                    ollama_model=args.ollama_model,
                    ollama_url=args.ollama_url,
                    llm_model=args.llm_model,
                    llm_api_key=args.llm_api_key,
                    llm_base_url=args.llm_base_url,
                    system_prompt=args.system_prompt or None,
                    user_prompt=args.user_prompt or None,
                )
                print(f"[analysis] {len(viral_clips)} clips identificados:", flush=True)
                timestamps = []
                descriptions = []
                for c in viral_clips:
                    start = float(c.get("start", 0))
                    end = float(c.get("end", 0))
                    reason = c.get("reason", "")
                    print(f"  {start:.1f}s - {end:.1f}s: {reason}", flush=True)
                    if end > start:
                        timestamps.append((start, end))
                        descriptions.append(reason)
                if not timestamps:
                    raise RuntimeError("Nenhum clip valido retornado pelo LLM")
                write_checkpoint(workdir, 4, "analysis", "Analise viral")

                # Etapa 5: Cutting
                cut_clips(source, timestamps, clips_dir)
                write_checkpoint(workdir, 5, "cutting", "Cortando clips")
                save_clips_metadata(clips_dir, timestamps, descriptions)

                # Etapa 6: ZIP
                create_zip(clips_dir)
                write_checkpoint(workdir, 6, "zip", "Criando ZIP")

        print("[done] Corte concluido com sucesso!", flush=True)
        sys.exit(0)

    except Exception as e:
        print(f"[error] {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
