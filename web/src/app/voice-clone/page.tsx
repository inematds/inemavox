"use client";

import { useState, useEffect, useRef } from "react";
import { createVoiceCloneJobWithUpload, getAudioUrl, createJobWebSocket } from "@/lib/api";

const LANGS = [
  { code: "pt", label: "Português (BR)" },
  { code: "en", label: "English" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
  { code: "it", label: "Italiano" },
  { code: "ja", label: "日本語" },
  { code: "zh", label: "中文" },
  { code: "ko", label: "한국어" },
  { code: "ru", label: "Русский" },
];

export default function VoiceClonePage() {
  const [refFile, setRefFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [lang, setLang] = useState("pt");
  const [status, setStatus] = useState<"idle" | "uploading" | "loading" | "done" | "error">("idle");
  const [uploadPct, setUploadPct] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  async function runClone() {
    if (!refFile || !text.trim()) return;
    wsRef.current?.close();
    setStatus("uploading");
    setError("");
    setJobId(null);
    setUploadPct(0);
    setProgress("Enviando audio de referencia...");

    try {
      const job = await createVoiceCloneJobWithUpload(
        refFile,
        { text, lang },
        (pct) => setUploadPct(pct),
      ) as { id: string };

      setJobId(job.id);
      setStatus("loading");
      setProgress("Clonando voz...");

      const ws = createJobWebSocket(job.id);
      wsRef.current = ws;

      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        const j = data.job;
        if (j?.status === "completed") {
          setStatus("done");
          setProgress("Concluido!");
          ws.close();
        } else if (j?.status === "failed") {
          setStatus("error");
          setError(j.error || "Falha na clonagem");
          ws.close();
        }
      };
      ws.onerror = () => { setStatus("error"); setError("Erro de conexao com WebSocket"); };
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Erro desconhecido");
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    runClone();
  }

  const busy = status === "uploading" || status === "loading";

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Clonar Voz</h1>
      <p className="text-gray-400 mb-8">Sintetize texto com a voz de qualquer pessoa — zero-shot com Chatterbox</p>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Audio de referencia */}
        <div className="border border-gray-800 rounded-lg p-5">
          <label className="block text-sm text-gray-400 mb-3">
            Audio de Referencia
            <span className="ml-2 text-gray-600 text-xs">WAV, MP3, MP4 — minimo 5s recomendado</span>
          </label>
          <label className="flex flex-col items-center justify-center border-2 border-dashed border-gray-700 rounded-lg p-8 cursor-pointer hover:border-pink-500/50 transition-colors">
            {refFile ? (
              <div className="text-center">
                <div className="text-pink-400 font-medium">{refFile.name}</div>
                <div className="text-gray-500 text-xs mt-1">{(refFile.size / 1024 / 1024).toFixed(1)} MB</div>
              </div>
            ) : (
              <div className="text-center text-gray-500">
                <div className="text-3xl mb-2">🎤</div>
                <div className="text-sm">Clique para selecionar o audio de referencia</div>
              </div>
            )}
            <input
              type="file"
              accept="audio/*,video/*"
              className="hidden"
              onChange={(e) => setRefFile(e.target.files?.[0] || null)}
            />
          </label>
        </div>

        {/* Texto */}
        <div className="border border-gray-800 rounded-lg p-5">
          <label className="block text-sm text-gray-400 mb-2">Texto para Falar</label>
          <textarea
            className="w-full bg-gray-900 border border-gray-700 rounded p-3 text-sm resize-none focus:outline-none focus:border-pink-500 h-32"
            placeholder="Digite o que voce quer que a voz clonada diga..."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="text-xs text-gray-600 mt-1">{text.length} caracteres</div>
        </div>

        {/* Idioma */}
        <div className="border border-gray-800 rounded-lg p-5">
          <label className="block text-sm text-gray-400 mb-2">Idioma de Saida</label>
          <select
            className="w-full bg-gray-900 border border-gray-700 rounded p-2 text-sm"
            value={lang}
            onChange={(e) => setLang(e.target.value)}
          >
            {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </div>

        {/* Upload progress */}
        {status === "uploading" && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-gray-400">
              <span>Enviando...</span><span>{uploadPct}%</span>
            </div>
            <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div className="h-full bg-pink-500 transition-all" style={{ width: `${uploadPct}%` }} />
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400 text-sm">{error}</div>
        )}

        <button
          type="submit"
          disabled={!refFile || !text.trim() || busy}
          className="w-full py-3 rounded-lg font-semibold transition-colors bg-pink-600 hover:bg-pink-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy ? progress : "Clonar Voz e Gerar Audio"}
        </button>
      </form>

      {/* Resultado */}
      {status === "done" && jobId && (
        <div className="mt-6 border border-green-500/30 bg-green-500/5 rounded-lg p-6">
          <div className="text-green-400 font-semibold mb-4 text-center">Voz clonada com sucesso!</div>
          <audio controls className="w-full mb-4" src={getAudioUrl(jobId)} />
          <div className="flex gap-3 justify-center">
            <a
              href={getAudioUrl(jobId)}
              download
              className="px-5 py-2.5 bg-green-600 hover:bg-green-500 rounded-lg font-semibold transition-colors text-sm"
            >
              ⬇ Baixar Audio
            </a>
            <button
              type="button"
              onClick={runClone}
              disabled={!refFile}
              className="px-5 py-2.5 bg-pink-600 hover:bg-pink-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg font-semibold transition-colors text-sm"
            >
              ↺ Repetir Clone
            </button>
          </div>
        </div>
      )}

      {/* Erro com botão de repetir */}
      {status === "error" && refFile && (
        <div className="mt-4 flex justify-center">
          <button
            type="button"
            onClick={runClone}
            className="px-5 py-2.5 bg-pink-600 hover:bg-pink-500 rounded-lg font-semibold transition-colors text-sm"
          >
            ↺ Tentar Novamente
          </button>
        </div>
      )}
    </div>
  );
}
