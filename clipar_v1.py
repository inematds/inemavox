#!/usr/bin/env python3
"""Clipar v1 - Corte de clips de video por timestamps manuais ou analise viral via Ollama."""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


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
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
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
    """Converte 'HH:MM:SS', 'MM:SS' ou 'SS' para segundos float."""
    parts = s.strip().split(":")
    if len(parts) == 1:
        return float(parts[0])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    else:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def parse_timestamps(timestamps_str: str) -> list[tuple[float, float]]:
    """Parseia 'HH:MM:SS-HH:MM:SS, MM:SS-MM:SS, ...' em lista de (start, end)."""
    clips = []
    for part in re.split(r"[,;]", timestamps_str):
        part = part.strip()
        if not part:
            continue
        match = re.match(r"^([\d:]+)\s*-\s*([\d:]+)$", part)
        if not match:
            print(f"[warn] Timestamp invalido ignorado: {part}", flush=True)
            continue
        start_s = parse_time_str(match.group(1))
        end_s = parse_time_str(match.group(2))
        if end_s <= start_s:
            print(f"[warn] Clip invalido (start >= end): {part}", flush=True)
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
    """Verifica se CUDA esta disponivel tanto no PyTorch quanto no CTranslate2."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return True
    except Exception:
        pass
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


def analyze_viral(
    segments: list[dict],
    ollama_model: str,
    num_clips: int,
    min_dur: int,
    max_dur: int,
    ollama_url: str = "http://localhost:11434",
) -> list[dict]:
    """Chama Ollama para identificar os segmentos mais virais."""
    print(f"[analysis] Analisando com {ollama_model} ({num_clips} clips, {min_dur}-{max_dur}s)...", flush=True)

    transcript_text = "\n".join(
        f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}"
        for seg in segments
    )

    prompt = f"""Analyze this video transcript and identify the {num_clips} most engaging/viral segments.

Requirements:
- Each clip must be between {min_dur} and {max_dur} seconds long
- Choose complete thoughts/stories, never cut mid-sentence
- Prioritize: hooks, surprising facts, emotional moments, actionable tips, controversial opinions
- Clips must not overlap

Transcript:
{transcript_text}

Respond ONLY with a valid JSON array (no extra text, no markdown):
[
  {{"start": 10.5, "end": 75.2, "reason": "Strong hook about..."}},
  {{"start": 120.0, "end": 195.0, "reason": "Viral moment: ..."}}
]"""

    payload = {
        "model": ollama_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.3},
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            content = resp_data["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Ollama API error: {e}")

    print(f"[analysis] Resposta do LLM recebida ({len(content)} chars)", flush=True)

    # Tentar parsear JSON direto
    try:
        clips_data = json.loads(content)
        if isinstance(clips_data, list):
            return clips_data
    except Exception:
        pass

    # Tentar extrair de bloco markdown
    match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", content)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Tentar encontrar array na resposta
    match = re.search(r"\[[\s\S]*\]", content)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    raise RuntimeError(f"Nao foi possivel parsear resposta do Ollama: {content[:300]}")


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
    args = parser.parse_args()

    clips_dir = Path(args.outdir)
    workdir = clips_dir.parent  # dub_work fica no pai de clips/

    (workdir / "dub_work").mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    try:
        if args.mode == "manual":
            # Etapa 1: Download
            write_checkpoint(workdir, 1, "download", "Download")
            source = download_input(args.input, workdir)

            # Etapa 2: Cutting
            write_checkpoint(workdir, 2, "cutting", "Cortando clips")
            timestamps = parse_timestamps(args.timestamps)
            if not timestamps:
                raise ValueError("Nenhum timestamp valido fornecido. Use o formato: 00:30-02:15,05:00-07:30")
            cut_clips(source, timestamps, clips_dir)

            # Etapa 3: ZIP
            write_checkpoint(workdir, 3, "zip", "Criando ZIP")
            create_zip(clips_dir)

        else:  # viral
            # Etapa 1: Download
            write_checkpoint(workdir, 1, "download", "Download")
            source = download_input(args.input, workdir)

            # Etapa 2: Extraction
            write_checkpoint(workdir, 2, "extraction", "Extracao de audio")
            audio = extract_audio(source, workdir)

            # Etapa 3: Transcription
            write_checkpoint(workdir, 3, "transcription", "Transcricao")
            segments = transcribe_for_viral(audio, args.whisper_model)

            if not segments:
                raise RuntimeError("Nenhum segmento de fala detectado no audio")

            # Etapa 4: Analysis
            write_checkpoint(workdir, 4, "analysis", "Analise viral")
            viral_clips = analyze_viral(
                segments,
                args.ollama_model,
                args.num_clips,
                args.min_duration,
                args.max_duration,
                args.ollama_url,
            )

            print(f"[analysis] {len(viral_clips)} clips identificados:", flush=True)
            timestamps = []
            for c in viral_clips:
                start = float(c.get("start", 0))
                end = float(c.get("end", 0))
                reason = c.get("reason", "")
                print(f"  {start:.1f}s - {end:.1f}s: {reason}", flush=True)
                if end > start:
                    timestamps.append((start, end))

            if not timestamps:
                raise RuntimeError("Nenhum clip valido retornado pelo LLM")

            # Etapa 5: Cutting
            write_checkpoint(workdir, 5, "cutting", "Cortando clips")
            cut_clips(source, timestamps, clips_dir)

            # Etapa 6: ZIP
            write_checkpoint(workdir, 6, "zip", "Criando ZIP")
            create_zip(clips_dir)

        print("[done] Corte concluido com sucesso!", flush=True)
        sys.exit(0)

    except Exception as e:
        print(f"[error] {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
