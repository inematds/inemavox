# Dublar Pro v4 - Dockerfile com GPU NVIDIA
# Base: NVIDIA PyTorch container (testado com GB10 Blackwell)
FROM nvcr.io/nvidia/pytorch:25.01-py3

WORKDIR /app

# Dependencias de sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    rubberband-cli \
    && rm -rf /var/lib/apt/lists/*

# Salvar versao do PyTorch NVIDIA antes de instalar deps
# (pip pode sobrescrever com versao CPU)
RUN TORCH_VER=$(python -c "import torch; print(torch.__version__)") && \
    echo "PyTorch NVIDIA: $TORCH_VER (CUDA: $(python -c 'import torch; print(torch.cuda.is_available())'))"

# Dependencias que NAO dependem de torch - instalar normalmente
RUN pip install --no-cache-dir \
    edge-tts>=6.1.0 \
    sentencepiece>=0.1.99 \
    protobuf>=3.20.0 \
    sacremoses>=0.0.53 \
    httpx>=0.24.0 \
    scipy>=1.10.0 \
    soundfile>=0.12.0 \
    yt-dlp>=2023.0.0 \
    Pillow>=10.0.0 \
    librosa>=0.10.0

# Dependencias que dependem de torch - instalar SEM dependencias
# para nao sobrescrever o PyTorch NVIDIA com versao CPU
RUN pip install --no-cache-dir --no-deps \
    faster-whisper ctranslate2 tokenizers huggingface-hub

# Dependencias de faster-whisper/ctranslate2 que nao puxam torch
RUN pip install --no-cache-dir av pyyaml onnxruntime

RUN pip install --no-cache-dir --no-deps \
    bark encodec funcy

RUN pip install --no-cache-dir --no-deps transformers safetensors accelerate

# OpenAI Whisper (usa PyTorch CUDA diretamente - fallback para ARM64 onde CTranslate2 nao tem CUDA)
RUN pip install --no-cache-dir --no-deps openai-whisper
RUN pip install --no-cache-dir tiktoken more-itertools

# Verificar que PyTorch NVIDIA sobreviveu (CUDA check nao funciona no build, so em runtime)
RUN python -c "\
import torch; \
v = torch.__version__; \
print(f'PyTorch: {v}'); \
is_nvidia = 'nv' in v or '+cu' in v; \
is_cpu = '+cpu' in v; \
print(f'NVIDIA build: {is_nvidia}, CPU-only: {is_cpu}'); \
assert not is_cpu, f'PyTorch foi substituido pela versao CPU! ({v})'; \
"

# Copiar pipeline
COPY dublar_pro_v4.py .
COPY dublar-pro.sh .

# Diretorios de trabalho e saida
RUN mkdir -p /app/dub_work /app/dublado

ENTRYPOINT ["python", "dublar_pro_v4.py"]
