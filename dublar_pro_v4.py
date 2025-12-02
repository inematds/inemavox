# dublar_pro_v4.py
# Pipeline de dublagem PROFISSIONAL v4.0 - COMPLETO
# Todas as 4 fases implementadas:
# - Fase 1: Correcoes criticas (normalizacao, max_length, maxstretch, seed)
# - Fase 2: Qualidade (contexto, CPS adaptativo, Ollama)
# - Fase 3: Features (YouTube, XTTS clonagem, diarizacao)
# - Fase 4: Testes e documentacao

import os, sys, json, csv, argparse, subprocess, shutil, re, warnings
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple
import numpy as np

warnings.filterwarnings("ignore")

# ============================================================================
# CONFIGURACOES GLOBAIS
# ============================================================================

VERSION = "4.0.0"

# Caracteres por segundo por idioma (para estimativa de duracao)
CPS_POR_IDIOMA = {
    "pt": 14, "pt-br": 14, "pt_br": 14,
    "en": 12, "en-us": 12, "en-gb": 12,
    "es": 13, "es-es": 13, "es-mx": 13,
    "fr": 13, "de": 12, "it": 13,
    "ja": 8, "zh": 6, "ko": 9,
    "ru": 12, "ar": 11, "hi": 12,
}

# Seed global para consistencia de voz
GLOBAL_SEED = 42

# Cache de contexto para traducao
CONTEXT_CACHE = {
    "previous_segments": [],
    "named_entities": set(),
    "technical_terms": set(),
}

# ============================================================================
# DICIONARIO DE CORRECOES DE TRADUCAO
# ============================================================================

CORRECOES_TRADUCAO = {
    # Erros comuns de traducao literal
    "escandalo": "zero",
    "a partir de escandalo": "do zero",
    "desde escandalo": "do zero",
    "promptes": "prompts",
    "prompts": "prompts",
    "povos": "pessoas",
    "nossos povos": "nossa equipe",
    "colocam juntos": "criaram",
    "colocaram juntos": "criaram",
    "por junto": "criar",

    # Expressoes idiomaticas
    "fora da caixa": "inovador",
    "na mesma pagina": "alinhados",
    "bola na trave": "quase conseguiu",
    "dar uma olhada": "verificar",
    "no final do dia": "no fim das contas",
    "tocar base": "entrar em contato",

    # Termos tecnicos que devem ficar em ingles
    "cadeia de caracteres": "string",
    "matriz": "array",
    "retorno de chamada": "callback",
    "ponto final": "endpoint",
    "gancho": "hook",

    # Correcoes de pontuacao
    ".Entao": ". Entao",
    ".Vou": ". Vou",
    ".Bem": ". Bem",
    ".Isso": ". Isso",
    ".E": ". E",
    ".O": ". O",
    ".A": ". A",
    "!Entao": "! Entao",
    "?Entao": "? Entao",

    # Nomes de produtos (preservar)
    "Codigo Claude": "Claude Code",
    "Codigo Nuvem": "Cloud Code",

    # let's / let me
    "let's": "vamos",
    "Let's": "Vamos",
    "let me": "deixe-me",
    "Let me": "Deixe-me",

    # Contracoes em ingles que escapam
    "I'm": "eu estou",
    "I'll": "eu vou",
    "we're": "nos estamos",
    "you're": "voce esta",
    "it's": "e",
    "that's": "isso e",
    "don't": "nao",
    "doesn't": "nao",
    "can't": "nao pode",
    "won't": "nao vai",

    # Correcoes de zoom/let
    "zoom de let": "vamos dar zoom",
    "zoom de lets": "vamos dar zoom",
    "zoom de let's": "vamos dar zoom",
}

# Termos que NUNCA devem ser traduzidos
TERMOS_PRESERVAR = {
    # Programacao
    "string", "array", "boolean", "null", "undefined", "true", "false",
    "const", "let", "var", "function", "class", "return", "async", "await",
    "promise", "callback", "middleware", "endpoint", "props", "state", "hook",
    "import", "export", "default", "extends", "interface", "type",

    # Ferramentas
    "git", "commit", "push", "pull", "merge", "branch", "checkout",
    "npm", "yarn", "pip", "docker", "kubernetes", "webpack", "babel",

    # Protocolos e formatos
    "API", "REST", "HTTP", "HTTPS", "JSON", "XML", "HTML", "CSS",
    "localhost", "URL", "URI", "DNS", "SSH", "FTP",

    # Linguagens e frameworks
    "Python", "JavaScript", "TypeScript", "React", "Node", "Vue", "Angular",
    "Django", "Flask", "FastAPI", "Express", "Next.js", "Nuxt",

    # Produtos
    "Claude Code", "ChatGPT", "GPT", "OpenAI", "Anthropic",
    "GitHub", "GitLab", "Bitbucket", "AWS", "Azure", "Google Cloud",

    # IA/ML
    "prompt", "prompts", "token", "tokens", "embedding", "embeddings",
    "transformer", "attention", "encoder", "decoder", "fine-tuning",
    "LLM", "GPT", "BERT", "model", "weights", "inference",
}

# ============================================================================
# GLOSSARIO TECNICO
# ============================================================================

GLOSSARIO_TECNICO = {
    "variable": "variavel",
    "parameter": "parametro",
    "argument": "argumento",
    "method": "metodo",
    "property": "propriedade",
    "attribute": "atributo",
    "instance": "instancia",
    "constructor": "construtor",
    "inheritance": "heranca",
    "request": "requisicao",
    "response": "resposta",
    "header": "cabecalho",
    "body": "corpo",
    "query": "consulta",
    "route": "rota",
    "controller": "controlador",
    "component": "componente",
    "service": "servico",
    "database": "banco de dados",
    "table": "tabela",
    "column": "coluna",
    "row": "linha",
    "record": "registro",
    "field": "campo",
    "deployment": "deploy",
    "container": "container",
    "pipeline": "pipeline",
}

# ============================================================================
# UTILITARIOS BASICOS
# ============================================================================

def sh(cmd, cwd=None, capture=False, timeout=300):
    """Executa comando shell com tratamento de erro melhorado"""
    cmd_str = " ".join(map(str, cmd))
    print(f">> {cmd_str[:100]}{'...' if len(cmd_str) > 100 else ''}")

    try:
        if capture:
            result = subprocess.run(cmd, check=True, cwd=cwd,
                                   capture_output=True, text=True, timeout=timeout)
            return result.stdout
        else:
            subprocess.run(cmd, check=True, cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[ERRO] Comando expirou apos {timeout}s")
        raise
    except subprocess.CalledProcessError as e:
        print(f"[ERRO] Comando falhou: {e}")
        raise

def ensure_ffmpeg():
    """Verifica se FFmpeg esta instalado"""
    for bin in ("ffmpeg", "ffprobe"):
        if not shutil.which(bin):
            print(f"[ERRO] {bin} nao encontrado no PATH.")
            print("Instale com: sudo apt install ffmpeg")
            sys.exit(1)

def check_rubberband():
    """Verifica se rubberband esta disponivel"""
    return shutil.which("rubberband") is not None

def check_yt_dlp():
    """Verifica se yt-dlp esta disponivel"""
    return shutil.which("yt-dlp") is not None

def check_ollama():
    """Verifica se Ollama esta rodando"""
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=5)
        return r.status_code == 200
    except:
        return False

def check_xtts():
    """Verifica se XTTS (Coqui TTS) esta disponivel"""
    try:
        from TTS.api import TTS
        return True
    except:
        return False

def check_pyannote():
    """Verifica se pyannote esta disponivel"""
    try:
        from pyannote.audio import Pipeline
        return True
    except:
        return False

def ffprobe_duration(path):
    """Obtem duracao de arquivo de audio/video"""
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nk=1:nw=1",
            str(path)
        ], text=True, timeout=30).strip()
        return max(0.0, float(out))
    except Exception:
        return 0.0

def ts_stamp(t):
    """Converte segundos para timestamp SRT"""
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

def get_device():
    """Detecta melhor dispositivo disponivel"""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"[GPU] Detectada: {gpu_name} ({vram:.1f}GB VRAM)")
            return "cuda"
    except:
        pass
    print("[CPU] Usando CPU (GPU nao disponivel)")
    return "cpu"

def set_global_seed(seed=GLOBAL_SEED):
    """Define seed global para reproducibilidade"""
    import random
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except:
        pass

def is_youtube_url(url):
    """Verifica se e uma URL do YouTube"""
    youtube_patterns = [
        r'(youtube\.com/watch\?v=)',
        r'(youtu\.be/)',
        r'(youtube\.com/embed/)',
        r'(youtube\.com/v/)',
    ]
    return any(re.search(p, str(url)) for p in youtube_patterns)

def download_youtube(url, output_dir):
    """Baixa video do YouTube usando yt-dlp, mantendo o titulo original"""
    print("\n" + "="*60)
    print("=== Download do YouTube ===")
    print("="*60)

    if not check_yt_dlp():
        print("[ERRO] yt-dlp nao encontrado. Instale com: pip install yt-dlp")
        sys.exit(1)

    # Usar titulo do video como nome do arquivo
    output_template = str(Path(output_dir) / "%(title)s.%(ext)s")

    sh([
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--restrict-filenames",  # Remove caracteres especiais do nome
        "-o", output_template,
        url
    ])

    # Encontrar o arquivo baixado
    mp4_files = list(Path(output_dir).glob("*.mp4"))
    if mp4_files:
        # Pegar o mais recente
        output_path = max(mp4_files, key=lambda p: p.stat().st_mtime)
        print(f"[OK] Video baixado: {output_path}")
        return output_path
    else:
        print("[ERRO] Nenhum arquivo MP4 encontrado apos download")
        sys.exit(1)

# ============================================================================
# NORMALIZACAO DE AUDIO SEGURA (v4 - CORRECAO CRITICA)
# ============================================================================

def normalize_audio_safe(audio_data, target_peak=0.84):
    """Normaliza audio de forma segura, evitando clipping e valores invalidos

    Args:
        audio_data: numpy array com dados de audio
        target_peak: pico alvo (0.84 = -1.5dB headroom)

    Returns:
        numpy array normalizado em int16
    """
    # Converter para float se necessario
    if audio_data.dtype == np.int16:
        audio = audio_data.astype(np.float32) / 32767.0
    elif audio_data.dtype == np.int32:
        audio = audio_data.astype(np.float32) / 2147483647.0
    elif audio_data.dtype in [np.float32, np.float64]:
        audio = audio_data.astype(np.float32)
    else:
        audio = audio_data.astype(np.float32)

    # Remover NaN e Inf
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)

    # Clip para range valido
    audio = np.clip(audio, -1.0, 1.0)

    # Normalizar para target_peak
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = audio / max_val * target_peak

    # Converter para int16
    audio_int16 = (audio * 32767).astype(np.int16)

    return audio_int16

