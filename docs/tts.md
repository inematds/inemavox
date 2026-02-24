# inemaVOX - Gerar Audio (TTS)

Sintetiza fala a partir de texto usando motores de TTS locais ou online. Suporta Edge TTS (Microsoft), Chatterbox (GPU local) e outros.

---

## Interface Web (`/tts`)

1. Acesse `http://localhost:3010/tts`
2. Digite o texto a sintetizar
3. Escolha o motor TTS e configure:
   - **Edge TTS**: selecione a voz e o idioma
   - **Chatterbox**: ajuste `cfg_weight`, `exaggeration`, `temperature`
4. Clique em **Gerar Audio** e ouça o resultado no player inline
5. Faca download do WAV gerado

---

## Motores TTS

| Motor | GPU | Internet | Qualidade | Notas |
|-------|-----|----------|-----------|-------|
| **Edge TTS** | Nao | Sim | Boa | Microsoft neural voices, rapido |
| **Chatterbox** | Sim | Nao | Alta | Melhor qualidade local, expressivo |
| **Piper** | Nao | Nao | Media | Leve, ideal para CPU |
| **Bark** | Sim | Nao | Alta | Suporta emocoes e sons especiais |

---

## Parametros Chatterbox

| Parametro | Descricao | Faixa | Default |
|-----------|-----------|-------|---------|
| `cfg_weight` | Peso de classificacao livre | 0.0 – 1.0 | 0.65 |
| `exaggeration` | Exageracao emocional | 0.0 – 1.0 | 0.50 |
| `temperature` | Aleatoriedade da geracao | 0.0 – 1.0 | 0.75 |

---

## Via API

```bash
curl -X POST http://localhost:8010/api/jobs/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Ola mundo, isto e um teste de sintese de voz.",
    "engine": "edge",
    "lang": "pt",
    "voice": "pt-BR-AntonioNeural"
  }'

# Chatterbox com parametros
curl -X POST http://localhost:8010/api/jobs/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Texto para sintetizar com Chatterbox.",
    "engine": "chatterbox",
    "lang": "pt",
    "cfg_weight": 0.65,
    "exaggeration": 0.5,
    "temperature": 0.75
  }'

# Download do audio gerado
curl http://localhost:8010/api/jobs/{JOB_ID}/audio -o audio.wav
```
