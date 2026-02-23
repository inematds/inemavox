#!/usr/bin/env python3
"""
Worker Whisper GPU — executa no conda env 'chatterbox' que tem torch+CUDA.
Chamado por transcrever_v1.py via subprocess quando CUDA está disponível.

Uso:
    python3 whisper_gpu_worker.py \
        --audio /path/audio.wav \
        --model large-v3 \
        [--lang pt] \
        --output-json /path/result.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

import torch
import whisper


def get_device():
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, help="Caminho do arquivo de audio")
    parser.add_argument("--model", default="large-v3", help="Modelo Whisper")
    parser.add_argument("--lang", default=None, help="Idioma de origem (auto se vazio)")
    parser.add_argument("--output-json", required=True, help="Caminho do JSON de saida")
    args = parser.parse_args()

    device = get_device()
    fp16 = device == "cuda"

    print(f"[whisper_gpu] device={device}, model={args.model}, lang={args.lang or 'auto'}", flush=True)

    t0 = time.time()
    model = whisper.load_model(args.model, device=device)
    print(f"[whisper_gpu] modelo carregado em {time.time()-t0:.1f}s", flush=True)

    result = model.transcribe(
        args.audio,
        language=args.lang or None,
        fp16=fp16,
        verbose=False,
    )

    segments = [
        {
            "start": round(seg["start"], 3),
            "end": round(seg["end"], 3),
            "text": seg["text"].strip(),
        }
        for seg in result["segments"]
    ]

    print(f"[whisper_gpu] {len(segments)} segmentos, idioma: {result.get('language', '?')}", flush=True)

    output = {
        "language": result.get("language", ""),
        "segments": segments,
    }
    Path(args.output_json).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[whisper_gpu] concluido", flush=True)


if __name__ == "__main__":
    main()
