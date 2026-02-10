"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import { getJob, getJobLogs, cancelJob, getDownloadUrl, getSubtitlesUrl, createJobWebSocket } from "@/lib/api";

type JobData = Record<string, unknown>;
type LogEntry = { timestamp: string; level: string; message: string };
type StageInfo = {
  num: number; id: string; name: string; icon: string;
  status: string; time?: number; elapsed?: number; estimate?: number; tool?: string;
};

function formatTime(seconds: number | undefined | null): string {
  if (!seconds || seconds <= 0) return "-";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m${s}s`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h${m}m`;
}

export default function JobDetail() {
  const params = useParams();
  const jobId = String(params.id);
  const [job, setJob] = useState<JobData | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const fetchJob = useCallback(() => {
    getJob(jobId).then(setJob).catch(() => setError("Erro ao carregar job"));
  }, [jobId]);

  const fetchLogs = useCallback(() => {
    getJobLogs(jobId, 200).then(setLogs).catch(() => {});
  }, [jobId]);

  useEffect(() => {
    fetchJob();
    fetchLogs();
    const interval = setInterval(() => { fetchJob(); fetchLogs(); }, 3000);
    return () => clearInterval(interval);
  }, [fetchJob, fetchLogs]);

  useEffect(() => {
    try {
      const ws = createJobWebSocket(jobId);
      wsRef.current = ws;
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.job) setJob(data.job);
          if (data.type === "log") setLogs((prev) => [...prev.slice(-500), data]);
        } catch { /* ignore */ }
      };
      return () => { ws.close(); };
    } catch { return; }
  }, [jobId]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const handleCancel = async () => {
    if (!confirm("Cancelar este job?")) return;
    setCancelling(true);
    try { await cancelJob(jobId); fetchJob(); } catch { setError("Erro ao cancelar"); }
    setCancelling(false);
  };

  if (!job && !error) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-800 rounded w-1/3" />
          <div className="h-64 bg-gray-800 rounded" />
        </div>
      </div>
    );
  }

  const config = (job?.config || {}) as Record<string, unknown>;
  const progress = (job?.progress || {}) as Record<string, unknown>;
  const stages = (progress.stages || []) as StageInfo[];
  const status = String(job?.status || "unknown");
  const device = String(job?.device || progress.device || "cpu");
  const isActive = status === "running" || status === "queued";
  const isCompleted = status === "completed";
  const isFailed = status === "failed";

  const etaText = String(progress.eta_text || "");
  const elapsedS = Number(progress.elapsed_s || job?.duration_s || 0);
  const percent = Number(progress.percent || (isCompleted ? 100 : 0));

  const statusLabels: Record<string, { color: string; label: string }> = {
    running: { color: "text-blue-400", label: "Em andamento" },
    completed: { color: "text-green-400", label: "Concluido" },
    failed: { color: "text-red-400", label: "Falhou" },
    queued: { color: "text-yellow-400", label: "Na fila" },
    cancelled: { color: "text-gray-400", label: "Cancelado" },
  };
  const sl = statusLabels[status] || { color: "text-gray-400", label: status };

  return (
    <div className="max-w-4xl mx-auto">
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 text-red-400">{error}</div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-bold font-mono">{jobId}</h1>
            <span className={`text-lg font-medium ${sl.color}`}>{sl.label}</span>
            <span className={`px-2 py-0.5 rounded text-xs font-bold ${
              device === "cuda" ? "bg-green-500/20 text-green-400 border border-green-500/30" : "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30"
            }`}>
              {device === "cuda" ? "GPU" : "CPU"}
            </span>
          </div>
          <p className="text-gray-500 text-sm">
            {job?.created_at ? new Date(Number(job.created_at) * 1000).toLocaleString("pt-BR") : "-"}
            <span className="mx-2">|</span>{String(config.src_lang || "auto")} → {String(config.tgt_lang || "pt")}
            <span className="mx-2">|</span>{String(config.content_type || "palestra")}
          </p>
        </div>
        <div className="flex gap-2">
          {isActive && (
            <button onClick={handleCancel} disabled={cancelling}
              className="bg-red-600 hover:bg-red-700 disabled:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm transition-colors">
              {cancelling ? "Cancelando..." : "Cancelar"}
            </button>
          )}
          <a href="/jobs" className="bg-gray-800 hover:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm transition-colors">
            Voltar
          </a>
        </div>
      </div>

      {/* Progress bar + ETA */}
      {(isActive || isCompleted) && (
        <section className="border border-gray-800 rounded-lg p-5 mb-6">
          <div className="flex justify-between items-center mb-3">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold">Progresso</h2>
              {isActive && etaText && (
                <span className="text-sm text-gray-400">
                  ETA: <span className="text-white font-mono">{etaText}</span>
                </span>
              )}
            </div>
            <div className="text-right">
              <span className="text-2xl font-bold font-mono text-blue-400">{percent}%</span>
              <div className="text-xs text-gray-500">{formatTime(elapsedS)} decorrido</div>
            </div>
          </div>

          {/* Bar */}
          <div className="bg-gray-800 rounded-full h-3 mb-5">
            <div className={`h-3 rounded-full transition-all duration-500 ${isCompleted ? "bg-green-500" : "bg-blue-500"}`}
              style={{ width: `${percent}%` }} />
          </div>

          {/* Pipeline steps */}
          <div className="space-y-1">
            {stages.map((stage) => {
              const isDone = stage.status === "done";
              const isRunning = stage.status === "running";
              const isPending = stage.status === "pending";

              return (
                <div key={stage.id}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                    isRunning ? "bg-blue-500/10 border border-blue-500/30" :
                    isDone ? "bg-gray-800/50" : "opacity-40"
                  }`}>
                  {/* Status icon */}
                  <div className={`w-6 text-center ${
                    isDone ? "text-green-400" : isRunning ? "text-blue-400" : "text-gray-600"
                  }`}>
                    {isDone ? "✓" : isRunning ? "▸" : "○"}
                  </div>

                  {/* Step number + name */}
                  <div className="w-6 text-center text-gray-500 font-mono text-xs">{stage.num}</div>
                  <div className={`flex-1 ${isRunning ? "text-white font-medium" : isDone ? "text-gray-400" : "text-gray-600"}`}>
                    {stage.name}
                    {stage.tool && <span className="text-xs text-gray-500 ml-2">{stage.tool}</span>}
                    {isRunning && <span className="ml-2 inline-block animate-pulse">●</span>}
                  </div>

                  {/* Time */}
                  <div className="text-right font-mono text-xs w-20">
                    {isDone && stage.time != null && (
                      <span className="text-green-400">{formatTime(stage.time)}</span>
                    )}
                    {isRunning && stage.elapsed != null && (
                      <span className="text-blue-400">{formatTime(stage.elapsed)}</span>
                    )}
                    {isPending && stage.estimate != null && (
                      <span className="text-gray-600">~{formatTime(stage.estimate)}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Error */}
      {isFailed && !!job?.error && (
        <section className="border border-red-500/30 bg-red-500/5 rounded-lg p-5 mb-6">
          <h2 className="text-lg font-semibold text-red-400 mb-2">Erro</h2>
          <pre className="text-sm text-red-300 whitespace-pre-wrap font-mono">{String(job.error)}</pre>
        </section>
      )}

      {/* Results */}
      {isCompleted && (
        <section className="border border-green-500/30 bg-green-500/5 rounded-lg p-5 mb-6">
          <h2 className="text-lg font-semibold text-green-400 mb-4">Resultado</h2>
          <div className="bg-black rounded-lg overflow-hidden mb-4">
            <video controls className="w-full" src={getDownloadUrl(jobId)}>
              Seu navegador nao suporta video.
            </video>
          </div>
          <div className="flex flex-wrap gap-3">
            <a href={getDownloadUrl(jobId)} download
              className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
              Download Video
            </a>
            <a href={getSubtitlesUrl(jobId, "orig")} download
              className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm transition-colors">
              Legendas Original
            </a>
            <a href={getSubtitlesUrl(jobId, "trad")} download
              className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm transition-colors">
              Legendas Traduzidas
            </a>
          </div>
          {!!job?.duration_s && (
            <div className="mt-4 text-sm text-gray-400">
              Tempo total: <span className="text-white">{formatTime(Number(job.duration_s))}</span>
              <span className="mx-2">|</span>
              Device: <span className={device === "cuda" ? "text-green-400" : "text-yellow-400"}>{device === "cuda" ? "GPU" : "CPU"}</span>
            </div>
          )}
        </section>
      )}

      {/* Config */}
      <section className="border border-gray-800 rounded-lg p-5 mb-6">
        <h2 className="text-lg font-semibold mb-3">Configuracao</h2>
        <div className="text-sm mb-3">
          <span className="text-gray-500">Input:</span> <span className="text-gray-300 break-all">{String(config.input || "-")}</span>
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div><span className="text-gray-500">Idiomas:</span> {String(config.src_lang || "auto")} → {String(config.tgt_lang || "pt")}</div>
          <div><span className="text-gray-500">Tipo:</span> {String(config.content_type || "palestra")}</div>
          <div><span className="text-gray-500">ASR:</span> {String(config.asr_engine || "whisper")}</div>
          <div>
            <span className="text-gray-500">
              {String(config.asr_engine) === "parakeet" ? "Modelo Parakeet:" : "Modelo Whisper:"}
            </span>{" "}
            {String(config.asr_engine) === "parakeet"
              ? String(config.parakeet_model || "nvidia/parakeet-tdt-1.1b").split("/").pop()
              : String(config.whisper_model || "large-v3")}
          </div>
          <div><span className="text-gray-500">TTS:</span> {String(config.tts_engine || "edge")}</div>
          {!!config.voice && <div><span className="text-gray-500">Voz:</span> {String(config.voice)}</div>}
          <div><span className="text-gray-500">Traducao:</span> {String(config.translation_engine || "m2m100")}</div>
          {!!config.ollama_model && <div><span className="text-gray-500">Modelo Ollama:</span> {String(config.ollama_model)}</div>}
          {!!config.large_model && <div><span className="text-gray-500">M2M100:</span> 1.2B (grande)</div>}
          <div><span className="text-gray-500">Sync:</span> {String(config.sync_mode || "smart")}</div>
          <div><span className="text-gray-500">Max Stretch:</span> {String(config.maxstretch || "1.3")}x</div>
          {!!config.tolerance && <div><span className="text-gray-500">Tolerancia:</span> {String(config.tolerance)}</div>}
          <div><span className="text-gray-500">Device:</span> <span className={device === "cuda" ? "text-green-400" : "text-yellow-400"}>{device.toUpperCase()}</span></div>
          <div><span className="text-gray-500">Seed:</span> {String(config.seed ?? "-")}</div>
          {!!config.no_truncate && <div><span className="text-green-400">Frases completas (sem corte)</span></div>}
          {!!config.diarize && <div><span className="text-purple-400">Multi-falante (diarizacao)</span></div>}
          {!!config.clone_voice && <div><span className="text-blue-400">Clonar voz original</span></div>}
        </div>
      </section>

      {/* Logs */}
      <section className="border border-gray-800 rounded-lg p-5">
        <button type="button" onClick={() => setShowLogs(!showLogs)}
          className="flex items-center gap-2 text-lg font-semibold hover:text-blue-400 transition-colors">
          <span className={`transform transition-transform text-sm ${showLogs ? "rotate-90" : ""}`}>&#9654;</span>
          Logs ({logs.length})
        </button>
        {showLogs && (
          <div className="mt-3 bg-gray-950 rounded-lg p-3 max-h-96 overflow-y-auto font-mono text-xs">
            {logs.length === 0 ? (
              <div className="text-gray-600">Nenhum log disponivel</div>
            ) : (
              logs.map((log, i) => (
                <div key={i} className="py-0.5 text-gray-300">{typeof log === "string" ? log : log.message}</div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        )}
      </section>
    </div>
  );
}
