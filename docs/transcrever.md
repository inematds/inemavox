# inemaVOX - Transcrever Video

Gera legendas e transcricoes a partir de qualquer video ou audio usando modelos de reconhecimento de fala (ASR) com GPU. Suporta dezenas de idiomas e exporta nos formatos SRT, TXT e JSON.

---

## Como funciona

```
Video/URL
   │
   ▼
1. Download/preparar  → yt-dlp ou arquivo local
2. Extrair audio      → ffmpeg (converte para WAV mono 16kHz)
3. Transcrever (ASR)  → Whisper / Parakeet
4. Exportar legendas  → SRT + TXT + JSON
   │
   ▼
transcript.srt / transcript.txt / transcript.json
```

---

## Interface Web (`/transcribe`)

1. Acesse `http://localhost:3010/transcribe`
2. Cole a URL do video **ou** envie um arquivo local
3. Configure:
   - **Motor ASR**: Whisper (multiplos idiomas) ou Parakeet (ingles, muito rapido)
   - **Modelo Whisper**: de `tiny` (rapido) a `large-v3` (maxima qualidade)
   - **Idioma**: auto-detect ou especifique para maior precisao
4. Clique em **Transcrever** e acompanhe o progresso
5. Ao concluir, faca download nos formatos desejados (SRT / TXT / JSON)

---

## CLI (`transcrever_v1.py`)

```bash
# Transcrever video local com Whisper large-v3
python transcrever_v1.py \
  --in video.mp4 \
  --outdir ./transcription \
  --asr whisper \
  --whisper-model large-v3

# Transcrever URL com idioma definido
python transcrever_v1.py \
  --in "https://www.youtube.com/watch?v=VIDEO_ID" \
  --outdir ./transcription \
  --asr whisper \
  --whisper-model large-v3 \
  --src en

# Transcrever ingles com Parakeet (mais rapido)
python transcrever_v1.py \
  --in podcast.mp4 \
  --outdir ./transcription \
  --asr parakeet
```

### Parametros

| Parametro | Descricao | Opcoes | Default |
|-----------|-----------|--------|---------|
| `--in` | Video, audio ou URL | arquivo local, URL YouTube/TikTok/etc | obrigatorio |
| `--outdir` | Diretorio de saida | qualquer path | obrigatorio |
| `--asr` | Motor de transcricao | `whisper`, `parakeet` | `whisper` |
| `--whisper-model` | Tamanho do modelo | `tiny`, `small`, `medium`, `large`, `large-v3` | `large-v3` |
| `--src` | Idioma do audio | `auto`, `en`, `pt`, `es`, `ja`, `zh`... | auto-detect |

---

## Modelos ASR

| Motor | GPU | Idiomas | Velocidade | Qualidade | Notas |
|-------|-----|---------|------------|-----------|-------|
| Whisper tiny | Opcional | 99 | Muito rapido | Basica | Para testes |
| Whisper small | Opcional | 99 | Rapido | Boa | Boa opcao para CPU |
| Whisper medium | Opcional | 99 | Medio | Muito boa | Equilibrio |
| Whisper large-v3 | Recomendado | 99 | Medio (GPU) | Excelente | Padrao recomendado |
| Parakeet 1.1B | Sim | **So ingles** | Muito rapido | Alta | NVIDIA, ideal para podcasts em ingles |

---

## Via API

```bash
# Transcrever por URL
curl -X POST http://localhost:8010/api/jobs/transcribe \
  -H "Content-Type: application/json" \
  -d '{
    "input": "https://www.youtube.com/watch?v=VIDEO_ID",
    "asr_engine": "whisper",
    "whisper_model": "large-v3"
  }'

# Com upload de arquivo
curl -X POST http://localhost:8010/api/jobs/transcribe/upload \
  -F "file=@video.mp4" \
  -F 'config_json={"asr_engine":"whisper","whisper_model":"large-v3","src_lang":"pt"}'

# Baixar resultado
curl http://localhost:8010/api/jobs/{JOB_ID}/transcript?format=srt -o legendas.srt
curl http://localhost:8010/api/jobs/{JOB_ID}/transcript?format=txt -o transcricao.txt
curl http://localhost:8010/api/jobs/{JOB_ID}/transcript?format=json -o dados.json
```

---

## Dicas

- Especifique `--src` quando souber o idioma: evita deteccao errada e melhora precisao
- Para podcasts em ingles, Parakeet e significativamente mais rapido que Whisper
- O arquivo JSON contem timestamps por palavra, util para legendas animadas
- Para audio com muito ruido ou sotaque forte, use `large-v3`
