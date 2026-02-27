"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getOllamaStatus, startOllama, stopOllama, getOptions, createCutJob, createCutJobWithUpload } from "@/lib/api";

type OllamaModel = { id: string; name: string; size_gb: number };

const DEFAULT_VIRAL_SYSTEM =
  "You are an expert video editor and social media strategist specializing in " +
  "viral short-form content. Your goal is to identify the most engaging, " +
  "shareable moments from video transcripts.";

const DEFAULT_VIRAL_USER =
  "Analyze this video transcript and identify the {num_clips} most engaging/viral segments.\n\n" +
  "Requirements:\n" +
  "- Each clip must be between {min_dur} and {max_dur} seconds long\n" +
  "- Choose complete thoughts/stories, never cut mid-sentence\n" +
  "- Prioritize: hooks, surprising facts, emotional moments, actionable tips, controversial opinions\n" +
  "- Clips must not overlap\n\n" +
  "Transcript:\n{transcript}\n\n" +
  "Respond ONLY with a valid JSON array (no extra text, no markdown):\n" +
  '[\n  {"start": 10.5, "end": 75.2, "reason": "Strong hook about..."},\n' +
  '  {"start": 120.0, "end": 195.0, "reason": "Viral moment: ..."}\n]';

const DEFAULT_TOPIC_SYSTEM =
  "You are an expert content analyst specializing in segmenting video content by topic. " +
  "Your goal is to identify distinct subjects discussed and group related content together " +
  "into coherent clips, one per topic.";

const DEFAULT_TOPIC_USER =
  "Analyze this video transcript and identify all distinct topics or subjects discussed.\n\n" +
  "Requirements:\n" +
  "- Each clip must cover ONE complete topic or subject area from start to finish\n" +
  "- Group ALL consecutive content about the same topic into a single clip\n" +
  "- When the speaker switches to a new subject, start a new clip\n" +
  "- Clips can be ANY duration — short or long, do NOT split clips to meet a time limit\n" +
  "- Find at most {num_clips} distinct topics (find fewer if there are fewer distinct subjects)\n" +
  "- Clips must not overlap and must cover the full transcript with no gaps\n\n" +
  "Transcript:\n{transcript}\n\n" +
  "Respond ONLY with a valid JSON array (no extra text, no markdown):\n" +
  '[\n  {"start": 10.5, "end": 75.2, "reason": "Assunto: Introducao e contexto"},\n' +
  '  {"start": 75.2, "end": 300.0, "reason": "Assunto: ..."}\n]';

