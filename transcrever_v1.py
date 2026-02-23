#!/usr/bin/env python3
"""Transcrever v1 - Transcricao standalone usando faster-whisper ou parakeet."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CHATTERBOX_PYTHON = os.environ.get(
    "CHATTERBOX_PYTHON",
    "/home/nmaldaner/miniconda3/envs/chatterbox/bin/python3",
)


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
    """Baixa video/audio se for URL, ou retorna o path local."""
    if input_val.startswith("http"):
        print(f"[download] Baixando: {input_val}", flush=True)
        out_template = workdir / "dub_work" / "source.%(ext)s"
        cmd = [
            "yt-dlp",
            # Preferencia: melhor audio isolado -> melhor com acodec -> qualquer formato
            # acodec!=none garante que o arquivo tenha audio (evita video-only como bytevc1)
            "-f", "bestaudio[ext=m4a]/bestaudio/best[acodec!=none]/best",
            "--output", str(out_template),
            "--no-playlist",
            "--write-info-json",
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


def extract_audio(source: Path, workdir: Path) -> Path:
    """Extrai audio do video como WAV mono 16kHz."""
    print("[extraction] Extraindo audio...", flush=True)
    audio_path = workdir / "dub_work" / "audio.wav"

    # Tentar com -vn (descarta video, extrai audio)
    cmd = [
        "ffmpeg", "-y", "-i", str(source),
        "-ac", "1", "-ar", "16000", "-vn",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        # Fallback: arquivo pode ser audio puro (m4a, mp3, opus) sem stream de video
        # Nesse caso remover -vn e converter direto
        if "does not contain any stream" in result.stderr or "Invalid argument" in result.stderr:
            print("[extraction] Sem stream de video detectado, convertendo como audio puro...", flush=True)
            cmd2 = [
                "ffmpeg", "-y", "-i", str(source),
                "-ac", "1", "-ar", "16000",
                str(audio_path),
            ]
            result2 = subprocess.run(cmd2, capture_output=True, text=True)
            if result2.returncode != 0:
                raise RuntimeError(f"ffmpeg falhou (audio puro): {result2.stderr[-500:]}")
            return audio_path

        raise RuntimeError(f"ffmpeg falhou: {result.stderr[-500:]}")
    return audio_path


def _has_cuda() -> bool:
    """Verifica se CUDA esta disponivel no PyTorch E no CTranslate2."""
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        import ctranslate2
        ctranslate2.get_supported_compute_types("cuda")  # lanca ValueError se sem CUDA
        return True
    except Exception:
        return False


def _chatterbox_has_cuda() -> bool:
    """Verifica se o conda env chatterbox tem CUDA disponivel."""
    if not Path(CHATTERBOX_PYTHON).exists():
        return False
    try:
        result = subprocess.run(
            [CHATTERBOX_PYTHON, "-c", "import torch; print('1' if torch.cuda.is_available() else '0')"],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout.strip() == "1"
    except Exception:
        return False


def transcribe_whisper_gpu(audio_path: Path, model: str, src_lang: str | None) -> list[dict]:
    """Transcreve via worker GPU usando openai-whisper no conda env chatterbox."""
    worker_script = Path(__file__).parent / "whisper_gpu_worker.py"
    output_json = audio_path.parent / "whisper_gpu_result.json"

    cmd = [
        CHATTERBOX_PYTHON, str(worker_script),
        "--audio", str(audio_path),
        "--model", model,
        "--output-json", str(output_json),
    ]
    if src_lang:
        cmd += ["--lang", src_lang]

    print(f"[transcription] Transcrevendo com Whisper GPU ({model})...", flush=True)
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"whisper_gpu_worker retornou codigo {result.returncode}")

    data = json.loads(output_json.read_text(encoding="utf-8"))
    segments = data["segments"]

    for seg in segments:
        print(f"  [{seg['start']:.1f}s -> {seg['end']:.1f}s] {seg['text']}", flush=True)

    print(f"[transcription] {len(segments)} segmentos, idioma: {data.get('language', '?')}", flush=True)
    return segments


def transcribe_whisper(audio_path: Path, model: str, src_lang: str | None) -> list[dict]:
    """Transcreve com Whisper. Usa GPU via conda env se disponivel, senao faster-whisper CPU."""
    if _chatterbox_has_cuda():
        return transcribe_whisper_gpu(audio_path, model, src_lang)

    print(f"[transcription] Transcrevendo com faster-whisper CPU {model}...", flush=True)
    from faster_whisper import WhisperModel

    device = "cuda" if _has_cuda() else "cpu"
    compute = "float16" if device == "cuda" else "int8"

    wm = WhisperModel(model, device=device, compute_type=compute)
    segments_iter, info = wm.transcribe(
        str(audio_path),
        language=src_lang or None,
        vad_filter=True,
    )

    results = []
    for seg in segments_iter:
        results.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
        })
        print(f"  [{seg.start:.1f}s -> {seg.end:.1f}s] {seg.text.strip()}", flush=True)

    print(f"[transcription] {len(results)} segmentos, idioma: {info.language}", flush=True)
    return results


def seconds_to_srt_time(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms = int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def get_video_title(workdir: Path, input_val: str) -> str:
    """Tenta obter o titulo do video da info JSON do yt-dlp ou do nome do arquivo."""
    info_json = workdir / "dub_work" / "source.info.json"
    if info_json.exists():
        try:
            info = json.loads(info_json.read_text(encoding="utf-8"))
            return str(info.get("title", "") or "")
        except Exception:
            pass
    if not input_val.startswith("http"):
        return Path(input_val).stem
    return ""


def save_transcript_summary(segments: list[dict], outdir: Path, title: str = ""):
    """Salva um JSON com titulo e descricao (preview do texto) da transcricao."""
    full_text = " ".join(seg["text"] for seg in segments)
    description = full_text[:500].strip()
    if len(full_text) > 500:
        last_space = description.rfind(" ")
        if last_space > 0:
            description = description[:last_space] + "..."
    duration_s = segments[-1]["end"] if segments else 0
    summary = {
        "title": title,
        "description": description,
        "total_segments": len(segments),
        "duration_s": round(duration_s, 1),
    }
    (outdir / "transcript_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[summary] Resumo salvo: titulo='{title}'", flush=True)


def export_transcription(segments: list[dict], outdir: Path):
    """Exporta SRT, TXT e JSON."""
    print("[export] Exportando legendas...", flush=True)
    outdir.mkdir(parents=True, exist_ok=True)

    # SRT
    srt_lines = []
    for i, seg in enumerate(segments, 1):
        srt_lines.append(str(i))
        srt_lines.append(f"{seconds_to_srt_time(seg['start'])} --> {seconds_to_srt_time(seg['end'])}")
        srt_lines.append(seg["text"])
        srt_lines.append("")
    (outdir / "transcript.srt").write_text("\n".join(srt_lines), encoding="utf-8")

    # TXT
    txt = "\n".join(seg["text"] for seg in segments)
    (outdir / "transcript.txt").write_text(txt, encoding="utf-8")

    # JSON
    (outdir / "transcript.json").write_text(
        json.dumps(segments, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"[export] Arquivos salvos em {outdir}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Transcrever v1")
    parser.add_argument("--in", dest="input", required=True, help="URL ou caminho do arquivo")
    parser.add_argument("--outdir", required=True, help="Diretorio de saida para transcricoes")
    parser.add_argument("--asr", default="whisper", choices=["whisper", "parakeet"])
    parser.add_argument("--whisper-model", default="large-v3", dest="whisper_model")
    parser.add_argument("--src", default=None, help="Idioma de origem (auto-detect se vazio)")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    workdir = outdir.parent  # dub_work fica no pai de transcription/

    (workdir / "dub_work").mkdir(parents=True, exist_ok=True)
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        # Checkpoint escrito APOS cada etapa (semantica: "etapa N concluida")
        # Assim o progresso mostra a etapa N como done e N+1 como running

        # Etapa 1: Download
        source = download_input(args.input, workdir)
        write_checkpoint(workdir, 1, "download", "Download")

        # Etapa 2: Extraction
        audio = extract_audio(source, workdir)
        write_checkpoint(workdir, 2, "extraction", "Extracao de audio")

        # Etapa 3: Transcription
        if args.asr == "whisper":
            segments = transcribe_whisper(audio, args.whisper_model, args.src)
        else:
            # parakeet - fallback para whisper por enquanto
            segments = transcribe_whisper(audio, "large-v3", "en")
        write_checkpoint(workdir, 3, "transcription", "Transcricao")

        # Etapa 4: Export
        export_transcription(segments, outdir)
        title = get_video_title(workdir, args.input)
        save_transcript_summary(segments, outdir, title)
        write_checkpoint(workdir, 4, "export", "Exportando legendas")

        print("[done] Transcricao concluida com sucesso!", flush=True)
        sys.exit(0)

    except Exception as e:
        print(f"[error] {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
