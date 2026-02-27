"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getOptions, createJob, createJobWithUpload, getOllamaStatus, startOllama, stopOllama, pullOllamaModel } from "@/lib/api";

type Options = {
  tts_engines: { id: string; name: string; needs_gpu: boolean; needs_internet: boolean; quality?: string; description?: string; detail?: string }[];
  translation_engines: { id: string; name: string; models: string[] | string; description?: string; detail?: string; needs_gpu?: boolean }[];
  whisper_models: { id: string; name: string; quality: string; turbo?: boolean }[];
  asr_engines: { id: string; name: string; description: string; detail?: string; needs_gpu: boolean; supports_languages: string | string[] }[];
  edge_voices: Record<string, { id: string; name: string; gender: string }[]>;
  bark_voices: Record<string, { id: string; name: string }[]>;
  content_types: { id: string; name: string; description: string; detail?: string; presets: Record<string, string | number | boolean | undefined> }[];
  languages: { code: string; name: string }[];
  ollama_models: { id: string; name: string; size_gb: number }[];
};

const SYNC_HELP: Record<string, { name: string; desc: string }> = {
  smart: {
    name: "Smart (recomendado)",
    desc: "Decide automaticamente: se o audio ficou curto, adiciona silencio. Se ficou longo mas dentro do limite de compressao, comprime a fala. Se ficou muito longo, trunca para nao distorcer demais.",
  },
  fit: {
    name: "Fit (comprimir/esticar)",
    desc: "Sempre comprime ou estica o audio para caber exatamente no tempo do segmento original. Pode soar acelerado se a traducao for muito mais longa que o original.",
  },
  pad: {
    name: "Pad (silencio)",
    desc: "Nao altera a velocidade da fala. Se o audio for mais curto que o slot, preenche com silencio. Se for mais longo, trunca no limite do tempo.",
  },
  extend: {
    name: "Extend (freeze frame)",
    desc: "Mantem a fala na velocidade natural. Se o audio for mais longo que o slot, congela o ultimo frame do video ate a fala terminar. O video final pode ficar mais longo que o original.",
  },
  none: {
    name: "None (sem sync)",
    desc: "Nao faz nenhum ajuste de tempo. Os segmentos de audio sao concatenados na ordem sem sincronizacao com o video original.",
  },
};

const ADVANCED_HELP: Record<string, string> = {
  maxstretch: "Limite maximo de compressao/esticamento da fala. Valor 1.3 significa que o audio pode ser acelerado ate 30% ou desacelerado ate 30%. Valores altos (1.5-2.0) permitem frases mais longas mas a voz pode soar acelerada. Valores baixos (1.1) mantem a voz natural mas podem cortar texto.",
  diarize: "Detecta automaticamente diferentes falantes no video e tenta manter vozes distintas na dublagem. Util para entrevistas, debates e filmes com multiplos personagens. Aumenta o tempo de processamento.",
  seed: "Numero para reproducibilidade. Usar o mesmo seed com a mesma configuracao produz resultados identicos. Util para testar diferentes configuracoes mantendo a mesma base aleatoria.",
  noTruncate: "Quando ativado, nunca corta palavras ou frases da traducao. O texto traduzido e mantido integralmente, e o sistema de sincronizacao (sync) fica responsavel por encaixar o audio mais longo. Combine com maxstretch alto ou sync extend para melhores resultados.",
};

function DetailCard({
  id, name, description, detail, selected, onSelect, expandedDetail, setExpandedDetail, badges, disabled,
}: {
  id: string; name: string; description: string; detail?: string;
  selected: boolean; onSelect: () => void;
  expandedDetail: string | null; setExpandedDetail: (v: string | null) => void;
  badges?: React.ReactNode; disabled?: boolean;
}) {
  const detailId = id;
  return (
    <div>
      <label
        className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
          selected ? "border-blue-500 bg-blue-500/10" : "border-gray-700 hover:border-gray-600"
        } ${expandedDetail === detailId ? "rounded-b-none" : ""} ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}>
        <input type="radio" checked={selected} onChange={onSelect} disabled={disabled} className="mt-1" />
        <div className="flex-1">
          <div className="font-medium">{name}</div>
          <div className="text-sm text-gray-400">{description}</div>
          {badges}
        </div>
        {detail && (
          <button type="button"
            onClick={(e) => { e.preventDefault(); setExpandedDetail(expandedDetail === detailId ? null : detailId); }}
            className="text-xs text-blue-400 hover:text-blue-300 whitespace-nowrap mt-1 flex items-center gap-1">
            <span className="inline-block w-4 h-4 rounded-full border border-blue-400/50 text-center leading-4 text-[10px]">i</span>
            {expandedDetail === detailId ? "Fechar" : "Saiba mais"}
          </button>
        )}
      </label>
      {expandedDetail === detailId && detail && (
        <div className={`px-4 py-3 text-sm text-gray-300 bg-gray-800/50 border border-t-0 rounded-b-lg ${
          selected ? "border-blue-500/50" : "border-gray-700"
        }`}>
          {detail}
        </div>
      )}
    </div>
  );
}