export default function CutPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Input
  const [input, setInput] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  // Mode
  const [mode, setMode] = useState<"manual" | "viral">("manual");

  // Manual
  const [timestamps, setTimestamps] = useState("");

  // Viral — análise
  const [analysisMode, setAnalysisMode] = useState<"viral" | "topics">("viral");
  const [numClips, setNumClips] = useState(5);
  const [minDuration, setMinDuration] = useState(30);
  const [maxDuration, setMaxDuration] = useState(120);
  const [asrEngine, setAsrEngine] = useState<"whisper" | "parakeet">("whisper");
  const [whisperModel, setWhisperModel] = useState("large-v3");
  const [parakeetModel, setParakeetModel] = useState("nvidia/parakeet-tdt-1.1b");

  // Prompts — viral
  const [viralSystem, setViralSystem] = useState(DEFAULT_VIRAL_SYSTEM);
  const [viralUser, setViralUser] = useState(DEFAULT_VIRAL_USER);
  // Prompts — topics
  const [topicSystem, setTopicSystem] = useState(DEFAULT_TOPIC_SYSTEM);
  const [topicUser, setTopicUser] = useState(DEFAULT_TOPIC_USER);

  const [showPromptEditor, setShowPromptEditor] = useState(false);

  // LLM provider
  const [llmProvider, setLlmProvider] = useState<"ollama" | "openai" | "anthropic" | "groq" | "deepseek" | "together" | "openrouter" | "custom">("ollama");
  const [ollamaModel, setOllamaModel] = useState("qwen2.5:7b");
  const [llmModel, setLlmModel] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");

  // Ollama state
  const [ollamaOnline, setOllamaOnline] = useState<boolean | null>(null);
  const [ollamaModels, setOllamaModels] = useState<OllamaModel[]>([]);
  const [ollamaLoading, setOllamaLoading] = useState(false);
  const [ollamaSort, setOllamaSort] = useState<"size" | "name">("size");

  // ASR options
  const [whisperModels, setWhisperModels] = useState<{ id: string; name: string; quality: string }[]>([]);
  const [asrEngines, setAsrEngines] = useState<{ id: string; name: string; description: string }[]>([]);

  useEffect(() => {
    getOptions().then((opts) => {
      if (opts.whisper_models) setWhisperModels(opts.whisper_models);
      if (opts.asr_engines) setAsrEngines(opts.asr_engines);
    }).catch(() => {});
  }, []);

  // Pre-preencher a partir de ?prefill= (retry de job existente)
  useEffect(() => {
    const raw = searchParams.get("prefill");
    if (!raw) return;
    try {
      const cfg = JSON.parse(decodeURIComponent(raw)) as Record<string, unknown>;
      if (cfg.input && typeof cfg.input === "string") setInput(cfg.input);
      if (cfg.timestamps) setTimestamps(String(cfg.timestamps));
      // Se mode é viral ou topics, muda para IA
      if (cfg.mode === "viral") { setMode("viral"); setAnalysisMode("viral"); }
      if (cfg.mode === "topics") { setMode("viral"); setAnalysisMode("topics"); }
      if (cfg.num_clips) setNumClips(Number(cfg.num_clips));
      if (cfg.min_duration) setMinDuration(Number(cfg.min_duration));
      if (cfg.max_duration) setMaxDuration(Number(cfg.max_duration));
      if (cfg.asr_engine) setAsrEngine(cfg.asr_engine as "whisper" | "parakeet");
      if (cfg.whisper_model) setWhisperModel(String(cfg.whisper_model));
      if (cfg.parakeet_model) setParakeetModel(String(cfg.parakeet_model));
      if (cfg.llm_provider) setLlmProvider(cfg.llm_provider as typeof llmProvider);
      if (cfg.ollama_model) setOllamaModel(String(cfg.ollama_model));
      if (cfg.llm_model) setLlmModel(String(cfg.llm_model));
      if (cfg.llm_api_key) setLlmApiKey(String(cfg.llm_api_key));
      if (cfg.llm_base_url) setLlmBaseUrl(String(cfg.llm_base_url));
      if (cfg.system_prompt) {
        if (cfg.mode === "topics") setTopicSystem(String(cfg.system_prompt));
        else setViralSystem(String(cfg.system_prompt));
      }
      if (cfg.user_prompt) {
        if (cfg.mode === "topics") setTopicUser(String(cfg.user_prompt));
        else setViralUser(String(cfg.user_prompt));
      }
    } catch { /* ignorar parse errors */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshOllamaStatus = async () => {
    try {
      const st = await getOllamaStatus();
      setOllamaOnline(st.online);
      if (st.online && st.models) setOllamaModels(st.models);
    } catch {
      setOllamaOnline(false);
    }
  };

  useEffect(() => {
    if (mode === "viral") {
      refreshOllamaStatus();
      const interval = setInterval(refreshOllamaStatus, 5000);
      return () => clearInterval(interval);
    }
  }, [mode]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input && !uploadFile) return;
    setLoading(true);
    setError(null);
    setUploadProgress(null);

    try {
      // When AI mode, use "topics" or "viral" based on analysisMode
      const effectiveMode = mode === "viral" ? analysisMode : mode;
      const config: Record<string, unknown> = {
        input: uploadFile ? uploadFile.name : input,
        mode: effectiveMode,
      };

      if (mode === "manual") {
        if (!timestamps.trim()) throw new Error("Informe os timestamps no modo manual");
        config.timestamps = timestamps.trim();
      } else {
        // num_clips: for topics with 0 (auto), send 50 as upper bound
        config.num_clips = analysisMode === "topics" && numClips === 0 ? 50 : numClips;
        // topics mode: no duration constraints — any size clip is ok
        if (analysisMode === "viral") {
          config.min_duration = minDuration;
          config.max_duration = maxDuration;
        }
        config.asr_engine = asrEngine;
        if (asrEngine === "parakeet") {
          config.parakeet_model = parakeetModel;
        } else {
          config.whisper_model = whisperModel;
        }
        config.llm_provider = llmProvider;
        if (llmProvider === "ollama") {
          config.ollama_model = ollamaModel;
        } else {
          config.llm_model = llmModel;
          config.llm_api_key = llmApiKey;
          if (llmProvider === "custom") config.llm_base_url = llmBaseUrl;
        }

        // Prompts (only send if different from backend viral defaults)
        const activeSystem = analysisMode === "topics" ? topicSystem : viralSystem;
        const activeUser = analysisMode === "topics" ? topicUser : viralUser;
        const defaultSystem = analysisMode === "topics" ? DEFAULT_TOPIC_SYSTEM : DEFAULT_VIRAL_SYSTEM;
        const defaultUser = analysisMode === "topics" ? DEFAULT_TOPIC_USER : DEFAULT_VIRAL_USER;

        // Always send for topics mode (backend default is viral); send for viral only if changed
        if (analysisMode === "topics" || activeSystem !== DEFAULT_VIRAL_SYSTEM) config.system_prompt = activeSystem !== defaultSystem ? activeSystem : (analysisMode === "topics" ? DEFAULT_TOPIC_SYSTEM : undefined);
        if (analysisMode === "topics") config.system_prompt = activeSystem;
        if (analysisMode === "topics") config.user_prompt = activeUser;
        if (analysisMode === "viral" && activeSystem !== DEFAULT_VIRAL_SYSTEM) config.system_prompt = activeSystem;
        if (analysisMode === "viral" && activeUser !== DEFAULT_VIRAL_USER) config.user_prompt = activeUser;
      }

      const job = uploadFile
        ? await createCutJobWithUpload(uploadFile, config, (p) => setUploadProgress(p))
        : await createCutJob(config);

      router.push(`/jobs/${(job as Record<string, unknown>).id}`);
    } catch (err) {
      setError(String(err));
      setLoading(false);
      setUploadProgress(null);
    }
  };

  const llmReady = llmProvider === "ollama" ? !!ollamaOnline : (!!llmModel && !!llmApiKey);

  const activeSystem = analysisMode === "topics" ? topicSystem : viralSystem;
  const activeUser = analysisMode === "topics" ? topicUser : viralUser;
  const setActiveSystem = analysisMode === "topics" ? setTopicSystem : setViralSystem;
  const setActiveUser = analysisMode === "topics" ? setTopicUser : setViralUser;
  const defaultActiveSystem = analysisMode === "topics" ? DEFAULT_TOPIC_SYSTEM : DEFAULT_VIRAL_SYSTEM;
  const defaultActiveUser = analysisMode === "topics" ? DEFAULT_TOPIC_USER : DEFAULT_VIRAL_USER;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Cortar Video</h1>
        <p className="text-gray-400">Extraia clips por timestamps manuais ou deixe a IA identificar os momentos certos</p>
      </div>

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

        {/* Mode */}
        <section className="border border-gray-800 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-4">Modo de Corte</h2>
          <div className="grid grid-cols-2 gap-3">
            <label className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
              mode === "manual" ? "border-blue-500 bg-blue-500/10" : "border-gray-700 hover:border-gray-600"
            }`}>
              <input type="radio" checked={mode === "manual"} onChange={() => setMode("manual")} className="mt-1" />
              <div>
                <div className="font-medium">Manual</div>
                <div className="text-sm text-gray-400">Defina timestamps especificos</div>
              </div>
            </label>
            <label className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
              mode === "viral" ? "border-orange-500 bg-orange-500/10" : "border-gray-700 hover:border-gray-600"
            }`}>
              <input type="radio" checked={mode === "viral"} onChange={() => setMode("viral")} className="mt-1" />
              <div>
                <div className="font-medium">Analise (IA)</div>
                <div className="text-sm text-gray-400">LLM transcreve e analisa o conteudo</div>
              </div>
            </label>
          </div>
        </section>

        {/* Manual config */}
        {mode === "manual" && (
          <section className="border border-gray-800 rounded-lg p-5">
            <h2 className="text-lg font-semibold mb-2">Timestamps</h2>
            <p className="text-sm text-gray-400 mb-3">
              Formatos aceitos: <code className="bg-gray-800 px-1 rounded">MM:SS-MM:SS</code> ou{" "}
              <code className="bg-gray-800 px-1 rounded">HH:MM:SS-HH:MM:SS</code>.
              Separe multiplos clips com virgula.
            </p>
            <textarea
              value={timestamps}
              onChange={(e) => setTimestamps(e.target.value)}
              placeholder={"00:30-02:15, 05:00-07:30\n10:45-12:00"}
              rows={3}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none font-mono text-sm"
              required
            />
            <p className="text-xs text-gray-500 mt-2">
              Exemplo: <code>00:30-02:15, 05:00-07:30</code> gera 2 clips (1m45s e 2m30s)
            </p>
          </section>
        )}

        {/* Viral config */}
        {mode === "viral" && (
          <section className="border border-orange-900/30 bg-orange-950/10 rounded-lg p-5 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Analise</h2>
              <div className="flex gap-1 bg-gray-900 border border-gray-700 rounded-lg p-1">
                <button type="button"
                  onClick={() => setAnalysisMode("viral")}
                  className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                    analysisMode === "viral"
                      ? "bg-orange-500/30 text-orange-300"
                      : "text-gray-400 hover:text-gray-300"
                  }`}>
                  Viral
                </button>
                <button type="button"
                  onClick={() => { setAnalysisMode("topics"); if (numClips === 5) setNumClips(0); }}
                  className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                    analysisMode === "topics"
                      ? "bg-purple-500/30 text-purple-300"
                      : "text-gray-400 hover:text-gray-300"
                  }`}>
                  Assunto
                </button>
              </div>
            </div>
            {analysisMode === "topics" && (
              <p className="text-xs text-purple-400/80 -mt-3">
                A IA identifica os diferentes assuntos discutidos e cria um clip por topico.
              </p>
            )}

            {/* Clips / topics count + duration */}
            <div className={`grid gap-4 ${analysisMode === "topics" ? "grid-cols-1 max-w-xs" : "grid-cols-3"}`}>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  {analysisMode === "topics" ? "Max. assuntos (0 = auto)" : "Numero de clips"}
                </label>
                <input
                  type="number" min={0} max={analysisMode === "topics" ? 50 : 20} value={numClips}
                  onChange={(e) => setNumClips(Number(e.target.value))}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
                {analysisMode === "topics" && (
                  <p className="text-xs text-gray-500 mt-1">0 = identifica todos os assuntos automaticamente</p>
                )}
              </div>
              {analysisMode === "viral" && (
                <>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Min. duracao (s)</label>
                    <input
                      type="number" min={5} max={600} value={minDuration}
                      onChange={(e) => setMinDuration(Number(e.target.value))}
                      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Max. duracao (s)</label>
                    <input
                      type="number" min={5} max={600} value={maxDuration}
                      onChange={(e) => setMaxDuration(Number(e.target.value))}
                      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white"
                    />
                  </div>
                </>
              )}
            </div>

            {/* Whisper model */}
            {/* ASR Engine */}
            <div>
              <label className="block text-sm text-gray-400 mb-2">Motor de Transcricao (ASR)</label>
              <div className="flex gap-2 mb-2">
                {(asrEngines.length > 0 ? asrEngines : [
                  { id: "whisper", name: "Whisper", description: "Multi-idioma" },
                  { id: "parakeet", name: "Parakeet", description: "Ingles, mais rapido" },
                ]).map((eng) => (
                  <button key={eng.id} type="button" onClick={() => setAsrEngine(eng.id as "whisper" | "parakeet")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                      asrEngine === eng.id
                        ? "bg-blue-500/20 border-blue-500/50 text-blue-300"
                        : "bg-gray-900 border-gray-700 text-gray-400 hover:border-gray-500"
                    }`}>
                    {eng.name}
                    <span className="ml-1 text-gray-500">— {eng.description}</span>
                  </button>
                ))}
              </div>
              {asrEngine === "whisper" && (
                <select value={whisperModel} onChange={(e) => setWhisperModel(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white">
                  {whisperModels.length > 0
                    ? whisperModels.map((m) => (
                      <option key={m.id} value={m.id}>{m.name} - {m.quality}</option>
                    ))
                    : <>
                      <option value="large-v3">large-v3 - Alta qualidade</option>
                      <option value="medium">medium - Balanceado</option>
                      <option value="small">small - Rapido</option>
                    </>
                  }
                </select>
              )}
              {asrEngine === "parakeet" && (
                <select value={parakeetModel} onChange={(e) => setParakeetModel(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white">
                  <option value="nvidia/parakeet-tdt-1.1b">parakeet-tdt-1.1b (recomendado)</option>
                  <option value="nvidia/parakeet-ctc-1.1b">parakeet-ctc-1.1b (mais rapido)</option>
                  <option value="nvidia/parakeet-rnnt-1.1b">parakeet-rnnt-1.1b (mais preciso)</option>
                </select>
              )}
            </div>

            {/* LLM Provider selector */}
            <div>
              <label className="block text-sm text-gray-400 mb-2">Modelo de Analise (LLM)</label>
              <div className="flex gap-2 mb-3 flex-wrap">
                {(["ollama", "openai", "anthropic", "groq", "deepseek", "together", "openrouter", "custom"] as const).map((p) => (
                  <button key={p} type="button" onClick={() => setLlmProvider(p)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                      llmProvider === p
                        ? "bg-orange-500/20 border-orange-500/50 text-orange-300"
                        : "bg-gray-900 border-gray-700 text-gray-400 hover:border-gray-500"
                    }`}>
                    {p === "ollama" ? "Ollama (local)" : p.charAt(0).toUpperCase() + p.slice(1)}
                  </button>
                ))}
              </div>

              {/* Ollama local */}
              {llmProvider === "ollama" && (
                <div className="border border-gray-700 rounded-lg p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className={`w-2.5 h-2.5 rounded-full ${ollamaOnline ? "bg-green-500" : "bg-red-500"}`} />
                      <span className="text-sm font-medium">Ollama {ollamaOnline ? "Online" : "Offline"}</span>
                    </div>
                    <button type="button" disabled={ollamaLoading}
                      onClick={async () => {
                        setOllamaLoading(true);
                        try {
                          if (ollamaOnline) await stopOllama(); else await startOllama();
                          await refreshOllamaStatus();
                        } catch { /* ignore */ }
                        setOllamaLoading(false);
                      }}
                      className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors disabled:opacity-50 ${
                        ollamaOnline
                          ? "bg-red-600/20 text-red-400 border-red-500/30 hover:bg-red-600/30"
                          : "bg-green-600/20 text-green-400 border-green-500/30 hover:bg-green-600/30"
                      }`}>
                      {ollamaLoading ? "..." : ollamaOnline ? "Desligar" : "Ligar"}
                    </button>
                  </div>
                  {!ollamaOnline && (
                    <p className="text-sm text-yellow-400 bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
                      Ollama offline. Clique em "Ligar" ou escolha um provider externo acima.
                    </p>
                  )}
                  {ollamaOnline && ollamaModels.length > 0 && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <label className="text-sm text-gray-400">Modelo</label>
                        <div className="flex gap-1">
                          {(["size", "name"] as const).map((s) => (
                            <button key={s} type="button" onClick={() => setOllamaSort(s)}
                              className={`px-2 py-0.5 rounded text-xs ${ollamaSort === s ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"}`}>
                              {s === "size" ? "Tamanho" : "A-Z"}
                            </button>
                          ))}
                        </div>
                      </div>
                      <div className="space-y-1.5 max-h-48 overflow-y-auto">
                        {[...ollamaModels]
                          .sort((a, b) => ollamaSort === "size" ? b.size_gb - a.size_gb : a.name.localeCompare(b.name))
                          .map((m) => {
                            const sel = ollamaModel === m.id;
                            const sizeColor = m.size_gb >= 30 ? "text-purple-400" : m.size_gb >= 10 ? "text-blue-400" : m.size_gb >= 5 ? "text-green-400" : "text-gray-400";
                            return (
                              <button type="button" key={m.id} onClick={() => setOllamaModel(m.id)}
                                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                                  sel ? "bg-orange-500/15 border border-orange-500/40 text-white" : "bg-gray-900 border border-gray-700/50 text-gray-300 hover:border-gray-600"
                                }`}>
                                <div className={`w-3 h-3 rounded-full border-2 flex-shrink-0 ${sel ? "border-orange-400 bg-orange-400" : "border-gray-600"}`} />
                                <span className="flex-1 font-medium">{m.name.split(":")[0]}</span>
                                {m.name.split(":")[1] && <span className="text-gray-500 text-xs">:{m.name.split(":")[1]}</span>}
                                <span className={`font-mono text-xs ${sizeColor}`}>{m.size_gb}GB</span>
                              </button>
                            );
                          })}
                      </div>
                    </div>
                  )}
                  {ollamaOnline && ollamaModels.length === 0 && (
                    <p className="text-sm text-yellow-400">Nenhum modelo instalado no Ollama.</p>
                  )}
                </div>
              )}

              {/* API Externa */}
              {llmProvider !== "ollama" && (
                <div className="border border-gray-700 rounded-lg p-4 space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">Modelo</label>
                      <input
                        type="text"
                        value={llmModel}
                        onChange={(e) => setLlmModel(e.target.value)}
                        placeholder={
                          llmProvider === "openai" ? "gpt-4o" :
                          llmProvider === "anthropic" ? "claude-sonnet-4-6" :
                          llmProvider === "groq" ? "llama-3.3-70b-versatile" :
                          llmProvider === "deepseek" ? "deepseek-chat" :
                          llmProvider === "together" ? "meta-llama/Llama-3-70b-chat-hf" :
                          llmProvider === "openrouter" ? "openai/gpt-4o" :
                          "model-name"
                        }
                        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:border-orange-500 focus:outline-none"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">API Key</label>
                      <input
                        type="password"
                        value={llmApiKey}
                        onChange={(e) => setLlmApiKey(e.target.value)}
                        placeholder="sk-..."
                        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:border-orange-500 focus:outline-none"
                        required
                      />
                    </div>
                  </div>
                  {llmProvider === "custom" && (
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">Base URL (compativel com OpenAI)</label>
                      <input
                        type="text"
                        value={llmBaseUrl}
                        onChange={(e) => setLlmBaseUrl(e.target.value)}
                        placeholder="https://meu-servidor.com"
                        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:border-orange-500 focus:outline-none"
                        required
                      />
                    </div>
                  )}
                  <p className="text-xs text-gray-500">
                    {llmProvider === "openai" && "OpenAI — modelos GPT-4o, GPT-4o-mini, o1, etc."}
                    {llmProvider === "anthropic" && "Anthropic — Claude Sonnet, Haiku, Opus"}
                    {llmProvider === "groq" && "Groq — inferencia ultra-rapida (Llama, Mixtral, Gemma)"}
                    {llmProvider === "deepseek" && "DeepSeek — DeepSeek-V3, DeepSeek-R1"}
                    {llmProvider === "together" && "Together AI — modelos open-source hospedados"}
                    {llmProvider === "openrouter" && "OpenRouter — acesso unificado a 300+ modelos (GPT, Claude, Llama, Gemini...)"}
                    {llmProvider === "custom" && "Qualquer API compativel com OpenAI Chat Completions"}
                  </p>
                </div>
              )}
            </div>

            {/* Prompt customization (collapsible, open by default) */}
            <div className="border border-gray-700/50 rounded-lg overflow-hidden">
              <button
                type="button"
                onClick={() => setShowPromptEditor((v) => !v)}
                className="w-full flex items-center justify-between px-4 py-3 text-sm text-gray-400 hover:text-gray-300 hover:bg-gray-800/50 transition-colors"
              >
                <span className="font-medium">
                  Prompt do LLM
                  {analysisMode === "topics" && (
                    <span className="ml-2 text-xs text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full">Por Assunto</span>
                  )}
                  {(activeSystem !== defaultActiveSystem || activeUser !== defaultActiveUser) && (
                    <span className="ml-2 text-xs text-orange-400 bg-orange-500/10 px-2 py-0.5 rounded-full">modificado</span>
                  )}
                </span>
                <span className="text-lg leading-none">{showPromptEditor ? "▲" : "▼"}</span>
              </button>

              {showPromptEditor && (
                <div className="px-4 pb-4 space-y-4 border-t border-gray-700/50 pt-4">
                  <p className="text-xs text-gray-500">
                    Variaveis no User Prompt:{" "}
                    <code className="bg-gray-800 px-1 rounded">{"{num_clips}"}</code>{" "}
                    <code className="bg-gray-800 px-1 rounded">{"{min_dur}"}</code>{" "}
                    <code className="bg-gray-800 px-1 rounded">{"{max_dur}"}</code>{" "}
                    <code className="bg-gray-800 px-1 rounded">{"{transcript}"}</code>
                  </p>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs text-gray-400 font-medium">System Prompt</label>
                      {activeSystem !== defaultActiveSystem && (
                        <button type="button" onClick={() => setActiveSystem(defaultActiveSystem)}
                          className="text-xs text-gray-500 hover:text-gray-300">Restaurar padrao</button>
                      )}
                    </div>
                    <textarea
                      value={activeSystem}
                      onChange={(e) => setActiveSystem(e.target.value)}
                      rows={3}
                      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-xs font-mono focus:border-orange-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs text-gray-400 font-medium">User Prompt</label>
                      {activeUser !== defaultActiveUser && (
                        <button type="button" onClick={() => setActiveUser(defaultActiveUser)}
                          className="text-xs text-gray-500 hover:text-gray-300">Restaurar padrao</button>
                      )}
                    </div>
                    <textarea
                      value={activeUser}
                      onChange={(e) => setActiveUser(e.target.value)}
                      rows={9}
                      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-xs font-mono focus:border-orange-500 focus:outline-none"
                    />
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Submit */}
        <div className="space-y-2">
          <button type="submit"
            disabled={loading || (!input && !uploadFile) || (mode === "viral" && !llmReady)}
            className={`w-full disabled:bg-gray-700 disabled:cursor-not-allowed text-white px-6 py-3 rounded-lg font-medium text-lg transition-colors ${
              mode === "viral"
                ? analysisMode === "topics" ? "bg-purple-600 hover:bg-purple-700" : "bg-orange-600 hover:bg-orange-700"
                : "bg-blue-600 hover:bg-blue-700"
            }`}>
            {loading
              ? uploadProgress !== null
                ? `Enviando... ${uploadProgress}%`
                : "Iniciando..."
              : mode === "viral"
              ? analysisMode === "topics" ? "Analisar por Assunto" : "Analisar Viral"
              : "Cortar Video"}
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
