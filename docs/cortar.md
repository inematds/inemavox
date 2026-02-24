# inemaVOX - Cortar Video

Extrai clips de um video por timestamps manuais ou deixa a IA identificar automaticamente os melhores momentos. Suporta dois modos de analise por IA: **Viral** (momentos mais envolventes) e **Por Assunto** (segmentacao por topico).

---

## Como funciona

### Modo Manual

```
Video + Timestamps ("00:30-02:15, 05:00-07:30")
   │
   ▼
ffmpeg recorta cada segmento sem reencoding (rapido)
   │
   ▼
clip_01.mp4, clip_02.mp4, ..., clips.zip
```

### Modo Analise (IA)

```
Video
   │
   ▼
1. Download/preparar  → yt-dlp ou arquivo local
2. Extrair audio      → ffmpeg
3. Transcrever        → Whisper large-v3
4. Analisar com LLM   → Ollama / OpenAI / Anthropic / Groq...
   (Viral: detecta melhores momentos para viralizar)
   (Assunto: identifica mudancas de topico e agrupa)
5. Recortar clips     → ffmpeg
6. Empacotar          → clips.zip
   │
   ▼
clip_01.mp4 ... clip_N.mp4 + clips.zip
```

---

## Interface Web (`/cut`)

1. Acesse `http://localhost:3010/cut`
2. Cole a URL do video **ou** envie um arquivo local
3. Escolha o modo:

### Modo Manual
- Informe os timestamps no formato `MM:SS-MM:SS` separados por virgula
- Exemplos: `00:30-02:15, 05:00-07:30, 10:00-12:45`
- Formatos aceitos: `SS`, `MM:SS`, `HH:MM:SS`

### Modo Analise (IA)
- Escolha o sub-modo: **Viral** ou **Assunto**
  - **Viral**: LLM identifica os N melhores momentos para engajamento (shorts, reels)
  - **Assunto**: LLM segmenta o video por topico (lives longas, podcasts, aulas)
- Configure o LLM provider e modelo
- No modo Viral: configure numero de clips e duracao min/max
- No modo Assunto: numero de clips e 0 significa automatico
- Prompts customizaveis (system + user) com botao "Restaurar padrao"

4. Clique em **Cortar** e acompanhe o progresso
5. Ao concluir, assista cada clip no player inline e faca download individual ou em ZIP

---

## CLI (`clipar_v1.py`)

```bash
# Modo manual por timestamps
python clipar_v1.py \
  --in video.mp4 \
  --outdir ./clips \
  --mode manual \
  --timestamps "00:30-02:15, 05:00-07:30"

# Modo viral com Ollama local
python clipar_v1.py \
  --in video.mp4 \
  --outdir ./clips \
  --mode viral \
  --ollama-model qwen2.5:7b \
  --num-clips 5 \
  --min-duration 30 \
  --max-duration 90

# Modo por assunto (segmentacao de topicos)
python clipar_v1.py \
  --in podcast.mp4 \
  --outdir ./clips \
  --mode topics \
  --ollama-model qwen2.5:14b

# Modo viral com Groq (rapido e gratuito)
python clipar_v1.py \
  --in video.mp4 \
  --outdir ./clips \
  --mode viral \
  --llm-provider groq \
  --llm-model llama-3.3-70b-versatile \
  --llm-api-key gsk_... \
  --num-clips 5
```

### Parametros

| Parametro | Descricao | Opcoes | Default |
|-----------|-----------|--------|---------|
| `--in` | Video ou URL | arquivo local, URL YouTube/TikTok/etc | obrigatorio |
| `--outdir` | Diretorio de saida | qualquer path | obrigatorio |
| `--mode` | Modo de corte | `manual`, `viral`, `topics` | `manual` |
| `--timestamps` | Timestamps (modo manual) | `"HH:MM:SS-HH:MM:SS, ..."` | — |
| `--num-clips` | Numero de clips (IA) | inteiro, 0=auto | `5` |
| `--min-duration` | Duracao minima em segundos | inteiro | `30` |
| `--max-duration` | Duracao maxima em segundos | inteiro | `120` |
| `--ollama-model` | Modelo Ollama | `qwen2.5:7b`, `qwen2.5:14b`... | `qwen2.5:7b` |
| `--llm-provider` | Provider externo | `ollama`, `openai`, `anthropic`, `groq`, `deepseek`, `openrouter` | `ollama` |
| `--llm-model` | Modelo do provider | ex: `gpt-4o`, `claude-3-5-sonnet` | — |
| `--llm-api-key` | API key do provider | string | — |
| `--whisper-model` | Modelo Whisper | `tiny`, `small`, `medium`, `large-v3` | `large-v3` |

---

## Providers LLM

| Provider | Parametro | Notas |
|----------|-----------|-------|
| Ollama (local) | `ollama` | Gratuito, sem internet, requer GPU |
| OpenAI | `openai` | `gpt-4o`, `gpt-4o-mini` |
| Anthropic | `anthropic` | `claude-3-5-sonnet-20241022` |
| Groq | `groq` | Rapido, tier gratuito disponivel |
| DeepSeek | `deepseek` | Custo muito baixo |
| OpenRouter | `openrouter` | Acesso a muitos providers |
| Custom | `custom` | Qualquer API OpenAI-compativel com `--llm-base-url` |

---

## Via API

```bash
# Corte manual
curl -X POST http://localhost:8010/api/jobs/cut \
  -H "Content-Type: application/json" \
  -d '{
    "input": "https://www.youtube.com/watch?v=VIDEO_ID",
    "mode": "manual",
    "timestamps": "00:30-02:15, 05:00-07:30"
  }'

# Corte viral com Ollama
curl -X POST http://localhost:8010/api/jobs/cut \
  -H "Content-Type: application/json" \
  -d '{
    "input": "https://www.youtube.com/watch?v=VIDEO_ID",
    "mode": "viral",
    "ollama_model": "qwen2.5:7b",
    "num_clips": 5,
    "min_duration": 30,
    "max_duration": 90
  }'

# Corte por assunto
curl -X POST http://localhost:8010/api/jobs/cut \
  -H "Content-Type: application/json" \
  -d '{
    "input": "https://www.youtube.com/watch?v=VIDEO_ID",
    "mode": "topics",
    "ollama_model": "qwen2.5:14b",
    "num_clips": 0
  }'

# Listar clips gerados
curl http://localhost:8010/api/jobs/{JOB_ID}/clips

# Download ZIP
curl http://localhost:8010/api/jobs/{JOB_ID}/clips/zip -o clips.zip
```

---

## Dicas

- No modo manual o recorte e sem reencoding — muito rapido
- **Viral**: ideal para Shorts/Reels, use `max_duration 60`
- **Assunto**: ideal para lives longas e podcasts; use `num_clips 0` para detectar automaticamente
- Groq com `llama-3.3-70b-versatile` oferece excelente qualidade com tier gratuito
- Os prompts customizaveis permitem ajustar o criterio de selecao sem alterar o codigo