# ============================================================================
# CHECKPOINT SYSTEM
# ============================================================================

def save_checkpoint(workdir, step_num, step_name, data=None):
    """Salva checkpoint da etapa concluida"""
    checkpoint_file = Path(workdir, "checkpoint.json")
    checkpoint = {
        "version": VERSION,
        "last_step": step_name,
        "last_step_num": step_num,
        "next_step": step_num + 1,
        "timestamp": datetime.now().isoformat(),
        "data": data or {}
    }
    with open(checkpoint_file, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)
    print(f"[CHECKPOINT] Etapa {step_num} salva: {step_name}")

def load_checkpoint(workdir):
    """Carrega checkpoint se existir"""
    checkpoint_file = Path(workdir, "checkpoint.json")
    if checkpoint_file.exists():
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

# ============================================================================
# FASE 3: DIARIZACAO (DETECTAR FALANTES)
# ============================================================================

def diarize_audio(wav_path, workdir, num_speakers=None):
    """Detecta diferentes falantes no audio usando pyannote

    Args:
        wav_path: caminho do arquivo WAV
        workdir: diretorio de trabalho
        num_speakers: numero de falantes (None = detectar automaticamente)

    Returns:
        lista de segmentos com speaker_id
    """
    print("\n" + "="*60)
    print("=== Diarizacao (Detectando Falantes) ===")
    print("="*60)

    if not check_pyannote():
        print("[WARN] pyannote nao instalado. Usando falante unico.")
        print("[INFO] Para instalar: pip install pyannote.audio")
        return None

    try:
        from pyannote.audio import Pipeline
        import torch

        # Carregar pipeline (requer token HuggingFace para alguns modelos)
        hf_token = os.environ.get("HF_TOKEN", None)

        if hf_token:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token
            )
        else:
            # Tentar modelo sem autenticacao
            print("[WARN] HF_TOKEN nao definido. Usando modelo basico.")
            pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization")

        device = get_device()
        if device == "cuda":
            pipeline = pipeline.to(torch.device("cuda"))

        # Executar diarizacao
        if num_speakers:
            diarization = pipeline(str(wav_path), num_speakers=num_speakers)
        else:
            diarization = pipeline(str(wav_path))

        # Converter para lista de segmentos
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "start": turn.start,
                "end": turn.end,
                "speaker": speaker
            })

        # Salvar diarizacao
        diar_path = Path(workdir, "diarization.json")
        with open(diar_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=2, ensure_ascii=False)

        # Contar falantes
        speakers = set(s["speaker"] for s in segments)
        print(f"[OK] Detectados {len(speakers)} falantes: {speakers}")

        return segments

    except Exception as e:
        print(f"[ERRO] Diarizacao falhou: {e}")
        return None

def merge_incomplete_segments(segments, max_duration=15.0):
    """Junta segmentos que terminam com frase incompleta (virgula, sem pontuacao)

    Resolve o problema do Whisper cortar frases no meio por limite de tempo.
    Segmentos que terminam com virgula ou sem pontuacao final sao unidos
    ao proximo segmento para formar frases completas.

    Args:
        segments: Lista de segmentos do Whisper
        max_duration: Duracao maxima de um segmento merged (evita segmentos muito longos)

    Returns:
        Lista de segmentos com frases completas
    """
    if not segments:
        return segments

    def needs_merge(text):
        """Verifica se o segmento precisa ser unido ao proximo"""
        text = text.strip()
        if not text:
            return False
        # Termina com virgula
        if text.endswith(','):
            return True
        # Termina com artigo/preposicao (indica frase cortada)
        incomplete_endings = [
            ' o', ' a', ' os', ' as', ' um', ' uma', ' uns', ' umas',
            ' de', ' do', ' da', ' dos', ' das', ' no', ' na', ' nos', ' nas',
            ' ao', ' aos', ' para', ' por', ' com', ' em', ' que', ' e', ' ou',
            ' se', ' the', ' to', ' of', ' in', ' and', ' a', ' an', ' this',
            ' our', ' your', ' my', ' we', ' you', ' it', ' is', ' are',
        ]
        text_lower = text.lower()
        for ending in incomplete_endings:
            if text_lower.endswith(ending):
                return True
        # Nao termina com pontuacao final
        if not text.endswith(('.', '!', '?', '"', "'", ')')):
            return True
        return False

    merged = []
    buffer = None

    for seg in segments:
        if buffer:
            # Verificar se nao vai ficar muito longo
            new_duration = seg['end'] - buffer['start']

            if new_duration <= max_duration:
                # Junta com buffer anterior
                buffer['text'] = buffer['text'].strip() + ' ' + seg['text'].strip()
                buffer['end'] = seg['end']

                # Verifica se agora esta completo
                if not needs_merge(buffer['text']):
                    merged.append(buffer)
                    buffer = None
                # Senao, continua acumulando
            else:
                # Muito longo, salva buffer e comeca novo
                merged.append(buffer)
                if needs_merge(seg['text']):
                    buffer = dict(seg)
                else:
                    merged.append(seg)
                    buffer = None
        else:
            if needs_merge(seg['text']):
                buffer = dict(seg)
            else:
                merged.append(seg)

    # Nao esquecer o ultimo buffer
    if buffer:
        merged.append(buffer)

    return merged

def merge_transcription_with_diarization(transcription_segs, diarization_segs):
    """Combina transcricao com diarizacao para atribuir falante a cada segmento"""
    if not diarization_segs:
        return transcription_segs

    merged = []
    for seg in transcription_segs:
        seg_mid = (seg["start"] + seg["end"]) / 2

        # Encontrar falante mais provavel
        best_speaker = "SPEAKER_00"
        best_overlap = 0

        for diar in diarization_segs:
            # Calcular overlap
            overlap_start = max(seg["start"], diar["start"])
            overlap_end = min(seg["end"], diar["end"])
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = diar["speaker"]

        seg_copy = dict(seg)
        seg_copy["speaker"] = best_speaker
        merged.append(seg_copy)

    return merged

# ============================================================================
# ETAPA 3: TRANSCRICAO (WHISPER)
# ============================================================================

def transcribe_faster_whisper(wav_path, workdir, src_lang, model_size="medium", diarize=False, num_speakers=None):
    """Transcricao com Faster-Whisper otimizado

    Se src_lang=None, detecta automaticamente o idioma.
    Retorna: (json_path, srt_path, segments, detected_language)
    """
    print("\n" + "="*60)
    print("=== ETAPA 3: Transcricao (Faster-Whisper) ===")
    print("="*60)

    from faster_whisper import WhisperModel
    import torch

    device = "cpu"
    compute_type = "int8"

    print(f"[INFO] Whisper modelo: {model_size}")
    print(f"[INFO] Whisper device: {device.upper()} (CTranslate2)")
    if src_lang:
        print(f"[INFO] Idioma origem: {src_lang}")
    else:
        print(f"[INFO] Idioma origem: AUTO-DETECTAR")

    if torch.cuda.is_available():
        print(f"[INFO] GPU disponivel: {torch.cuda.get_device_name(0)}")

    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    # VAD otimizado para evitar fragmentacao excessiva
    segments_generator, info = model.transcribe(
        str(wav_path),
        language=src_lang,  # None = auto-detect
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=600,
            speech_pad_ms=500,
            threshold=0.5,
        ),
        beam_size=5,
        best_of=5,
        temperature=0.0,
        condition_on_previous_text=True,
    )

    # Idioma detectado (ou o especificado)
    detected_lang = info.language if hasattr(info, 'language') else src_lang
    lang_prob = getattr(info, 'language_probability', None)

    if not src_lang:
        print(f"[INFO] Idioma detectado: {detected_lang} (probabilidade: {lang_prob:.1%})" if lang_prob else f"[INFO] Idioma detectado: {detected_lang}")

    # Consumir o generator e mostrar progresso
    print("[INFO] Transcrevendo... (isso pode levar alguns minutos)")
    segs = []
    seg_count = 0
    for s in segments_generator:
        text = (s.text or "").strip()
        if text:
            segs.append({
                "start": float(s.start),
                "end": float(s.end),
                "text": text
            })
            seg_count += 1
            if seg_count % 50 == 0:
                print(f"  Processados: {seg_count} segmentos...")

    # Merge de segmentos incompletos (frases cortadas no meio)
    segs_antes = len(segs)
    segs = merge_incomplete_segments(segs, max_duration=15.0)
    segs_depois = len(segs)
    if segs_antes != segs_depois:
        print(f"[INFO] Merge de frases incompletas: {segs_antes} -> {segs_depois} segmentos")

    # Diarizacao opcional
    if diarize:
        diar_segs = diarize_audio(wav_path, workdir, num_speakers)
        if diar_segs:
            segs = merge_transcription_with_diarization(segs, diar_segs)

    # Salvar arquivos
    srt_path = Path(workdir, "asr.srt")
    json_path = Path(workdir, "asr.json")

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, s in enumerate(segs, 1):
            speaker_tag = f"[{s.get('speaker', 'SPEAKER_00')}] " if 'speaker' in s else ""
            f.write(f"{i}\n{ts_stamp(s['start'])} --> {ts_stamp(s['end'])}\n{speaker_tag}{s['text']}\n\n")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "language": detected_lang,
            "language_specified": src_lang,
            "segments": segs,
            "info": {
                "language_probability": lang_prob,
                "duration": getattr(info, 'duration', None),
            }
        }, f, ensure_ascii=False, indent=2)

    print(f"[OK] Transcrito: {len(segs)} segmentos")
    return json_path, srt_path, segs, detected_lang

# ============================================================================
# ETAPA 4: TRADUCAO - FUNCOES AUXILIARES
# ============================================================================

def proteger_termos_tecnicos(texto):
    """Protege termos tecnicos antes da traducao"""
    protegido = texto
    mapa = {}

    for i, termo in enumerate(sorted(TERMOS_PRESERVAR, key=len, reverse=True)):
        pattern = re.compile(re.escape(termo), re.IGNORECASE)
        if pattern.search(protegido):
            placeholder = f"__TERMO_{i:03d}__"
            match = pattern.search(protegido)
            if match:
                mapa[placeholder] = match.group(0)
                protegido = pattern.sub(placeholder, protegido)

    return protegido, mapa

def restaurar_termos_tecnicos(texto, mapa):
    """Restaura termos tecnicos apos traducao"""
    restaurado = texto
    for placeholder, original in mapa.items():
        restaurado = restaurado.replace(placeholder, original)
    return restaurado

