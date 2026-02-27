"""Gerenciador de modelos - Ollama, TTS voices, Whisper models."""

import httpx
import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Vozes Edge TTS organizadas por codigo de idioma curto (pt, en, es, ...)
EDGE_VOICES = {
    "pt": [
        {"id": "pt-BR-AntonioNeural",   "name": "Antonio BR (Masculino)",  "gender": "male"},
        {"id": "pt-BR-FranciscaNeural", "name": "Francisca BR (Feminino)", "gender": "female"},
        {"id": "pt-BR-ThalitaNeural",   "name": "Thalita BR (Feminino)",   "gender": "female"},
        {"id": "pt-PT-DuarteNeural",    "name": "Duarte PT (Masculino)",   "gender": "male"},
        {"id": "pt-PT-RaquelNeural",    "name": "Raquel PT (Feminino)",    "gender": "female"},
    ],
    "en": [
        {"id": "en-US-GuyNeural",     "name": "Guy US (Male)",     "gender": "male"},
        {"id": "en-US-JennyNeural",   "name": "Jenny US (Female)", "gender": "female"},
        {"id": "en-US-AriaNeural",    "name": "Aria US (Female)",  "gender": "female"},
        {"id": "en-US-DavisNeural",   "name": "Davis US (Male)",   "gender": "male"},
        {"id": "en-GB-RyanNeural",    "name": "Ryan GB (Male)",    "gender": "male"},
        {"id": "en-GB-SoniaNeural",   "name": "Sonia GB (Female)", "gender": "female"},
    ],
    "es": [
        {"id": "es-ES-AlvaroNeural",  "name": "Alvaro ES (Masculino)", "gender": "male"},
        {"id": "es-ES-ElviraNeural",  "name": "Elvira ES (Femenino)",  "gender": "female"},
        {"id": "es-MX-JorgeNeural",   "name": "Jorge MX (Masculino)",  "gender": "male"},
        {"id": "es-MX-DaliaNeural",   "name": "Dalia MX (Femenino)",   "gender": "female"},
    ],
    "fr": [
        {"id": "fr-FR-HenriNeural",   "name": "Henri (Masculin)",  "gender": "male"},
        {"id": "fr-FR-DeniseNeural",  "name": "Denise (Feminin)",  "gender": "female"},
        {"id": "fr-FR-VivienneNeural","name": "Vivienne (Feminin)","gender": "female"},
    ],
    "de": [
        {"id": "de-DE-ConradNeural",  "name": "Conrad (Mannlich)", "gender": "male"},
        {"id": "de-DE-KatjaNeural",   "name": "Katja (Weiblich)",  "gender": "female"},
        {"id": "de-DE-AmalaNeural",   "name": "Amala (Weiblich)",  "gender": "female"},
    ],
    "it": [
        {"id": "it-IT-DiegoNeural",   "name": "Diego (Maschile)",  "gender": "male"},
        {"id": "it-IT-ElsaNeural",    "name": "Elsa (Femminile)",  "gender": "female"},
        {"id": "it-IT-IsabellaNeural","name": "Isabella (Femm.)",  "gender": "female"},
    ],
    "ja": [
        {"id": "ja-JP-KeitaNeural",   "name": "Keita (男性)",   "gender": "male"},
        {"id": "ja-JP-NanamiNeural",  "name": "Nanami (女性)",  "gender": "female"},
        {"id": "ja-JP-AoiNeural",     "name": "Aoi (女性)",     "gender": "female"},
    ],
    "zh": [
        {"id": "zh-CN-YunyangNeural", "name": "Yunyang (男)",  "gender": "male"},
        {"id": "zh-CN-XiaoxiaoNeural","name": "Xiaoxiao (女)", "gender": "female"},
        {"id": "zh-CN-YunxiNeural",   "name": "Yunxi (男)",    "gender": "male"},
    ],
    "ko": [
        {"id": "ko-KR-InJoonNeural",  "name": "InJoon (남성)", "gender": "male"},
        {"id": "ko-KR-SunHiNeural",   "name": "SunHi (여성)",  "gender": "female"},
    ],
    "ru": [
        {"id": "ru-RU-DmitryNeural",  "name": "Dmitry (Муж.)", "gender": "male"},
        {"id": "ru-RU-SvetlanaNeural","name": "Svetlana (Жен.)","gender": "female"},
    ],
}