export default function NewJobPage() {
  return (
    <Suspense>
      <NewJob />
    </Suspense>
  );
}

function NewJob() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [options, setOptions] = useState<Options | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [input, setInput] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [srcLang, setSrcLang] = useState("");
  const [tgtLang, setTgtLang] = useState("pt");
  const [contentType, setContentType] = useState("palestra");
  const [ttsEngine, setTtsEngine] = useState("edge");
  const [voice, setVoice] = useState("");
  const [asrEngine, setAsrEngine] = useState("whisper");
  const [whisperModel, setWhisperModel] = useState("large-v3");
  const [parakeetModel, setParakeetModel] = useState("nvidia/parakeet-tdt-1.1b");
  const [translationEngine, setTranslationEngine] = useState("m2m100");
  const [ollamaModel, setOllamaModel] = useState("qwen2.5:14b");
  const [largeModel, setLargeModel] = useState(false);
  const [diarize, setDiarize] = useState(false);
  const [numSpeakers, setNumSpeakers] = useState<number | "">("");
  const [noTruncate, setNoTruncate] = useState(false);
  const [cloneVoice, setCloneVoice] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [syncMode, setSyncMode] = useState("smart");
  const [maxstretch, setMaxstretch] = useState(1.3);
  const [ttsRate, setTtsRate] = useState("+0%");
  const [seed, setSeed] = useState(42);

  // Ollama control
  const [ollamaOnline, setOllamaOnline] = useState<boolean | null>(null);
  const [ollamaLoading, setOllamaLoading] = useState(false);
  const [ollamaPulling, setOllamaPulling] = useState(false);
  const [pullModelName, setPullModelName] = useState("qwen2.5:72b");
  const [ollamaSort, setOllamaSort] = useState<"size" | "name">("size");

  // UI state
  const [expandedDetail, setExpandedDetail] = useState<string | null>(null);
  const [expandedHelp, setExpandedHelp] = useState<string | null>(null);
  const [openSections, setOpenSections] = useState<Set<string>>(new Set());

  const toggleSection = (section: string) => {
    setOpenSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) next.delete(section); else next.add(section);
      return next;
    });
  };
  const closeSection = (section: string) => {
    setOpenSections((prev) => { const next = new Set(prev); next.delete(section); return next; });
  };

  useEffect(() => {
    getOptions().then(setOptions).catch(() => setError("API offline"));
  }, []);

  // Pre-preencher a partir de ?prefill= (retry de job existente)
  useEffect(() => {
    const raw = searchParams.get("prefill");
    if (!raw) return;
    try {
      const cfg = JSON.parse(decodeURIComponent(raw)) as Record<string, unknown>;
      if (cfg.input && typeof cfg.input === "string") setInput(cfg.input);
      if (cfg.src_lang) setSrcLang(String(cfg.src_lang));
      if (cfg.tgt_lang) setTgtLang(String(cfg.tgt_lang));
      if (cfg.content_type) setContentType(String(cfg.content_type));
      if (cfg.tts_engine) setTtsEngine(String(cfg.tts_engine));
      if (cfg.voice) setVoice(String(cfg.voice));
      if (cfg.asr_engine) setAsrEngine(String(cfg.asr_engine));
      if (cfg.whisper_model) setWhisperModel(String(cfg.whisper_model));
      if (cfg.parakeet_model) setParakeetModel(String(cfg.parakeet_model));
      if (cfg.translation_engine) setTranslationEngine(String(cfg.translation_engine));
      if (cfg.ollama_model) setOllamaModel(String(cfg.ollama_model));
      if (cfg.large_model) setLargeModel(Boolean(cfg.large_model));
      if (cfg.diarize) setDiarize(Boolean(cfg.diarize));
      if (cfg.num_speakers) setNumSpeakers(Number(cfg.num_speakers));
      if (cfg.no_truncate) setNoTruncate(Boolean(cfg.no_truncate));
      if (cfg.clone_voice) setCloneVoice(Boolean(cfg.clone_voice));
      if (cfg.sync_mode) setSyncMode(String(cfg.sync_mode));
      if (cfg.maxstretch) setMaxstretch(Number(cfg.maxstretch));
      if (cfg.tts_rate) setTtsRate(String(cfg.tts_rate));
      if (cfg.seed) setSeed(Number(cfg.seed));
    } catch { /* ignorar parse errors */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Verificar status do Ollama quando motor de traducao for ollama
  const refreshOllamaStatus = async () => {
    try {
      const st = await getOllamaStatus();
      setOllamaOnline(st.online);
      if (st.online && st.models) {
        setOptions((prev) => prev ? { ...prev, ollama_models: st.models } : prev);
      }
    } catch {
      setOllamaOnline(false);
    }
  };

  useEffect(() => {
    if (translationEngine === "ollama") {
      refreshOllamaStatus();
      const interval = setInterval(refreshOllamaStatus, 5000);
      return () => clearInterval(interval);
    }
  }, [translationEngine]);

  // Aplicar presets do tipo de conteudo
  useEffect(() => {
    if (!options) return;
    const ct = options.content_types.find((c) => c.id === contentType);
    if (ct) {
      if (ct.presets.sync) setSyncMode(String(ct.presets.sync));
      if (ct.presets.maxstretch) setMaxstretch(Number(ct.presets.maxstretch));
      setNoTruncate(Boolean(ct.presets.no_truncate));
      setDiarize(Boolean(ct.presets.diarize));
      setTtsRate(ct.presets.tts_rate ? String(ct.presets.tts_rate) : "+0%");
    }
  }, [contentType, options]);

  // Auto-selecionar Parakeet para ingles
  useEffect(() => {
    if (srcLang === "en") {
      setAsrEngine("parakeet");
    } else if (srcLang && srcLang !== "en" && asrEngine === "parakeet") {
      setAsrEngine("whisper");
    }
  }, [srcLang, asrEngine]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input && !uploadFile) return;
    setLoading(true);
    setUploadProgress(null);
    setError(null);

    try {
      const ct = options?.content_types.find((c) => c.id === contentType);
      const tolerance = ct?.presets?.tolerance;

      const config: Record<string, unknown> = {
        input: uploadFile ? uploadFile.name : input,
        tgt_lang: tgtLang,
        tts_engine: ttsEngine,
        asr_engine: asrEngine,
        whisper_model: whisperModel,
        translation_engine: translationEngine,
        sync_mode: syncMode,
        maxstretch,
        seed,
        content_type: contentType,
      };
      if (srcLang) config.src_lang = srcLang;
      if (voice) config.voice = voice;
      if (asrEngine === "parakeet") config.parakeet_model = parakeetModel;
      if (translationEngine === "ollama") config.ollama_model = ollamaModel;
      if (largeModel) config.large_model = true;
      if (diarize) config.diarize = true;
      if (diarize && numSpeakers) config.num_speakers = Number(numSpeakers);
      if (noTruncate) config.no_truncate = true;
      if (cloneVoice) config.clone_voice = true;
      if (tolerance !== undefined) config.tolerance = Number(tolerance);
      if (ttsRate && ttsRate !== "+0%") config.tts_rate = ttsRate;

      const job = uploadFile
        ? await createJobWithUpload(uploadFile, config, (p) => setUploadProgress(p))
        : await createJob(config);
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      setError(String(err));
      setLoading(false);
      setUploadProgress(null);
    }
  };

  const langCode = tgtLang.startsWith("pt") ? "pt-BR" : tgtLang === "en" ? "en-US" : `${tgtLang}-${tgtLang.toUpperCase()}`;
  const edgeVoices = options?.edge_voices[langCode] || [];
  const barkVoices = options?.bark_voices[tgtLang] || [];

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Nova Dublagem</h1>
      <p className="text-gray-400 mb-8">Configure o pipeline de dublagem do seu video</p>

      {searchParams.get("prefill") && (
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 mb-6 text-blue-300 text-sm">
          Configuracao carregada do job anterior. Altere o que quiser antes de reenviar.
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 text-red-400">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Input */}
        <section className="border border-gray-800 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-4">Video de Entrada</h2>
          <input
            type="text"
            value={input}
            onChange={(e) => { setInput(e.target.value); setUploadFile(null); }}
            placeholder="URL do YouTube"
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            disabled={!!uploadFile}
            required={!uploadFile}
          />
          <div className="mt-3 flex items-center gap-3">
            <span className="text-sm text-gray-500">ou</span>
            <label className="cursor-pointer bg-gray-800 hover:bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-sm text-gray-300 transition-colors">
              {uploadFile ? uploadFile.name : "Enviar arquivo de video"}
              <input
                type="file"
                accept="video/*,audio/*"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) { setUploadFile(f); setInput(""); }
                }}
              />
            </label>
            {uploadFile && (
              <button type="button" onClick={() => setUploadFile(null)}
                className="text-sm text-red-400 hover:text-red-300">Remover</button>
            )}
          </div>
        </section>

        {/* Idiomas */}
        <section className="border border-gray-800 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-4">Idiomas</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Origem (vazio = auto-detect)</label>
              <select value={srcLang} onChange={(e) => setSrcLang(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white">
                <option value="">Auto-detect</option>
                {options?.languages.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Destino</label>
              <select value={tgtLang} onChange={(e) => setTgtLang(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white">
                {options?.languages.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
              </select>
            </div>
          </div>
        </section>

        {/* Tipo de Conteudo */}
        <section className="border border-gray-800 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-4">Tipo de Conteudo</h2>
          {openSections.has("ct") ? (
            <div className="space-y-3">
              {options?.content_types.map((ct) => (
                <div key={ct.id}>
                  <DetailCard
                    id={`ct_${ct.id}`}
                    name={ct.name}
                    description={ct.description}
                    detail={ct.detail}
                    selected={contentType === ct.id}
                    onSelect={() => { setContentType(ct.id); closeSection("ct"); }}
                    expandedDetail={expandedDetail}
                    setExpandedDetail={setExpandedDetail}
                    badges={
                      expandedDetail === `ct_${ct.id}` ? (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {ct.presets.sync && <span className="text-xs bg-gray-700/50 px-2 py-0.5 rounded">sync: {String(ct.presets.sync)}</span>}
                          {ct.presets.maxstretch && <span className="text-xs bg-gray-700/50 px-2 py-0.5 rounded">compressao: {String(Number(ct.presets.maxstretch) * 100 - 100)}%</span>}
                          {ct.presets.tts_rate && ct.presets.tts_rate !== "+0%" && <span className="text-xs bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded">voz: {String(ct.presets.tts_rate)}</span>}
                          {ct.presets.no_truncate && <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded">frases completas</span>}
                          {ct.presets.diarize && <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded">multi-falante</span>}
                        </div>
                      ) : undefined
                    }
                  />
                </div>
              ))}
            </div>
          ) : (
            <button type="button" onClick={() => toggleSection("ct")}
              className="w-full flex items-center gap-3 p-3 rounded-lg border border-blue-500 bg-blue-500/10 text-left hover:bg-blue-500/15 transition-colors">
              <span className="text-blue-400">&#9654;</span>
              <div className="flex-1">
                <div className="font-medium">{options?.content_types.find((c) => c.id === contentType)?.name || contentType}</div>
                <div className="text-sm text-gray-400">{options?.content_types.find((c) => c.id === contentType)?.description}</div>
              </div>
              <span className="text-xs text-gray-500">Alterar</span>
            </button>
          )}
        </section>

        {/* Motores */}
        <section className="border border-gray-800 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-4">Motores de IA</h2>

          {/* ASR Engine */}
          <div className="mb-5">
            <label className="block text-sm text-gray-400 mb-2">Transcricao (ASR)</label>
            {openSections.has("asr") ? (
              <div className="space-y-2">
                {options?.asr_engines?.map((asr) => {
                  const isLangUnsupported = Array.isArray(asr.supports_languages)
                    && srcLang
                    && !asr.supports_languages.includes(srcLang);
                  return (
                    <DetailCard
                      key={asr.id}
                      id={`asr_${asr.id}`}
                      name={asr.name}
                      description={asr.description}
                      detail={asr.detail}
                      selected={asrEngine === asr.id}
                      onSelect={() => { setAsrEngine(asr.id); closeSection("asr"); }}
                      expandedDetail={expandedDetail}
                      setExpandedDetail={setExpandedDetail}
                      disabled={!!isLangUnsupported}
                      badges={
                        <div className="flex flex-wrap gap-1 mt-1">
                          {asr.needs_gpu && <span className="text-xs bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded">Requer GPU</span>}
                          {asr.supports_languages === "all"
                            ? <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded">99+ idiomas</span>
                            : <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">Apenas ingles</span>}
                        </div>
                      }
                    />
                  );
                })}
              </div>
            ) : (
              <button type="button" onClick={() => toggleSection("asr")}
                className="w-full flex items-center gap-3 p-3 rounded-lg border border-blue-500 bg-blue-500/10 text-left hover:bg-blue-500/15 transition-colors">
                <span className="text-blue-400">&#9654;</span>
                <div className="flex-1">
                  <div className="font-medium">{options?.asr_engines?.find((a) => a.id === asrEngine)?.name || asrEngine}</div>
                  <div className="text-sm text-gray-400">{options?.asr_engines?.find((a) => a.id === asrEngine)?.description}</div>
                </div>
                <span className="text-xs text-gray-500">Alterar</span>
              </button>
            )}

            {/* Parakeet + non-English warning */}
            {asrEngine === "parakeet" && srcLang && srcLang !== "en" && (
              <div className="mt-2 text-sm text-yellow-400 bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
                Parakeet suporta apenas ingles. O idioma selecionado ({srcLang}) nao e suportado.
              </div>
            )}
            {asrEngine === "parakeet" && !srcLang && (
              <div className="mt-2 text-sm text-yellow-400 bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
                Parakeet suporta apenas ingles. Para seguranca, selecione o idioma de origem manualmente.
              </div>
            )}
          </div>

          {/* Whisper Model - only when whisper selected */}
          {asrEngine === "whisper" && (
            <div className="mb-4">
              <label className="block text-sm text-gray-400 mb-1">Modelo Whisper</label>
              <select value={whisperModel} onChange={(e) => setWhisperModel(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white">
                {options?.whisper_models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} - {m.quality}{m.turbo ? " (rapido)" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Parakeet Model - only when parakeet selected */}
          {asrEngine === "parakeet" && (
            <div className="mb-4">
              <label className="block text-sm text-gray-400 mb-1">Modelo Parakeet</label>
              <select value={parakeetModel} onChange={(e) => setParakeetModel(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white">
                <option value="nvidia/parakeet-tdt-1.1b">TDT 1.1B (recomendado)</option>
                <option value="nvidia/parakeet-ctc-1.1b">CTC 1.1B (mais rapido)</option>
                <option value="nvidia/parakeet-rnnt-1.1b">RNNT 1.1B (mais preciso)</option>
              </select>
            </div>
          )}

          {/* TTS */}
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-2">Motor TTS (Voz)</label>
            {openSections.has("tts") ? (
              <div className="space-y-2">
                {options?.tts_engines.map((te) => (
                  <DetailCard
                    key={te.id}
                    id={`tts_${te.id}`}
                    name={te.name}
                    description={te.description || ""}
                    detail={te.detail}
                    selected={ttsEngine === te.id}
                    onSelect={() => { setTtsEngine(te.id); setVoice(""); closeSection("tts"); }}
                    expandedDetail={expandedDetail}
                    setExpandedDetail={setExpandedDetail}
                    badges={
                      <div className="flex flex-wrap gap-1 mt-1">
                        {te.needs_gpu && <span className="text-xs bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded">GPU</span>}
                        {!te.needs_gpu && <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded">CPU</span>}
                        {te.needs_internet && <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">Online</span>}
                        {!te.needs_internet && <span className="text-xs bg-gray-500/20 text-gray-400 px-2 py-0.5 rounded">Offline</span>}
                        {te.quality && <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded">{te.quality}</span>}
                      </div>
                    }
                  />
                ))}
              </div>
            ) : (
              <button type="button" onClick={() => toggleSection("tts")}
                className="w-full flex items-center gap-3 p-3 rounded-lg border border-blue-500 bg-blue-500/10 text-left hover:bg-blue-500/15 transition-colors">
                <span className="text-blue-400">&#9654;</span>
                <div className="flex-1">
                  <div className="font-medium">{options?.tts_engines.find((t) => t.id === ttsEngine)?.name || ttsEngine}</div>
                  <div className="text-sm text-gray-400">{options?.tts_engines.find((t) => t.id === ttsEngine)?.description}</div>
                </div>
                <span className="text-xs text-gray-500">Alterar</span>
              </button>
            )}
          </div>

          {/* Voz */}
          {ttsEngine === "edge" && edgeVoices.length > 0 && (
            <div className="mb-4">
              <label className="block text-sm text-gray-400 mb-1">Voz Edge TTS</label>
              <select value={voice} onChange={(e) => setVoice(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white">
                <option value="">Padrao</option>
                {edgeVoices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </div>
          )}
          {ttsEngine === "bark" && barkVoices.length > 0 && (
            <div className="mb-4">
              <label className="block text-sm text-gray-400 mb-1">Voz Bark</label>
              <select value={voice} onChange={(e) => setVoice(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white">
                <option value="">Padrao (Speaker 3)</option>
                {barkVoices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </div>
          )}

          {/* Clone Voice */}
          {(ttsEngine === "xtts" || ttsEngine === "chatterbox") && (
            <label className="flex items-center gap-2 mb-4 text-sm">
              <input type="checkbox" checked={cloneVoice} onChange={(e) => setCloneVoice(e.target.checked)} />
              Clonar voz do video original
            </label>
          )}

          {/* Traducao */}
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-2">Motor de Traducao</label>
            {openSections.has("trad") ? (
              <div className="space-y-2">
                {options?.translation_engines.map((te) => (
                  <DetailCard
                    key={te.id}
                    id={`trad_${te.id}`}
                    name={te.name}
                    description={te.description || ""}
                    detail={te.detail}
                    selected={translationEngine === te.id}
                    onSelect={() => { setTranslationEngine(te.id); closeSection("trad"); }}
                    expandedDetail={expandedDetail}
                    setExpandedDetail={setExpandedDetail}
                    badges={
                      <div className="flex flex-wrap gap-1 mt-1">
                        {te.needs_gpu && <span className="text-xs bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded">Requer GPU</span>}
                        {!te.needs_gpu && <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded">CPU</span>}
                      </div>
                    }
                  />
                ))}
              </div>
            ) : (
              <button type="button" onClick={() => toggleSection("trad")}
                className="w-full flex items-center gap-3 p-3 rounded-lg border border-blue-500 bg-blue-500/10 text-left hover:bg-blue-500/15 transition-colors">
                <span className="text-blue-400">&#9654;</span>
                <div className="flex-1">
                  <div className="font-medium">{options?.translation_engines.find((t) => t.id === translationEngine)?.name || translationEngine}</div>
                  <div className="text-sm text-gray-400">{options?.translation_engines.find((t) => t.id === translationEngine)?.description}</div>
                </div>
                <span className="text-xs text-gray-500">Alterar</span>
              </button>
            )}
          </div>

          {/* Painel Ollama */}
          {translationEngine === "ollama" && (
            <div className="mb-4 border border-gray-700 rounded-lg p-4 space-y-3">
              {/* Status + Liga/Desliga */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`w-2.5 h-2.5 rounded-full ${ollamaOnline ? "bg-green-500" : "bg-red-500"}`} />
                  <span className="text-sm font-medium">
                    Ollama {ollamaOnline ? "Online" : "Offline"}
                  </span>
                </div>
                <button
                  type="button"
                  disabled={ollamaLoading}
                  onClick={async () => {
                    setOllamaLoading(true);
                    try {
                      if (ollamaOnline) {
                        await stopOllama();
                      } else {
                        await startOllama();
                      }
                      await refreshOllamaStatus();
                    } catch { /* ignore */ }
                    setOllamaLoading(false);
                  }}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    ollamaOnline
                      ? "bg-red-600/20 text-red-400 hover:bg-red-600/30 border border-red-500/30"
                      : "bg-green-600/20 text-green-400 hover:bg-green-600/30 border border-green-500/30"
                  } disabled:opacity-50`}
                >
                  {ollamaLoading ? "..." : ollamaOnline ? "Desligar" : "Ligar"}
                </button>
              </div>

              {/* Modelo selecionado */}
              {ollamaOnline && options?.ollama_models && options.ollama_models.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-sm text-gray-400">Modelo</label>
                    <div className="flex gap-1">
                      <button type="button" onClick={() => setOllamaSort("size")}
                        className={`px-2 py-0.5 rounded text-xs transition-colors ${ollamaSort === "size" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"}`}>
                        Tamanho
                      </button>
                      <button type="button" onClick={() => setOllamaSort("name")}
                        className={`px-2 py-0.5 rounded text-xs transition-colors ${ollamaSort === "name" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"}`}>
                        A-Z
                      </button>
                    </div>
                  </div>
                  <div className="space-y-1.5 max-h-64 overflow-y-auto">
                    {[...options.ollama_models]
                      .sort((a, b) => ollamaSort === "size" ? b.size_gb - a.size_gb : a.name.localeCompare(b.name))
                      .map((m) => {
                        const selected = ollamaModel === m.id;
                        const family = m.name.split(":")[0];
                        const variant = m.name.split(":")[1] || "";
                        const sizeColor = m.size_gb >= 30 ? "text-purple-400" : m.size_gb >= 10 ? "text-blue-400" : m.size_gb >= 5 ? "text-green-400" : "text-gray-400";
                        return (
                          <button type="button" key={m.id} onClick={() => setOllamaModel(m.id)}
                            className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left text-sm transition-colors ${
                              selected
                                ? "bg-blue-500/15 border border-blue-500/40 text-white"
                                : "bg-gray-900 border border-gray-700/50 text-gray-300 hover:border-gray-600"
                            }`}>
                            <div className={`w-3 h-3 rounded-full border-2 flex-shrink-0 ${selected ? "border-blue-400 bg-blue-400" : "border-gray-600"}`} />
                            <div className="flex-1 min-w-0">
                              <span className="font-medium">{family}</span>
                              {variant && <span className="text-gray-500 ml-1">:{variant}</span>}
                            </div>
                            <span className={`font-mono text-xs flex-shrink-0 ${sizeColor}`}>{m.size_gb}GB</span>
                          </button>
                        );
                      })}
                  </div>
                </div>
              )}

              {/* Sem modelos */}
              {ollamaOnline && (!options?.ollama_models || options.ollama_models.length === 0) && (
                <div className="text-sm text-yellow-400">
                  Nenhum modelo instalado. Baixe um modelo abaixo.
                </div>
              )}

              {/* Baixar novo modelo */}
              {ollamaOnline && (
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Baixar modelo</label>
                  <div className="flex gap-2">
                    <select value={pullModelName} onChange={(e) => setPullModelName(e.target.value)}
                      className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm">
                      <option value="qwen2.5:7b">qwen2.5:7b (5GB) - rapido</option>
                      <option value="qwen2.5:14b">qwen2.5:14b (9GB) - recomendado</option>
                      <option value="qwen2.5:32b">qwen2.5:32b (20GB) - muito bom</option>
                      <option value="qwen2.5:72b">qwen2.5:72b (45GB) - excelente</option>
                      <option value="gemma3:12b">gemma3:12b (8GB) - alternativa</option>
                      <option value="llama3.1:8b">llama3.1:8b (5GB) - alternativa</option>
                    </select>
                    <button
                      type="button"
                      disabled={ollamaPulling}
                      onClick={async () => {
                        setOllamaPulling(true);
                        try {
                          await pullOllamaModel(pullModelName);
                          await refreshOllamaStatus();
                        } catch { /* ignore */ }
                        setOllamaPulling(false);
                      }}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white rounded-lg text-sm font-medium transition-colors"
                    >
                      {ollamaPulling ? "Baixando..." : "Baixar"}
                    </button>
                  </div>
                  {ollamaPulling && (
                    <div className="mt-2 text-xs text-blue-400 animate-pulse">
                      Baixando modelo... Isso pode demorar alguns minutos.
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {translationEngine === "m2m100" && (
            <label className="flex items-center gap-2 mb-4 text-sm">
              <input type="checkbox" checked={largeModel} onChange={(e) => setLargeModel(e.target.checked)} />
              Usar modelo grande (M2M100 1.2B - melhor qualidade)
            </label>
          )}
        </section>

        {/* Multiplos Falantes */}
        <section className="border border-gray-800 rounded-lg p-5">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={diarize}
              onChange={(e) => { setDiarize(e.target.checked); if (!e.target.checked) setNumSpeakers(""); }}
              className="w-4 h-4"
            />
            <div>
              <div className="font-medium">Multiplos Falantes</div>
              <div className="text-sm text-gray-400">Detecta e separa vozes diferentes no video (entrevistas, podcasts, debates)</div>
            </div>
          </label>

          {diarize && (
            <div className="mt-4 pl-7 space-y-3">
              <div className="flex items-center gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Numero de falantes</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min="2"
                      max="10"
                      value={numSpeakers}
                      onChange={(e) => setNumSpeakers(e.target.value === "" ? "" : Number(e.target.value))}
                      placeholder="Auto"
                      className="w-24 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-600"
                    />
                    <span className="text-sm text-gray-500">Deixe vazio para detectar automaticamente</span>
                  </div>
                </div>
              </div>

              {ttsEngine !== "edge" && (
                <div className="text-sm text-yellow-400 bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
                  O motor TTS selecionado ({ttsEngine}) nao suporta vozes distintas por falante. Use <strong>Edge TTS</strong> para que cada pessoa receba uma voz diferente na dublagem.
                </div>
              )}

              {ttsEngine === "edge" && (
                <div className="text-sm text-purple-300 bg-purple-500/10 border border-purple-500/30 rounded-lg p-3">
                  Cada falante detectado recebera automaticamente uma voz diferente do Edge TTS.
                </div>
              )}
            </div>
          )}
        </section>

        {/* Opcoes Avancadas */}
        <section className="border border-gray-800 rounded-lg p-5">
          <button type="button" onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors">
            <span className={`transform transition-transform ${showAdvanced ? "rotate-90" : ""}`}>&#9654;</span>
            Opcoes Avancadas
          </button>

          {showAdvanced && (
            <div className="mt-4 space-y-4">
              {/* Sync Mode */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <label className="block text-sm text-gray-400">Modo de Sync</label>
                  <button type="button"
                    onClick={() => setExpandedHelp(expandedHelp === "sync" ? null : "sync")}
                    className="w-4 h-4 rounded-full border border-gray-500 text-gray-400 hover:text-white hover:border-gray-300 text-[10px] leading-4 text-center">
                    i
                  </button>
                </div>
                <select value={syncMode} onChange={(e) => setSyncMode(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white">
                  {Object.entries(SYNC_HELP).map(([id, info]) => (
                    <option key={id} value={id}>{info.name}</option>
                  ))}
                </select>
                {expandedHelp === "sync" && (
                  <div className="mt-2 space-y-2">
                    {Object.entries(SYNC_HELP).map(([id, info]) => (
                      <div key={id} className={`text-xs p-2 rounded ${syncMode === id ? "bg-blue-500/10 border border-blue-500/30 text-blue-300" : "bg-gray-800/50 text-gray-400"}`}>
                        <span className="font-medium text-gray-300">{info.name}:</span> {info.desc}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Max Stretch */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <label className="block text-sm text-gray-400">Max Stretch: {maxstretch}x ({Math.round((maxstretch - 1) * 100)}% compressao)</label>
                  <button type="button"
                    onClick={() => setExpandedHelp(expandedHelp === "maxstretch" ? null : "maxstretch")}
                    className="w-4 h-4 rounded-full border border-gray-500 text-gray-400 hover:text-white hover:border-gray-300 text-[10px] leading-4 text-center">
                    i
                  </button>
                </div>
                <input type="range" min="1" max="2.5" step="0.05" value={maxstretch}
                  onChange={(e) => setMaxstretch(Number(e.target.value))}
                  className="w-full" />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>1.0x (sem compressao)</span>
                  <span>2.5x (muito rapido)</span>
                </div>
                {expandedHelp === "maxstretch" && (
                  <div className="mt-2 text-xs p-2 rounded bg-gray-800/50 text-gray-400">
                    {ADVANCED_HELP.maxstretch}
                  </div>
                )}
              </div>

              {/* No Truncate */}
              <div>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={noTruncate} onChange={(e) => setNoTruncate(e.target.checked)} />
                    Manter frases completas (nao truncar texto)
                  </label>
                  <button type="button"
                    onClick={() => setExpandedHelp(expandedHelp === "noTruncate" ? null : "noTruncate")}
                    className="w-4 h-4 rounded-full border border-gray-500 text-gray-400 hover:text-white hover:border-gray-300 text-[10px] leading-4 text-center">
                    i
                  </button>
                </div>
                {expandedHelp === "noTruncate" && (
                  <div className="mt-2 text-xs p-2 rounded bg-gray-800/50 text-gray-400">
                    {ADVANCED_HELP.noTruncate}
                  </div>
                )}
              </div>

              {/* TTS Rate */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Velocidade da voz: {ttsRate === "+0%" ? "normal" : ttsRate}
                </label>
                <input type="range" min="-30" max="50" step="5"
                  value={parseInt(ttsRate.replace("%", "").replace("+", ""))}
                  onChange={(e) => {
                    const v = parseInt(e.target.value);
                    setTtsRate(v >= 0 ? `+${v}%` : `${v}%`);
                  }}
                  className="w-full" />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>-30% (mais lento)</span>
                  <span>+0% (normal)</span>
                  <span>+50% (mais rapido)</span>
                </div>
              </div>

              {/* Seed */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <label className="block text-sm text-gray-400">Seed</label>
                  <button type="button"
                    onClick={() => setExpandedHelp(expandedHelp === "seed" ? null : "seed")}
                    className="w-4 h-4 rounded-full border border-gray-500 text-gray-400 hover:text-white hover:border-gray-300 text-[10px] leading-4 text-center">
                    i
                  </button>
                </div>
                <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))}
                  className="w-32 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white" />
                {expandedHelp === "seed" && (
                  <div className="mt-2 text-xs p-2 rounded bg-gray-800/50 text-gray-400">
                    {ADVANCED_HELP.seed}
                  </div>
                )}
              </div>
            </div>
          )}
        </section>

        {/* Submit */}
        <div className="space-y-2">
          <button type="submit" disabled={loading || (!input && !uploadFile)}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed
              text-white px-6 py-3 rounded-lg font-medium text-lg transition-colors">
            {loading
              ? uploadProgress !== null
                ? `Enviando... ${uploadProgress}%`
                : "Iniciando..."
              : "Iniciar Dublagem"}
          </button>
          {loading && uploadProgress !== null && (
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          )}
        </div>
      </form>
    </div>
  );
}
