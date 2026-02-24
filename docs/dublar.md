# inemaVOX - Dublar Video

Traduz e dubla automaticamente qualquer video usando IA local. O pipeline cobre desde o download do video ate a mixagem final com audio dublado sincronizado.

---

## Como funciona

O pipeline executa **10 etapas**:

```
Video/URL
   │
   ▼
1. Download          → yt-dlp (YouTube, TikTok, Instagram...)
2. Extrair audio     → ffmpeg
3. Transcrever (ASR) → Whisper large-v3 / Parakeet 1.1B
4. Traduzir          → M2M100 (offline) / Ollama (LLM local)
5. Dividir segmentos → ffmpeg
6. Sintetizar voz    → Edge TTS / Chatterbox / Bark / Piper
7. Sincronizar       → rubberband (stretch/compress por segmento)
8. Concatenar        → ffmpeg
9. Pos-processar     → normalizacao de volume, filtros
10. Mux final        → video original + audio dublado
   │
   ▼
video_dublado.mp4
```

---

## Interface Web (`/new`)

1. Acesse `http://localhost:3010/new`
2. Cole a URL do video **ou** envie um arquivo local
3. Configure os parametros:
   - **Idioma de origem**: auto-detect ou especifique (ex: `en`, `es`, `ja`)
   - **Idioma de destino**: ex: `pt` para Portugues Brasileiro
   - **Tipo de conteudo**: palestra, podcast, filme, etc (aplica presets automaticamente)
   - **Motor TTS**: veja tabela abaixo
   - **Motor de traducao**: M2M100 (rapido, offline) ou Ollama (melhor qualidade)
   - **Modelo Whisper/Parakeet**: recomendado `large-v3` para maxima qualidade
   - **Multiplos Falantes**: ativa diarizacao (entrevistas, podcasts, debates)
4. Clique em **Iniciar Dublagem** e acompanhe o progresso etapa por etapa
5. Para re-tentar um job, clique em **↺ Re-tentar** — abre o formulario pre-preenchido para ajustar a configuracao antes de reenviar

---

## Multiplos Falantes (Diarizacao)

Para videos com mais de uma pessoa falando (podcasts, entrevistas, debates):

1. Marque a opcao **Multiplos Falantes** no formulario
2. Opcionalmente informe o **numero de falantes** (deixe vazio para detectar automaticamente)
3. Use **Edge TTS** como motor de voz — e o unico que atribui vozes diferentes por falante

Com diarizacao ativa, o pipeline:
- Detecta automaticamente os falantes usando **pyannote**
- Atribui cada segmento ao seu falante
- No Edge TTS, cada `SPEAKER_XX` recebe uma voz distinta automaticamente

---

## Motores TTS

| Motor | GPU | Internet | Multi-voz | Qualidade | Notas |
|-------|-----|----------|-----------|-----------|-------|
| **Edge TTS** | Nao | Sim | Sim | Boa | Microsoft neural voices; suporta multi-falante |
| **Chatterbox** | Sim | Nao | Nao | Alta | Melhor qualidade local; suporta clone de voz |
| **Bark** | Sim | Nao | Nao | Alta | Expressivo, suporta emocoes |
| **Piper** | Nao | Nao | Nao | Media | Leve, ideal para CPU |

### Vozes Edge TTS (exemplos)

| Idioma | Vozes |
|--------|-------|
| Portugues BR | `pt-BR-FranciscaNeural` (F), `pt-BR-AntonioNeural` (M) |
| Portugues PT | `pt-PT-RaquelNeural` (F), `pt-PT-DuarteNeural` (M) |
| Ingles | `en-US-JennyNeural`, `en-US-GuyNeural` |
| Espanhol | `es-ES-ElviraNeural`, `es-MX-DaliaNeural` |

---

## Motores de Traducao

| Motor | GPU | Internet | Qualidade | Notas |
|-------|-----|----------|-----------|-------|
| **M2M100 418M** | Opcional | Nao | Boa | Rapido, modelo menor |
| **M2M100 1.2B** | Recomendado | Nao | Muito boa | Padrao recomendado |
| **Ollama** | Sim | Nao | Excelente | Depende do modelo; usa contexto |

> **Dica:** Ollama com `qwen2.5:14b` produz a melhor qualidade de traducao, especialmente para contextos tecnicos e linguagem coloquial.

---

## Modos de Sincronizacao

| Modo | Descricao | Quando usar |
|------|-----------|-------------|
| `smart` | Ajusta automaticamente (stretch + padding) | Padrao para maioria dos casos |
| `fit` | Estica/comprime o audio para caber exatamente | Boa sincronia labial |
| `pad` | Adiciona silencio ao final se o audio for curto | Preserva timbre natural |
| `extend` | Estica apenas, nunca corta | Vozes sensiveis a compressao |
| `none` | Sem sincronizacao | Debug / testes |

---

## Saida

```
jobs/{id}/
├── dublado/
│   └── video_dublado.mp4     # Video final com audio dublado
└── dub_work/
    ├── asr.srt               # Legendas no idioma original
    └── asr_trad.srt          # Legendas traduzidas
```

O resultado fica disponivel no job detail (`/jobs/{id}`) com:
- Player inline do video dublado
- Titulo do video detectado automaticamente
- Download do MP4 e das legendas SRT

---

## Via API

```bash
# Dublar por URL
curl -X POST http://localhost:8010/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "input": "https://www.youtube.com/watch?v=VIDEO_ID",
    "tgt_lang": "pt",
    "tts_engine": "edge",
    "translation_engine": "m2m100",
    "whisper_model": "large-v3",
    "sync_mode": "smart"
  }'

# Dublar com multiplos falantes
curl -X POST http://localhost:8010/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "input": "https://www.youtube.com/watch?v=VIDEO_ID",
    "tgt_lang": "pt",
    "tts_engine": "edge",
    "diarize": true,
    "num_speakers": 2
  }'

# Dublar com upload de arquivo
curl -X POST http://localhost:8010/api/jobs/upload \
  -F "file=@video.mp4" \
  -F 'config_json={"tgt_lang":"pt","tts_engine":"edge","translation_engine":"m2m100"}'
```

---

## Dicas

- Use `large-v3` para idiomas com sotaque forte ou audio com ruido
- Para videos com multiplos falantes, ative **Multiplos Falantes** + Edge TTS
- Se o audio dublado ficar fora de sincronia, tente sync `fit` ou reduza maxstretch para `1.1`
- M2M100 e totalmente offline; Ollama requer o servico rodando em `localhost:11434`
- Parakeet so funciona com audio em ingles; use Whisper para outros idiomas
- Chatterbox oferece a melhor qualidade local com suporte a clone de voz
