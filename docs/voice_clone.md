# inemaVOX - Clonar Voz

Clona uma voz de referencia e sintetiza texto com ela. Dois pipelines disponiveis: **MTL** (Chatterbox completo) e **VC Pipeline** (Edge TTS → conversao de voz com S3Gen).

---

## Interface Web (`/voice-clone`)

1. Acesse `http://localhost:3010/voice-clone`
2. Digite o texto a sintetizar
3. Faca upload do **audio de referencia** (10–30 segundos, voz clara, sem ruido)
   - A interface analisa a qualidade da referencia em tempo real (score visual)
   - Score: Insuficiente (<3s) / Fraca (3-8s) / Boa (8-20s) / Excelente (>20s)
4. Escolha o engine:
   - **Chatterbox (MTL)**: clona diretamente, qualidade alta, requer GPU
   - **Chatterbox-VC (Pipeline)**: Edge TTS → S3Gen VC, mais rapido
5. Clique em **Clonar Voz** e ouça o resultado
6. Use **↺ Repetir Clone** para gerar variacao com o mesmo audio de referencia

---

## Engines de Clone

### Chatterbox (MTL)
- Pipeline completo de clonagem
- Parametros ajustaveis: `cfg_weight`, `exaggeration`, `temperature`
- Melhor para vozes com caracteristicas unicas
- Requer GPU com VRAM suficiente

### Chatterbox-VC (Pipeline)
- Edge TTS gera o audio de base → S3Gen converte para a voz de referencia
- Mais rapido e consistente
- Nao usa parametros MTL (cfg/exaggeration/temperature)
- Bom para textos longos

---

## Qualidade do Audio de Referencia

| Score | Duracao | Resultado esperado |
|-------|---------|-------------------|
| Insuficiente | < 3s | Nao aceito |
| Fraca | 3 – 8s | Clone impreciso |
| Boa | 8 – 20s | Boa semelhanca |
| Excelente | > 20s | Maxima semelhanca |

**Dicas para bom audio de referencia:**
- Ambiente silencioso, sem eco
- Voz continua (nao frases curtas esparsas)
- Formato WAV ou MP3 com bitrate >= 128kbps
- A interface converte automaticamente para o formato correto (22050Hz → 24000Hz)

---

## Via API

```bash
# Clone com Chatterbox MTL (upload de referencia)
curl -X POST http://localhost:8010/api/jobs/voice-clone \
  -F "ref_audio=@referencia.wav" \
  -F 'config_json={
    "text": "Texto para sintetizar com a voz clonada.",
    "engine": "chatterbox",
    "lang": "pt",
    "cfg_weight": 0.65,
    "exaggeration": 0.35,
    "temperature": 0.75
  }'

# Clone com VC Pipeline
curl -X POST http://localhost:8010/api/jobs/voice-clone \
  -F "ref_audio=@referencia.wav" \
  -F 'config_json={
    "text": "Texto para sintetizar.",
    "engine": "chatterbox-vc",
    "lang": "pt"
  }'

# Download do audio clonado
curl http://localhost:8010/api/jobs/{JOB_ID}/audio -o clone.wav
```

---

## Bugs Corrigidos

- **Referencia mel length mismatch**: referencia convertida automaticamente de 22050Hz para 24000Hz
- **EOS prematuro**: parametros ajustados (`exaggeration=0.35`, `cfg_weight=0.4`) reduzem cortes
- **Referencia trimada para 10s** para evitar padding inconsistente
