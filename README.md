# Dublar v5

Pipeline completo de dublagem automatica de videos com IA. Transcreve, traduz e dubla videos de qualquer idioma usando modelos de IA locais e na nuvem. Inclui interface web com monitor em tempo real e suporte GPU via Docker.

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                     │
│                    http://localhost:3000                  │
│  Dashboard | Nova Dublagem | Jobs | Monitor de Progresso │
└──────────────────────┬──────────────────────────────────┘
                       │ REST + WebSocket
┌──────────────────────▼──────────────────────────────────┐
│                   Backend (FastAPI)                       │
│                   http://localhost:8000                   │
│  Job Manager | Model Manager | System Monitor | WebSocket│
└──────────────────────┬──────────────────────────────────┘
                       │ subprocess
┌──────────────────────▼──────────────────────────────────┐
│              Pipeline CLI (dublar_pro_v4.py)              │
│  10 etapas: Download → ASR → Traducao → TTS → Mux       │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                     Motores de IA                         │
│  ASR: Whisper, Parakeet    | TTS: Edge, Bark, XTTS, Piper│
│  Traducao: M2M100, Ollama  | Sync: smart, fit, pad, extend│
└─────────────────────────────────────────────────────────┘
```

## Pipeline - 10 Etapas

| # | Etapa | Descricao |
|---|-------|-----------|
| 1 | Download | Baixa video do YouTube (yt-dlp) ou usa arquivo local |
| 2 | Transcricao (ASR) | Transcreve audio com Whisper ou Parakeet |
| 3 | Traducao | Traduz texto com M2M100 (offline) ou Ollama/LLM |
| 4 | Split | Divide traducao em segmentos sincronizados |
| 5 | TTS | Gera audio com Edge TTS, Bark, XTTS ou Piper |
| 6 | Fade | Aplica fade in/out nos segmentos de audio |
| 7 | Sincronizacao | Ajusta timing (smart/fit/pad/extend) |
| 8 | Concatenacao | Junta todos os segmentos |
| 9 | Pos-Processamento | Normaliza audio, aplica filtros |
| 10 | Mux | Combina audio traduzido com video original |

## Inicio Rapido

### Opcao 1: Local (sem Docker)

```bash
# 1. Clonar repositorio
git clone https://github.com/inematds/dublarv5.git
cd dublarv5

# 2. Instalar dependencias do pipeline
pip install -r requirements.txt

# 3. Backend API
pip install fastapi "uvicorn[standard]" websockets aiosqlite httpx python-multipart
uvicorn api.server:app --host 0.0.0.0 --port 8000 &

# 4. Frontend
cd web && npm install && npm run dev &

# 5. Abrir no navegador
# http://localhost:3000
```

### Opcao 2: Docker com GPU

```bash
# Build e execucao completa
docker compose up --build

# Ou individualmente:
docker build -f Dockerfile.api -t dublar-api:gpu .
docker run --gpus all --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
  -p 8000:8000 -v ./jobs:/app/jobs dublar-api:gpu
```

### Opcao 3: CLI direto

```bash
# CPU (venv local)
python dublar_pro_v4.py --in video.mp4 --tgt pt --tts edge

# GPU (Docker)
./dublar-gpu.sh --in video.mp4 --src en --tgt pt --tts bark

# URL do YouTube
python dublar_pro_v4.py --in "https://youtube.com/watch?v=XXX" --tgt pt
```

## Interface Web

### Dashboard (`/`)
- Status do sistema: GPU, CPU, RAM, Ollama
- Jobs em andamento com barra de progresso
- Historico de jobs recentes

### Nova Dublagem (`/new`)
- **Video**: URL do YouTube ou caminho local
- **Idiomas**: Origem (auto-detect) e destino
- **Tipo de Conteudo**:
  - *Apresentacao/Demo*: sync preciso (video coincide com audio)
  - *Palestra/Talking Head*: sync moderado
  - *Conteudo Geral*: sync livre, prioriza qualidade
- **Motor TTS**: Edge (online), Bark (GPU), XTTS (clone voz), Piper (leve)
- **Motor Traducao**: M2M100 (offline) ou Ollama (LLM local)
- **Modelo Whisper**: tiny, small, medium, large, large-v3
- **Opcoes Avancadas**: sync mode, max stretch, diarizacao, seed

### Monitor de Progresso (`/jobs/[id]`)
- Barra de progresso geral com 10 etapas visuais
- Logs em tempo real via WebSocket
- Botao de cancelar
- Player de video + download ao concluir

### Lista de Jobs (`/jobs`)
- Filtros: todos, em andamento, concluidos, falhos, na fila

## API Endpoints

### Sistema
| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/health` | Health check |
| GET | `/api/system/status` | Status GPU, CPU, RAM, disco, Ollama |