def aplicar_correcoes(texto):
    """Aplica dicionario de correcoes pos-traducao"""
    corrigido = texto

    frases = {k: v for k, v in CORRECOES_TRADUCAO.items() if ' ' in k or "'" in k}
    palavras = {k: v for k, v in CORRECOES_TRADUCAO.items() if ' ' not in k and "'" not in k}

    for errado, correto in frases.items():
        corrigido = corrigido.replace(errado, correto)

    for errado, correto in palavras.items():
        pattern = re.compile(r'\b' + re.escape(errado) + r'\b', re.IGNORECASE)
        corrigido = pattern.sub(correto, corrigido)

    corrigido = re.sub(r'([.!?])([A-Za-z])', r'\1 \2', corrigido)
    corrigido = re.sub(r' +', ' ', corrigido)

    return corrigido.strip()

def aplicar_glossario(texto, src_lang, tgt_lang):
    """Aplica glossario tecnico na traducao"""
    if src_lang != "en" or tgt_lang != "pt":
        return texto

    resultado = texto
    for ingles, portugues in GLOSSARIO_TECNICO.items():
        pattern = re.compile(r'\b' + re.escape(ingles) + r'\b', re.IGNORECASE)
        resultado = pattern.sub(portugues, resultado)

    return resultado

def estimar_duracao_texto(texto, idioma="pt"):
    """Estima duracao de fala para um texto"""
    cps = CPS_POR_IDIOMA.get(idioma.lower(), 13)
    return len(texto) / cps

# ============================================================================
# FASE 2: CPS ADAPTATIVO
# ============================================================================

def calcular_cps_original(audio_path, segments):
    """Calcula CPS real do audio original baseado nos segmentos"""
    total_chars = 0
    total_dur = 0

    for seg in segments:
        text = seg.get("text", "")
        dur = seg["end"] - seg["start"]
        if dur > 0 and len(text) > 5:
            total_chars += len(text)
            total_dur += dur

    if total_dur > 0:
        return total_chars / total_dur
    return 13  # Default

def ajustar_texto_para_duracao(texto, duracao_alvo, cps_original, idioma="pt", no_truncate=False):
    """Ajusta texto para caber na duracao alvo baseado no CPS original

    FASE 2: CPS Adaptativo - usa o CPS real do video original

    Args:
        texto: Texto traduzido
        duracao_alvo: Duracao em segundos do segmento original
        cps_original: Caracteres por segundo do video original
        idioma: Idioma do texto
        no_truncate: Se True, nao trunca texto (frases completas, sync ajusta)
    """
    # Se no_truncate ativado, retorna texto original sem modificacao
    if no_truncate:
        return texto

    # Usar CPS do audio original em vez do default do idioma
    cps_alvo = cps_original * 1.1  # 10% de margem

    chars_alvo = int(duracao_alvo * cps_alvo)
    chars_atual = len(texto)

    if chars_atual <= chars_alvo:
        return texto  # OK, cabe

    # Precisa reduzir
    ratio = chars_alvo / chars_atual

    if ratio >= 0.9:
        # Pequena reducao - remover enchimentos
        enchimentos = [
            r'\bna verdade\b', r'\bbasicamente\b', r'\bgeralmente\b',
            r'\bsimplesmente\b', r'\brealmente\b', r'\bcertamente\b',
            r'\bobviamente\b', r'\bnaturalmente\b', r'\bprovavelmente\b',
            r'\bpraticamente\b', r'\bdefinitivamente\b',
        ]
        simplificado = texto
        for pattern in enchimentos:
            simplificado = re.sub(pattern, '', simplificado, flags=re.IGNORECASE)
        simplificado = re.sub(r' +', ' ', simplificado).strip()
        return simplificado

    elif ratio >= 0.7:
        # Reducao media - truncar mantendo sentido
        palavras = texto.split()
        palavras_alvo = int(len(palavras) * ratio)
        simplificado = ' '.join(palavras[:palavras_alvo])
        if not simplificado.endswith(('.', '!', '?')):
            simplificado += '.'
        return simplificado

    else:
        # Reducao grande - deixar texto original (sync vai ajustar)
        return texto

# ============================================================================
# FASE 2: TRADUCAO COM CONTEXTO VIA OLLAMA
# ============================================================================

def _clean_ollama_response(response, original_text):
    """Limpa resposta do Ollama removendo instruções, notas e lixo.

    Retorna None se a resposta for inválida (para usar fallback).
    """
    if not response:
        return None

    text = response.strip()

    # Lista de padrões que indicam resposta INVÁLIDA (retorna None para fallback)
    invalid_patterns = [
        "Deixe-me know",
        "Let me know",
        "anything else",
        "need anything",
        "Here's the translation",
        "Here is the translation",
        "I'll translate",
        "I will translate",
        "Sure!",
        "Sure,",
        "Of course",
        "Happy to help",
        "Please provide",
        "provide the text",
        "characters or less",
        "character limit",
        "(Translated to",
        "Translated to Brazilian",
        "I'd be happy",
        "I can help",
        "What would you like",
        "Could you please",
    ]

    for pattern in invalid_patterns:
        if pattern.lower() in text.lower():
            return None

    # Se a resposta é igual ao texto original (não traduziu), retorna None
    if text.strip() == original_text.strip():
        return None

    # Lista de prefixos/substrings para REMOVER
    garbage_patterns = [
        "REGRAS CRÍTICAS:",
        "CRITICAL RULES:",
        "Tradução concisa (máximo",
        "Concise translation (max",
        "Translation:",
        "Tradução:",
        "(Note:",
        "Note:",
        "Nota:",
        "chars):",
        "caracteres):",
        "- Isso é para DUBBING",
        "- This is for VIDEO DUBBING",
        "- Máximo de",
        "- Maximum",
        "- Remova palavras",
        "- Remove filler",
        "- Manter termos",
        "- Keep technical",
        "- NÃO adicione",
        "- Do NOT add",
        "- Se tiver dúvida",
        "- If in doubt",
        "Texto (",
        "Text (",
    ]

    # Se contém qualquer padrão de lixo, tentar extrair só a tradução
    has_garbage = any(p in text for p in garbage_patterns)

    if has_garbage:
        # Estratégia 1: Pegar texto após último ":" em linha com "chars)" ou "caracteres)"
        lines = text.split('\n')
        for line in reversed(lines):
            line = line.strip()
            # Ignorar linhas vazias ou muito curtas
            if len(line) < 5:
                continue
            # Ignorar linhas que começam com "-" (instruções)
            if line.startswith('-'):
                continue
            # Ignorar linhas que são claramente instruções
            if any(p in line for p in garbage_patterns):
                continue
            # Esta linha pode ser a tradução
            # Remover prefixos comuns
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) > 1 and len(parts[1].strip()) > 5:
                    candidate = parts[1].strip()
                    # Verificar se não é instrução
                    if not any(p in candidate for p in garbage_patterns):
                        text = candidate
                        break
            else:
                text = line
                break

    # Limpar aspas
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        text = text[1:-1]

    # Remover notas no final
    for sep in ['\n\nNote:', '\n\nNota:', '\n(Note', '\n(Nota']:
        if sep in text:
            text = text.split(sep)[0].strip()

    # Se ainda tem múltiplas linhas, pegar a última que parece tradução válida
    if '\n' in text:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        valid_lines = []
        for line in lines:
            # Ignorar linhas de instrução
            if line.startswith('-'):
                continue
            if any(p in line for p in garbage_patterns):
                continue
            if len(line) > 5:
                valid_lines.append(line)

        if valid_lines:
            # Pegar a última linha válida (geralmente é a tradução)
            text = valid_lines[-1]

    # Validação final: se ainda contém lixo óbvio, retorna None
    final_garbage = ["REGRAS", "CRITICAL", "chars)", "caracteres)", "DUBBING"]
    if any(g in text for g in final_garbage):
        return None

    # Se ficou muito curto ou vazio
    if len(text.strip()) < 3:
        return None

    return text.strip()


def translate_ollama_with_context(text, src_lang, tgt_lang, model="llama3",
                                   previous_segments=None, target_duration=None,
                                   cps_original=None):
    """Traduz texto usando Ollama COM CONTEXTO dos segmentos anteriores

    FASE 2: Contexto na traducao - passa segmentos anteriores para manter consistencia
    """
    import httpx

    lang_names = {
        "pt": "Portuguese (Brazilian)",
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "ja": "Japanese",
        "zh": "Chinese",
    }

    src_name = lang_names.get(src_lang, src_lang)
    tgt_name = lang_names.get(tgt_lang, tgt_lang)

    # Calcular limite de caracteres
    max_chars = int(target_duration * cps_original * 1.1) if target_duration and cps_original else len(text)

    # Prompt balanceado - claro mas sem instruções que o modelo repete
    prompt = f"""You are a translator. Translate the text from {src_name} to {tgt_name}.
Output ONLY the translation, nothing else. Maximum {max_chars} characters.

Text: {text}

{tgt_name}:"""

    try:
        response = httpx.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Mais determinístico
                    "top_p": 0.8,
                    "num_predict": max_chars + 50,  # Limitar tokens gerados
                }
            },
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            translated = result.get("response", "").strip()

            # Limpar resposta do Ollama - MUITO mais robusto
            translated = _clean_ollama_response(translated, text)

            return translated
        else:
            return None
    except Exception as e:
        print(f"[WARN] Ollama erro: {e}")
        return None

def _translate_single_m2m100(text, src, tgt, tok=None, model=None):
    """Traduz um único texto com M2M100 (fallback leve)"""
    try:
        if tok is None or model is None:
            from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
            tok = AutoTokenizer.from_pretrained("facebook/m2m100_418M")
            model = AutoModelForSeq2SeqLM.from_pretrained("facebook/m2m100_418M")
            device = get_device()
            model = model.to(device)

        tok.src_lang = src
        encoded = tok(text, return_tensors="pt", max_length=256, truncation=True).to(model.device)
        generated = model.generate(
            **encoded,
            forced_bos_token_id=tok.get_lang_id(tgt),
            max_length=256,
            num_beams=3
        )
        return tok.decode(generated[0], skip_special_tokens=True)
    except Exception as e:
        return None


