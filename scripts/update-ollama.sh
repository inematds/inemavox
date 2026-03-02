#!/bin/bash
# Atualização Ollama 0.15.2 → 0.17.4 com rollback automático
# Uso: sudo bash scripts/update-ollama.sh [rollback]

set -e

BINARY="/usr/local/bin/ollama"
NEW_BINARY="/tmp/ollama-arm64/bin/ollama"
BACKUP="/usr/local/bin/ollama.backup-0.15.2"

if [[ "$1" == "rollback" ]]; then
    echo "=== ROLLBACK: restaurando 0.15.2 ==="
    if [[ ! -f "$BACKUP" ]]; then
        echo "ERRO: backup não encontrado em $BACKUP"
        exit 1
    fi
    cp "$BACKUP" "$BINARY"
    systemctl restart ollama
    echo "Rollback concluído."
    ollama --version
    exit 0
fi

echo "=== Atualizando Ollama ==="

# Verificar se o novo binário está disponível
if [[ ! -f "$NEW_BINARY" ]]; then
    echo "ERRO: novo binário não encontrado em $NEW_BINARY"
    echo "Execute o download primeiro."
    exit 1
fi

echo "1. Fazendo backup do binário atual..."
cp "$BINARY" "$BACKUP"
echo "   Backup salvo em: $BACKUP"

echo "2. Instalando novo binário..."
cp "$NEW_BINARY" "$BINARY"
chmod +x "$BINARY"

echo "3. Reiniciando serviço Ollama..."
systemctl restart ollama
sleep 3

echo "4. Verificando versão..."
ollama --version

echo ""
echo "=== Atualização concluída! ==="
echo "Para reverter: sudo bash scripts/update-ollama.sh rollback"