# Vozes Bark por idioma
BARK_VOICES = {
    "pt": [{"id": f"v2/pt_speaker_{i}", "name": f"Speaker {i}"} for i in range(10)],
    "en": [{"id": f"v2/en_speaker_{i}", "name": f"Speaker {i}"} for i in range(10)],
    "es": [{"id": f"v2/es_speaker_{i}", "name": f"Speaker {i}"} for i in range(10)],
    "fr": [{"id": f"v2/fr_speaker_{i}", "name": f"Speaker {i}"} for i in range(10)],
    "de": [{"id": f"v2/de_speaker_{i}", "name": f"Speaker {i}"} for i in range(10)],
}

WHISPER_MODELS = [
    {"id": "tiny", "name": "Tiny (39M)", "size_mb": 75, "quality": "baixa"},
    {"id": "small", "name": "Small (244M)", "size_mb": 460, "quality": "media"},
    {"id": "medium", "name": "Medium (769M)", "size_mb": 1500, "quality": "boa"},
    {"id": "large-v3", "name": "Large v3 (1.5B)", "size_mb": 3000, "quality": "excelente"},
    {"id": "large-v3-turbo", "name": "Large v3 Turbo (809M)", "size_mb": 1600, "quality": "excelente", "turbo": True},
]

ASR_ENGINES = [
    {
        "id": "whisper",
        "name": "Whisper (OpenAI / Faster-Whisper)",
        "description": "Multi-idioma. Suporta 99+ idiomas com deteccao automatica.",
        "detail": "Usa Faster-Whisper (CTranslate2) com aceleracao GPU ou OpenAI Whisper (PyTorch) como fallback. Detecta idioma automaticamente. Modelos de 39M a 1.5B parametros. O large-v3-turbo e uma versao destilada ~3x mais rapida com qualidade similar ao large-v3.",
        "needs_gpu": False,
        "supports_languages": "all",
    },
    {
        "id": "parakeet",
        "name": "Parakeet (NVIDIA NeMo)",
        "description": "Otimizado para GPU NVIDIA. Apenas ingles, ~3-5x mais rapido que Whisper.",
        "detail": "Modelo da NVIDIA treinado para ingles. Usa NeMo toolkit com otimizacoes para GPUs NVIDIA. Significativamente mais rapido que Whisper para ingles. NAO suporta outros idiomas. Requer GPU NVIDIA com CUDA. Modelos: TDT-1.1B (recomendado, melhor pontuacao), CTC-1.1B (mais rapido), RNNT-1.1B (mais preciso).",
        "needs_gpu": True,
        "supports_languages": ["en"],
    },
]