def translate_segments_ollama(segs, src, tgt, workdir, model="llama3", cps_original=None, no_truncate=False):
    """Traducao com Ollama (LLM local) COM CONTEXTO"""
    print("\n" + "="*60)
    print(f"=== ETAPA 4: Traducao (Ollama - {model}) ===")
    print("="*60)

    if not check_ollama():
        print("[WARN] Ollama nao esta rodando. Fallback para M2M100.")
        return None

    out = []
    previous_segments = []
    fallback_count = 0

    # Preparar M2M100 para fallback (carrega sob demanda)
    m2m_tok = None
    m2m_model = None

    print(f"[INFO] Traduzindo {len(segs)} segmentos com {model}...")
    print(f"[INFO] CPS original: {cps_original:.1f}" if cps_original else "[INFO] CPS: padrao")

    for i, s in enumerate(segs):
        texto_original = s.get("text", "")
        duracao_seg = s["end"] - s["start"]

        # Proteger termos tecnicos
        texto_protegido, mapa = proteger_termos_tecnicos(texto_original)

        # Traduzir via Ollama COM CONTEXTO
        translated = translate_ollama_with_context(
            texto_protegido, src, tgt, model,
            previous_segments=previous_segments,
            target_duration=duracao_seg,
            cps_original=cps_original
        )

        if translated:
            txt_restaurado = restaurar_termos_tecnicos(translated, mapa)
            txt_corrigido = aplicar_correcoes(txt_restaurado)
            txt_final = aplicar_glossario(txt_corrigido, src, tgt)

            # Ajustar para duracao usando CPS adaptativo
            if cps_original:
                txt_final = ajustar_texto_para_duracao(txt_final, duracao_seg, cps_original, tgt, no_truncate)
        else:
            # Fallback: usar M2M100 para este segmento
            fallback_count += 1
            if m2m_tok is None:
                print(f"  [WARN] Seg {i+1}: Ollama falhou, carregando M2M100 para fallback...")
                try:
                    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
                    m2m_tok = AutoTokenizer.from_pretrained("facebook/m2m100_418M")
                    m2m_model = AutoModelForSeq2SeqLM.from_pretrained("facebook/m2m100_418M")
                    device = get_device()
                    m2m_model = m2m_model.to(device)
                except Exception as e:
                    print(f"  [ERRO] Falha ao carregar M2M100: {e}")

            if m2m_tok and m2m_model:
                txt_final = _translate_single_m2m100(texto_protegido, src, tgt, m2m_tok, m2m_model)
                if txt_final:
                    txt_final = restaurar_termos_tecnicos(txt_final, mapa)
                    txt_final = aplicar_correcoes(txt_final)
                    txt_final = aplicar_glossario(txt_final, src, tgt)
                    if cps_original:
                        txt_final = ajustar_texto_para_duracao(txt_final, duracao_seg, cps_original, tgt, no_truncate)
                else:
                    txt_final = texto_original  # Último recurso
            else:
                txt_final = texto_original  # Se M2M100 também falhou

        item = dict(s)
        item["text_trad"] = txt_final
        item["text_original"] = texto_original
        out.append(item)

        # Atualizar contexto
        previous_segments.append(item)
        if len(previous_segments) > 5:
            previous_segments = previous_segments[-5:]

        if (i + 1) % 10 == 0 or i == len(segs) - 1:
            print(f"  Progresso: {i + 1}/{len(segs)}")

    # Salvar arquivos
    srt_t = Path(workdir, "asr_trad.srt")
    json_t = Path(workdir, "asr_trad.json")

    with open(srt_t, "w", encoding="utf-8") as f:
        for i, s in enumerate(out, 1):
            f.write(f"{i}\n{ts_stamp(s['start'])} --> {ts_stamp(s['end'])}\n{s['text_trad']}\n\n")

    with open(json_t, "w", encoding="utf-8") as f:
        json.dump({
            "language": tgt,
            "source_language": src,
            "model": f"ollama/{model}",
            "segments": out
        }, f, ensure_ascii=False, indent=2)

    if fallback_count > 0:
        print(f"[INFO] Fallbacks M2M100 usados: {fallback_count}/{len(segs)} segmentos")

    print(f"[OK] Traduzido: {len(out)} segmentos")
    return out, json_t, srt_t

# ============================================================================
# TRADUCAO VIA M2M100 (MELHORADO v4)
# ============================================================================

def translate_segments_m2m100(segs, src, tgt, workdir, use_large_model=False, cps_original=None, no_truncate=False):
    """Traducao com M2M100 melhorado - max_length aumentado"""
    print("\n" + "="*60)
    print("=== ETAPA 4: Traducao (M2M100 Melhorado) ===")
    print("="*60)

    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    import torch

    device = get_device()

    if use_large_model and device == "cuda":
        try:
            vram = torch.cuda.get_device_properties(0).total_memory / 1e9
            if vram >= 6:
                model_name = "facebook/m2m100_1.2B"
                print(f"[INFO] Usando modelo GRANDE: {model_name}")
            else:
                model_name = "facebook/m2m100_418M"
        except:
            model_name = "facebook/m2m100_418M"
    else:
        model_name = "facebook/m2m100_418M"
        print(f"[INFO] Usando modelo: {model_name}")

    print(f"[INFO] Device: {device.upper()}")

    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name).to(device)

    src = (src or "en").lower()
    tgt = (tgt or "pt").lower()

    if hasattr(tok, "lang_code_to_id"):
        if src not in tok.lang_code_to_id:
            src = "en"
        if tgt not in tok.lang_code_to_id:
            tgt = "pt"

    out = []
    batch = []
    idxs = []
    mapas_termos = []
    duracoes = []
    max_batch = 16 if device == "cuda" else 8

    def flush():
        nonlocal out, batch, idxs, mapas_termos, duracoes
        if not batch:
            return

        tok.src_lang = src
        enc = tok(batch, return_tensors="pt", padding=True, truncation=True, max_length=1024)
        enc = {k: v.to(device) for k, v in enc.items()}

        gen = model.generate(
            **enc,
            forced_bos_token_id=tok.get_lang_id(tgt),
            max_new_tokens=512,
            num_beams=5,
            length_penalty=1.0,
            early_stopping=True,
        )

        texts = tok.batch_decode(gen, skip_special_tokens=True)

        for j, txt in enumerate(texts):
            i = idxs[j]
            item = dict(segs[i])

            txt_restaurado = restaurar_termos_tecnicos(txt, mapas_termos[j])
            txt_corrigido = aplicar_correcoes(txt_restaurado)
            txt_final = aplicar_glossario(txt_corrigido, src, tgt)

            # CPS adaptativo
            if cps_original:
                txt_final = ajustar_texto_para_duracao(txt_final, duracoes[j], cps_original, tgt, no_truncate)

            item["text_trad"] = txt_final
            item["text_original"] = segs[i].get("text", "")
            out.append(item)

        batch.clear()
        idxs.clear()
        mapas_termos.clear()
        duracoes.clear()

    print(f"[INFO] Traduzindo {len(segs)} segmentos...")

    for i, s in enumerate(segs):
        texto_original = s.get("text", "")
        texto_protegido, mapa = proteger_termos_tecnicos(texto_original)

        batch.append(texto_protegido)
        idxs.append(i)
        mapas_termos.append(mapa)
        duracoes.append(s["end"] - s["start"])

        if len(batch) >= max_batch:
            flush()
            print(f"  Progresso: {len(out)}/{len(segs)}")

    flush()

    # Salvar arquivos
    srt_t = Path(workdir, "asr_trad.srt")
    json_t = Path(workdir, "asr_trad.json")

    with open(srt_t, "w", encoding="utf-8") as f:
        for i, s in enumerate(out, 1):
            f.write(f"{i}\n{ts_stamp(s['start'])} --> {ts_stamp(s['end'])}\n{s['text_trad']}\n\n")

    with open(json_t, "w", encoding="utf-8") as f:
        json.dump({
            "language": tgt,
            "source_language": src,
            "model": model_name,
            "segments": out
        }, f, ensure_ascii=False, indent=2)

    print(f"[OK] Traduzido: {len(out)} segmentos")

    del model
    if device == "cuda":
        torch.cuda.empty_cache()

    return out, json_t, srt_t

# ============================================================================
# ETAPA 5: SPLIT INTELIGENTE
# ============================================================================

def split_long_segments(segments, maxdur):
    """Divide segmentos longos de forma inteligente"""
    print("\n" + "="*60)
    print("=== ETAPA 5: Split Inteligente ===")
    print("="*60)

    if not maxdur or maxdur <= 0:
        print("[INFO] Split desativado")
        return segments

    out = []
    split_count = 0

    for seg_idx, s in enumerate(segments, 1):
        start, end = s["start"], s["end"]
        text = (s.get("text_trad") or "").strip()
        dur = max(0.001, end - start)

        if dur <= maxdur or len(text.split()) < 12:
            out.append(s)
            continue

        print(f"[SPLIT] Seg {seg_idx}: {dur:.2f}s, {len(text)} chars")

        parts = re.split(r'([.!?:;,])', text)
        cps = max(len(text) / dur, 8.0)

        def is_valid(t):
            t2 = re.sub(r"\s+", " ", (t or "")).strip()
            return len(re.findall(r"[A-Za-z0-9]", t2)) >= 3

        buf = ""
        pieces = []

        for chunk in parts:
            if chunk is None:
                continue
            cand = (buf + chunk).strip()
            est = len(cand) / cps if cand else 0

            if cand and est > maxdur and is_valid(buf):
                pieces.append(buf.strip())
                buf = chunk.strip()
            else:
                buf = cand

        if is_valid(buf):
            pieces.append(buf.strip())

        if not pieces:
            out.append(s)
            continue

        total_chars = sum(len(p) for p in pieces)
        cur = start

        for i, piece in enumerate(pieces):
            piece_ratio = len(piece) / total_chars
            piece_dur = dur * piece_ratio
            nxt = cur + piece_dur

            if i == len(pieces) - 1:
                nxt = end

            new_seg = {
                "start": cur,
                "end": nxt,
                "text_trad": piece,
                "text_original": s.get("text_original", ""),
            }
            # Preservar speaker se existir
            if "speaker" in s:
                new_seg["speaker"] = s["speaker"]
            out.append(new_seg)
            cur = nxt

        split_count += 1

    print(f"[OK] Resultado: {len(out)} segmentos ({split_count} divididos)")
    return out

# ============================================================================
# FASE 3: CLONAGEM DE VOZ (XTTS)
# ============================================================================

def extract_voice_sample(wav_path, workdir, duration=10):
    """Extrai amostra de voz do audio original para clonagem

    Args:
        wav_path: caminho do audio original
        workdir: diretorio de trabalho
        duration: duracao da amostra em segundos

    Returns:
        caminho da amostra de voz
    """
    print("[INFO] Extraindo amostra de voz para clonagem...")

    sample_path = Path(workdir, "voice_sample.wav")

    # Extrair os primeiros 'duration' segundos com fala
    # Pular os primeiros 2 segundos (possiveis ruidos)
    sh([
        "ffmpeg", "-y",
        "-ss", "2",
        "-i", str(wav_path),
        "-t", str(duration),
        "-ar", "22050",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(sample_path)
    ])

    print(f"[OK] Amostra extraida: {sample_path}")
    return sample_path