### Modelos
| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/models/options` | Todas opcoes: TTS, vozes, Whisper, idiomas |
| GET | `/api/models/ollama` | Modelos Ollama disponiveis |
| POST | `/api/models/ollama/unload` | Descarregar modelo (liberar VRAM) |

### Jobs
| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| POST | `/api/jobs` | Criar novo job |
| GET | `/api/jobs` | Listar jobs |
| GET | `/api/jobs/{id}` | Status e progresso |
| GET | `/api/jobs/{id}/logs` | Logs do job |
| GET | `/api/jobs/{id}/download` | Download video dublado |
| GET | `/api/jobs/{id}/subtitles` | Download legendas SRT |
| DELETE | `/api/jobs/{id}` | Cancelar job |
| WS | `/ws/jobs/{id}` | Progresso em tempo real |

### Exemplo: Criar Job via cURL

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "input": "https://www.youtube.com/watch?v=VIDEO_ID",
    "tgt_lang": "pt",
    "tts_engine": "edge",
    "translation_engine": "m2m100",
    "whisper_model": "large-v3",
    "sync_mode": "smart",
    "content_type": "palestra"
  }'
```

## Configuracao

### Variaveis de Ambiente

| Variavel | Padrao | Descricao |
|----------|--------|-----------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | URL do backend para o frontend |
| `OLLAMA_HOST` | `http://localhost:11434` | URL do servidor Ollama |

### Presets por Tipo de Conteudo

| Tipo | Sync | Max Stretch | Uso |
|------|------|-------------|-----|
| Apresentacao | smart | 1.15x | Demos, screencasts, tutoriais |
| Palestra | smart | 1.30x | Vlogs, entrevistas, podcasts |
| Geral | fit | 1.50x | Documentarios, narracoes |

### Motores TTS

| Motor | GPU | Internet | Qualidade | Velocidade |
|-------|-----|----------|-----------|------------|
| Edge TTS | Nao | Sim | Boa | Rapido |
| Bark | Sim | Nao | Alta | Lento (CPU) / Rapido (GPU) |
| XTTS | Sim | Nao | Alta + Clone | Medio |
| Piper | Nao | Nao | Media | Muito rapido |

### Motores de Traducao

| Motor | GPU | Internet | Qualidade |
|-------|-----|----------|-----------|
| M2M100 (418M) | Opcional | Nao | Boa |
| M2M100 (1.2B) | Recomendado | Nao | Muito boa |
| Ollama (qwen2.5:14b) | Sim | Nao | Excelente |
| Ollama (qwen2.5:72b) | Sim | Nao | Maxima |

## Presets de Qualidade (CLI)

```bash
# Rapido (Edge + M2M100 + Whisper small)
python dublar_pro_v4.py --in video.mp4 --tgt pt --qualidade rapido

# Balanceado (padrao)
python dublar_pro_v4.py --in video.mp4 --tgt pt --qualidade balanceado

# Maximo (Ollama + Whisper large + diarizacao)
python dublar_pro_v4.py --in video.mp4 --tgt pt --qualidade maximo
```

## Parametros CLI

