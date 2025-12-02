#!/usr/bin/env python3
"""
Teste isolado do Parakeet (NVIDIA NeMo) para transcrição.
Compara com Whisper large-v3.

Uso:
    python test_parakeet.py --audio arquivo.wav
    python test_parakeet.py --video arquivo.mp4
"""

import argparse
import subprocess
import time
from pathlib import Path


def extract_audio(video_path, output_wav):
    """Extrai áudio do vídeo"""
    print(f"[INFO] Extraindo áudio de {video_path}...")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(output_wav)
    ], capture_output=True)
    return output_wav


def transcribe_whisper(audio_path):
    """Transcrição com Faster-Whisper large-v3"""
    print("\n" + "="*60)
    print("=== WHISPER LARGE-V3 ===")
    print("="*60)

    try:
        from faster_whisper import WhisperModel

        start = time.time()
        model = WhisperModel("large-v3", device="cuda", compute_type="float16")

        segments, info = model.transcribe(
            str(audio_path),
            language=None,  # Auto-detect
            beam_size=5,
            vad_filter=True
        )

        results = []
        for seg in segments:
            results.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip()
            })

        elapsed = time.time() - start

        print(f"[INFO] Idioma detectado: {info.language}")
        print(f"[INFO] Tempo: {elapsed:.1f}s")
        print(f"[INFO] Segmentos: {len(results)}")
        print("\n--- Primeiros 5 segmentos ---")
        for i, seg in enumerate(results[:5]):
            print(f"{i+1}. [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}")

        return results, elapsed, info.language

    except Exception as e:
        print(f"[ERRO] Whisper falhou: {e}")
        return None, 0, None


def transcribe_parakeet(audio_path):
    """Transcrição com NVIDIA Parakeet"""
    print("\n" + "="*60)
    print("=== NVIDIA PARAKEET ===")
    print("="*60)

    try:
        import nemo.collections.asr as nemo_asr

        start = time.time()

        # Modelo Parakeet - escolher um:
        # - nvidia/parakeet-ctc-1.1b (mais rápido)
        # - nvidia/parakeet-rnnt-1.1b (mais preciso)
        # - nvidia/parakeet-tdt-1.1b (melhor pontuação)
        model_name = "nvidia/parakeet-tdt-1.1b"

        print(f"[INFO] Carregando modelo: {model_name}")
        model = nemo_asr.models.ASRModel.from_pretrained(model_name)
        model = model.cuda()

        # Transcrever
        output = model.transcribe([str(audio_path)], timestamps=True)

        elapsed = time.time() - start

        # Processar resultados
        results = []
        hyp = output[0][0] if isinstance(output[0], list) else output[0]

        # Debug: ver estrutura completa
        print(f"[DEBUG] Tipo: {type(hyp)}")
        if hasattr(hyp, 'timestamp') and hyp.timestamp:
            print(f"[DEBUG] timestamp keys: {hyp.timestamp.keys()}")
            for k, v in hyp.timestamp.items():
                sample = v[:2] if isinstance(v, list) and len(v) > 0 else v
                print(f"[DEBUG] timestamp[{k}]: {sample}")

        # Usar timestamps do Parakeet
        if hasattr(hyp, 'timestamp') and hyp.timestamp:
            ts = hyp.timestamp
            # Formato com 'word' - agrupa palavras em segmentos por pausas
            if 'word' in ts:
                words = ts['word']
                # Agrupar palavras em segmentos (pausas > 0.5s)
                current_seg = {"start": 0, "end": 0, "words": []}
                for w in words:
                    start = w.get('start', 0)  # tempo em segundos
                    end = w.get('end', 0)
                    word = w.get('word', '')

                    if not current_seg["words"]:
                        current_seg["start"] = start
                        current_seg["end"] = end
                        current_seg["words"].append(word)
                    elif start - current_seg["end"] > 0.3 or len(current_seg["words"]) > 15:  # Pausa > 0.3s ou > 15 palavras
                        results.append({
                            "start": current_seg["start"],
                            "end": current_seg["end"],
                            "text": " ".join(current_seg["words"])
                        })
                        current_seg = {"start": start, "end": end, "words": [word]}
                    else:
                        current_seg["end"] = end
                        current_seg["words"].append(word)

                # Último segmento
                if current_seg["words"]:
                    results.append({
                        "start": current_seg["start"],
                        "end": current_seg["end"],
                        "text": " ".join(current_seg["words"])
                    })

            # Formato com 'segment'
            elif 'segment' in ts:
                for seg in ts['segment']:
                    results.append({
                        "start": seg.get('start', 0),
                        "end": seg.get('end', 0),
                        "text": seg.get('segment', '')
                    })

        # Fallback: texto completo
        if not results:
            text = hyp.text if hasattr(hyp, 'text') else str(hyp)
            results.append({
                "start": 0,
                "end": 0,
                "text": text
            })

        print(f"[INFO] Tempo: {elapsed:.1f}s")
        print(f"[INFO] Segmentos: {len(results)}")
        print("\n--- Primeiros 5 segmentos ---")
        for i, seg in enumerate(results[:5]):
            print(f"{i+1}. [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}")

        return results, elapsed

    except ImportError:
        print("[ERRO] NeMo não instalado. Instale com:")
        print("  pip install nemo_toolkit[asr]")
        return None, 0
    except Exception as e:
        print(f"[ERRO] Parakeet falhou: {e}")
        import traceback
        traceback.print_exc()
        return None, 0