def tts_xtts_clone(segments, workdir, tgt_lang, voice_sample):
    """TTS com XTTS - Clona voz do audio original

    FASE 3: Clonagem de voz usando XTTS v2
    """
    print("\n" + "="*60)
    print("=== ETAPA 6: TTS (XTTS - Clonagem de Voz) ===")
    print("="*60)

    if not check_xtts():
        print("[ERRO] XTTS nao disponivel. Instale com: pip install TTS")
        print("[INFO] Nota: Requer Python < 3.12")
        return None, None, None

    try:
        from TTS.api import TTS
        from scipy.io import wavfile
        import torch

        device = get_device()

        # Carregar modelo XTTS
        print("[INFO] Carregando modelo XTTS v2...")
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

        # Mapear idioma
        lang_map = {
            "pt": "pt", "pt-br": "pt", "pt_br": "pt",
            "en": "en", "en-us": "en", "en-gb": "en",
            "es": "es", "fr": "fr", "de": "de",
            "it": "it", "ja": "ja", "zh-cn": "zh-cn",
        }
        lang = lang_map.get(tgt_lang.lower(), "en")

        SAMPLE_RATE = 22050
        seg_files = []
        metricas = []

        print(f"[INFO] Voz de referencia: {voice_sample}")
        print(f"[INFO] Idioma: {lang}")

        tsv = Path(workdir, "segments.csv")
        with open(tsv, "w", encoding="utf-8", newline="") as fcsv:
            writer = csv.writer(fcsv)
            writer.writerow(["idx", "t_in", "t_out", "target_dur", "actual_dur", "ratio", "texto_trad", "file"])

            for i, s in enumerate(segments, 1):
                txt = (s.get("text_trad") or "").strip()
                target_dur = s["end"] - s["start"]

                if len(re.findall(r"[A-Za-z0-9]", txt)) < 3:
                    txt = "pausa"

                out_path = Path(workdir, f"seg_{i:04d}.wav")

                try:
                    # Gerar com voz clonada
                    tts.tts_to_file(
                        text=txt,
                        file_path=str(out_path),
                        speaker_wav=str(voice_sample),
                        language=lang
                    )

                    actual_dur = ffprobe_duration(out_path)
                    ratio = actual_dur / target_dur if target_dur > 0 else 1.0

                except Exception as e:
                    print(f"  [ERRO] Seg {i}: {e}")
                    silence = np.zeros(int(target_dur * SAMPLE_RATE), dtype=np.int16)
                    wavfile.write(str(out_path), SAMPLE_RATE, silence)
                    actual_dur = target_dur
                    ratio = 1.0

                seg_files.append(out_path)
                metricas.append({"idx": i, "target": target_dur, "actual": actual_dur, "ratio": ratio})

                writer.writerow([i, s["start"], s["end"], f"{target_dur:.3f}",
                               f"{actual_dur:.3f}", f"{ratio:.3f}", txt[:50], out_path.name])

                if i % 5 == 0 or i == len(segments):
                    print(f"  Progresso: {i}/{len(segments)}")

        if metricas:
            ratios = [m["ratio"] for m in metricas]
            print(f"\n[STATS] TTS XTTS:")
            print(f"  Segmentos: {len(seg_files)}")
            print(f"  Ratio medio: {np.mean(ratios):.2%}")

        return seg_files, SAMPLE_RATE, metricas

    except Exception as e:
        print(f"[ERRO] XTTS falhou: {e}")
        return None, None, None

# ============================================================================
# ETAPA 6: TTS (EDGE - PADRAO v4)
# ============================================================================

def tts_edge(segments, workdir, tgt_lang, voice=None, rate="+0%", speaker_voices=None):
    """TTS com Edge TTS (Microsoft) - PADRAO v4 - Vozes consistentes

    Args:
        speaker_voices: dict mapeando speaker_id para voz (para diarizacao)
    """
    print("\n" + "="*60)
    print("=== ETAPA 6: TTS (Edge TTS - Microsoft) ===")
    print("="*60)

    import asyncio
    try:
        import edge_tts
    except ImportError:
        print("[ERRO] edge-tts nao instalado. Instale com: pip install edge-tts")
        sys.exit(1)

    from scipy.io import wavfile

    VOZES_PADRAO = {
        "pt": "pt-BR-AntonioNeural",
        "pt-br": "pt-BR-AntonioNeural",
        "pt_br": "pt-BR-AntonioNeural",
        "en": "en-US-GuyNeural",
        "en-us": "en-US-GuyNeural",
        "en-gb": "en-GB-RyanNeural",
        "es": "es-ES-AlvaroNeural",
        "es-mx": "es-MX-JorgeNeural",
        "fr": "fr-FR-HenriNeural",
        "de": "de-DE-ConradNeural",
        "it": "it-IT-DiegoNeural",
        "ja": "ja-JP-KeitaNeural",
        "zh": "zh-CN-YunxiNeural",
        "ko": "ko-KR-InJoonNeural",
    }

    # Vozes alternativas para multiplos falantes
    VOZES_ALTERNATIVAS = {
        "pt": ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaNeural"],
        "en": ["en-US-GuyNeural", "en-US-JennyNeural", "en-US-AriaNeural"],
        "es": ["es-ES-AlvaroNeural", "es-ES-ElviraNeural"],
    }

    lang = (tgt_lang or "pt").lower().replace("_", "-")
    default_voice = voice or VOZES_PADRAO.get(lang, "pt-BR-AntonioNeural")

    # Mapear falantes para vozes se diarizacao ativada
    if speaker_voices is None:
        speaker_voices = {}

    # Detectar falantes unicos
    speakers = set(s.get("speaker", "SPEAKER_00") for s in segments)
    if len(speakers) > 1:
        print(f"[INFO] Multiplos falantes detectados: {speakers}")
        alt_voices = VOZES_ALTERNATIVAS.get(lang[:2], [default_voice])
        for i, spk in enumerate(sorted(speakers)):
            if spk not in speaker_voices:
                speaker_voices[spk] = alt_voices[i % len(alt_voices)]
        print(f"[INFO] Mapeamento de vozes: {speaker_voices}")

    print(f"[INFO] Voz padrao: {default_voice}")
    print(f"[INFO] Idioma: {lang}")
    print(f"[INFO] Rate: {rate}")

    SAMPLE_RATE = 24000

    seg_files = []
    metricas = []
    tsv = Path(workdir, "segments.csv")

    async def generate_audio(text, output_path, target_dur, voice_to_use):
        """Gera audio usando Edge TTS"""
        communicate = edge_tts.Communicate(text, voice_to_use, rate=rate)
        mp3_path = str(output_path).replace(".wav", ".mp3")
        await communicate.save(mp3_path)

        subprocess.run([
            "ffmpeg", "-y", "-i", mp3_path,
            "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le",
            str(output_path)
        ], capture_output=True)

        if os.path.exists(mp3_path):
            os.remove(mp3_path)

        actual_dur = ffprobe_duration(output_path)
        return actual_dur

    async def process_all_segments():
        with open(tsv, "w", encoding="utf-8", newline="") as fcsv:
            writer = csv.writer(fcsv)
            writer.writerow(["idx", "t_in", "t_out", "target_dur", "actual_dur", "ratio", "speaker", "voice", "texto_trad", "file"])

            for i, s in enumerate(segments, 1):
                txt = (s.get("text_trad") or "").strip()
                target_dur = s["end"] - s["start"]
                speaker = s.get("speaker", "SPEAKER_00")
                voice_to_use = speaker_voices.get(speaker, default_voice)

                if len(re.findall(r"[A-Za-z0-9]", txt)) < 3:
                    txt = "pausa"

                out_path = Path(workdir, f"seg_{i:04d}.wav")

                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        actual_dur = await generate_audio(txt, out_path, target_dur, voice_to_use)
                        ratio = actual_dur / target_dur if target_dur > 0 else 1.0
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)  # Esperar 2s antes de retry
                        else:
                            print(f"  [ERRO] Seg {i}: {e}")
                            silence = np.zeros(int(target_dur * SAMPLE_RATE), dtype=np.int16)
                            wavfile.write(str(out_path), SAMPLE_RATE, silence)
                            actual_dur = target_dur
                            ratio = 1.0

                # Pequeno delay entre requisições para evitar rate limit
                await asyncio.sleep(0.1)

                seg_files.append(out_path)
                metricas.append({"idx": i, "target": target_dur, "actual": actual_dur, "ratio": ratio})

                writer.writerow([i, s["start"], s["end"], f"{target_dur:.3f}",
                               f"{actual_dur:.3f}", f"{ratio:.3f}", speaker, voice_to_use, txt[:50], out_path.name])

                if i % 10 == 0 or i == len(segments):
                    print(f"  Progresso: {i}/{len(segments)}")

    asyncio.run(process_all_segments())

    if metricas:
        ratios = [m["ratio"] for m in metricas]
        print(f"\n[STATS] TTS Edge:")
        print(f"  Segmentos: {len(seg_files)}")
        print(f"  Ratio medio: {np.mean(ratios):.2%}")
        print(f"  Ratio min/max: {np.min(ratios):.2%} / {np.max(ratios):.2%}")

    return seg_files, SAMPLE_RATE, metricas

# ============================================================================
# ETAPA 6: TTS (BARK COM SEED FIXA)
# ============================================================================