| Parametro | Descricao | Default |
|-----------|-----------|---------|
| `--in` | Video ou URL YouTube | obrigatorio |
| `--src` | Idioma origem | auto-detectar |
| `--tgt` | Idioma destino | obrigatorio |
| `--tts` | edge, bark, piper, xtts | edge |
| `--tradutor` | m2m100, ollama | m2m100 |
| `--modelo` | Modelo Ollama | qwen2.5:14b |
| `--sync` | none, fit, pad, smart, extend | smart |
| `--whisper-model` | tiny, small, medium, large, large-v3 | medium |
| `--qualidade` | rapido, balanceado, maximo | balanceado |
| `--voice` | Voz TTS especifica | padrao do motor |
| `--diarize` | Detectar multiplos falantes | desativado |
| `--clonar-voz` | Clonar voz original (XTTS) | desativado |
| `--seed` | Seed para reproducibilidade | 42 |
| `--maxstretch` | Max stretch do audio | 1.3 |

## Estrutura do Projeto

```
dublarv5/
├── dublar_pro_v4.py          # Pipeline principal (3000+ linhas)
├── dublar-pro.sh             # Wrapper CLI
├── dublar-gpu.sh             # Wrapper CLI com Docker GPU
├── baixar-e-cortar.sh        # Utilitario: download + corte de video
├── requirements.txt          # Dependencias Python do pipeline
│
├── Dockerfile                # Container GPU para pipeline CLI
├── Dockerfile.api            # Container GPU para backend API
├── docker-compose.yml        # Orquestracao completa
│
├── api/                      # Backend FastAPI
│   ├── server.py             # Endpoints REST + WebSocket
│   ├── job_manager.py        # Gerenciador de jobs e fila
│   ├── model_manager.py      # Opcoes de modelos, vozes, idiomas
│   ├── system_monitor.py     # Monitor GPU/CPU/RAM/disco
│   └── requirements.txt      # Dependencias do backend
│
├── web/                      # Frontend Next.js 16
│   ├── package.json
│   ├── next.config.ts        # Config com proxy API
│   ├── Dockerfile
│   └── src/
│       ├── app/
│       │   ├── layout.tsx    # Layout principal (nav, tema escuro)
│       │   ├── page.tsx      # Dashboard
│       │   ├── new/page.tsx  # Formulario nova dublagem
│       │   └── jobs/
│       │       ├── page.tsx  # Lista de jobs
│       │       └── [id]/page.tsx  # Detalhe + progresso
│       └── lib/
│           └── api.ts        # Client API (fetch + WebSocket)
│
├── dub_work/                 # Arquivos temporarios (gitignored)
└── dublado/                  # Videos finais (gitignored)
```

## Docker GPU - Notas ARM64

Em maquinas ARM64 (como Grace Blackwell), PyTorch via pip instala apenas CPU. A solucao:

1. **Base image**: `nvcr.io/nvidia/pytorch:25.01-py3` (ja tem CUDA)
2. **Flags obrigatorias**: `--gpus all --ipc=host --ulimit memlock=-1 --ulimit stack=67108864`
3. **Preservar PyTorch NVIDIA**: pacotes como bark, faster-whisper, transformers sao instalados com `--no-deps` para nao sobrescrever o torch NVIDIA com versao CPU
4. **Ollama na mesma GPU**: CUDA gerencia memoria automaticamente

## Troubleshooting

### "API offline" no frontend
```bash
curl http://localhost:8000/api/health
# Se falhar, iniciar backend:
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

### PyTorch CPU no Docker
```bash
docker run --gpus all --entrypoint python dublar-pro:gpu \
  -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# Esperado: 2.6.0a0+...nv25.01 True
```

### Bark muito lento
Bark no CPU: ~6s/segmento. Com GPU: ~0.5-1s/segmento.
```bash
./dublar-gpu.sh --in video.mp4 --tgt pt --tts bark
```

### Ollama nao responde
```bash
curl http://localhost:11434/api/tags
# Se falhar: ollama serve
```

## Hardware Testado

| Componente | Detalhes |
|------------|----------|
| GPU | NVIDIA GB10 (Blackwell) - 119.7 GB VRAM, Compute Cap 12.1 |
| CPU | ARM64 - 20 cores Cortex-X925/A725 |
| RAM | 119 GB |
| OS | Ubuntu 24.04 LTS |
