"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getOptions, createTranscriptionJob, createTranscriptionJobWithUpload } from "@/lib/api";

export default function TranscribePage() {
  return (
    <Suspense>
      <Transcribe />
    </Suspense>
  );
}

function Transcribe() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Input
  const [input, setInput] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  // ASR
  const [asrEngine, setAsrEngine] = useState("whisper");
  const [whisperModel, setWhisperModel] = useState("large-v3");
  const [srcLang, setSrcLang] = useState("");

  // Options
  const [whisperModels, setWhisperModels] = useState<{ id: string; name: string; quality: string; turbo?: boolean }[]>([]);
  const [languages, setLanguages] = useState<{ code: string; name: string }[]>([]);

  useEffect(() => {
    getOptions().then((opts) => {
      if (opts.whisper_models) setWhisperModels(opts.whisper_models);
      if (opts.languages) setLanguages(opts.languages);
    }).catch(() => setError("API offline. Inicie o backend."));
  }, []);

  // Pre-preencher a partir de ?prefill= (retry de job existente)
  useEffect(() => {
    const raw = searchParams.get("prefill");
    if (!raw) return;
    try {
      const cfg = JSON.parse(decodeURIComponent(raw)) as Record<string, unknown>;
      if (cfg.input && typeof cfg.input === "string") setInput(cfg.input);
      if (cfg.asr_engine) setAsrEngine(String(cfg.asr_engine));
      if (cfg.whisper_model) setWhisperModel(String(cfg.whisper_model));
      if (cfg.src_lang) setSrcLang(String(cfg.src_lang));
    } catch { /* ignorar parse errors */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input && !uploadFile) return;
    setLoading(true);
    setError(null);
    setUploadProgress(null);

    try {
      const config: Record<string, unknown> = {
        input: uploadFile ? uploadFile.name : input,
        asr_engine: asrEngine,
        whisper_model: whisperModel,
      };
      if (srcLang) config.src_lang = srcLang;

      const job = uploadFile
        ? await createTranscriptionJobWithUpload(uploadFile, config, (p) => setUploadProgress(p))
        : await createTranscriptionJob(config);

      router.push(`/jobs/${(job as Record<string, unknown>).id}`);
    } catch (err) {
      setError(String(err));
      setLoading(false);
      setUploadProgress(null);
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Transcrever Video</h1>
        <p className="text-gray-400">Gera legendas SRT, TXT e JSON a partir de um video ou audio</p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 text-red-400">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Input */}
        <section className="border border-gray-800 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-4">Video ou Audio de Entrada</h2>
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
              {uploadFile ? uploadFile.name : "Enviar arquivo"}
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

        {/* ASR */}
        <section className="border border-gray-800 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-4">Motor de Transcricao</h2>

          <div className="grid grid-cols-2 gap-3 mb-4">
            <label className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
              asrEngine === "whisper" ? "border-purple-500 bg-purple-500/10" : "border-gray-700 hover:border-gray-600"
            }`}>
              <input type="radio" checked={asrEngine === "whisper"} onChange={() => setAsrEngine("whisper")} className="mt-1" />
              <div>
                <div className="font-medium">Whisper</div>
                <div className="text-sm text-gray-400">99+ idiomas, alta qualidade</div>
                <span className="inline-block mt-1 text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded">Multilingual</span>
              </div>
            </label>
            <label className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
              asrEngine === "parakeet" ? "border-purple-500 bg-purple-500/10" : "border-gray-700 hover:border-gray-600"
            }`}>
              <input type="radio" checked={asrEngine === "parakeet"} onChange={() => setAsrEngine("parakeet")} className="mt-1" />
              <div>
                <div className="font-medium">Parakeet</div>
                <div className="text-sm text-gray-400">Otimizado para ingles</div>
                <span className="inline-block mt-1 text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">Ingles only</span>
              </div>
            </label>
          </div>

          {asrEngine === "whisper" && (
            <div className="mb-4">
              <label className="block text-sm text-gray-400 mb-1">Modelo Whisper</label>
              <select value={whisperModel} onChange={(e) => setWhisperModel(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white">
                {whisperModels.length > 0
                  ? whisperModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} - {m.quality}{m.turbo ? " (rapido)" : ""}
                    </option>
                  ))
                  : <>
                    <option value="large-v3">large-v3 - Alta qualidade</option>
                    <option value="medium">medium - Balanceado</option>
                    <option value="small">small - Rapido</option>
                  </>
                }
              </select>
            </div>
          )}

          {asrEngine === "parakeet" && (
            <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-sm text-yellow-400">
              Parakeet suporta apenas ingles. Para outros idiomas, use Whisper.
            </div>
          )}

          <div>
            <label className="block text-sm text-gray-400 mb-1">Idioma de origem (vazio = auto-detect)</label>
            <select value={srcLang} onChange={(e) => setSrcLang(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white">
              <option value="">Auto-detect</option>
              {languages.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
            </select>
          </div>
        </section>

        {/* Output info */}
        <section className="border border-gray-800 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-3">Saidas Geradas</h2>
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-gray-900 rounded-lg p-3 text-center">
              <div className="text-2xl mb-1">📄</div>
              <div className="font-medium text-sm">SRT</div>
              <div className="text-xs text-gray-500 mt-1">Legendas sincronizadas</div>
            </div>
            <div className="bg-gray-900 rounded-lg p-3 text-center">
              <div className="text-2xl mb-1">📝</div>
              <div className="font-medium text-sm">TXT</div>
              <div className="text-xs text-gray-500 mt-1">Texto puro</div>
            </div>
            <div className="bg-gray-900 rounded-lg p-3 text-center">
              <div className="text-2xl mb-1">🗂</div>
              <div className="font-medium text-sm">JSON</div>
              <div className="text-xs text-gray-500 mt-1">Dados estruturados</div>
            </div>
          </div>
        </section>

        {/* Submit */}
        <div className="space-y-2">
          <button type="submit" disabled={loading || (!input && !uploadFile)}
            className="w-full bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white px-6 py-3 rounded-lg font-medium text-lg transition-colors">
            {loading
              ? uploadProgress !== null
                ? `Enviando... ${uploadProgress}%`
                : "Iniciando..."
              : "Iniciar Transcricao"}
          </button>
          {loading && uploadProgress !== null && (
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className="bg-purple-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          )}
        </div>
      </form>
    </div>
  );
}
