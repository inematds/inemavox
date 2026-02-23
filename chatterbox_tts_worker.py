#!/usr/bin/env python3
"""
Worker Chatterbox TTS — executa no conda env 'chatterbox'.
Chamado por tts_chatterbox() em dublar_pro_v5.py via subprocess.

Uso:
    python3 chatterbox_tts_worker.py \
        --segments-json /path/segs.json \
        --workdir /path/workdir \
        --lang pt \
        [--ref /path/voice_sample.wav] \
        --output-json /path/result.json
"""

import argparse
import json
import sys
import time
import re
from pathlib import Path

import torch
import soundfile as sf
import numpy as np


CHATTERBOX_SR = 24000

# Idiomas suportados pelo modelo Multilingual
MTL_LANGS = {
    "pt", "pt-br", "pt_br",
    "es", "fr", "de", "it", "nl", "pl", "cs", "sk", "hu", "ro",
    "uk", "ru", "tr", "ar", "zh", "ja", "ko", "hi", "sw", "cy"
}


def get_device() -> str:
    """Detecta device com verificação de VRAM disponível.
    MTL requer ~3-4GB VRAM. Se insuficiente, fallback para CPU.
    """
    if not torch.cuda.is_available():
        return "cpu"
    try:
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        free_gb = free_bytes / 1e9
        # MTL precisa de ~3-4GB; VC usa só o decoder (~1.5GB)
        # Threshold conservador de 2.5GB para ambos os modelos
        if free_gb < 2.5:
            print(f"[chatterbox_worker] VRAM insuficiente ({free_gb:.1f}GB livre de {total_bytes/1e9:.1f}GB), usando CPU", flush=True)
            return "cpu"
        print(f"[chatterbox_worker] VRAM disponivel: {free_gb:.1f}GB livre", flush=True)
        return "cuda"
    except Exception:
        return "cuda"


def salvar_silencio(path, duracao_s, sr=CHATTERBOX_SR):
    """Grava silencio para segmento que falhou."""
    n = max(1, int(duracao_s * sr))
    sf.write(str(path), np.zeros(n, dtype=np.float32), sr)


def normalizar_lang(lang: str) -> str:
    """Normaliza codigo de idioma para formato Chatterbox."""
    return lang.lower().replace("-", "_").split("_")[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--segments-json", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--lang", required=True)
    parser.add_argument("--ref", default=None, help="WAV de referencia para voice clone")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--cfg-weight",   type=float, default=0.65, help="CFG weight (0.1-1.0). Alto = mais fiel ao ref")
    parser.add_argument("--exaggeration", type=float, default=0.5,  help="Exaggeration (0.1-1.0). Alto = mais expressivo")
    parser.add_argument("--temperature",  type=float, default=0.75, help="Temperature (0.1-1.5). Alto = mais variado")
    args = parser.parse_args()

    with open(args.segments_json, encoding="utf-8") as f:
        segments = json.load(f)

    workdir = Path(args.workdir)
    lang = normalizar_lang(args.lang)
    device = get_device()
    ref = args.ref if args.ref and Path(args.ref).exists() else None

    use_multilingual = lang != "en"

    print(f"[chatterbox_worker] device={device}, lang={lang}, modelo={'mtl' if use_multilingual else 'turbo'}", flush=True)
    if ref:
        print(f"[chatterbox_worker] voice clone: {ref}", flush=True)

    t0 = time.time()
    try:
        if use_multilingual:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            model = ChatterboxMultilingualTTS.from_pretrained(device=device)
        else:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            model = ChatterboxTurboTTS.from_pretrained(device=device)
    except Exception as e:
        if device == "cuda" and ("out of memory" in str(e).lower() or "cuda" in str(e).lower()):
            print(f"[chatterbox_worker] CUDA OOM ao carregar modelo, retentando em CPU: {e}", flush=True)
            torch.cuda.empty_cache()
            if use_multilingual:
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS
                model = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
            else:
                from chatterbox.tts_turbo import ChatterboxTurboTTS
                model = ChatterboxTurboTTS.from_pretrained(device="cpu")
            device = "cpu"
        else:
            raise

    print(f"[chatterbox_worker] modelo carregado em {time.time()-t0:.1f}s (device={device})", flush=True)

    seg_results = []

    for i, seg in enumerate(segments, 1):
        txt = (seg.get("text_trad") or seg.get("text") or "").strip()
        target_dur = seg.get("end", 0) - seg.get("start", 0)
        out_path = workdir / f"seg_{i:04d}.wav"

        if len(re.findall(r"[A-Za-z0-9\u00C0-\u024F]", txt)) < 3:
            salvar_silencio(out_path, target_dur)
            seg_results.append({
                "idx": i, "file": str(out_path),
                "target": target_dur, "actual": target_dur, "ratio": 1.0
            })
            continue

        t0 = time.time()
        try:
            if use_multilingual:
                kwargs = {
                    "language_id": lang,
                    "exaggeration": args.exaggeration,
                    "cfg_weight":   args.cfg_weight,
                    "temperature":  args.temperature,
                }
                if ref:
                    kwargs["audio_prompt_path"] = ref
                wav = model.generate(txt, **kwargs)
            else:
                kwargs = {
                    "exaggeration": args.exaggeration,
                    "cfg_weight":   args.cfg_weight,
                    "temperature":  args.temperature,
                }
                if ref:
                    kwargs["audio_prompt_path"] = ref
                wav = model.generate(txt, **kwargs)

            audio_np = wav.squeeze().cpu().numpy()
            sf.write(str(out_path), audio_np, CHATTERBOX_SR)
            actual_dur = len(audio_np) / CHATTERBOX_SR
            ratio = actual_dur / target_dur if target_dur > 0 else 1.0

        except Exception as e:
            print(f"[chatterbox_worker] ERRO seg {i}: {e}", flush=True)
            salvar_silencio(out_path, target_dur)
            actual_dur = target_dur
            ratio = 1.0

        seg_results.append({
            "idx": i, "file": str(out_path),
            "target": target_dur, "actual": actual_dur, "ratio": ratio
        })

        if i % 5 == 0 or i == len(segments):
            print(f"[chatterbox_worker] progresso: {i}/{len(segments)}", flush=True)

    result = {"sr": CHATTERBOX_SR, "segments": seg_results}
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[chatterbox_worker] concluido: {len(seg_results)} segmentos", flush=True)


if __name__ == "__main__":
    main()
