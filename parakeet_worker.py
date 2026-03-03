#!/usr/bin/env python3
"""
Worker Parakeet GPU — executa no conda env 'chatterbox' que tem NeMo + CUDA.
Chamado por dublar_pro_v5.py e transcrever_v1.py via subprocess.

Uso:
    python3 parakeet_worker.py \
        --audio /path/audio.wav \
        --model nvidia/parakeet-tdt-1.1b \
        --output-json /path/result.json
"""

import argparse
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, help="Caminho do arquivo de audio (WAV 16kHz mono)")
    parser.add_argument("--model", default="nvidia/parakeet-tdt-1.1b", help="Modelo Parakeet HuggingFace ID")
    parser.add_argument("--output-json", required=True, help="Caminho do JSON de saida")
    parser.add_argument("--segment-pause", type=float, default=0.3, help="Pausa minima em segundos para novo segmento")
    parser.add_argument("--segment-max-words", type=int, default=15, help="Max palavras por segmento")
    args = parser.parse_args()

    try:
        import nemo.collections.asr as nemo_asr
    except ImportError:
        print("[parakeet_worker] ERRO: nemo_toolkit nao instalado", flush=True)
        sys.exit(1)

    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[parakeet_worker] device={device}, model={args.model}", flush=True)

    t0 = time.time()
    model = nemo_asr.models.ASRModel.from_pretrained(args.model)
    model = model.to(device)
    model.eval()
    print(f"[parakeet_worker] modelo carregado em {time.time()-t0:.1f}s", flush=True)

    # Parakeet precisa de WAV 16kHz mono — converter se necessario
    audio_path = args.audio
    import subprocess, tempfile, os
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels",
         "-of", "csv=p=0", audio_path],
        capture_output=True, text=True
    )
    info = probe.stdout.strip().split(",")
    needs_resample = len(info) < 2 or info[0] != "16000" or info[1] != "1"

    if needs_resample:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-ac", "1", "-ar", "16000", tmp.name],
            capture_output=True, check=True
        )
        audio_path = tmp.name
        print(f"[parakeet_worker] audio reamostrado para 16kHz mono", flush=True)
    else:
        tmp = None

    try:
        t1 = time.time()
        output = model.transcribe([audio_path], timestamps=True)
        print(f"[parakeet_worker] transcricao em {time.time()-t1:.1f}s", flush=True)
    finally:
        if tmp:
            os.unlink(tmp.name)

    # Extrair timestamps por palavra e agrupar em segmentos
    segments = _build_segments(output, args.segment_pause, args.segment_max_words)

    print(f"[parakeet_worker] {len(segments)} segmentos gerados", flush=True)
    for seg in segments:
        print(f"  [{seg['start']:.1f}s -> {seg['end']:.1f}s] {seg['text'][:80]}", flush=True)

    result = {
        "language": "en",  # Parakeet so suporta ingles
        "segments": segments,
    }
    Path(args.output_json).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("[parakeet_worker] concluido", flush=True)


def _build_segments(output, pause_threshold=0.3, max_words=15):
    """Agrupa palavras do Parakeet em segmentos por pausa ou limite de palavras."""
    # output pode ser lista de hipoteses ou objeto NeMo
    # Tentar extrair timestamps de palavra
    try:
        if hasattr(output[0], "timestamp"):
            words = output[0].timestamp.get("word", [])
        elif isinstance(output, list) and len(output) > 0:
            first = output[0]
            if hasattr(first, "words"):
                words = first.words
            elif isinstance(first, dict):
                words = first.get("words", [])
            else:
                words = []
        else:
            words = []
    except Exception:
        words = []

    if not words:
        # Sem timestamps por palavra — retornar o texto completo como um segmento
        try:
            if hasattr(output[0], "text"):
                text = output[0].text
            elif isinstance(output[0], str):
                text = output[0]
            else:
                text = str(output[0])
        except Exception:
            text = str(output)
        # Estimar duração (sem info de timestamp, usar 0-999)
        return [{"start": 0.0, "end": 999.0, "text": text.strip()}]

    segments = []
    current_words = []
    current_start = None

    def flush_segment(end_time):
        if not current_words:
            return
        text = " ".join(w["word"] if isinstance(w, dict) else w.word for w in current_words)
        segments.append({
            "start": round(current_start, 3),
            "end": round(end_time, 3),
            "text": text.strip(),
        })

    for i, w in enumerate(words):
        # Suporte a dicts ou objetos
        if isinstance(w, dict):
            word_text = w.get("word", w.get("char", ""))
            word_start = float(w.get("start_offset", w.get("start", 0)))
            word_end = float(w.get("end_offset", w.get("end", word_start + 0.1)))
        else:
            word_text = getattr(w, "word", getattr(w, "char", ""))
            word_start = float(getattr(w, "start_offset", getattr(w, "start", 0)))
            word_end = float(getattr(w, "end_offset", getattr(w, "end", word_start + 0.1)))

        if not word_text.strip():
            continue

        if current_start is None:
            current_start = word_start

        # Verificar pausa ou limite de palavras
        if current_words:
            prev = current_words[-1]
            if isinstance(prev, dict):
                prev_end = float(prev.get("end_offset", prev.get("end", 0)))
            else:
                prev_end = float(getattr(prev, "end_offset", getattr(prev, "end", 0)))

            gap = word_start - prev_end
            if gap >= pause_threshold or len(current_words) >= max_words:
                flush_segment(prev_end)
                current_words = []
                current_start = word_start

        current_words.append(w)

    # Ultimo segmento
    if current_words:
        last = current_words[-1]
        if isinstance(last, dict):
            last_end = float(last.get("end_offset", last.get("end", current_start + 1)))
        else:
            last_end = float(getattr(last, "end_offset", getattr(last, "end", current_start + 1)))
        flush_segment(last_end)

    return segments


if __name__ == "__main__":
    main()
