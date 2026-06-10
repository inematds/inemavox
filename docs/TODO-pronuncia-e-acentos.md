# TODO — Camada de pronúncia (léxico) + revisão de acentuação no TTS

> Status: **a implementar.** Documentado a partir do uso no projeto `inemaref` (skills de
> motion comic / vídeo narrado), 2026-06-10. Implementar quando for mexer nisto.

## Problema

A narração em **português** sai errada em dois casos:

1. **Acentuação ausente** — texto sem acento ("piramide", "voce", "historia") faz o TTS
   pronunciar errado (sílaba tônica/vogal trocada). Hoje quem chama o `/tts` precisa lembrar de
   acentuar — e quando esquece, a fala sai torta, sem nenhum aviso.
2. **Termos em inglês** — nomes/palavras em inglês numa narração PT ("Maslow", "software",
   "design", "design thinking") são lidos com a fonética portuguesa e soam errados.

## Por que resolver AQUI (no inemavox)

O **inemavox é o ponto único** por onde **todos os projetos** de voz passam (inemaref,
videoprodutor, cursos, bots, etc. chamam o endpoint `/tts` / `/tts/vc`). Resolver no daemon = **um
lugar só**; todos os projetos passam a pronunciar certo **de graça**, sem mudar cada skill cliente.
A alternativa (uma lib/`tts.py` em cada projeto) recai no problema de manter N cópias.

## Proposta

Uma **camada de pré-processamento do texto**, aplicada **no servidor antes de sintetizar**
(no worker/endpoint de TTS, antes de mandar pro Chatterbox), com duas partes:

### 1. Léxico de pronúncia — `pronuncias.json` (editável num lugar só)

```json
{
  "Maslow": "Máslou",
  "software": "softuér",
  "design": "dizáin",
  "marketing": "márquetin",
  "insight": "ínsait",
  "feedback": "fídibéqui"
}
```

- Substituição por **limite de palavra** (regex `\b`), **case-insensitive**, preservando
  pontuação. Aplicar antes da síntese.
- Carregar o JSON na subida do worker (ou hot-reload). Editar o arquivo = ajustar a pronúncia de
  todos os projetos.
- Opcional: por idioma (`pronuncias.pt.json`) e/ou um campo no request para desativar
  (`aplicar_lexico: false`).

### 2. Revisão de acentuação (opcional, mais conservador)

- Checar o texto PT com **hunspell `pt_BR`** (ou `pyspellchecker` lang=`pt`) antes de sintetizar.
- Modo **aviso** (default seguro): retornar/loggar as palavras suspeitas de estarem sem acento
  (não corrige sozinho — corrigir acento automático é arriscado).
- Modo **auto** (opt-in via flag no request): substituir só quando houver **uma** forma acentuada
  inequívoca no dicionário (ex.: "voce"→"você", "historia"→"história"); pular ambíguos
  ("e"/"é", "esta"/"está", "secretaria"/"secretária").

## Onde mexer (referência)

- Endpoint/worker de TTS (o que atende `/tts` e `/tts/vc`) — aplicar a camada **antes** de chamar
  o Chatterbox. Ver `chatterbox_tts_worker.py` / `chatterbox_vc_worker.py` e a API em `api/`.
- Adicionar `pronuncias.json` na raiz (ou em `config/`), com loader + hot-reload.
- Ver também `docs/tts.md` (contrato do endpoint) — documentar os campos novos
  (`aplicar_lexico`, `revisar_acentos`).

## Critério de pronto

- Texto com termo do léxico → sai com a pronúncia regravada.
- Texto PT sem acento → (modo aviso) loga as suspeitas; (modo auto) corrige só os inequívocos.
- `pronuncias.json` editável sem redeploy (hot-reload) e versionado no repo.
- Projetos clientes (ex.: inemaref) **não precisam mudar nada** — ganham a correção de graça.
