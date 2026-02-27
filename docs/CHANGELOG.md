# inemaVOX - Changelog

---

## v1.8.3 — diarização funcionando (2026-02-24)

### Fix diarização (torchaudio 2.10 + pyannote 3.1.1)

Série de patches de compatibilidade para fazer pyannote funcionar com o ecossistema atual:

- **torchaudio 2.9+** substituiu `torchaudio.load()` por TorchCodec (pacote separado não instalado)
  → fallback automático para `soundfile` quando TorchCodec não disponível
- **torchaudio 2.9+** removeu `torchaudio.info()` completamente
  → shim via `soundfile.info()` retornando objeto compatível com `AudioMetaData`
- **numpy 2.0** removeu `np.NAN` (além de `np.NaN` já corrigido anteriormente)
  → `np.NAN = np.nan` adicionado ao patch
- **torchaudio 2.5+** removeu `list_audio_backends()` e `get_audio_backend()`
  → shims adicionados (`lambda: []` e `lambda: None`)
- **torchaudio.backend.common** removido (usado em `pyannote/audio/tasks/segmentation/mixins.py`)
  → try/except com stub de `AudioMetaData`
- **speechbrain**: chamada a `list_audio_backends()` sem guard → adicionado `hasattr` check
- **PyTorch 2.6+** mudou default de `weights_only=False` para `True` em `torch.load()`
  → `lightning_fabric/utilities/cloud_io.py` patcheado para usar `False` em arquivos locais
- **HF Token tipo errado**: token fine-grained não acessa repos públicos gated
  → necessário token tipo **Read** (clássico), não fine-grained

### Resultado
- `SPEAKER_00` e `SPEAKER_01` detectados corretamente em áudio com 2 falantes
- Edge TTS mapeia automaticamente: `SPEAKER_00` → `AntonioNeural` (M), `SPEAKER_01` → `FranciscaNeural` (F)

---

## v1.8.2 — post-release fixes (2026-02-24)

### Fix diarizacao (multiplos falantes)
- `pyannote.audio 3.1.1` instalado no venv
- Patches de compatibilidade para ecossistema atual:
  - `torchaudio 2.10.0`: removeu `set_audio_backend` e `AudioMetaData` → shims adicionados
  - `numpy 2.3.5`: removeu `np.NaN` → alias para `np.nan`
  - `huggingface_hub 1.4.1`: removeu parametro `use_auth_token=` → arquivos do pyannote patcheados diretamente para usar `token=`
- `start.sh`: carrega `.env` automaticamente; avisa se `HF_TOKEN` nao configurado
- `.env.example`: template com instrucoes para configurar `HF_TOKEN`
- **Requer aceite manual de termos** em `https://hf.co/pyannote/speaker-diarization-3.1` e `https://hf.co/pyannote/segmentation-3.0`
- Badge `👥 Multi-falante` exibido no header e na secao de config do job detail
- Job detail dublagem: mostra se diarizacao estava ativa e quantos falantes

---

## v1.8.2 (2026-02-24)

### Novo
- **Multiplos Falantes** — secao propria e visivel no form de dublagem
  - Checkbox com campo opcional `num_speakers` (2-10 ou auto)
  - Aviso quando o TTS escolhido nao suporta multi-voz (somente Edge TTS suporta)
  - Info confirmando mapeamento automatico de vozes quando Edge TTS esta ativo
- **Re-tentar com edicao** — botao "↺ Re-tentar" agora abre o formulario pre-preenchido
  - Usuario pode alterar qualquer configuracao antes de reenviar
  - Suporta todos os tipos de job: dublagem, corte, transcricao, TTS, clone, download
  - Banner azul informando que a config foi carregada

### Fix
- Venv recriado com `torch 2.10.0+cu128` — GPU (CUDA) disponivel para m2m100 e transcricao
- Versao da MEMORY.md estava desatualizada (1.7.5 → 1.8.2)
- Documentacao com portas erradas (3000/8000 → 3010/8010) corrigida

