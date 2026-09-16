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
    parser.add_argument("--max-chunk-seconds", type=float, default=1800,
                        help="Duracao maxima de cada chunk em segundos (0 = sem limite). Default: 1800 (30 min)")
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

    # Obter duracao do audio para correcao de timestamps
    audio_duration_s = _get_duration(audio_path, subprocess)

    try:
        max_chunk = args.max_chunk_seconds
        if max_chunk > 0 and audio_duration_s > max_chunk:
            segments = _transcribe_chunked(
                model, audio_path, audio_duration_s, max_chunk,
                args.segment_pause, args.segment_max_words, subprocess, tempfile, os
            )
        else:
            segments = _transcribe_single(
                model, audio_path, audio_duration_s,
                args.segment_pause, args.segment_max_words
            )
    finally:
        if tmp:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

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


def _get_duration(audio_path, subprocess_mod):
    """Retorna duracao do audio em segundos via ffprobe."""
    try:
        _probe = subprocess_mod.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", audio_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(_probe.stdout.strip())
    except Exception:
        return 0.0


def _transcribe_single(model, audio_path, audio_duration_s, pause, max_words):
    """Transcreve arquivo completo em uma unica chamada. Aplica correcao de timestamps."""
    t1 = time.time()
    output = model.transcribe([audio_path], timestamps=True)
    print(f"[parakeet_worker] transcricao em {time.time()-t1:.1f}s", flush=True)

    segments = _build_segments(output, pause, max_words)

    # Corrigir timestamps se estiverem em frame indices (nao em segundos).
    # Parakeet TDT 1.1b usa stride de 80ms (10ms hop × 8x subsampling).
    # Detecta automaticamente pelo ratio entre ultimo timestamp e duracao real.
    if segments and audio_duration_s > 0:
        last_ts = segments[-1]["end"]
        if last_ts > audio_duration_s * 2:
            scale = audio_duration_s / last_ts
            print(f"[parakeet_worker] corrigindo timestamps: scale={scale:.4f} (ratio={last_ts/audio_duration_s:.1f}x)", flush=True)
            for seg in segments:
                seg["start"] = round(seg["start"] * scale, 3)
                seg["end"] = round(seg["end"] * scale, 3)

    return segments


