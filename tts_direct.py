#!/usr/bin/env python3
"""
tts_direct.py — inemaVOX: Gera audio a partir de texto.

Uso:
    python tts_direct.py --text "Ola mundo" --lang pt --engine edge --outdir /path/out
    python tts_direct.py --text "Hello" --lang en --engine chatterbox --outdir /path/out
    python tts_direct.py --text "Ola" --lang pt --engine chatterbox --ref ref.wav --outdir /path/out
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Vozes padrao por idioma (Edge TTS)
EDGE_VOICE_DEFAULTS = {
    "pt": "pt-BR-FranciscaNeural",
    "pt-br": "pt-BR-FranciscaNeural",
    "en": "en-US-JennyNeural",
    "es": "es-MX-DaliaNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural",
    "ja": "ja-JP-NanamiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ko": "ko-KR-SunHiNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ar": "ar-SA-ZariyahNeural",
    "hi": "hi-IN-SwaraNeural",
    "nl": "nl-NL-ColetteNeural",
    "pl": "pl-PL-ZofiaNeural",
    "tr": "tr-TR-EmelNeural",
}


def write_checkpoint(outdir: Path, step: str, detail: str = ""):
    cp = {"last_step": step, "detail": detail}
    (outdir.parent / "dub_work" / "checkpoint.json").write_text(
        json.dumps(cp), encoding="utf-8"
    )


async def run_edge(text: str, lang: str, voice: str | None, outdir: Path) -> Path:
    import edge_tts

    voice_id = voice or EDGE_VOICE_DEFAULTS.get(lang.lower(), "pt-BR-FranciscaNeural")
    out_path = outdir / "generated.mp3"

    print(f"[tts_direct] Edge TTS: voz={voice_id}, lang={lang}", flush=True)
    communicate = edge_tts.Communicate(text, voice_id)
    await communicate.save(str(out_path))
    print(f"[tts_direct] Audio gerado: {out_path} ({out_path.stat().st_size} bytes)", flush=True)
    return out_path


def convert_ref_to_wav(ref_path: str, outdir: Path) -> str:
    """Converte áudio de referência para WAV 22050Hz mono via ffmpeg.
    Necessário porque soundfile não lê MP4/MP3 diretamente.
    """
    p = Path(ref_path)
    if p.suffix.lower() == ".wav":
        return ref_path  # já é WAV, usar direto
    wav_path = outdir / "ref_converted.wav"
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", ref_path,
             "-ar", "22050", "-ac", "1", "-f", "wav", str(wav_path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and wav_path.exists():
            print(f"[tts_direct] Referencia convertida para WAV: {wav_path}", flush=True)
            return str(wav_path)
        print(f"[tts_direct] ffmpeg falhou na conversao: {result.stderr[-200:]}", flush=True)
    except Exception as e:
        print(f"[tts_direct] Erro ao converter referencia: {e}", flush=True)
    return ref_path  # fallback: tentar com original


def split_sentences(text: str, max_chars: int = 120) -> list[str]:
    """Divide texto longo em sentenças curtas para evitar loop no modelo."""
    import re
    # Dividir em sentenças por pontuação
    parts = re.split(r'(?<=[.!?,;:])\s+', text.strip())
    sentences: list[str] = []
    current = ""
    for part in parts:
        if len(current) + len(part) + 1 <= max_chars:
            current = (current + " " + part).strip() if current else part
        else:
            if current:
                sentences.append(current)
            # Parte muito longa: dividir por vírgulas ou forçar
            if len(part) > max_chars:
                words = part.split()
                chunk = ""
                for w in words:
                    if len(chunk) + len(w) + 1 <= max_chars:
                        chunk = (chunk + " " + w).strip() if chunk else w
                    else:
                        if chunk:
                            sentences.append(chunk)
                        chunk = w
                if chunk:
                    sentences.append(chunk)
            else:
                current = part
    if current:
        sentences.append(current)
    return [s for s in sentences if s.strip()]


def run_chatterbox(text: str, lang: str, ref: str | None, outdir: Path) -> Path:
    chatterbox_python = os.environ.get(
        "CHATTERBOX_PYTHON",
        "/home/nmaldaner/miniconda3/envs/chatterbox/bin/python3"
    )
    worker_script = Path(__file__).parent / "chatterbox_tts_worker.py"

    if not Path(chatterbox_python).exists():
        raise RuntimeError(
            f"Python Chatterbox nao encontrado: {chatterbox_python}\n"
            "Defina CHATTERBOX_PYTHON=/path/python3 do conda env chatterbox"
        )

    # Converter referência para WAV se necessário (soundfile não lê MP4/MP3)
    ref_wav = None
    if ref and Path(ref).exists():
        ref_wav = convert_ref_to_wav(ref, outdir)
        print(f"[tts_direct] Chatterbox voice clone: {ref_wav}", flush=True)
    else:
        print(f"[tts_direct] Chatterbox voz padrao (lang={lang})", flush=True)

    # Dividir texto longo em sentenças (max 120 chars) para evitar loop/EOS prematuro
    sentences = split_sentences(text, max_chars=120)
    print(f"[tts_direct] Texto dividido em {len(sentences)} segmentos", flush=True)

    segments = [
        {"text_trad": s, "start": float(i * 15), "end": float((i + 1) * 15)}
        for i, s in enumerate(sentences)
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False, encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False)
        segs_json = f.name

    output_json = outdir / "chatterbox_result.json"

    try:
        cmd = [
            chatterbox_python, str(worker_script),
            "--segments-json", segs_json,
            "--workdir", str(outdir),
            "--lang", lang,
            "--output-json", str(output_json),
        ]
        if ref_wav:
            cmd += ["--ref", ref_wav]

        result = subprocess.run(cmd, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"Chatterbox worker retornou codigo {result.returncode}")

        data = json.loads(output_json.read_text(encoding="utf-8"))
        sr = data.get("sr", 24000)
        seg_files = [Path(s["file"]) for s in data["segments"] if Path(s["file"]).exists()]

        if not seg_files:
            raise RuntimeError("Nenhum segmento de audio gerado")

        out_path = outdir / "generated.wav"

        if len(seg_files) == 1:
            seg_files[0].rename(out_path)
        else:
            # Concatenar todos os segmentos em um único WAV
            import soundfile as sf
            import numpy as np
            chunks = []
            silence = np.zeros(int(sr * 0.25), dtype=np.float32)  # 250ms entre frases
            for i, seg_file in enumerate(seg_files):
                audio, _ = sf.read(str(seg_file))
                chunks.append(audio.astype(np.float32))
                if i < len(seg_files) - 1:
                    chunks.append(silence)
            combined = np.concatenate(chunks)
            sf.write(str(out_path), combined, sr)
            print(f"[tts_direct] {len(seg_files)} segmentos concatenados", flush=True)

        print(f"[tts_direct] Audio gerado: {out_path} ({out_path.stat().st_size} bytes)", flush=True)
        return out_path

    finally:
        Path(segs_json).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True, help="Texto para sintetizar")
    parser.add_argument("--lang", default="pt", help="Idioma (pt, en, es...)")
    parser.add_argument("--engine", default="edge",
                        choices=["edge", "chatterbox"],
                        help="Motor TTS")
    parser.add_argument("--voice", default=None, help="ID de voz (Edge TTS)")
    parser.add_argument("--ref", default=None, help="Audio de referencia para voice clone")
    parser.add_argument("--outdir", required=True, help="Diretorio de saida")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Criar dub_work para checkpoint
    (outdir.parent / "dub_work").mkdir(exist_ok=True)

    print(f"\n{'='*50}", flush=True)
    print(f"  inemaVOX - Gerando Audio", flush=True)
    print(f"  Engine : {args.engine}", flush=True)
    print(f"  Idioma : {args.lang}", flush=True)
    print(f"  Texto  : {args.text[:80]}{'...' if len(args.text) > 80 else ''}", flush=True)
    print(f"{'='*50}\n", flush=True)

    write_checkpoint(outdir, "1", "Iniciando geracao de audio")

    if args.engine == "edge":
        out = asyncio.run(run_edge(args.text, args.lang, args.voice, outdir))
    elif args.engine == "chatterbox":
        out = run_chatterbox(args.text, args.lang, args.ref, outdir)
    else:
        print(f"[ERRO] Engine nao suportada: {args.engine}", flush=True)
        sys.exit(1)

    write_checkpoint(outdir, "done", str(out))
    print(f"\n[OK] Concluido: {out}", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