TTS_ENGINES = [
    {
        "id": "edge",
        "name": "Edge TTS (Microsoft)",
        "needs_gpu": False,
        "needs_internet": True,
        "quality": "excelente",
        "description": "Vozes naturais de alta qualidade. Rapido e gratis, requer internet.",
        "detail": "Usa a API gratuita da Microsoft (mesmas vozes do Windows e Edge). Suporta dezenas de idiomas com multiplas vozes por idioma. Qualidade excelente, velocidade rapida, sem custo de GPU. Unica desvantagem: precisa de conexao com internet.",
    },
    {
        "id": "bark",
        "name": "Bark (Suno AI)",
        "needs_gpu": True,
        "needs_internet": False,
        "quality": "boa",
        "description": "Voz expressiva com emocao. Ri, suspira, tem entonacao natural. Lento.",
        "detail": "Modelo generativo da Suno AI que produz fala com emocao real: risadas, pausas dramaticas, suspiros, entonacao expressiva. Consome bastante VRAM e e significativamente mais lento que Edge TTS. Ideal para conteudo dramatico ou quando expressividade importa mais que velocidade.",
    },
    {
        "id": "piper",
        "name": "Piper (Leve)",
        "needs_gpu": False,
        "needs_internet": False,
        "quality": "razoavel",
        "description": "Ultra-leve e offline. Roda em qualquer hardware sem internet.",
        "detail": "Motor TTS minimalista que roda em CPU sem internet. Muito rapido e leve, ideal para ambientes sem rede ou com hardware limitado. Qualidade inferior aos outros motores - voz soa mais robotica. Use quando offline total for requisito.",
    },
    {
        "id": "xtts",
        "name": "XTTS (Clonar Voz)",
        "needs_gpu": True,
        "needs_internet": False,
        "quality": "muito boa",
        "description": "Clona a voz original do video. A dublagem soa como a mesma pessoa.",
        "detail": "Modelo Coqui XTTS que clona a voz do falante original do video. Extrai caracteristicas da voz (timbre, tom, ritmo) e gera a fala traduzida com a mesma voz. Requer GPU e e mais lento. O resultado e impressionante: parece que a pessoa original esta falando em outro idioma.",
    },
    {
        "id": "chatterbox",
        "name": "Chatterbox (Voice Clone Neural)",
        "needs_gpu": True,
        "needs_internet": False,
        "quality": "excelente",
        "description": "Voice clone zero-shot de alta qualidade. Suporta PT, EN e 20+ idiomas.",
        "detail": "Modelo neural da Resemble AI. Roteamento automatico: ingles usa Turbo 350M (rapido), outros idiomas usam Multilingual 500M (PT, ES, FR, DE e mais 20 idiomas). Voice clone zero-shot: com --clonar-voz extrai a voz do video e gera o audio dublado com o mesmo timbre. SR de saida: 24000 Hz. Requer conda env 'chatterbox' instalado.",
    },
]

TRANSLATION_ENGINES = [
    {
        "id": "m2m100",
        "name": "M2M100 (Facebook)",
        "needs_gpu": False,
        "models": ["418M", "1.2B"],
        "description": "Traducao offline multi-idioma. Funciona sem internet e sem GPU.",
        "detail": "Modelo multilingual da Meta. Suporta 100 idiomas em qualquer direcao sem passar pelo ingles. Modelo 418M rapido e leve, 1.2B melhor qualidade. Roda em CPU. Bom para frases curtas, pode perder contexto em frases longas.",
    },
    {
        "id": "ollama",
        "name": "Ollama (LLM Local)",
        "needs_gpu": True,
        "models": "dynamic",
        "description": "Traducao via LLM local. Melhor qualidade, mais lento, requer VRAM.",
        "detail": "Usa LLM local via Ollama. Qualidade superior ao M2M100 pois entende contexto, expressoes idiomaticas e tom. Requer Ollama instalado com modelo carregado (ex: qwen2.5:14b). Mais lento e usa VRAM da GPU. Ideal quando qualidade de traducao e prioridade.",
    },
]

