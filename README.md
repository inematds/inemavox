# inemaVOX

<p align="center">
  <img src="docs/inemavox.jpg" alt="inemaVOX - Suite de Voz com IA" width="800"/>
</p>

Suite de voz com IA local. Dubla, transcreve, corta e baixa videos com modelos rodando direto na GPU — sem custo de API, sem nuvem. Interface web com monitor em tempo real.

**Versao atual: 5.3.1**

---

## Recursos

| Recurso | Script | Descricao | Docs |
|---------|--------|-----------|------|
| **Baixar** | `baixar_v1.py` | Download de videos do YouTube, TikTok, Instagram, Facebook e +1000 sites | [docs/baixar.md](docs/baixar.md) |
| **Dublar** | `dublar_pro_v5.py` | Traduz e dubla videos com IA (10 etapas) | [docs/dublar.md](docs/dublar.md) |
| **Transcrever** | `transcrever_v1.py` | Gera legendas SRT/TXT/JSON com Whisper ou Parakeet | [docs/transcrever.md](docs/transcrever.md) |
| **Cortar** | `clipar_v1.py` | Extrai clips por timestamps ou detecta momentos virais com LLM | [docs/cortar.md](docs/cortar.md) |

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                         │
│                    http://localhost:3000                      │
│  Dashboard | Dublar | Transcrever | Cortar | Baixar | Jobs  │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST + WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                   Backend (FastAPI)                           │
│                   http://localhost:8000                       │
│  Job Manager | Model Manager | System Monitor | WebSocket    │
└──────────────────────────┬──────────────────────────────────┘
                           │ Docker subprocess
┌──────────────────────────▼──────────────────────────────────┐
│              Pipelines (montados como volume no Docker)       │
│  dublar_pro_v5.py | clipar_v1.py | transcrever_v1.py        │
│  baixar_v1.py                                                │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     Motores de IA                             │
│  ASR: Whisper large-v3, Parakeet 1.1B                        │
│  TTS: Edge TTS, Bark, XTTS, Piper                            │
│  Traducao: M2M100, Ollama (qualquer modelo local)            │
│  LLM: Ollama, OpenAI, Anthropic, Groq, DeepSeek, OpenRouter  │
└─────────────────────────────────────────────────────────────┘
```

---

## Inicio Rapido

### Opcao 1: Script de inicializacao

```bash
./start.sh
# API: http://localhost:8000
# Web: http://localhost:3000
```

### Opcao 2: Manual

```bash
# Backend
pip install fastapi "uvicorn[standard]" websockets httpx python-multipart
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload &

# Frontend
cd web && npm install && npm run dev -- -p 3000 -H 0.0.0.0 &
```

### Opcao 3: Docker GPU

```bash
# Build da imagem do pipeline
docker build -t inemavox:gpu .

# Iniciar servicos
./start.sh
```

---

## Interface Web

### Dashboard (`/`)
- Status do sistema: GPU, CPU, RAM, Ollama
- Cards de acao rapida para cada funcionalidade
- Tabela de jobs recentes com tipo, status e link para detalhes

### Baixar Video (`/download`) — *novo em v5.3.0*
- Cole o link do video (YouTube, TikTok, Instagram, Facebook, Twitter/X, Twitch, +1000 sites)
- Escolha a qualidade: Melhor, 1080p, 720p, 480p ou So Audio (MP3)
- Acompanhe o progresso do download em tempo real
- Player inline e download direto ao concluir

### Dublar Video (`/new`)
- URL do YouTube ou upload de arquivo local
- Idioma de origem (auto-detect) e destino
- Motor TTS: Edge (online), Bark (GPU), XTTS (clone de voz), Piper (leve)
- Motor de traducao: M2M100 (offline) ou Ollama (LLM local)
- Modelo Whisper: tiny, small, medium, large, large-v3
- Opcoes avancadas: sync mode, diarizacao, stretch maximo, seed

### Transcrever Video (`/transcribe`)
- URL ou upload de arquivo
- Motor ASR: Whisper ou Parakeet (NVIDIA)
- Modelo Whisper configuravel
- Idioma de origem (auto-detect ou especifico)
- Download da transcricao em SRT, TXT ou JSON

### Cortar Video (`/cut`)
- **Modo Manual**: informe timestamps no formato `MM:SS-MM:SS` separados por virgula
- **Modo Viral (IA)**: LLM analisa a transcricao e identifica os N melhores momentos
  - Providers: Ollama (local), OpenAI, Anthropic, Groq, DeepSeek, Together, OpenRouter, Custom
  - Configuravel: numero de clips, duracao minima/maxima, modelo Whisper
- Download individual ou ZIP com todos os clips

### Lista de Jobs (`/jobs`)
- Historico completo com tipo (Dublagem/Transcricao/Corte/Download) e status
- **Filtro por tipo**: Todos / Dublagem / Corte / Transcricao / Download (com contador)
- **Filtro por status**: Todos / Running / Queued / Completed / Failed (com contador)
- Barra de progresso inline para jobs em execucao (etapa atual, %, ETA)
- Tag GPU/CPU por job
- Info especifica por tipo (idiomas, modo, ASR...)
- Botao de excluir job direto na lista (sem entrar no detalhe)
- Link direto para detalhes de cada job

### Detalhe do Job (`/jobs/[id]`)
- Barra de progresso por etapa com tempo decorrido e estimativas para etapas pendentes
- Progresso detalhado de ferramentas em tempo real (%, velocidade, ETA dentro da etapa)
- Titulo e resumo automatico do video (para jobs de Dublagem e Transcricao)
- Player inline para clips (modo Corte) com lista, timecodes e descricoes geradas por IA
- Logs expansiveis via WebSocket em tempo real
- Secao de resultado especifica por tipo de job
- Acoes: cancelar (job ativo), re-tentar (job falho/cancelado), excluir

---

## Scripts CLI

Cada script tem documentacao detalhada com todos os parametros, exemplos e dicas:

| Script | Documentacao |
|--------|-------------|
| `baixar_v1.py` | [docs/baixar.md](docs/baixar.md) — qualidades, sites suportados, exemplos |
| `dublar_pro_v5.py` | [docs/dublar.md](docs/dublar.md) — pipeline, TTS, sync, traducao |
| `transcrever_v1.py` | [docs/transcrever.md](docs/transcrever.md) — ASR, formatos de saida, idiomas |
| `clipar_v1.py` | [docs/cortar.md](docs/cortar.md) — modo manual, modo viral, providers LLM |

### Exemplos rapidos

```bash
# Baixar video
python baixar_v1.py --url "https://youtube.com/watch?v=ID" --outdir ./download --quality 1080p