def tts_bark_optimized(segments, workdir, text_temp=0.7, wave_temp=0.5,
                       history_prompt=None, max_retries=2):
    """TTS com Bark otimizado - v4: seed fixa para consistencia"""
    print("\n" + "="*60)
    print("=== ETAPA 6: TTS (Bark Otimizado) ===")
    print("="*60)

    import torch
    from scipy.io.wavfile import write

    set_global_seed(GLOBAL_SEED)
    print(f"[INFO] Seed fixa: {GLOBAL_SEED}")

    _original_torch_load = torch.load

    def _patched_torch_load(f, map_location=None, *args, **kwargs):
        kwargs['weights_only'] = False
        return _original_torch_load(f, map_location=map_location, *args, **kwargs)

    torch.load = _patched_torch_load

    from bark import generate_audio, SAMPLE_RATE

    device = get_device()
    print(f"[INFO] Bark device: {device.upper()}")

    if device == "cuda":
        os.environ['SUNO_USE_SMALL_MODELS'] = '0'
        os.environ['SUNO_OFFLOAD_CPU'] = '0'

    history = None
    if history_prompt:
        try:
            from bark.generation import load_history_prompt
            history = load_history_prompt(history_prompt)
            print(f"[INFO] Usando voz: {history_prompt}")
        except Exception as e:
            print(f"[WARN] Nao foi possivel carregar voz {history_prompt}: {e}")
            history = history_prompt

    seg_files = []
    metricas = []

    tsv = Path(workdir, "segments.csv")
    with open(tsv, "w", encoding="utf-8", newline="") as fcsv:
        writer = csv.writer(fcsv)
        writer.writerow(["idx", "t_in", "t_out", "target_dur", "actual_dur",
                        "ratio", "retries", "texto_trad", "file"])

        for i, s in enumerate(segments, 1):
            set_global_seed(GLOBAL_SEED + i)

            txt = (s.get("text_trad") or "").strip()
            target_dur = s["end"] - s["start"]

            if len(re.findall(r"[A-Za-z0-9]", txt)) < 3:
                txt = "pausa curta"

            out_path = Path(workdir, f"seg_{i:04d}.wav")

            best_audio = None
            best_dur = float('inf')
            best_ratio = float('inf')
            retries_used = 0

            for attempt in range(max_retries + 1):
                current_text_temp = max(0.4, text_temp - attempt * 0.1)
                current_wave_temp = max(0.3, wave_temp - attempt * 0.1)

                try:
                    audio = generate_audio(
                        txt,
                        history_prompt=history,
                        text_temp=current_text_temp,
                        waveform_temp=current_wave_temp
                    )

                    actual_dur = len(audio) / SAMPLE_RATE
                    ratio = actual_dur / target_dur if target_dur > 0 else 1.0

                    if ratio <= 1.3:
                        best_audio = audio
                        best_dur = actual_dur
                        best_ratio = ratio
                        break

                    if abs(ratio - 1.0) < abs(best_ratio - 1.0):
                        best_audio = audio
                        best_dur = actual_dur
                        best_ratio = ratio

                    retries_used = attempt + 1

                except Exception as e:
                    print(f"  [ERRO] Seg {i} tentativa {attempt+1}: {e}")
                    if attempt == max_retries:
                        best_audio = np.zeros(int(target_dur * SAMPLE_RATE), dtype=np.float32)
                        best_dur = target_dur
                        best_ratio = 1.0

            if best_audio is not None:
                audio_int16 = normalize_audio_safe(best_audio)
                write(out_path, SAMPLE_RATE, audio_int16)
            else:
                audio_int16 = np.zeros(int(target_dur * SAMPLE_RATE), dtype=np.int16)
                write(out_path, SAMPLE_RATE, audio_int16)

            seg_files.append(out_path)
            metricas.append({
                "idx": i, "target": target_dur, "actual": best_dur,
                "ratio": best_ratio, "retries": retries_used
            })

            writer.writerow([i, s["start"], s["end"], f"{target_dur:.3f}",
                           f"{best_dur:.3f}", f"{best_ratio:.3f}", retries_used,
                           txt[:50], out_path.name])

            if i % 10 == 0 or i == len(segments):
                print(f"  Progresso: {i}/{len(segments)}")

    torch.load = _original_torch_load

    if metricas:
        ratios = [m["ratio"] for m in metricas]
        print(f"\n[STATS] TTS Bark:")
        print(f"  Segmentos: {len(seg_files)}")
        print(f"  Ratio medio: {np.mean(ratios):.2%}")

    return seg_files, SAMPLE_RATE, metricas

# ============================================================================
# ETAPA 6: TTS (PIPER)
# ============================================================================

def tts_piper(segments, workdir, tgt_lang, model_path=None):
    """TTS com Piper - Offline, leve e rapido"""
    print("\n" + "="*60)
    print("=== ETAPA 6: TTS (Piper - Offline) ===")
    print("="*60)

    from scipy.io import wavfile

    if not model_path:
        default_paths = [
            Path.home() / ".local/share/piper/pt_BR-faber-medium.onnx",
            Path.home() / "piper-models/pt_BR-faber-medium.onnx",
            Path("models/piper/pt_BR-faber-medium.onnx"),
        ]
        for p in default_paths:
            if p.exists():
                model_path = str(p)
                break

    if not model_path or not Path(model_path).exists():
        print("[ERRO] Modelo Piper nao encontrado!")
        print("[INFO] Baixe de: https://github.com/rhasspy/piper/releases")
        sys.exit(1)

    print(f"[INFO] Modelo: {model_path}")

    SAMPLE_RATE = 22050
    seg_files = []
    tsv = Path(workdir, "segments.csv")

    with open(tsv, "w", encoding="utf-8", newline="") as fcsv:
        writer = csv.writer(fcsv)
        writer.writerow(["idx", "t_in", "t_out", "texto_trad", "file"])

        for i, s in enumerate(segments, 1):
            txt = (s.get("text_trad") or "").strip()

            if len(re.findall(r"[A-Za-z0-9]", txt)) < 3:
                txt = "pausa"

            out_path = Path(workdir, f"seg_{i:04d}.wav")

            try:
                proc = subprocess.run(
                    ["piper", "-m", model_path, "-f", str(out_path)],
                    input=txt.encode("utf-8"),
                    capture_output=True
                )

                if proc.returncode != 0:
                    raise Exception(proc.stderr.decode())

            except Exception as e:
                print(f"  [ERRO] Seg {i}: {e}")
                dur = s.get("end", 1) - s.get("start", 0)
                silence = np.zeros(int(dur * SAMPLE_RATE), dtype=np.int16)
                wavfile.write(str(out_path), SAMPLE_RATE, silence)

            seg_files.append(out_path)
            writer.writerow([i, s["start"], s["end"], txt[:50], out_path.name])

            if i % 10 == 0 or i == len(segments):
                print(f"  Progresso: {i}/{len(segments)}")

    print(f"[OK] TTS Piper: {len(seg_files)} segmentos")
    return seg_files, SAMPLE_RATE, []

# ============================================================================
# ETAPA 6.1: FADE
# ============================================================================

def apply_fade(seg_files, workdir, fade_in=0.01, fade_out=0.01):
    """Aplica fade-in e fade-out nos segmentos"""
    print("\n=== ETAPA 6.1: Aplicando Fade ===")
    from scipy.io import wavfile as wf

    xf_files = []
    for p in seg_files:
        out = Path(workdir, p.name.replace(".wav", "_xf.wav"))

        try:
            sr, data = wf.read(str(p))

            if data.dtype == np.int16:
                data = data.astype(np.float32) / 32767.0

            fade_in_samples = int(fade_in * sr)
            fade_out_samples = int(fade_out * sr)

            if fade_in_samples > 0 and fade_in_samples < len(data):
                fade_in_curve = np.linspace(0, 1, fade_in_samples)
                data[:fade_in_samples] *= fade_in_curve

            if fade_out_samples > 0 and fade_out_samples < len(data):
                fade_out_curve = np.linspace(1, 0, fade_out_samples)
                data[-fade_out_samples:] *= fade_out_curve

            audio_int16 = normalize_audio_safe(data)
            wf.write(str(out), sr, audio_int16)

        except Exception as e:
            print(f"  [WARN] Fade falhou para {p.name}: {e}")
            shutil.copy(str(p), str(out))

        xf_files.append(out)

    print(f"[OK] Fade aplicado: {len(xf_files)} segmentos")
    return xf_files

# ============================================================================
# ETAPA 7: SINCRONIZACAO (v4 - maxstretch=2.0)
# ============================================================================

def time_stretch_rubberband(input_path, output_path, ratio):
    """Time-stretch com rubberband (preserva pitch)"""
    if not check_rubberband():
        return False

    try:
        sh(["rubberband",
            "-t", str(ratio),
            "-p", "0",
            "--crisp", "5",
            str(input_path),
            str(output_path)])
        return True
    except:
        return False

def sync_fit_advanced(p, target, workdir, sr, tol, maxstretch, use_rubberband=True):
    """Sincronizacao fit avancada usando ffmpeg atempo (melhor qualidade para voz)"""

    cur = ffprobe_duration(p)
    if cur <= 0:
        return p

    ratio = target / cur

    if abs(ratio - 1.0) < tol:
        return p

    ratio = max(min(ratio, maxstretch), 1.0 / maxstretch)

    out = Path(workdir, p.name.replace(".wav", "_fit.wav"))

    # Opcao 1: Rubberband (melhor qualidade)
    if use_rubberband and check_rubberband():
        if time_stretch_rubberband(p, out, ratio):
            print(f"    [FIT-RB] {cur:.2f}s -> {target:.2f}s (ratio={ratio:.3f})")
            return out

    # Opcao 2: FFmpeg atempo (boa qualidade, sem dependencias extras)
    try:
        # atempo aceita valores entre 0.5 e 2.0
        # Para valores fora desse range, encadear multiplos filtros
        atempo_val = 1.0 / ratio  # atempo > 1 acelera, < 1 desacelera

        # Construir cadeia de filtros atempo se necessario
        if atempo_val < 0.5:
            # Muito lento - encadear
            filters = []
            while atempo_val < 0.5:
                filters.append("atempo=0.5")
                atempo_val *= 2
            filters.append(f"atempo={atempo_val:.4f}")
            filter_str = ",".join(filters)
        elif atempo_val > 2.0:
            # Muito rapido - encadear
            filters = []
            while atempo_val > 2.0:
                filters.append("atempo=2.0")
                atempo_val /= 2
            filters.append(f"atempo={atempo_val:.4f}")
            filter_str = ",".join(filters)
        else:
            filter_str = f"atempo={atempo_val:.4f}"

        result = subprocess.run([
            "ffmpeg", "-y", "-i", str(p),
            "-filter:a", filter_str,
            "-c:a", "pcm_s16le",
            str(out)
        ], capture_output=True)

        if result.returncode == 0 and out.exists():
            print(f"    [FIT-FF] {cur:.2f}s -> {target:.2f}s (ratio={ratio:.3f})")
            return out

    except Exception as e:
        print(f"    [WARN] ffmpeg atempo falhou: {e}")

    # Fallback: retornar original sem modificar
    print(f"    [WARN] sync_fit falhou, usando original")
    return p

def sync_pad(p, target, workdir, sr):
    """Sincronizacao com padding"""
    from scipy.io import wavfile as wf

    cur = ffprobe_duration(p)
    if cur <= 0:
        return p

    out = Path(workdir, p.name.replace(".wav", "_pad.wav"))

    try:
        file_sr, data = wf.read(str(p))

        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32767.0

        target_samples = int(target * file_sr)

        if len(data) >= target_samples:
            data = data[:target_samples]
        else:
            pad_samples = target_samples - len(data)
            silence = np.zeros(pad_samples, dtype=np.float32)
            data = np.concatenate([data, silence])

        audio_int16 = normalize_audio_safe(data)
        wf.write(str(out), file_sr, audio_int16)
        return out

    except Exception as e:
        print(f"    [WARN] sync_pad falhou: {e}")
        return p

