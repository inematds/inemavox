# inemaVOX - Baixar Video

Faz download de videos de +1000 sites usando yt-dlp. Suporta YouTube, TikTok, Instagram, Facebook, Twitter/X, Twitch e muitos outros.

---

## Como funciona

```
URL do video
   │
   ▼
yt-dlp seleciona a melhor stream conforme qualidade
   │
   ▼
ffmpeg mescla video + audio (quando necessario)
   │
   ▼
video.mp4 (ou video.mp3 no modo audio)
```

---

## Interface Web (`/download`)

1. Acesse `http://localhost:3010/download`
2. Cole a URL do video
3. Escolha a qualidade: **Melhor**, 1080p, 720p, 480p, **So Audio (MP3)**
4. Clique em **Baixar** e acompanhe o progresso em tempo real (%, velocidade, ETA)
5. Ao concluir, assista no player inline ou clique em **Download**

---

## Via API

```bash
# Criar job de download
curl -X POST http://localhost:8010/api/jobs/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=VIDEO_ID", "quality": "1080p"}'

# Baixar o arquivo quando concluido
curl http://localhost:8010/api/jobs/{JOB_ID}/download-file -o video.mp4
```

## Qualidades

| Opcao | Resolucao | Formato |
|-------|-----------|---------|
| `best` | Maxima disponivel | MP4 |
| `1080p` | 1920×1080 | MP4 |
| `720p` | 1280×720 | MP4 |
| `480p` | 854×480 | MP4 |
| `audio` | — | MP3 192kbps |

---

## Dicas

- `best` e recomendado quando nao souber a qualidade disponivel
- Para podcasts longos use `audio` para economizar espaco
- yt-dlp e atualizado frequentemente; se um site parar de funcionar: `pip install -U yt-dlp`