# Dublar
python dublar_pro_v5.py --in "https://youtube.com/watch?v=ID" --tgt pt --tts edge

# Transcrever
python transcrever_v1.py --in video.mp4 --outdir ./transcription --whisper-model large-v3

# Cortar (manual)
python clipar_v1.py --in video.mp4 --outdir ./clips --mode manual --timestamps "00:30-02:15, 05:00-07:30"

# Cortar (viral com IA)
python clipar_v1.py --in video.mp4 --outdir ./clips --mode viral --ollama-model qwen2.5:7b --num-clips 5
```

---

## API REST

### Sistema

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/health` | Health check e versao |
| GET | `/api/system/status` | Status GPU, CPU, RAM, disco, Ollama |
| GET | `/api/stats` | Estatisticas e ETAs aprendidos |

### Modelos e Ollama

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/models/options` | Todas opcoes: TTS, vozes, Whisper, idiomas |
| GET | `/api/models/ollama` | Modelos Ollama disponiveis |
| POST | `/api/models/ollama/unload` | Descarregar modelo (liberar VRAM) |
| GET | `/api/ollama/status` | Status do Ollama |
| POST | `/api/ollama/start` | Iniciar servico Ollama |
| POST | `/api/ollama/stop` | Parar servico Ollama |
| POST | `/api/ollama/pull` | Baixar modelo Ollama |

### Jobs — Criar

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| POST | `/api/jobs` | Criar job de dublagem |
| POST | `/api/jobs/upload` | Criar job de dublagem com upload de arquivo |
| POST | `/api/jobs/download` | Criar job de download de video |
| POST | `/api/jobs/transcribe` | Criar job de transcricao |
| POST | `/api/jobs/transcribe/upload` | Criar job de transcricao com upload |
| POST | `/api/jobs/cut` | Criar job de corte de clips |
| POST | `/api/jobs/cut/upload` | Criar job de corte com upload |

### Jobs — Gerenciar

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/jobs` | Listar todos os jobs |
| GET | `/api/jobs/{id}` | Status e progresso do job |
| GET | `/api/jobs/{id}/logs` | Logs do job |
| DELETE | `/api/jobs/{id}` | Cancelar job |
| DELETE | `/api/jobs/{id}?delete=true` | Excluir job e arquivos |
| POST | `/api/jobs/{id}/retry` | Re-tentar job falho |

