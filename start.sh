#!/bin/bash
# Dublar v5 - Start all services
# Usage: ./start.sh [--docker]

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[DUBLAR]${NC} $1"; }
warn() { echo -e "${YELLOW}[DUBLAR]${NC} $1"; }
err() { echo -e "${RED}[DUBLAR]${NC} $1"; }

cleanup() {
    log "Parando servicos..."
    [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null && log "Backend parado (PID $API_PID)"
    [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null && log "Frontend parado (PID $WEB_PID)"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ---------- Docker mode ----------
if [ "$1" = "--docker" ]; then
    log "Modo Docker com GPU"

    # Verificar Docker
    if ! command -v docker &>/dev/null; then
        err "Docker nao encontrado. Instale: https://docs.docker.com/engine/install/"
        exit 1
    fi

    # Verificar NVIDIA runtime
    if ! docker info 2>/dev/null | grep -q "nvidia"; then
        warn "NVIDIA Container Toolkit pode nao estar instalado"
        warn "Instale: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    fi

    log "Construindo imagens..."
    docker compose build

    log "Subindo servicos..."
    docker compose up
    exit 0
fi

# ---------- Local mode ----------
log "========================================="
log "  Dublar v5 - Iniciando servicos locais"
log "========================================="
echo ""

# 1. Verificar dependencias
log "Verificando dependencias..."

if ! command -v ffmpeg &>/dev/null; then
    err "ffmpeg nao encontrado. Instale: sudo apt install ffmpeg"
    exit 1
fi

# 2. Verificar/criar venv
if [ ! -d "$DIR/venv/bin" ]; then
    warn "Venv nao encontrado. Criando..."
    python3 -m venv "$DIR/venv"
    "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt"
fi

PYTHON="$DIR/venv/bin/python"
PIP="$DIR/venv/bin/pip"

# 3. Instalar deps do backend se necessario
if ! "$PYTHON" -c "import fastapi" 2>/dev/null; then
    log "Instalando dependencias do backend..."
    "$PIP" install -q fastapi "uvicorn[standard]" websockets aiosqlite httpx python-multipart
fi

# 4. Instalar deps do frontend se necessario
if [ ! -d "$DIR/web/node_modules" ]; then
    log "Instalando dependencias do frontend..."
    cd "$DIR/web" && npm install
    cd "$DIR"
fi

# 5. Verificar Ollama
if curl -s http://localhost:11434/api/tags &>/dev/null; then
    OLLAMA_MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; tags=json.load(sys.stdin); print(', '.join(m['name'] for m in tags.get('models',[])))" 2>/dev/null || echo "?")
    log "Ollama: ${GREEN}online${NC} (modelos: $OLLAMA_MODELS)"
else
    warn "Ollama: offline (traducao via Ollama nao disponivel)"
fi

# 6. Verificar GPU
if command -v nvidia-smi &>/dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    log "GPU: ${GREEN}$GPU_NAME${NC}"
else
    warn "GPU: nao detectada (pipeline rodara em CPU)"
fi

# 6.1 Verificar Docker GPU image
if docker image inspect dublar-pro:gpu &>/dev/null 2>&1; then
    log "Docker GPU: ${GREEN}dublar-pro:gpu disponivel${NC} (pipeline rodara com GPU via Docker)"
else
    warn "Docker GPU: imagem dublar-pro:gpu nao encontrada (pipeline rodara em CPU)"
    warn "  Para habilitar GPU: docker build -t dublar-pro:gpu ."
fi

echo ""

# 7. Criar diretorio de jobs
mkdir -p "$DIR/jobs"

# 8. Iniciar Backend API
log "Iniciando Backend API (porta 8000)..."
"$DIR/venv/bin/uvicorn" api.server:app --host 0.0.0.0 --port 8000 --reload \
    > "$DIR/logs_api.log" 2>&1 &
API_PID=$!

# Aguardar backend ficar pronto
for i in $(seq 1 15); do
    if curl -s http://localhost:8000/api/health &>/dev/null; then
        log "Backend API: ${GREEN}http://localhost:8000${NC} (PID $API_PID)"
        break
    fi
    sleep 1
    if [ "$i" -eq 15 ]; then
        err "Backend nao iniciou! Verifique logs_api.log"
        cat "$DIR/logs_api.log"
        exit 1
    fi
done

# 9. Iniciar Frontend
log "Iniciando Frontend (porta 3000)..."
cd "$DIR/web" && npm run dev -- -p 3000 -H 0.0.0.0 \
    > "$DIR/logs_web.log" 2>&1 &
WEB_PID=$!
cd "$DIR"

# Aguardar frontend ficar pronto
for i in $(seq 1 15); do
    if curl -s http://localhost:3000 &>/dev/null; then
        log "Frontend:    ${GREEN}http://localhost:3000${NC} (PID $WEB_PID)"
        break
    fi
    sleep 1
    if [ "$i" -eq 15 ]; then
        err "Frontend nao iniciou! Verifique logs_web.log"
        cat "$DIR/logs_web.log"
        exit 1
    fi
done

# 10. Pronto
IP=$(hostname -I | awk '{print $1}')
echo ""
log "========================================="
log "  Dublar v5 - Tudo no ar!"
log "========================================="
echo ""
log "  Dashboard:     http://$IP:3000"
log "  Nova Dublagem: http://$IP:3000/new"
log "  Jobs:          http://$IP:3000/jobs"
log "  API:           http://$IP:8000/api/health"
log "  API Docs:      http://$IP:8000/docs"
echo ""
log "  Logs backend:  tail -f $DIR/logs_api.log"
log "  Logs frontend: tail -f $DIR/logs_web.log"
echo ""
log "  Pressione Ctrl+C para parar tudo"
echo ""

# Manter rodando
wait
