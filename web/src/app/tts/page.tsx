"use client";

import { useState, useEffect, useRef } from "react";
import { createTtsJob, createTtsJobWithUpload, getAudioUrl, createJobWebSocket, getOptions } from "@/lib/api";

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

export default function TtsPage() {
  const [text, setText] = useState("");
  const [lang, setLang] = useState("pt");
  const [engine, setEngine] = useState("edge");
  const [voice, setVoice] = useState("");
  const [edgeVoices, setEdgeVoices] = useState<{ id: string; name: string }[]>([]);
  const [refFile, setRefFile] = useState<File | null>(null);
  const [uploadPct, setUploadPct] = useState(0);
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    getOptions().then((opts) => {
      const voices = opts?.edge_voices?.[lang] || [];
      setEdgeVoices(voices);
      setVoice(voices[0]?.id || "");
    }).catch(() => {});
  }, [lang]);

  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setStatus("loading");
    setError("");
    setJobId(null);
    setProgress("Criando job...");

    try {
      let job: { id: string };
      if (engine === "chatterbox" && refFile) {
        job = await createTtsJobWithUpload(
          refFile,
          { text, lang, engine },
          (pct) => setUploadPct(pct),
        ) as { id: string };
      } else {
        job = await createTtsJob({ text, lang, engine, voice: voice || undefined }) as { id: string };
      }
      setJobId(job.id);
      setProgress("Gerando audio...");

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
          setError(j.error || "Falha na geracao");
          ws.close();
        }
      };
      ws.onerror = () => { setStatus("error"); setError("Erro de conexao com WebSocket"); };
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Erro desconhecido");
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Gerar Audio</h1>
      <p className="text-gray-400 mb-8">Converta texto em fala com IA local</p>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Texto */}
        <div className="border border-gray-800 rounded-lg p-5">
          <label className="block text-sm text-gray-400 mb-2">Texto</label>
          <textarea
            className="w-full bg-gray-900 border border-gray-700 rounded p-3 text-sm resize-none focus:outline-none focus:border-blue-500 h-36"
            placeholder="Digite o texto que deseja transformar em audio..."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="text-xs text-gray-600 mt-1">{text.length} caracteres</div>
        </div>

        {/* Idioma + Motor */}
        <div className="border border-gray-800 rounded-lg p-5 grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Idioma</label>
            <select
              className="w-full bg-gray-900 border border-gray-700 rounded p-2 text-sm"
              value={lang}
              onChange={(e) => setLang(e.target.value)}
            >
              {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Motor de Voz</label>
            <select
              className="w-full bg-gray-900 border border-gray-700 rounded p-2 text-sm"
              value={engine}
              onChange={(e) => setEngine(e.target.value)}
            >
              <option value="edge">Edge TTS (rapido, online)</option>
              <option value="chatterbox">Chatterbox (GPU, offline)</option>
            </select>
          </div>
        </div>

        {/* Voz Edge */}
        {engine === "edge" && edgeVoices.length > 0 && (
          <div className="border border-gray-800 rounded-lg p-5">
            <label className="block text-sm text-gray-400 mb-2">Voz</label>
            <select
              className="w-full bg-gray-900 border border-gray-700 rounded p-2 text-sm"
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
            >
              {edgeVoices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </div>
        )}

        {/* Voz Chatterbox: referencia opcional */}
        {engine === "chatterbox" && (
          <div className="border border-gray-800 rounded-lg p-5">
            <label className="block text-sm text-gray-400 mb-1">Audio de referencia (opcional)</label>
            <p className="text-xs text-gray-600 mb-3">Envie um audio para clonar a voz. Sem arquivo, usa a voz padrao do Chatterbox.</p>
            <label className={`flex items-center gap-3 border-2 border-dashed rounded-lg px-4 py-3 cursor-pointer transition-colors ${
              refFile ? "border-purple-500/50 hover:border-purple-500/70" : "border-gray-700 hover:border-purple-500/40"
            }`}>
              {refFile ? (
                <>
                  <span className="text-purple-400 text-sm font-medium truncate">{refFile.name}</span>
                  <span className="text-gray-500 text-xs ml-auto shrink-0">{(refFile.size / 1024 / 1024).toFixed(1)} MB</span>
                  <button type="button" onClick={(ev) => { ev.preventDefault(); setRefFile(null); }}
                    className="text-gray-500 hover:text-red-400 text-xs ml-1 shrink-0">✕</button>
                </>
              ) : (
                <span className="text-gray-500 text-sm">Clique para selecionar WAV / MP3 / MP4...</span>
              )}
              <input type="file" accept="audio/*,video/*,.wav,.mp3,.mp4,.m4a,.ogg,.webm" className="hidden"
                onChange={(e) => setRefFile(e.target.files?.[0] || null)} />
            </label>
            {status === "loading" && refFile && uploadPct < 100 && (
              <div className="mt-2">
                <div className="flex justify-between text-xs text-gray-400 mb-1">
                  <span>Enviando referencia...</span><span>{uploadPct}%</span>
                </div>
                <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
                  <div className="h-full bg-purple-500 transition-all" style={{ width: `${uploadPct}%` }} />
                </div>
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400 text-sm">{error}</div>
        )}

        {status === "done" ? (
          <button
            type="button"
            onClick={() => { setStatus("idle"); setJobId(null); setError(""); setProgress(""); setUploadPct(0); }}
            className="w-full py-3 rounded-lg font-semibold transition-colors bg-gray-700 hover:bg-gray-600"
          >
            + Gerar Novo Audio
          </button>
        ) : (
          <button
            type="submit"
            disabled={!text.trim() || status === "loading"}
            className="w-full py-3 rounded-lg font-semibold transition-colors bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {status === "loading" ? progress : "Gerar Audio"}
          </button>
        )}
      </form>

      {/* Resultado */}
      {status === "done" && jobId && (
        <div className="mt-6 border border-green-500/30 bg-green-500/5 rounded-lg p-5">
          <div className="text-green-400 font-semibold mb-3">Audio gerado com sucesso!</div>
          <audio controls className="w-full mb-4" src={getAudioUrl(jobId)}>
            Seu navegador nao suporta audio.
          </audio>
          <a
            href={getAudioUrl(jobId)}
            download
            className="inline-flex items-center gap-2 bg-green-600 hover:bg-green-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            ⬇ Baixar Audio
          </a>
        </div>
      )}
    </div>
  );
}
