"""Gerenciador de modelos - Ollama, TTS voices, Whisper models."""

import httpx
import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Vozes Edge TTS organizadas por idioma
EDGE_VOICES = {
    "pt-BR": [
        {"id": "pt-BR-AntonioNeural", "name": "Antonio (Masculino)", "gender": "male"},
        {"id": "pt-BR-FranciscaNeural", "name": "Francisca (Feminino)", "gender": "female"},
        {"id": "pt-BR-ThalitaNeural", "name": "Thalita (Feminino)", "gender": "female"},
    ],
    "en-US": [
        {"id": "en-US-GuyNeural", "name": "Guy (Male)", "gender": "male"},
        {"id": "en-US-JennyNeural", "name": "Jenny (Female)", "gender": "female"},
        {"id": "en-US-AriaNeural", "name": "Aria (Female)", "gender": "female"},
    ],
    "es-ES": [
        {"id": "es-ES-AlvaroNeural", "name": "Alvaro (Masculino)", "gender": "male"},
        {"id": "es-ES-ElviraNeural", "name": "Elvira (Femenino)", "gender": "female"},
    ],
    "es-MX": [
        {"id": "es-MX-JorgeNeural", "name": "Jorge (Masculino)", "gender": "male"},
    ],
    "fr-FR": [
        {"id": "fr-FR-HenriNeural", "name": "Henri (Masculin)", "gender": "male"},
        {"id": "fr-FR-DeniseNeural", "name": "Denise (Feminin)", "gender": "female"},
    ],
    "de-DE": [
        {"id": "de-DE-ConradNeural", "name": "Conrad (Mannlich)", "gender": "male"},
        {"id": "de-DE-KatjaNeural", "name": "Katja (Weiblich)", "gender": "female"},
    ],
    "it-IT": [
        {"id": "it-IT-DiegoNeural", "name": "Diego (Maschile)", "gender": "male"},
        {"id": "it-IT-ElsaNeural", "name": "Elsa (Femminile)", "gender": "female"},
    ],
    "ja-JP": [
        {"id": "ja-JP-KeitaNeural", "name": "Keita (Male)", "gender": "male"},
        {"id": "ja-JP-NanamiNeural", "name": "Nanami (Female)", "gender": "female"},
    ],
    "zh-CN": [
        {"id": "zh-CN-YunyangNeural", "name": "Yunyang (Male)", "gender": "male"},
        {"id": "zh-CN-XiaoxiaoNeural", "name": "Xiaoxiao (Female)", "gender": "female"},
    ],
    "ko-KR": [
        {"id": "ko-KR-InJoonNeural", "name": "InJoon (Male)", "gender": "male"},
        {"id": "ko-KR-SunHiNeural", "name": "SunHi (Female)", "gender": "female"},
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
]

TTS_ENGINES = [
    {"id": "edge", "name": "Edge TTS (Microsoft)", "needs_gpu": False, "needs_internet": True, "quality": "excelente"},
    {"id": "bark", "name": "Bark (Suno AI)", "needs_gpu": True, "needs_internet": False, "quality": "boa"},
    {"id": "piper", "name": "Piper (Leve)", "needs_gpu": False, "needs_internet": False, "quality": "razoavel"},
    {"id": "xtts", "name": "XTTS (Clonar Voz)", "needs_gpu": True, "needs_internet": False, "quality": "muito boa"},
]

TRANSLATION_ENGINES = [
    {"id": "m2m100", "name": "M2M100 (Facebook)", "needs_gpu": False, "models": ["418M", "1.2B"]},
    {"id": "ollama", "name": "Ollama (LLM Local)", "needs_gpu": True, "models": "dynamic"},
]

CONTENT_TYPES = [
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
        "edge_voices": EDGE_VOICES,
        "bark_voices": BARK_VOICES,
        "content_types": CONTENT_TYPES,
        "languages": SUPPORTED_LANGUAGES,
    }