CONTENT_TYPES = [
    {
        "id": "tutorial",
        "name": "Tutorial / Apresentacao",
        "description": "Screencast, tutorial, demo, social media. Fala natural, sem cortes.",
        "detail": "Fala 20% mais rapida para compensar que o portugues e mais longo que o ingles. Se ainda sobrar audio, o video congela o frame ate a fala terminar — sem cortar nenhuma palavra. A melhor opcao para tutoriais curtos onde o conteudo completo e mais importante que o timing exato.",
        "presets": {"sync": "extend", "maxstretch": 1.5, "no_truncate": True, "tts_rate": "+20%"},
    },
    {
        "id": "palestra",
        "name": "Palestra / Talking Head",
        "description": "Vlog, entrevista, podcast com video. Equilibra timing e conteudo.",
        "detail": "Comprime a fala ate 30% para caber no tempo original. Se a frase traduzida for muito longa, corta palavras do final para manter sincronia com o video. Bom para quando o apresentador aparece na tela e o timing labial importa moderadamente.",
        "presets": {"sync": "smart", "maxstretch": 1.3, "tolerance": 0.1},
    },
    {
        "id": "curso",
        "name": "Curso / Aula",
        "description": "Conteudo educacional. Nunca corta frases, comprime bastante se preciso.",
        "detail": "Mantem todas as frases completas sem cortar nenhuma palavra. Se a traducao ficar mais longa que o original, comprime a velocidade da fala em ate 2x. Ideal para cursos e aulas onde perder conteudo e inaceitavel, mesmo que a fala fique um pouco mais rapida.",
        "presets": {"sync": "smart", "maxstretch": 2.0, "no_truncate": True},
    },
    {
        "id": "podcast",
        "name": "Podcast / Entrevista",
        "description": "Conversa longa. Frases completas, velocidade moderada.",
        "detail": "Mantem frases completas e comprime ate 50% se necessario. Bom equilibrio entre preservar o conteudo e nao distorcer demais a voz. Para podcasts e entrevistas longas onde o ouvinte precisa de todo o contexto.",
        "presets": {"sync": "fit", "maxstretch": 1.5, "no_truncate": True},
    },
    {
        "id": "apresentacao",
        "name": "Apresentacao / Demo",
        "description": "Tutorial, screencast, demo de software. Timing preciso com a tela.",
        "detail": "Prioriza sincronizacao com o que acontece na tela. Comprime ate 15% e corta texto se necessario para que a fala acompanhe as acoes no video. Essencial para demos onde o narrador diz 'clique aqui' e o cursor se move.",
        "presets": {"sync": "smart", "maxstretch": 1.15, "tolerance": 0.05},
    },
    {
        "id": "narracao",
        "name": "Narracao / Documentario",
        "description": "Sem apresentador. Voz natural, video congela se preciso.",
        "detail": "Fala 100% natural sem nenhuma compressao ou corte. Se a traducao for mais longa que o original, o video congela no ultimo frame ate a fala terminar. O video final pode ficar mais longo que o original. Perfeito para documentarios e narracoes onde a qualidade da voz e prioridade maxima.",
        "presets": {"sync": "extend", "maxstretch": 2.0, "no_truncate": True},
    },
    {
        "id": "shorts",
        "name": "Shorts / Reels",
        "description": "Video curto. Timing exato, cada frame importa.",
        "detail": "Timing ultra-preciso para videos curtos onde cada segundo conta. Comprime no maximo 10% e corta texto agressivamente se necessario. A duracao do video e identica ao original. Para TikTok, Reels, Shorts onde a sincronia visual e critica.",
        "presets": {"sync": "smart", "maxstretch": 1.1, "tolerance": 0.03},
    },
    {
        "id": "filme",
        "name": "Filme / Serie",
        "description": "Lip-sync importa. Prefere cortar a desincronizar.",
        "detail": "Otimizado para cenas com atores falando. Comprime ate 20% e corta texto para manter sincronia labial. Usa diarizacao para detectar diferentes personagens. Timing preciso para que a voz combine com os movimentos da boca.",
        "presets": {"sync": "smart", "maxstretch": 1.2, "tolerance": 0.05, "diarize": True},
    },
]

SUPPORTED_LANGUAGES = [
    {"code": "pt", "name": "Portugues"},
    {"code": "en", "name": "Ingles"},
    {"code": "es", "name": "Espanhol"},
    {"code": "fr", "name": "Frances"},
    {"code": "de", "name": "Alemao"},
    {"code": "it", "name": "Italiano"},
    {"code": "ja", "name": "Japones"},
    {"code": "zh", "name": "Chines"},
    {"code": "ko", "name": "Coreano"},
    {"code": "ru", "name": "Russo"},
    {"code": "ar", "name": "Arabe"},
    {"code": "hi", "name": "Hindi"},
]


