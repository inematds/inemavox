#!/usr/bin/env python3
"""
Worker Chatterbox VC — executa no conda env 'chatterbox'.
Pipeline: áudio fonte (Edge TTS) + referência → ChatterboxVC → voz clonada.

Sem T3 (sem LLM autoregressive), sem risco de EOS prematuro.
O S3Gen decoder converte diretamente os tokens do áudio fonte para a voz do ref.

Uso:
    python3 chatterbox_vc_worker.py \
        --source /path/edge_source.mp3 \
        --ref    /path/ref_converted.wav \
        --output /path/generated.wav
"""

import argparse
import time
from pathlib import Path

import torch
import soundfile as sf


def get_device() -> str:
    """Detecta device com verificação de VRAM disponível.
    S3Gen (VC) usa ~1.5GB VRAM. Threshold conservador de 1.5GB.
    """
    if not torch.cuda.is_available():
        return "cpu"
    try:
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        free_gb = free_bytes / 1e9
        if free_gb < 1.5:
            print(f"[vc_worker] VRAM insuficiente ({free_gb:.1f}GB livre de {total_bytes/1e9:.1f}GB), usando CPU", flush=True)
            return "cpu"
        print(f"[vc_worker] VRAM disponivel: {free_gb:.1f}GB livre", flush=True)
        return "cuda"
    except Exception:
        return "cuda"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True,
                        help="Áudio fonte (saída do Edge TTS — fala neutra)")
    parser.add_argument("--ref", required=True,
                        help="WAV de referência 24kHz mono para clonagem de voz")
    parser.add_argument("--output", required=True,
                        help="Caminho do WAV de saída com a voz clonada")
    args = parser.parse_args()

    source_path = Path(args.source)
    ref_path = Path(args.ref)
    out_path = Path(args.output)

    if not source_path.exists():
        raise FileNotFoundError(f"Áudio fonte não encontrado: {source_path}")
    if not ref_path.exists():
        raise FileNotFoundError(f"Referência não encontrada: {ref_path}")

    device = get_device()
    print(f"[vc_worker] device={device}", flush=True)
    print(f"[vc_worker] source={source_path} ({source_path.stat().st_size} bytes)", flush=True)
    print(f"[vc_worker] ref={ref_path} ({ref_path.stat().st_size} bytes)", flush=True)

    # Carregar modelo
    t0 = time.time()
    from chatterbox.vc import ChatterboxVC
    try:
        model = ChatterboxVC.from_pretrained(device=device)
    except Exception as e:
        if device == "cuda" and ("out of memory" in str(e).lower() or "cuda" in str(e).lower()):
            print(f"[vc_worker] CUDA OOM ao carregar modelo, retentando em CPU: {e}", flush=True)
            torch.cuda.empty_cache()
            model = ChatterboxVC.from_pretrained(device="cpu")
            device = "cpu"
        else:
            raise
    print(f"[vc_worker] modelo carregado em {time.time() - t0:.1f}s (device={device})", flush=True)

    # Converter: fonte → voz do ref
    t1 = time.time()
    wav = model.generate(
        audio=str(source_path),
        target_voice_path=str(ref_path),
    )
    elapsed = time.time() - t1
    print(f"[vc_worker] conversão VC concluida em {elapsed:.1f}s", flush=True)

    audio_np = wav.squeeze().cpu().numpy()
    sf.write(str(out_path), audio_np, model.sr)
    print(f"[vc_worker] salvo: {out_path} ({out_path.stat().st_size} bytes)", flush=True)


if __name__ == "__main__":
    main()
