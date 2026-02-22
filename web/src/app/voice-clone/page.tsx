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

type QualityLevel = "analisando" | "insuficiente" | "fraca" | "boa" | "excelente";

type RefAnalysis = {
  level: QualityLevel;
  duration: number;
  bitrate_kbps: number;
  label: string;
  score: number; // 0-100
  hints: string[];
};

const QUALITY_META: Record<QualityLevel, { color: string; bar: string; icon: string }> = {
  analisando: { color: "text-gray-400", bar: "bg-gray-500", icon: "⏳" },
  insuficiente: { color: "text-red-400", bar: "bg-red-500", icon: "✗" },
  fraca:        { color: "text-orange-400", bar: "bg-orange-500", icon: "!" },
  boa:          { color: "text-yellow-400", bar: "bg-yellow-400", icon: "✓" },
  excelente:    { color: "text-green-400", bar: "bg-green-500", icon: "✓✓" },
};

async function analyzeRef(file: File): Promise<RefAnalysis> {
  // Medir duração via HTMLAudioElement
  const duration = await new Promise<number>((resolve) => {
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    audio.preload = "metadata";
    audio.onloadedmetadata = () => { URL.revokeObjectURL(url); resolve(audio.duration); };
    audio.onerror = () => { URL.revokeObjectURL(url); resolve(-1); };
    audio.src = url;
  });

  const bitrate_kbps = duration > 0 ? Math.round((file.size * 8) / duration / 1000) : 0;

  const hints: string[] = [];
  let score = 0;
  let level: QualityLevel;

  if (duration < 0) {
    // Não conseguiu ler — formato pode ser problemático mas deixar tentar
    level = "fraca";
    score = 30;
    hints.push("Não foi possível medir a duração — o modelo vai tentar assim mesmo.");
  } else if (duration < 3) {
    level = "insuficiente";
    score = 10;
    hints.push(`Áudio muito curto (${duration.toFixed(1)}s). Mínimo recomendado: 5s.`);
    hints.push("Clones com < 3s costumam sair com voz completamente diferente.");
  } else if (duration < 8) {
    level = "fraca";
    score = 40;
    hints.push(`Duração marginal (${duration.toFixed(1)}s). Ideal: acima de 10s.`);
    hints.push("O clone pode capturar a voz, mas com menos naturalidade.");
  } else if (duration < 30) {
    level = "boa";
    score = 75;
    hints.push(`Duração boa (${duration.toFixed(1)}s).`);
    if (duration < 15) hints.push("Para ainda mais fidelidade, use 15-30s de referência.");
  } else {
    level = "excelente";
    score = 95;
    hints.push(`Duração excelente (${duration.toFixed(1)}s).`);
  }

  // Penalizar bitrate muito baixo (possível áudio comprimido demais)
  if (bitrate_kbps > 0 && bitrate_kbps < 48 && level !== "insuficiente") {
    score = Math.max(score - 20, 15);
    hints.push(`Bitrate estimado baixo (~${bitrate_kbps}kbps) — qualidade de áudio pode ser ruim.`);
    if (level === "excelente") level = "boa";
    else if (level === "boa") level = "fraca";
  }

  // Bônus para WAV (lossless)
  if (file.name.toLowerCase().endsWith(".wav")) {
    hints.push("Formato WAV — qualidade máxima para o modelo.");
  }

  // Aviso se duração muito longa (> 60s desnecessário)
  if (duration > 60) {
    hints.push("Áudio longo: o modelo usa só os primeiros ~30s de referência.");
  }

  return { level, duration, bitrate_kbps, score, label: level.charAt(0).toUpperCase() + level.slice(1), hints };
}

function RefQualityBadge({ analysis }: { analysis: RefAnalysis | null }) {
  if (!analysis) return null;
  const meta = QUALITY_META[analysis.level];

  return (
    <div className={`mt-3 rounded-lg p-3 border ${
      analysis.level === "insuficiente" ? "border-red-500/40 bg-red-500/5" :
      analysis.level === "fraca"        ? "border-orange-500/40 bg-orange-500/5" :
      analysis.level === "boa"          ? "border-yellow-400/40 bg-yellow-400/5" :
      analysis.level === "excelente"    ? "border-green-500/40 bg-green-500/5" :
                                          "border-gray-700 bg-gray-800/50"
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className={`flex items-center gap-2 text-sm font-semibold ${meta.color}`}>
          <span>{meta.icon}</span>
          <span>Qualidade da Referência: {analysis.label}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          {analysis.duration > 0 && <span>{analysis.duration.toFixed(1)}s</span>}
          {analysis.bitrate_kbps > 0 && <span>~{analysis.bitrate_kbps}kbps</span>}
        </div>
      </div>

      {/* Barra de score */}
      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden mb-2">
        <div
          className={`h-full rounded-full transition-all duration-500 ${meta.bar}`}
          style={{ width: `${analysis.score}%` }}
        />
      </div>

      {/* Hints */}
      <ul className="space-y-0.5">
        {analysis.hints.map((h, i) => (
          <li key={i} className="text-xs text-gray-400 flex gap-1.5">
            <span className="text-gray-600 mt-0.5">›</span>
            <span>{h}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function VoiceClonePage() {
  const [refFile, setRefFile] = useState<File | null>(null);
  const [refAnalysis, setRefAnalysis] = useState<RefAnalysis | null>(null);
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

  async function handleRefChange(file: File | null) {
    setRefFile(file);
    setRefAnalysis(null);
    if (!file) return;
    // Mostrar "analisando" enquanto processa
    setRefAnalysis({ level: "analisando", duration: 0, bitrate_kbps: 0, score: 0, label: "Analisando...", hints: [] });
    const analysis = await analyzeRef(file);
    setRefAnalysis(analysis);
  }

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
  const refInsuficiente = refAnalysis?.level === "insuficiente";

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Clonar Voz</h1>
      <p className="text-gray-400 mb-8">Sintetize texto com a voz de qualquer pessoa — zero-shot com Chatterbox</p>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Audio de referencia */}
        <div className="border border-gray-800 rounded-lg p-5">
          <label className="block text-sm text-gray-400 mb-3">
            Audio de Referencia
            <span className="ml-2 text-gray-600 text-xs">WAV, MP3, MP4 — mínimo 5s, ideal 10-30s</span>
          </label>
          <label className={`flex flex-col items-center justify-center border-2 border-dashed rounded-lg p-8 cursor-pointer transition-colors ${
            refInsuficiente
              ? "border-red-500/50 hover:border-red-500/70"
              : refAnalysis?.level === "excelente"
              ? "border-green-500/50 hover:border-green-500/70"
              : refAnalysis?.level === "boa"
              ? "border-yellow-400/50 hover:border-yellow-400/70"
              : "border-gray-700 hover:border-pink-500/50"
          }`}>
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
              onChange={(e) => handleRefChange(e.target.files?.[0] || null)}
            />
          </label>

          {/* Badge de qualidade */}
          <RefQualityBadge analysis={refAnalysis} />
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
          disabled={!refFile || !text.trim() || busy || refInsuficiente}
          className="w-full py-3 rounded-lg font-semibold transition-colors bg-pink-600 hover:bg-pink-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy ? progress : refInsuficiente ? "Referência insuficiente — troque o áudio" : "Clonar Voz e Gerar Audio"}
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