---

## v1.8.1 (2026-02-24)

### Novo
- **Badges GPU/CPU por etapa** no job detail de dublagem
  - Cada etapa do pipeline exibe `[GPU]`, `[CPU]`, `[Ollama]`, `[Online]`
  - m2m100 mostra `[GPU · m2m100]` ou `[CPU · m2m100]` conforme device do job

### Fix
- **GPU para m2m100**: venv tinha `torch 2.10.0+cpu` (instalado sem CUDA index URL)
  - Reinstalado `torch 2.10.0+cu128` com pacotes nvidia completos
  - `[JobManager] Modo: Local (cuda)` confirmado apos reinicializacao da API

---

## v1.8.0 (2026-02-22)

### Novo
- **Chatterbox-VC** — novo engine de clone de voz via pipeline Edge TTS → S3Gen VC
  - Worker dedicado: `chatterbox_vc_worker.py`
  - Mais rapido e consistente que o MTL completo
  - Toggle MTL / VC Pipeline na interface de voice clone
- **Corte por Assunto** — modo `topics` no clipar
  - LLM analisa transcricao e segmenta por mudanca de topico
  - Ideal para lives, podcasts e aulas com multiplos temas
  - Numero de clips `0` = detectar automaticamente
- **Prompts customizaveis** no corte viral/assunto
  - Editor colapsavel com campos system + user
  - Botao "Restaurar padrao" para cada modo
  - Prompts diferentes por modo (Viral vs Assunto)
- **Modo Analise (IA)** renomeado e com toggle compacto Viral | Assunto
- **Config de jobs TTS/Clone** exibida no job detail (texto, engine, parametros)
- **Versao dinamica** no Dashboard via `system.version` da API
- **Workers com fallback CPU** quando CUDA OOM (threshold de VRAM configuravel)
- **Whisper GPU worker** dedicado: `whisper_gpu_worker.py`

---

## v1.7.x (2026-02-22)

### Novo
- **Gerar Audio (TTS)** — nova pagina `/tts` para sintese de texto em voz
- **Clonar Voz** — nova pagina `/voice-clone` com upload de referencia
- **Analise de qualidade da referencia** no voice clone
  - Score visual: Insuficiente / Fraca / Boa / Excelente
  - Baseado em duracao (HTMLAudioElement) + estimativa de bitrate
  - Penalidade para bitrate < 48kbps
  - Borda do dropzone muda de cor conforme score
  - Botao bloqueado se referencia insuficiente
- **Botao Repetir Clone** — gera variacao sem re-upload da referencia
- Suporte a `download`, `tts_generate`, `voice_clone` no Dashboard e lista de jobs
- Chatterbox adicionado ao seletor de TTS na dublagem

### Fix
- **Voice clone qualidade**: referencia convertida 22050Hz → 24000Hz (S3GEN_SR do MTL)
  - Evita erro: `Reference mel length != 2 * reference token length`
- **Trim da referencia para 10s** (DEC_COND_LEN) evita padding inconsistente
- **Parametros de geracao ajustados**: `exaggeration=0.35`, `cfg_weight=0.4`, `temp=0.75`
  - Reduzem loops e EOS prematuro nos segmentos
- **yt-dlp path**: resolver via `venv/bin` (FileNotFoundError corrigido)
- **Portas corretas**: API `:8010`, Web `:3010`
- Recuperacao de status de job apos hot-reload durante execucao

---

## v1.0.0 (rebrand)

- Rebrand de "Dublar Pro" para **inemaVOX**
- Suite completa: Dublagem, Transcricao, Corte, Download, TTS, Clone de Voz
- Interface web moderna em Next.js com Tailwind CSS
- API FastAPI com sistema de jobs e filas
- Suporte a GPU NVIDIA (incluindo Blackwell GB10 com cu128)