async def get_ollama_models() -> list:
    """Lista modelos disponiveis no Ollama."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {
                        "id": m["name"],
                        "name": m["name"],
                        "size_gb": round(m.get("size", 0) / 1e9, 1),
                        "modified": m.get("modified_at", ""),
                    }
                    for m in data.get("models", [])
                ]
    except Exception:
        pass
    return []


async def get_ollama_status() -> dict:
    """Verifica status do Ollama."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags")
            running_resp = await client.get(f"{OLLAMA_HOST}/api/ps")
            running = []
            if running_resp.status_code == 200:
                running = running_resp.json().get("models", [])
            return {
                "online": resp.status_code == 200,
                "host": OLLAMA_HOST,
                "running_models": [m.get("name", "") for m in running],
            }
    except Exception:
        return {"online": False, "host": OLLAMA_HOST, "running_models": []}


async def start_ollama() -> dict:
    """Inicia o servico Ollama."""
    import subprocess, shutil
    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        return {"success": False, "error": "Ollama nao encontrado. Instale: curl -fsSL https://ollama.com/install.sh | sh"}
    # Verificar se ja esta rodando
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags")
            if resp.status_code == 200:
                return {"success": True, "message": "Ollama ja estava rodando"}
    except Exception:
        pass
    # Iniciar em background
    try:
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Aguardar ate 5s para ficar pronto
        import asyncio
        for _ in range(10):
            await asyncio.sleep(0.5)
            try:
                async with httpx.AsyncClient(timeout=2) as client:
                    resp = await client.get(f"{OLLAMA_HOST}/api/tags")
                    if resp.status_code == 200:
                        return {"success": True, "message": "Ollama iniciado"}
            except Exception:
                continue
        return {"success": False, "error": "Ollama iniciou mas nao respondeu a tempo"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def stop_ollama() -> dict:
    """Para o servico Ollama."""
    import subprocess, signal
    try:
        # Encontrar PID do ollama serve
        result = subprocess.run(["pgrep", "-f", "ollama serve"], capture_output=True, text=True)
        pids = result.stdout.strip().split()
        if not pids:
            return {"success": True, "message": "Ollama nao estava rodando"}
        for pid in pids:
            os.kill(int(pid), signal.SIGTERM)
        # Aguardar parar
        import asyncio
        for _ in range(6):
            await asyncio.sleep(0.5)
            try:
                async with httpx.AsyncClient(timeout=1) as client:
                    await client.get(f"{OLLAMA_HOST}/api/tags")
            except Exception:
                return {"success": True, "message": "Ollama parado"}
        return {"success": True, "message": "Sinal enviado, pode demorar a parar"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def pull_ollama_model(model: str):
    """Baixa um modelo no Ollama (streaming progress)."""
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_HOST}/api/pull",
                json={"name": model, "stream": True},
            ) as resp:
                last_status = ""
                async for line in resp.aiter_lines():
                    if line.strip():
                        import json
                        data = json.loads(line)
                        last_status = data.get("status", "")
                return {"success": True, "status": last_status}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def unload_ollama_model(model: str) -> bool:
    """Descarrega modelo Ollama para liberar VRAM."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": model, "keep_alive": 0},
            )
            return resp.status_code == 200
    except Exception:
        return False


def get_all_options() -> dict:
    """Retorna todas as opcoes disponiveis para a interface."""
    return {
        "tts_engines": TTS_ENGINES,
        "translation_engines": TRANSLATION_ENGINES,
        "whisper_models": WHISPER_MODELS,
        "asr_engines": ASR_ENGINES,
        "edge_voices": EDGE_VOICES,
        "bark_voices": BARK_VOICES,
        "content_types": CONTENT_TYPES,
        "languages": SUPPORTED_LANGUAGES,
    }