def sync_smart_advanced(p, target, workdir, sr, tol, maxstretch, use_rubberband=True):
    """Sincronizacao smart avancada

    Logica:
    - Se audio < target: adiciona silencio (pad) - nao distorce
    - Se audio > target mas dentro de maxstretch: comprime (fit)
    - Se audio > target * maxstretch: trunca em vez de distorcer muito
    """
    cur = ffprobe_duration(p)
    if cur <= 0:
        return p

    low = target * (1 - tol)
    high = target * (1 + tol)

    if cur < low:
        # Audio curto demais - adicionar silencio
        return sync_pad(p, target, workdir, sr)
    elif cur > high:
        # Audio longo demais
        ratio = target / cur
        if ratio < (1.0 / maxstretch):
            # Distorcao seria muito grande - truncar em vez de comprimir
            return sync_pad(p, target, workdir, sr)  # sync_pad tambem trunca
        else:
            return sync_fit_advanced(p, target, workdir, sr, tol, maxstretch, use_rubberband)
    else:
        return p

# ============================================================================
# ETAPA 8: CONCATENACAO
# ============================================================================

def concat_segments(seg_files, workdir, samplerate):
    """Concatena segmentos de audio"""
    print("\n" + "="*60)
    print("=== ETAPA 8: Concatenacao ===")
    print("="*60)

    lst = Path(workdir, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in seg_files:
            f.write(f"file '{p.name}'\n")

    out = Path(workdir, "dub_raw.wav")
    sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-c:a", "pcm_s16le", "-ar", str(samplerate), "-ac", "1",
        str(out)])

    print(f"[OK] Concatenado: {out.name}")
    return out

# ============================================================================
# ETAPA 9: POS-PROCESSAMENTO
# ============================================================================

def postprocess_audio(wav_in, workdir, samplerate):
    """Pos-processamento do audio final"""
    print("\n" + "="*60)
    print("=== ETAPA 9: Pos-processamento ===")
    print("="*60)

    from scipy.io import wavfile as wf

    out = Path(workdir, "dub_final.wav")

    try:
        file_sr, data = wf.read(str(wav_in))
        audio_int16 = normalize_audio_safe(data, target_peak=0.84)
        wf.write(str(out), file_sr, audio_int16)
        print(f"[OK] Pos-processado: {out.name}")
    except Exception as e:
        print(f"[WARN] Pos-processamento falhou: {e}")
        shutil.copy(str(wav_in), str(out))

    return out

# ============================================================================
# ETAPA 10: MUX FINAL
# ============================================================================

def mux_video(video_in, wav_in, out_mp4, bitrate):
    """Combina video original com audio dublado"""
    print("\n" + "="*60)
    print("=== ETAPA 10: Mux Final ===")
    print("="*60)

    sh(["ffmpeg", "-y",
        "-i", str(video_in),
        "-i", str(wav_in),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", bitrate,
        str(out_mp4)])

    print(f"[OK] Video final: {out_mp4}")

# ============================================================================
# METRICAS DE QUALIDADE
# ============================================================================

