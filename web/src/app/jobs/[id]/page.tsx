"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  getJob, getJobLogs, cancelJob, deleteJob, retryJob,
  getDownloadUrl, getSubtitlesUrl,
  getClips, getClipUrl, getClipsZipUrl, getTranscriptUrl,
  getTranscriptSummary, getVideoSummary,
  getDownloadFileUrl, getAudioUrl,
  createJobWebSocket,
} from "@/lib/api";

type JobData = Record<string, unknown>;
type LogEntry = { timestamp: string; level: string; message: string };
type LogProgress = {
  type: string; percent: number; size?: string; speed?: string; eta?: string; detail?: string;
};
type StageInfo = {
  num: number; id: string; name: string; icon: string;
  status: string; time?: number; elapsed?: number; estimate?: number; tool?: string;
  log_progress?: LogProgress;
};
type ClipInfo = { name: string; size_bytes: number; url: string; title?: string; description?: string; start?: number; end?: number };
type VideoSummary = { title: string; description: string };

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

function formatTimecode(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export default function JobDetail() {
  const params = useParams();
  const jobId = String(params.id);
  const [job, setJob] = useState<JobData | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [clips, setClips] = useState<ClipInfo[]>([]);
  const [playingClip, setPlayingClip] = useState<string | null>(null);
  const [videoSummary, setVideoSummary] = useState<VideoSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const fetchJob = useCallback(() => {
    getJob(jobId).then(setJob).catch(() => setError("Erro ao carregar job"));
  }, [jobId]);

  const fetchLogs = useCallback(() => {
    getJobLogs(jobId, 200).then(setLogs).catch(() => {});
  }, [jobId]);

  const fetchClips = useCallback((jobType: string) => {
    if (jobType === "cutting") {
      getClips(jobId).then(setClips).catch(() => {});
    }
  }, [jobId]);

  useEffect(() => {
    fetchJob();
    fetchLogs();
    const interval = setInterval(() => { fetchJob(); fetchLogs(); }, 3000);
    return () => clearInterval(interval);
  }, [fetchJob, fetchLogs]);

  useEffect(() => {
    if (job && job.status === "completed") {
      const config = (job.config || {}) as Record<string, unknown>;
      const jobType = String(config.job_type || "dubbing");
      if (jobType === "cutting") fetchClips(jobType);
      if (jobType === "transcription") {
        getTranscriptSummary(jobId)
          .then((d) => setVideoSummary(d as VideoSummary))
          .catch(() => {});
      }
      if (jobType === "dubbing") {
        getVideoSummary(jobId)
          .then((d) => setVideoSummary(d as VideoSummary))
          .catch(() => {});
      }
    }
  }, [job, fetchClips, jobId]);

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

  const handleDelete = async () => {
    if (!confirm(`Excluir job ${jobId} e todos os arquivos? Esta ação não pode ser desfeita.`)) return;
    setDeleting(true);
    try {
      await deleteJob(jobId);
      window.location.href = "/jobs";
    } catch {
      setError("Erro ao excluir job");
      setDeleting(false);
    }
  };

  const handleRetry = async () => {
    setRetrying(true);
    try {
      const newJob = await retryJob(jobId) as Record<string, unknown>;
      window.location.href = `/jobs/${newJob.id}`;
    } catch {
      setError("Erro ao re-tentar job");
      setRetrying(false);
    }
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
  const jobType = String(config.job_type || "dubbing");

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

  const jobTypeLabels: Record<string, { label: string; className: string }> = {
    dubbing: { label: "Dublagem", className: "bg-blue-500/20 text-blue-400 border border-blue-500/30" },
    cutting: { label: "Corte", className: "bg-orange-500/20 text-orange-400 border border-orange-500/30" },
    transcription: { label: "Transcricao", className: "bg-purple-500/20 text-purple-400 border border-purple-500/30" },
    download: { label: "Download", className: "bg-green-500/20 text-green-400 border border-green-500/30" },
    tts_generate: { label: "Gerar Audio", className: "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30" },
    voice_clone: { label: "Clonar Voz", className: "bg-pink-500/20 text-pink-400 border border-pink-500/30" },
  };
  const jtl = jobTypeLabels[jobType] || { label: jobType, className: "bg-gray-500/20 text-gray-400 border border-gray-500/30" };

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
            <span className={`px-2 py-0.5 rounded text-xs font-bold ${jtl.className}`}>
              {jtl.label}
            </span>
            <span className={`px-2 py-0.5 rounded text-xs font-bold ${
              device === "cuda" ? "bg-green-500/20 text-green-400 border border-green-500/30" : "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30"
            }`}>
              {device === "cuda" ? "GPU" : "CPU"}
            </span>
          </div>
          <p className="text-gray-500 text-sm">
            {job?.created_at ? new Date(Number(job.created_at) * 1000).toLocaleString("pt-BR") : "-"}
            {jobType === "dubbing" && (
              <>
                <span className="mx-2">|</span>{String(config.src_lang || "auto")} → {String(config.tgt_lang || "pt")}
              </>
            )}
            {jobType === "cutting" && (
              <>
                <span className="mx-2">|</span>Modo: {String(config.mode || "manual")}
              </>
            )}
            {jobType === "transcription" && (
              <>
                <span className="mx-2">|</span>ASR: {String(config.asr_engine || "whisper")}
              </>
            )}
            {jobType === "download" && (
              <>
                <span className="mx-2">|</span>Qualidade: {String(config.quality || "best")}
              </>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          {isActive && (
            <button onClick={handleCancel} disabled={cancelling}
              className="bg-red-600 hover:bg-red-700 disabled:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm transition-colors">
              {cancelling ? "Cancelando..." : "Cancelar"}
            </button>
          )}
          {(status === "failed" || status === "cancelled") && (
            <button onClick={handleRetry} disabled={retrying}
              className="bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/40 text-blue-400 px-4 py-2 rounded-lg text-sm transition-colors disabled:opacity-50">
              {retrying ? "Iniciando..." : "↺ Re-tentar"}
            </button>
          )}
          {!isActive && (
            <button onClick={handleDelete} disabled={deleting}
              className="bg-gray-800 hover:bg-red-900/50 hover:border-red-800 border border-gray-700 text-gray-400 hover:text-red-400 px-4 py-2 rounded-lg text-sm transition-colors disabled:opacity-50">
              {deleting ? "Excluindo..." : "🗑 Excluir"}
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
                    {isRunning && !stage.log_progress && <span className="ml-2 inline-block animate-pulse">●</span>}
                    {/* Download/tool progress */}
                    {isRunning && stage.log_progress && (
                      <div className="mt-1">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-gray-700 rounded-full h-1.5">
                            <div className="bg-blue-500 h-1.5 rounded-full transition-all duration-500"
                              style={{ width: `${stage.log_progress.percent}%` }} />
                          </div>
                          <span className="text-xs text-blue-400 font-mono w-12 text-right">
                            {stage.log_progress.percent.toFixed(1)}%
                          </span>
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5">
                          {stage.log_progress.detail || (
                            <>{stage.log_progress.size && <span>{stage.log_progress.size}</span>}
                            {stage.log_progress.speed && <span className="ml-2">{stage.log_progress.speed}</span>}
                            {stage.log_progress.eta && <span className="ml-2">ETA {stage.log_progress.eta}</span>}</>
                          )}
                        </div>
                      </div>
                    )}
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

      {/* Results - Dubbing */}
      {isCompleted && jobType === "dubbing" && (
        <section className="border border-green-500/30 bg-green-500/5 rounded-lg p-5 mb-6">
          <h2 className="text-lg font-semibold text-green-400 mb-4">Resultado</h2>
          {videoSummary && (videoSummary.title || videoSummary.description) && (
            <div className="mb-4 pb-4 border-b border-green-500/20">
              {videoSummary.title && (
                <h3 className="text-base font-semibold text-white mb-1">{videoSummary.title}</h3>
              )}
              {videoSummary.description && (
                <p className="text-sm text-gray-400 leading-relaxed">{videoSummary.description}</p>
              )}
            </div>
          )}
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

      {/* Results - Cutting */}
      {isCompleted && jobType === "cutting" && (
        <section className="border border-orange-500/30 bg-orange-500/5 rounded-lg p-5 mb-6">
          <h2 className="text-lg font-semibold text-orange-400 mb-4">
            Clips Gerados {clips.length > 0 && <span className="text-base font-normal text-gray-400">({clips.length} clips)</span>}
          </h2>

          {clips.length === 0 ? (
            <p className="text-gray-500 text-sm">Carregando clips...</p>
          ) : (
            <div className="mb-4">
              {/* Player inline */}
              {playingClip && (
                <div className="mb-4 bg-black rounded-lg overflow-hidden border border-orange-500/30">
                  <div className="flex items-center justify-between px-3 py-2 bg-gray-900/80">
                    <span className="text-sm font-mono text-orange-300">{playingClip}</span>
                    <button
                      onClick={() => setPlayingClip(null)}
                      className="text-gray-500 hover:text-white text-lg leading-none transition-colors"
                      title="Fechar player"
                    >✕</button>
                  </div>
                  <video
                    key={playingClip}
                    src={getClipUrl(jobId, playingClip)}
                    controls
                    autoPlay
                    className="w-full max-h-[480px]"
                  />
                </div>
              )}

              {/* Lista de clips */}
              <div className="space-y-2">
                {clips.map((clip) => {
                  const isPlaying = playingClip === clip.name;
                  return (
                    <div key={clip.name}
                      className={`rounded-lg px-4 py-3 transition-colors border ${
                        isPlaying ? "bg-orange-500/10 border-orange-500/30" : "bg-gray-900 border-gray-800"
                      }`}>
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => setPlayingClip(isPlaying ? null : clip.name)}
                          className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 transition-colors ${
                            isPlaying
                              ? "bg-orange-500 text-white"
                              : "bg-gray-700 hover:bg-orange-600 text-gray-300 hover:text-white"
                          }`}
                          title={isPlaying ? "Parar" : "Play"}
                        >
                          {isPlaying ? "■" : "▶"}
                        </button>
                        <div className="flex-1 min-w-0">
                          <div className={`font-medium text-sm ${isPlaying ? "text-orange-300" : "text-white"}`}>
                            {clip.title || clip.name}
                          </div>
                          {clip.start != null && clip.end != null && (
                            <div className="text-xs text-gray-500 font-mono">
                              {formatTimecode(clip.start)} → {formatTimecode(clip.end)}
                              <span className="ml-2 text-gray-600">({formatTime(clip.end - clip.start)})</span>
                            </div>
                          )}
                        </div>
                        <span className="text-xs text-gray-500 flex-shrink-0">{formatSize(clip.size_bytes)}</span>
                        <a href={getClipUrl(jobId, clip.name)} download
                          className="bg-gray-700 hover:bg-gray-600 text-gray-300 px-3 py-1 rounded text-xs font-medium transition-colors flex-shrink-0">
                          ⬇ Download
                        </a>
                      </div>
                      {clip.description && (
                        <p className="mt-2 ml-11 text-xs text-gray-400 leading-relaxed">{clip.description}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <a href={getClipsZipUrl(jobId)} download
            className="inline-flex items-center gap-2 bg-orange-600 hover:bg-orange-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
            📦 Download ZIP (todos os clips)
          </a>
          {!!job?.duration_s && (
            <div className="mt-4 text-sm text-gray-400">
              Tempo total: <span className="text-white">{formatTime(Number(job.duration_s))}</span>
            </div>
          )}
        </section>
      )}

      {/* Results - Download */}
      {isCompleted && jobType === "download" && (
        <section className="border border-green-500/30 bg-green-500/5 rounded-lg p-5 mb-6">
          <h2 className="text-lg font-semibold text-green-400 mb-4">Video Baixado</h2>
          <div className="bg-black rounded-lg overflow-hidden mb-4">
            <video controls className="w-full" src={getDownloadFileUrl(jobId)}>
              Seu navegador nao suporta video.
            </video>
          </div>
          <a href={getDownloadFileUrl(jobId)} download
            className="inline-flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
            ⬇ Download
          </a>
          {!!job?.duration_s && (
            <div className="mt-4 text-sm text-gray-400">
              Tempo total: <span className="text-white">{formatTime(Number(job.duration_s))}</span>
            </div>
          )}
        </section>
      )}

      {/* Results - Transcription */}
      {isCompleted && jobType === "transcription" && (
        <section className="border border-purple-500/30 bg-purple-500/5 rounded-lg p-5 mb-6">
          <h2 className="text-lg font-semibold text-purple-400 mb-4">Transcricao</h2>
          {videoSummary && (videoSummary.title || videoSummary.description) && (
            <div className="mb-4 pb-4 border-b border-purple-500/20">
              {videoSummary.title && (
                <h3 className="text-base font-semibold text-white mb-1">{videoSummary.title}</h3>
              )}
              {videoSummary.description && (
                <p className="text-sm text-gray-400 leading-relaxed">{videoSummary.description}</p>
              )}
            </div>
          )}
          <div className="flex flex-wrap gap-3">
            <a href={getTranscriptUrl(jobId, "srt")} download
              className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
              <span>📄</span> Download SRT
            </a>
            <a href={getTranscriptUrl(jobId, "txt")} download
              className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm transition-colors">
              <span>📝</span> Download TXT
            </a>
            <a href={getTranscriptUrl(jobId, "json")} download
              className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm transition-colors">
              <span>🗂</span> Download JSON
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

      {/* Results - TTS Generate */}
      {isCompleted && jobType === "tts_generate" && (
        <section className="border border-cyan-500/30 bg-cyan-500/5 rounded-lg p-5 mb-6">
          <h2 className="text-lg font-semibold text-cyan-400 mb-4">Audio Gerado</h2>
          <audio controls className="w-full mb-4" src={getAudioUrl(jobId)}>
            Seu navegador nao suporta audio.
          </audio>
          <a href={getAudioUrl(jobId)} download
            className="inline-flex items-center gap-2 bg-cyan-600 hover:bg-cyan-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
            ⬇ Download Audio
          </a>
          {!!job?.duration_s && (
            <div className="mt-4 text-sm text-gray-400">
              Tempo total: <span className="text-white">{formatTime(Number(job.duration_s))}</span>
            </div>
          )}
        </section>
      )}

      {/* Results - Voice Clone */}
      {isCompleted && jobType === "voice_clone" && (
        <section className="border border-pink-500/30 bg-pink-500/5 rounded-lg p-5 mb-6">
          <h2 className="text-lg font-semibold text-pink-400 mb-4">Voz Clonada</h2>
          <audio controls className="w-full mb-4" src={getAudioUrl(jobId)}>
            Seu navegador nao suporta audio.
          </audio>
          <a href={getAudioUrl(jobId)} download
            className="inline-flex items-center gap-2 bg-pink-600 hover:bg-pink-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
            ⬇ Download Audio
          </a>
          {!!job?.duration_s && (
            <div className="mt-4 text-sm text-gray-400">
              Tempo total: <span className="text-white">{formatTime(Number(job.duration_s))}</span>
            </div>
          )}
        </section>
      )}

      {/* Config */}
      <section className="border border-gray-800 rounded-lg p-5 mb-6">
        <h2 className="text-lg font-semibold mb-3">Configuracao</h2>
        {jobType !== "download" && (
          <div className="text-sm mb-3">
            <span className="text-gray-500">Input:</span> <span className="text-gray-300 break-all">{String(config.input || "-")}</span>
          </div>
        )}
        {jobType === "dubbing" && (
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
            <div><span className="text-gray-500">Sync:</span> {String(config.sync_mode || "smart")}</div>
            <div><span className="text-gray-500">Device:</span> <span className={device === "cuda" ? "text-green-400" : "text-yellow-400"}>{device.toUpperCase()}</span></div>
          </div>
        )}
        {jobType === "cutting" && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><span className="text-gray-500">Modo:</span> {String(config.mode || "manual")}</div>
            {config.mode === "manual" && !!config.timestamps && (
              <div className="col-span-2"><span className="text-gray-500">Timestamps:</span> <code className="bg-gray-800 px-1 rounded">{String(config.timestamps ?? "")}</code></div>
            )}
            {config.mode === "viral" && (
              <>
                <div><span className="text-gray-500">Modelo LLM:</span> {String(config.ollama_model || "-")}</div>
                <div><span className="text-gray-500">Num clips:</span> {String(config.num_clips || 5)}</div>
                <div><span className="text-gray-500">Duracao:</span> {String(config.min_duration || 30)}s - {String(config.max_duration || 120)}s</div>
                <div><span className="text-gray-500">Whisper:</span> {String(config.whisper_model || "large-v3")}</div>
              </>
            )}
          </div>
        )}
        {jobType === "transcription" && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><span className="text-gray-500">ASR:</span> {String(config.asr_engine || "whisper")}</div>
            <div><span className="text-gray-500">Modelo:</span> {String(config.whisper_model || "large-v3")}</div>
            <div><span className="text-gray-500">Idioma:</span> {String(config.src_lang || "auto-detect")}</div>
            <div><span className="text-gray-500">Device:</span> <span className={device === "cuda" ? "text-green-400" : "text-yellow-400"}>{device.toUpperCase()}</span></div>
          </div>
        )}
        {jobType === "download" && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="col-span-2 break-all"><span className="text-gray-500">URL:</span> <a href={String(config.url || "")} target="_blank" rel="noreferrer" className="text-green-400 hover:underline">{String(config.url || "-")}</a></div>
            <div><span className="text-gray-500">Qualidade:</span> {String(config.quality || "best")}</div>
          </div>
        )}
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