def compare_results(whisper_results, parakeet_results, whisper_time, parakeet_time):
    """Compara resultados"""
    print("\n" + "="*60)
    print("=== COMPARAÇÃO ===")
    print("="*60)

    if whisper_results and parakeet_results:
        print(f"\n{'Métrica':<25} {'Whisper':<15} {'Parakeet':<15}")
        print("-" * 55)
        print(f"{'Tempo (s)':<25} {whisper_time:<15.1f} {parakeet_time:<15.1f}")
        print(f"{'Segmentos':<25} {len(whisper_results):<15} {len(parakeet_results):<15}")

        whisper_chars = sum(len(s['text']) for s in whisper_results)
        parakeet_chars = sum(len(s['text']) for s in parakeet_results)
        print(f"{'Caracteres totais':<25} {whisper_chars:<15} {parakeet_chars:<15}")

        speedup = whisper_time / parakeet_time if parakeet_time > 0 else 0
        print(f"\n[INFO] Parakeet é {speedup:.1f}x mais rápido que Whisper")

        # Salvar resultados para comparação manual
        print("\n--- Comparação lado a lado (primeiros 5) ---")
        max_segs = min(5, len(whisper_results), len(parakeet_results))
        for i in range(max_segs):
            print(f"\nSegmento {i+1}:")
            print(f"  Whisper:  {whisper_results[i]['text'][:80]}...")
            print(f"  Parakeet: {parakeet_results[i]['text'][:80]}...")


def main():
    parser = argparse.ArgumentParser(description="Teste comparativo Whisper vs Parakeet")
    parser.add_argument("--audio", help="Arquivo de áudio WAV")
    parser.add_argument("--video", help="Arquivo de vídeo (extrai áudio)")
    parser.add_argument("--only-parakeet", action="store_true", help="Testar só Parakeet")
    parser.add_argument("--only-whisper", action="store_true", help="Testar só Whisper")

    args = parser.parse_args()

    if not args.audio and not args.video:
        print("Uso: python test_parakeet.py --audio arquivo.wav")
        print("  ou: python test_parakeet.py --video arquivo.mp4")
        return

    # Preparar áudio
    if args.video:
        audio_path = Path("/tmp/test_parakeet_audio.wav")
        extract_audio(args.video, audio_path)
    else:
        audio_path = Path(args.audio)

    if not audio_path.exists():
        print(f"[ERRO] Arquivo não encontrado: {audio_path}")
        return

    print(f"\n[INFO] Áudio: {audio_path}")

    whisper_results, whisper_time, _ = None, 0, None
    parakeet_results, parakeet_time = None, 0

    # Testar Whisper
    if not args.only_parakeet:
        whisper_results, whisper_time, _ = transcribe_whisper(audio_path)

    # Testar Parakeet
    if not args.only_whisper:
        parakeet_results, parakeet_time = transcribe_parakeet(audio_path)

    # Comparar
    if whisper_results and parakeet_results:
        compare_results(whisper_results, parakeet_results, whisper_time, parakeet_time)

    print("\n[OK] Teste concluído!")


if __name__ == "__main__":
    main()