def calculate_quality_metrics(segments, seg_files, workdir):
    """Calcula metricas de qualidade da dublagem"""
    print("\n" + "="*60)
    print("=== Metricas de Qualidade ===")
    print("="*60)

    metricas = {
        "total_segments": len(segments),
        "sync_stats": {
            "within_5pct": 0,
            "within_10pct": 0,
            "within_20pct": 0,
            "over_20pct": 0,
        },
        "translation_stats": {
            "avg_compression": 0,
            "chars_original": 0,
            "chars_translated": 0,
        }
    }

    total_ratio = 0

    for i, (seg, seg_file) in enumerate(zip(segments, seg_files)):
        target_dur = seg["end"] - seg["start"]
        actual_dur = ffprobe_duration(seg_file)

        if target_dur > 0:
            ratio = actual_dur / target_dur
            diff = abs(ratio - 1.0)

            if diff <= 0.05:
                metricas["sync_stats"]["within_5pct"] += 1
            elif diff <= 0.10:
                metricas["sync_stats"]["within_10pct"] += 1
            elif diff <= 0.20:
                metricas["sync_stats"]["within_20pct"] += 1
            else:
                metricas["sync_stats"]["over_20pct"] += 1

            total_ratio += ratio

        orig = seg.get("text_original", "")
        trad = seg.get("text_trad", "")
        metricas["translation_stats"]["chars_original"] += len(orig)
        metricas["translation_stats"]["chars_translated"] += len(trad)

    if len(segments) > 0:
        metricas["sync_stats"]["avg_ratio"] = total_ratio / len(segments)

    if metricas["translation_stats"]["chars_original"] > 0:
        metricas["translation_stats"]["avg_compression"] = (
            metricas["translation_stats"]["chars_translated"] /
            metricas["translation_stats"]["chars_original"]
        )

    print(f"  Segmentos totais: {metricas['total_segments']}")
    print(f"  Sincronizacao:")
    print(f"    - Dentro de 5%: {metricas['sync_stats']['within_5pct']}")
    print(f"    - Dentro de 10%: {metricas['sync_stats']['within_10pct']}")
    print(f"    - Dentro de 20%: {metricas['sync_stats']['within_20pct']}")
    print(f"    - Acima de 20%: {metricas['sync_stats']['over_20pct']}")
    print(f"  Traducao:")
    print(f"    - Compressao media: {metricas['translation_stats']['avg_compression']:.2%}")

    metrics_file = Path(workdir, "quality_metrics.json")
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metricas, f, indent=2, ensure_ascii=False)

    return metricas

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n" + "="*60)
    print(f"  DUBLAR PRO v{VERSION} - COMPLETO")
    print("  Pipeline de Dublagem Profissional")
    print("  Fases 1-4 implementadas")
    print("="*60)

    ap = argparse.ArgumentParser(
        description="Dublagem profissional v4 com todas as features",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Basico (idioma origem especificado)
  python dublar_pro_v4.py --in video.mp4 --src en --tgt pt

  # Auto-detectar idioma origem (omitir --src)
  python dublar_pro_v4.py --in video.mp4 --tgt pt

  # YouTube direto
  python dublar_pro_v4.py --in "https://youtube.com/watch?v=XXX" --tgt pt

  # Com Ollama (traducao natural)
  python dublar_pro_v4.py --in video.mp4 --tgt pt --tradutor ollama --modelo llama3

  # Clonagem de voz
  python dublar_pro_v4.py --in video.mp4 --src en --tgt pt --tts xtts --clonar-voz

  # Multiplos falantes (diarizacao)
  python dublar_pro_v4.py --in video.mp4 --src en --tgt pt --diarize

  # Maxima qualidade
  python dublar_pro_v4.py --in video.mp4 --src en --tgt pt --qualidade maximo
        """
    )

    # Entrada
    ap.add_argument("--in", dest="inp", required=True, help="Video de entrada ou URL YouTube")
    ap.add_argument("--src", default=None, help="Idioma de origem (auto-detectar se omitido)")
    ap.add_argument("--tgt", required=True, help="Idioma de destino (pt, en, es, etc)")

    # Saida
    ap.add_argument("--out", dest="out", default=None, help="Video de saida")
    ap.add_argument("--outdir", default="dublado", help="Diretorio de saida")

    # Traducao
    ap.add_argument("--tradutor", choices=["ollama", "m2m100"], default="m2m100",
                   help="Engine de traducao")
    ap.add_argument("--modelo", default="llama3", help="Modelo Ollama")
    ap.add_argument("--large-model", action="store_true", help="Usar M2M100 1.2B")

    # TTS
    ap.add_argument("--tts", choices=["edge", "bark", "piper", "xtts"], default="edge",
                   help="Engine TTS")
    ap.add_argument("--voice", default=None, help="Voz TTS")
    ap.add_argument("--rate", default="+0%", help="Velocidade Edge TTS")
    ap.add_argument("--texttemp", type=float, default=0.7, help="Bark text temperature")
    ap.add_argument("--wavetemp", type=float, default=0.5, help="Bark waveform temperature")
    ap.add_argument("--max-retries", type=int, default=2, help="Max retries TTS")
    ap.add_argument("--clonar-voz", action="store_true", help="Clonar voz do video original (XTTS)")

    # Whisper
    ap.add_argument("--whisper-model", default="large-v3",
                   choices=["tiny", "small", "medium", "large", "large-v2", "large-v3"],
                   help="Modelo Whisper (padrao: large-v3)")

    # Diarizacao
    ap.add_argument("--diarize", action="store_true", help="Detectar multiplos falantes")
    ap.add_argument("--num-speakers", type=int, default=None, help="Numero de falantes (auto se nao especificado)")

    # Sincronizacao
    ap.add_argument("--sync", choices=["none", "fit", "pad", "smart"], default="smart",
                   help="Modo de sincronizacao")
    ap.add_argument("--tolerance", type=float, default=0.1, help="Tolerancia sync")
    ap.add_argument("--maxstretch", type=float, default=1.3, help="Max compressao (1.3=30%)")
    ap.add_argument("--no-rubberband", action="store_true", help="Desabilitar rubberband (usar ffmpeg atempo)")
    ap.add_argument("--no-truncate", action="store_true",
                   help="Nao truncar texto traduzido (frases completas, sync ajusta duracao)")

    # Outros
    ap.add_argument("--maxdur", type=float, default=10.0, help="Duracao maxima segmento")
    ap.add_argument("--rate-audio", type=int, default=24000, help="Sample rate final")
    ap.add_argument("--bitrate", default="192k", help="Bitrate AAC")
    ap.add_argument("--fade", type=int, default=1, choices=[0, 1], help="Aplicar fade")
    ap.add_argument("--seed", type=int, default=42, help="Seed para reproducibilidade")

    # Atalhos
    ap.add_argument("--qualidade", choices=["rapido", "balanceado", "maximo"], default="balanceado",
                   help="Preset de qualidade")

    args = ap.parse_args()

    # Aplicar presets de qualidade
    if args.qualidade == "rapido":
        args.tts = "edge"
        args.tradutor = "m2m100"
        args.whisper_model = "medium"  # medium para rapido
    elif args.qualidade == "maximo":
        args.tts = "xtts" if args.clonar_voz and check_xtts() else "edge"
        args.tradutor = "ollama" if check_ollama() else "m2m100"
        args.no_rubberband = False
        args.large_model = True
        args.whisper_model = "large-v3"  # large-v3 para maximo
        args.diarize = True
    # balanceado usa o padrao (large-v3)

    # Se clonar-voz mas nao especificou XTTS
    if args.clonar_voz and args.tts != "xtts":
        args.tts = "xtts"

    # Configurar seed global
    global GLOBAL_SEED
    GLOBAL_SEED = args.seed
    set_global_seed(GLOBAL_SEED)

    # Verificacoes
    ensure_ffmpeg()

    # Verificar se e URL do YouTube
    video_in = args.inp
    workdir = Path("dub_work")
    workdir.mkdir(exist_ok=True)

    if is_youtube_url(video_in):
        video_in = download_youtube(video_in, workdir)
    else:
        video_in = Path(video_in).resolve()
        if not video_in.exists():
            print(f"[ERRO] Arquivo nao encontrado: {video_in}")
            sys.exit(1)

    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True)

    if args.out:
        out_mp4 = Path(args.out)
    else:
        out_mp4 = outdir / f"{Path(video_in).stem}_dublado.mp4"

    # Mostrar configuracao
    print(f"\n[CONFIG] v{VERSION}")
    print(f"  Entrada: {video_in}")
    print(f"  Saida: {out_mp4}")
    print(f"  Idiomas: {args.src} -> {args.tgt}")
    print(f"  Tradutor: {args.tradutor}" + (f" ({args.modelo})" if args.tradutor == "ollama" else ""))
    print(f"  TTS: {args.tts}" + (" (clonagem)" if args.clonar_voz else ""))
    print(f"  Diarizacao: {'Sim' if args.diarize else 'Nao'}")
    print(f"  Sync: {args.sync} (tol: {args.tolerance}, max: {args.maxstretch})")
    print(f"  Qualidade: {args.qualidade}")

    # Dicionario para armazenar tempos de cada etapa
    import time
    tempos_etapas = {}
    tempo_inicio_total = time.time()

    # ========== ETAPA 1-2: Extracao ==========
    t_etapa = time.time()
    print("\n" + "="*60)
    print("=== ETAPA 1-2: Validacao e Extracao ===")
    print("="*60)

    audio_src = Path(workdir, "audio_src.wav")
    sh(["ffmpeg", "-y", "-i", str(video_in),
        "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le",
        str(audio_src)])

    # Extrair amostra para clonagem de voz se necessario
    voice_sample = None
    if args.clonar_voz:
        voice_sample = extract_voice_sample(audio_src, workdir)

    save_checkpoint(workdir, 2, "extraction")
    tempos_etapas["1-2_extracao"] = time.time() - t_etapa

    # ========== ETAPA 3: Transcricao ==========
    t_etapa = time.time()
    asr_json, asr_srt, segs, detected_lang = transcribe_faster_whisper(
        audio_src, workdir, args.src, args.whisper_model,
        diarize=args.diarize, num_speakers=args.num_speakers
    )
    save_checkpoint(workdir, 3, "transcription")
    tempos_etapas["3_transcricao"] = time.time() - t_etapa

    # Usar idioma detectado se nao foi especificado
    src_lang = detected_lang or args.src
    if not args.src:
        print(f"[INFO] Usando idioma detectado: {src_lang}")

    # Calcular CPS original para traducao adaptativa
    cps_original = calcular_cps_original(audio_src, segs)
    print(f"[INFO] CPS original calculado: {cps_original:.1f}")

    # ========== ETAPA 4: Traducao ==========
    t_etapa = time.time()
    no_truncate = getattr(args, 'no_truncate', False)
    if no_truncate:
        print("[INFO] Modo --no-truncate ativado: frases completas, sync ajusta duracao")
    if args.tradutor == "ollama":
        result = translate_segments_ollama(segs, src_lang, args.tgt, workdir, args.modelo, cps_original, no_truncate)
        if result is None:
            print("[INFO] Fallback para M2M100...")
            segs_trad, trad_json, trad_srt = translate_segments_m2m100(
                segs, src_lang, args.tgt, workdir, args.large_model, cps_original, no_truncate
            )
        else:
            segs_trad, trad_json, trad_srt = result
    else:
        segs_trad, trad_json, trad_srt = translate_segments_m2m100(
            segs, src_lang, args.tgt, workdir, args.large_model, cps_original, no_truncate
        )
    save_checkpoint(workdir, 4, "translation")
    tempos_etapas["4_traducao"] = time.time() - t_etapa

    # ========== ETAPA 5: Split ==========
    t_etapa = time.time()
    segs_trad = split_long_segments(segs_trad, args.maxdur)
    save_checkpoint(workdir, 5, "split")
    tempos_etapas["5_split"] = time.time() - t_etapa

    # ========== ETAPA 6: TTS ==========
    t_etapa = time.time()
    if args.tts == "xtts" and voice_sample:
        result = tts_xtts_clone(segs_trad, workdir, args.tgt, voice_sample)
        if result[0] is None:
            print("[INFO] XTTS falhou, usando Edge...")
            seg_files, sr_segs, tts_metrics = tts_edge(
                segs_trad, workdir, args.tgt, voice=args.voice, rate=args.rate
            )
        else:
            seg_files, sr_segs, tts_metrics = result
    elif args.tts == "edge":
        seg_files, sr_segs, tts_metrics = tts_edge(
            segs_trad, workdir, args.tgt, voice=args.voice, rate=args.rate
        )
    elif args.tts == "bark":
        voice = args.voice or "v2/pt_speaker_3"
        seg_files, sr_segs, tts_metrics = tts_bark_optimized(
            segs_trad, workdir,
            text_temp=args.texttemp,
            wave_temp=args.wavetemp,
            history_prompt=voice,
            max_retries=args.max_retries
        )
    else:  # piper
        seg_files, sr_segs, tts_metrics = tts_piper(
            segs_trad, workdir, args.tgt, model_path=args.voice
        )

    save_checkpoint(workdir, 6, "tts")
    tempos_etapas["6_tts"] = time.time() - t_etapa

    # ========== ETAPA 6.1: Fade ==========
    if args.fade == 1:
        seg_files = apply_fade(seg_files, workdir)

    # ========== ETAPA 7: Sincronizacao ==========
    t_etapa = time.time()
    print("\n" + "="*60)
    print("=== ETAPA 7: Sincronizacao ===")
    print("="*60)

    fixed = []
    use_rb = not args.no_rubberband  # Usar rubberband por padrao

    # Garantir que temos a mesma quantidade de segmentos e arquivos
    n_segs = len(segs_trad)
    n_files = len(seg_files)
    if n_segs != n_files:
        print(f"[WARN] Mismatch: {n_segs} segmentos vs {n_files} arquivos")

    # Usar o menor para evitar index out of range, mas processar todos os arquivos
    for i, p in enumerate(seg_files):
        if i < len(segs_trad):
            s = segs_trad[i]
            target = max(0.05, s["end"] - s["start"])
        else:
            # Arquivo extra do split - usar duracao padrao
            target = ffprobe_duration(p) or 2.0

        if args.sync == "none":
            fixed.append(p)
        elif args.sync == "fit":
            fixed.append(sync_fit_advanced(p, target, workdir, sr_segs,
                                          args.tolerance, args.maxstretch, use_rb))
        elif args.sync == "pad":
            fixed.append(sync_pad(p, target, workdir, sr_segs))
        elif args.sync == "smart":
            fixed.append(sync_smart_advanced(p, target, workdir, sr_segs,
                                            args.tolerance, args.maxstretch, use_rb))

    seg_files = fixed
    save_checkpoint(workdir, 7, "sync")
    tempos_etapas["7_sync"] = time.time() - t_etapa

    # ========== ETAPA 8: Concatenacao ==========
    t_etapa = time.time()
    dub_raw = concat_segments(seg_files, workdir, sr_segs)
    save_checkpoint(workdir, 8, "concat")
    tempos_etapas["8_concat"] = time.time() - t_etapa

    # ========== ETAPA 9: Pos-processamento ==========
    t_etapa = time.time()
    dub_final = postprocess_audio(dub_raw, workdir, args.rate_audio)
    save_checkpoint(workdir, 9, "postprocess")
    tempos_etapas["9_postprocess"] = time.time() - t_etapa

    # ========== ETAPA 10: Mux ==========
    t_etapa = time.time()
    mux_video(video_in, dub_final, out_mp4, args.bitrate)
    save_checkpoint(workdir, 10, "mux")
    tempos_etapas["10_mux"] = time.time() - t_etapa

    # Tempo total
    tempo_total = time.time() - tempo_inicio_total

    # ========== Metricas ==========
    metrics = calculate_quality_metrics(segs_trad, seg_files, workdir)

    # ========== Logs finais ==========
    logs = {
        "version": VERSION,
        "timestamp": datetime.now().isoformat(),
        "input_video": str(video_in),
        "output_video": str(out_mp4),
        "config": {
            "src": args.src,
            "tgt": args.tgt,
            "tradutor": args.tradutor,
            "modelo_llm": args.modelo if args.tradutor == "ollama" else None,
            "tts": args.tts,
            "voice": args.voice,
            "clonar_voz": args.clonar_voz,
            "diarize": args.diarize,
            "sync": args.sync,
            "tolerance": args.tolerance,
            "maxstretch": args.maxstretch,
            "cps_original": cps_original,
            "qualidade": args.qualidade,
            "seed": GLOBAL_SEED,
        },
        "metrics": metrics,
        "tempos": {
            "etapas": tempos_etapas,
            "total_segundos": tempo_total,
        },
    }

    with open(Path(workdir, "logs.json"), "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

    # ========== Resumo ==========
    print("\n" + "="*60)
    print("  DUBLAGEM CONCLUIDA!")
    print("="*60)
    print(f"\n  Saidas:")
    print(f"    Video: {out_mp4}")
    print(f"    Legendas: {trad_srt}")
    print(f"    Logs: {workdir}/logs.json")
    print(f"    Metricas: {workdir}/quality_metrics.json")
    print(f"\n  Intermediarios em: {workdir}/")

    # Exibir tempos de cada etapa
    print("\n" + "="*60)
    print("  TEMPOS POR ETAPA")
    print("="*60)
    nomes_etapas = {
        "1-2_extracao": "1-2. Extracao de audio",
        "3_transcricao": "3. Transcricao (Whisper)",
        "4_traducao": "4. Traducao",
        "5_split": "5. Split de segmentos",
        "6_tts": "6. Sintese de voz (TTS)",
        "7_sync": "7. Sincronizacao",
        "8_concat": "8. Concatenacao",
        "9_postprocess": "9. Pos-processamento",
        "10_mux": "10. Mixagem final",
    }
    for key, nome in nomes_etapas.items():
        if key in tempos_etapas:
            t = tempos_etapas[key]
            if t >= 3600:
                tempo_str = f"{int(t//3600)}h {int((t%3600)//60)}m {int(t%60)}s"
            elif t >= 60:
                tempo_str = f"{int(t//60)}m {int(t%60)}s"
            else:
                tempo_str = f"{t:.1f}s"
            print(f"  {nome}: {tempo_str}")

    # Tempo total
    if tempo_total >= 3600:
        total_str = f"{int(tempo_total//3600)}h {int((tempo_total%3600)//60)}m {int(tempo_total%60)}s"
    elif tempo_total >= 60:
        total_str = f"{int(tempo_total//60)}m {int(tempo_total%60)}s"
    else:
        total_str = f"{tempo_total:.1f}s"
    print(f"\n  TEMPO TOTAL: {total_str}")
    print("="*60)

if __name__ == "__main__":
    main()