def _transcribe_chunked(model, audio_path, total_duration, max_chunk,
                         pause, max_words, subprocess_mod, tempfile_mod, os_mod):
    """
    Divide o audio em chunks de no maximo max_chunk segundos com overlap de 5s,
    transcreve cada chunk separadamente, ajusta timestamps e concatena os segmentos.
    """
    OVERLAP = 5.0  # segundos de overlap entre chunks para evitar corte de palavras

    # Calcular chunks: cada um comeca em start, dura ate min(max_chunk, fim)
    chunks = []
    start = 0.0
    while start < total_duration:
        end = min(start + max_chunk, total_duration)
        chunks.append((start, end))
        if end >= total_duration:
            break
        # Proximo chunk comeca max_chunk - OVERLAP atras do fim deste
        start = end - OVERLAP

    n = len(chunks)
    print(f"[parakeet_worker] audio longo ({total_duration:.0f}s): dividindo em {n} chunk(s) de ate {max_chunk:.0f}s (overlap={OVERLAP}s)", flush=True)

    all_segments = []
    chunk_files = []

    try:
        for idx, (chunk_start, chunk_end) in enumerate(chunks):
            chunk_duration = chunk_end - chunk_start
            print(f"[parakeet_worker] chunk {idx+1}/{n}: {chunk_start:.1f}s -> {chunk_end:.1f}s ({chunk_duration:.1f}s)", flush=True)

            # Extrair chunk com ffmpeg
            tmp_chunk = tempfile_mod.NamedTemporaryFile(
                suffix=f"_chunk{idx}.wav", delete=False
            )
            tmp_chunk.close()
            chunk_files.append(tmp_chunk.name)

            subprocess_mod.run(
                ["ffmpeg", "-y", "-i", audio_path,
                 "-ss", str(chunk_start), "-t", str(chunk_duration),
                 "-ac", "1", "-ar", "16000", tmp_chunk.name],
                capture_output=True, check=True
            )

            # Duracao real do chunk extraido (pode diferir levemente)
            chunk_duration_real = _get_duration(tmp_chunk.name, subprocess_mod)
            if chunk_duration_real <= 0:
                chunk_duration_real = chunk_duration

            # Transcrever chunk
            t1 = time.time()
            output = model.transcribe([tmp_chunk.name], timestamps=True)
            print(f"[parakeet_worker] chunk {idx+1}/{n} transcrito em {time.time()-t1:.1f}s", flush=True)

            # Construir segmentos para este chunk
            chunk_segments = _build_segments(output, pause, max_words)

            # Corrigir timestamps do chunk (pode estar em frame indices)
            if chunk_segments and chunk_duration_real > 0:
                last_ts = chunk_segments[-1]["end"]
                if last_ts > chunk_duration_real * 2:
                    scale = chunk_duration_real / last_ts
                    print(f"[parakeet_worker] chunk {idx+1}: corrigindo timestamps scale={scale:.4f}", flush=True)
                    for seg in chunk_segments:
                        seg["start"] = round(seg["start"] * scale, 3)
                        seg["end"] = round(seg["end"] * scale, 3)

            # Determinar regiao valida do chunk (excluir overlap com chunk anterior)
            # O primeiro chunk nao tem overlap de entrada.
            # Chunks subsequentes: os primeiros OVERLAP segundos sao overlap do chunk anterior —
            # descartar segmentos que terminam antes de OVERLAP (ja foram capturados pelo chunk anterior).
            valid_from = OVERLAP if idx > 0 else 0.0
            # O ultimo chunk vai ate o fim — sem overlap de saida.
            # Chunks intermediarios: descartar segmentos que comecam apos (chunk_duration - OVERLAP)
            # pois serao recapturados no proximo chunk com mais contexto.
            valid_to = chunk_duration_real - OVERLAP if idx < n - 1 else chunk_duration_real

            # Ajustar offset global e filtrar pela janela valida
            for seg in chunk_segments:
                seg_start_local = seg["start"]
                seg_end_local = seg["end"]

                # Descartar segmentos inteiramente fora da janela valida
                if seg_end_local <= valid_from:
                    continue
                if seg_start_local >= valid_to and idx < n - 1:
                    continue

                # Ajustar para tempo global
                seg["start"] = round(seg_start_local + chunk_start, 3)
                seg["end"] = round(seg_end_local + chunk_start, 3)
                all_segments.append(seg)

    finally:
        for f in chunk_files:
            try:
                os_mod.unlink(f)
            except Exception:
                pass

    # Ordenar por start (pode haver pequenas sobreposicoes nas fronteiras)
    all_segments.sort(key=lambda s: s["start"])

    # Mesclar segmentos adjacentes na fronteira dos chunks que ficaram muito proximos
    # (gap < pause threshold) — evita segmentos quebrados na juncao
    merged = _merge_adjacent_segments(all_segments, gap_threshold=pause)

    return merged


def _merge_adjacent_segments(segments, gap_threshold=0.3):
    """
    Mescla segmentos consecutivos cujo gap seja menor que gap_threshold.
    Tambem remove duplicatas exatas que possam surgir nas fronteiras de chunk.
    """
    if not segments:
        return segments

    result = [dict(segments[0])]
    for seg in segments[1:]:
        prev = result[-1]
        gap = seg["start"] - prev["end"]

        # Remover duplicata exata ou sobreposicao total
        if seg["start"] >= prev["start"] and seg["end"] <= prev["end"]:
            continue  # segmento inteiramente contido no anterior

        if gap < gap_threshold:
            # Mesclar com o segmento anterior
            prev["end"] = seg["end"]
            prev["text"] = prev["text"].rstrip() + " " + seg["text"].lstrip()
        else:
            result.append(dict(seg))

    return result


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