### Jobs — Resultados

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/jobs/{id}/download` | Download do video dublado |
| GET | `/api/jobs/{id}/download-file` | Download do video baixado |
| GET | `/api/jobs/{id}/subtitles?lang=trad` | Download de legendas SRT |
| GET | `/api/jobs/{id}/transcript?format=srt` | Transcricao (srt/txt/json) |
| GET | `/api/jobs/{id}/clips` | Lista de clips gerados |
| GET | `/api/jobs/{id}/clips/{nome}` | Download de clip individual |
| GET | `/api/jobs/{id}/clips/zip` | Download de todos os clips em ZIP |
| GET | `/api/jobs/{id}/transcript-summary` | Titulo e preview da transcricao (gerado on-the-fly) |
| GET | `/api/jobs/{id}/video-summary` | Titulo e resumo do video dublado |

### WebSocket

| Endpoint | Descricao |
|----------|-----------|
| `WS /ws/jobs/{id}` | Progresso em tempo real |

---

## Exemplos via cURL

### Criar job de download

```bash
curl -X POST http://localhost:8000/api/jobs/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=VIDEO_ID", "quality": "1080p"}'
```

### Criar job de dublagem (URL)

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "input": "https://www.youtube.com/watch?v=VIDEO_ID",
    "tgt_lang": "pt",
    "tts_engine": "edge",
    "translation_engine": "m2m100",
    "whisper_model": "large-v3",
    "sync_mode": "smart"
  }'
```

### Criar job de transcricao com upload

```bash
curl -X POST http://localhost:8000/api/jobs/transcribe/upload \
  -F "file=@video.mp4" \
  -F 'config_json={"asr_engine":"whisper","whisper_model":"large-v3"}'
```

### Criar job de corte com timestamps

```bash
curl -X POST http://localhost:8000/api/jobs/cut \
  -H "Content-Type: application/json" \
  -d '{
    "input": "https://www.youtube.com/watch?v=VIDEO_ID",
    "mode": "manual",
    "timestamps": "00:30-02:15, 05:00-07:30"
  }'
```

### Consultar status do job

```bash
curl http://localhost:8000/api/jobs/JOB_ID
```

---

## Estrutura de Arquivos por Job

```
jobs/
└── {job_id}/
    ├── config.json          # Configuracao do job
    ├── output.log           # Logs de execucao
    ├── stage_times.json     # Tempo por etapa
    ├── dub_work/
    │   └── checkpoint.json  # Progresso (last_step_num)
    │
    ├── dublado/             # Jobs de dublagem
    │   └── video_dublado.mp4
    │
    ├── transcription/       # Jobs de transcricao
    │   ├── transcript.srt
    │   ├── transcript.txt
    │   └── transcript.json
    │
    ├── clips/               # Jobs de corte
    │   ├── clip_01.mp4
    │   ├── clip_02.mp4
    │   └── clips.zip
    │
    └── download/            # Jobs de download
        └── video.mp4
```

---

## Estrutura do Projeto

```
inemavox/
├── dublar_pro_v5.py          # Pipeline de dublagem (10 etapas)
├── transcrever_v1.py         # Pipeline de transcricao (4 etapas)
├── clipar_v1.py              # Pipeline de corte de clips
├── baixar_v1.py              # Download via yt-dlp
├── requirements.txt          # Dependencias Python do pipeline
├── Dockerfile                # Container GPU (base: nvidia/pytorch:25.01-py3)
│
├── api/                      # Backend FastAPI
│   ├── server.py             # Endpoints REST + WebSocket (versao APP_VERSION)
│   ├── job_manager.py        # Gerenciador de fila e execucao dos jobs
│   ├── model_manager.py      # Opcoes de modelos, vozes, idiomas, Ollama
│   ├── system_monitor.py     # Monitor GPU/CPU/RAM/disco
│   └── stats_tracker.py      # Estatisticas e ETAs aprendidos
│
└── web/                      # Frontend Next.js
    ├── next.config.ts        # Proxy reverso para /api → :8000
    └── src/
        ├── app/
        │   ├── layout.tsx        # Navbar + tema escuro
        │   ├── page.tsx          # Dashboard
        │   ├── nav-version.tsx   # Versao dinamica no navbar
        │   ├── new/page.tsx      # Formulario de dublagem
        │   ├── transcribe/page.tsx  # Formulario de transcricao
        │   ├── cut/page.tsx      # Formulario de corte
        │   ├── download/page.tsx # Formulario de download
        │   └── jobs/
        │       ├── page.tsx      # Lista de jobs
        │       └── [id]/page.tsx # Detalhe + progresso em tempo real
        └── lib/
            └── api.ts            # Funcoes de acesso a API
```

---

## Funcoes da API Frontend (`web/src/lib/api.ts`)

| Funcao | Descricao |
|--------|-----------|
| `createJob(config)` | Criar job de dublagem |
| `createJobWithUpload(file, config, onProgress)` | Dublagem com upload |
| `createDownloadJob(config)` | Criar job de download |
| `createTranscriptionJob(config)` | Criar job de transcricao |
| `createTranscriptionJobWithUpload(file, config, onProgress)` | Transcricao com upload |
| `createCutJob(config)` | Criar job de corte |
| `createCutJobWithUpload(file, config, onProgress)` | Corte com upload |
| `listJobs()` | Listar todos os jobs |
| `getJob(jobId)` | Buscar job por ID |
| `getJobLogs(jobId, lastN)` | Buscar logs do job |
| `cancelJob(jobId)` | Cancelar job |
| `deleteJob(jobId)` | Excluir job e arquivos |
| `retryJob(jobId)` | Re-tentar job falho |
| `getDownloadUrl(jobId)` | URL do video dublado |
| `getDownloadFileUrl(jobId)` | URL do video baixado |
| `getSubtitlesUrl(jobId, lang)` | URL das legendas |
| `getTranscriptUrl(jobId, format)` | URL da transcricao |
| `getClips(jobId)` | Listar clips do job |
| `getClipUrl(jobId, clipName)` | URL de clip individual |
| `getClipsZipUrl(jobId)` | URL do ZIP de clips |
| `getTranscriptSummary(jobId)` | Titulo e preview da transcricao |
| `getVideoSummary(jobId)` | Titulo e resumo do video dublado |
| `getSystemStatus()` | Status do sistema |
| `getOptions()` | Opcoes de modelos |
| `getOllamaStatus()` | Status do Ollama |
| `startOllama()` | Iniciar Ollama |
| `stopOllama()` | Parar Ollama |
| `pullOllamaModel(model)` | Baixar modelo Ollama |
| `createJobWebSocket(jobId)` | WebSocket de progresso |

---

## Motores de IA

| Tipo | Motores | Detalhes |
|------|---------|----------|
| **TTS** | Edge TTS, Bark, XTTS, Piper | Ver [docs/dublar.md#motores-tts](docs/dublar.md#motores-tts) |
| **ASR** | Whisper (tiny→large-v3), Parakeet 1.1B | Ver [docs/transcrever.md#modelos-asr](docs/transcrever.md#modelos-asr) |
| **Traducao** | M2M100 418M/1.2B, Ollama | Ver [docs/dublar.md#motores-de-traducao](docs/dublar.md#motores-de-traducao) |
| **LLM (corte viral)** | Ollama, OpenAI, Anthropic, Groq, DeepSeek, OpenRouter | Ver [docs/cortar.md#providers-llm-modo-viral](docs/cortar.md#providers-llm-modo-viral) |

---

## Configuracao

### Variaveis de Ambiente

| Variavel | Padrao | Descricao |
|----------|--------|-----------|
| `JOBS_DIR` | `jobs/` | Diretorio para armazenar os jobs |
| `DOCKER_GPU_IMAGE` | `inemavox:gpu` | Imagem Docker com GPU |
| `OLLAMA_HOST` | `http://localhost:11434` | URL do servidor Ollama |
| `NEXT_PUBLIC_API_URL` | `""` (relativo) | URL do backend para o frontend |

### Docker — Flags obrigatorias

```bash
docker run \
  --gpus all \
  --ipc=host \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  --network host \
  inemavox:gpu
```

---

## Troubleshooting

### API offline no frontend

```bash
curl http://localhost:8000/api/health
# Se falhar:
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

### GPU nao detectada no Docker

```bash
docker run --gpus all --entrypoint python inemavox:gpu \
  -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# Esperado: 2.6.0a0+...nv25.01 True
```

### Job preso em "queued"

```bash
# Verificar se ha um container Docker travado
docker ps | grep inemavox
# Matar se necessario:
docker kill inemavox-{job_id}
```

### Ollama nao responde

```bash
curl http://localhost:11434/api/tags
# Se falhar:
ollama serve
```

### yt-dlp desatualizado (falha em novos sites)

```bash
pip install -U yt-dlp
# Ou dentro do Docker:
docker exec {container} pip install -U yt-dlp
```

---

## Hardware Testado

| Componente | Detalhes |
|------------|----------|
| GPU | NVIDIA GB10 Blackwell — CUDA 12.8, driver 580.95 |
| CPU | ARM64 — 20 cores |
| RAM | 119 GB |
| OS | Ubuntu 24.04 LTS |
| Base Image | `nvcr.io/nvidia/pytorch:25.01-py3` |

---

## Historico de Versoes

| Versao | Descricao |
|--------|-----------|
| **5.3.1** | UX: filtros na lista de jobs, titulo/resumo automatico nos resultados, player de clips com timecodes; fixes de checkpoint e recuperacao de status apos hot-reload |
| 5.3.0 | Feature Baixar: download de videos do YouTube e +1000 sites via yt-dlp |
| 5.2.x | Features Cortar (clipar_v1.py) e Transcrever (transcrever_v1.py), modo viral com LLM |
| 5.1.x | Interface web multi-modo, sistema de jobs com checkpoint e recuperacao |
| 5.0.x | Pipeline v5 com suporte a Docker GPU Blackwell |
