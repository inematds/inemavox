"use client";

import { useEffect, useMemo, useState } from "react";
import { getSystemStatus, listJobs, setJobAnalyzed } from "@/lib/api";

function StatusCard({ title, value, sub, color = "blue" }: { title: string; value: string; sub?: string; color?: string }) {
  const colors: Record<string, string> = {
    blue: "border-blue-500/30 bg-blue-500/5",
    green: "border-green-500/30 bg-green-500/5",
    yellow: "border-yellow-500/30 bg-yellow-500/5",
    red: "border-red-500/30 bg-red-500/5",
  };
  return (
    <div className={`border rounded-lg p-4 ${colors[color] || colors.blue}`}>
      <div className="text-sm text-gray-400">{title}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
}

function JobTypeTag({ jobType }: { jobType: string }) {
  const tags: Record<string, { label: string; className: string }> = {
    dubbing:      { label: "Dublagem",    className: "bg-blue-500/20 text-blue-400 border border-blue-500/30" },
    cutting:      { label: "Corte",       className: "bg-orange-500/20 text-orange-400 border border-orange-500/30" },
    transcription:{ label: "Transcrever", className: "bg-purple-500/20 text-purple-400 border border-purple-500/30" },
    download:     { label: "Download",    className: "bg-green-500/20 text-green-400 border border-green-500/30" },
    tts_generate: { label: "Gerar Audio", className: "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30" },
    voice_clone:  { label: "Clonar Voz", className: "bg-pink-500/20 text-pink-400 border border-pink-500/30" },
  };
  const tag = tags[jobType] || { label: jobType, className: "bg-gray-500/20 text-gray-400 border border-gray-500/30" };
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${tag.className}`}>
      {tag.label}
    </span>
  );
}

type Job = Record<string, unknown>;

const PAGE_SIZE = 10;

function computeInfo(job: Job): string {
  const config = (job.config || {}) as Record<string, unknown>;
  const jobType = String(config.job_type || "dubbing");
  if (jobType === "dubbing") return `${config.src_lang || "auto"} → ${config.tgt_lang || "pt"}`;
  if (jobType === "cutting") return String(config.mode || "manual");
  if (jobType === "transcription") return String(config.asr_engine || "whisper");
  if (jobType === "download") {
    try { return new URL(String(config.url || "")).hostname.replace("www.", ""); } catch { return "download"; }
  }
  if (jobType === "tts_generate") return `${config.engine || "edge"} | ${String(config.text || "").substring(0, 35)}`;
  if (jobType === "voice_clone") return String(config.text || "").substring(0, 45);
  return "";
}

function computeVideoLabel(job: Job): string {
  const config = (job.config || {}) as Record<string, unknown>;
  const rawTitle = String(job.video_title || "");
  const inputUrl = String(config.input || config.url || "");
  let label = rawTitle;
  if (!label && inputUrl.startsWith("http")) {
    try { label = new URL(inputUrl).pathname.split("/").filter(Boolean).pop() || inputUrl; } catch { label = inputUrl; }
  }
  return label;
}

export default function Dashboard() {
  const [system, setSystem] = useState<Record<string, unknown> | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Filtros
  const [qId, setQId] = useState("");
  const [qInfo, setQInfo] = useState("");
  const [qType, setQType] = useState("all");
  const [qStatus, setQStatus] = useState("all");
  const [qAnalyzed, setQAnalyzed] = useState<"all" | "yes" | "no">("all");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const load = async () => {
      try {
        const [sys, jbs] = await Promise.all([getSystemStatus(), listJobs()]);
        setSystem(sys);
        setJobs(jbs);
      } catch {
        setError("API offline. Inicie o backend: uvicorn api.server:app --port 8010");
      }
    };
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  // Reset page on filter change
  useEffect(() => { setPage(1); }, [qId, qInfo, qType, qStatus, qAnalyzed]);

  const gpu = (system?.gpu || {}) as Record<string, unknown>;
  const cpu = (system?.cpu || {}) as Record<string, unknown>;
  const memory = (system?.memory || {}) as Record<string, unknown>;
  const ollama = (system?.ollama || {}) as Record<string, unknown>;

  const activeJobs = jobs.filter((j) => j.status === "running");

  const filtered = useMemo(() => {
    const needleId = qId.trim().toLowerCase();
    const needleInfo = qInfo.trim().toLowerCase();
    return jobs.filter((j) => {
      const config = (j.config || {}) as Record<string, unknown>;
      const jType = String(config.job_type || "dubbing");
      if (qType !== "all" && jType !== qType) return false;
      if (qStatus !== "all" && String(j.status) !== qStatus) return false;
      if (qAnalyzed === "yes" && !j.analyzed) return false;
      if (qAnalyzed === "no" && j.analyzed) return false;
      if (needleId && !String(j.id).toLowerCase().includes(needleId)) return false;
      if (needleInfo) {
        const hay = [
          computeInfo(j),
          computeVideoLabel(j),
          String(config.input || ""),
          String(config.url || ""),
          String(j.error || ""),
        ].join(" ").toLowerCase();
        if (!hay.includes(needleInfo)) return false;
      }
      return true;
    });
  }, [jobs, qId, qInfo, qType, qStatus, qAnalyzed]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageJobs = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const toggleAnalyzed = async (e: React.MouseEvent, jobId: string, current: boolean) => {
    e.preventDefault();
    e.stopPropagation();
    // Optimistic update
    setJobs((prev) => prev.map((j) => j.id === jobId ? { ...j, analyzed: !current } : j));
    try { await setJobAnalyzed(jobId, !current); } catch { /* ignore; next poll will reconcile */ }
  };

  return (
    <div>
      <div className="mb-8">
        <div className="flex items-baseline gap-3">
          <h1 className="text-3xl font-bold">Dashboard</h1>
          {system?.version && (
            <span className="text-sm font-mono text-gray-600">v{String(system.version)}</span>
          )}
        </div>
        <p className="text-gray-400 mt-1">Monitor do sistema e jobs</p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6">
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Status Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatusCard
          title="GPU"
          value={gpu.available ? String(gpu.name || "NVIDIA") : "Offline"}
          sub={gpu.temperature_c ? `${gpu.temperature_c}C | ${gpu.power_w}W` : undefined}
          color={gpu.available ? "green" : "red"}
        />
        <StatusCard
          title="CPU"
          value={`${cpu.usage_pct || 0}%`}
          sub={`${cpu.cores || 0} cores`}
          color={Number(cpu.usage_pct) > 80 ? "red" : "green"}
        />
        <StatusCard
          title="RAM"
          value={`${memory.usage_pct || 0}%`}
          sub={`${Math.round(Number(memory.available_mb || 0) / 1024)}GB livre`}
          color={Number(memory.usage_pct) > 80 ? "yellow" : "green"}
        />
        <StatusCard
          title="Ollama"
          value={ollama.online ? "Online" : "Offline"}
          sub={Array.isArray(ollama.running_models) && ollama.running_models.length > 0
            ? String(ollama.running_models[0])
            : "Nenhum modelo carregado"}
          color={ollama.online ? "green" : "red"}
        />
      </div>

      {/* Active Jobs */}
      {activeJobs.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-semibold mb-4">Jobs em Andamento</h2>
          <div className="space-y-3">
            {activeJobs.map((job) => {
              const progress = (job.progress || {}) as Record<string, unknown>;
              const device = String(job.device || progress.device || "cpu");
              const config = (job.config || {}) as Record<string, unknown>;
              const jobType = String(config.job_type || "dubbing");
              return (
                <a key={String(job.id)} href={`/jobs/${job.id}`}
                  className="block border border-blue-500/30 bg-blue-500/5 rounded-lg p-4 hover:bg-blue-500/10 transition-colors">
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{String(job.id)}</span>
                      <JobTypeTag jobType={jobType} />
                      <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                        device === "cuda" ? "bg-green-500/20 text-green-400 border border-green-500/30" : "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30"
                      }`}>
                        {device === "cuda" ? "GPU" : "CPU"}
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="text-blue-400 font-mono">{String(progress.percent || 0)}%</span>
                      {!!progress.eta_text && (
                        <div className="text-xs text-gray-500">ETA: {String(progress.eta_text)}</div>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 bg-gray-800 rounded-full h-2">
                    <div
                      className="bg-blue-500 h-2 rounded-full transition-all"
                      style={{ width: `${progress.percent || 0}%` }}
                    />
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Etapa: {String(progress.stage_name || "...")} ({String(progress.current_stage || 0)}/{String(progress.total_stages || 10)})
                  </div>
                </a>
              );
            })}
          </div>
        </div>
      )}

      {/* Recent Jobs */}
      <div>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h2 className="text-xl font-semibold">Jobs Recentes</h2>
          <span className="text-xs text-gray-500">
            {filtered.length} {filtered.length === 1 ? "resultado" : "resultados"}
            {filtered.length !== jobs.length && ` (de ${jobs.length})`}
          </span>
        </div>

        {/* Filtros */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2 mb-3">
          <input
            type="text"
            value={qId}
            onChange={(e) => setQId(e.target.value)}
            placeholder="ID..."
            className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500 font-mono"
          />
          <input
            type="text"
            value={qInfo}
            onChange={(e) => setQInfo(e.target.value)}
            placeholder="Buscar titulo, URL, erro..."
            className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500 md:col-span-2"
          />
          <select
            value={qType}
            onChange={(e) => setQType(e.target.value)}
            className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
          >
            <option value="all">Todos os tipos</option>
            <option value="dubbing">Dublagem</option>
            <option value="cutting">Corte</option>
            <option value="transcription">Transcricao</option>
            <option value="download">Download</option>
            <option value="tts_generate">Gerar Audio</option>
            <option value="voice_clone">Clonar Voz</option>
          </select>
          <select
            value={qStatus}
            onChange={(e) => setQStatus(e.target.value)}
            className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
          >
            <option value="all">Todos os status</option>
            <option value="running">running</option>
            <option value="queued">queued</option>
            <option value="completed">completed</option>
            <option value="failed">failed</option>
            <option value="cancelled">cancelled</option>
          </select>
        </div>
        <div className="mb-4 flex gap-2 flex-wrap">
          {(["all", "no", "yes"] as const).map((k) => (
            <button key={k} onClick={() => setQAnalyzed(k)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                qAnalyzed === k ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"
              }`}>
              {k === "all" ? "Todos" : k === "yes" ? "Analisados" : "Nao analisados"}
            </button>
          ))}
        </div>

        {jobs.length === 0 ? (
          <div className="border border-gray-800 rounded-lg p-8 text-center text-gray-500">
            Nenhum job ainda.{" "}
            <a href="/new" className="text-blue-400 hover:underline">Dublagem</a>,{" "}
            <a href="/cut" className="text-orange-400 hover:underline">Cortar</a> ou{" "}
            <a href="/transcribe" className="text-purple-400 hover:underline">Transcrever</a> um video.
          </div>
        ) : filtered.length === 0 ? (
          <div className="border border-gray-800 rounded-lg p-8 text-center text-gray-500">
            Nenhum job com estes filtros.
          </div>
        ) : (
          <>
            <div className="border border-gray-800 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-900 text-gray-400">
                  <tr>
                    <th className="text-center px-2 py-3 w-10" title="Analisado">✓</th>
                    <th className="text-left px-4 py-3">ID</th>
                    <th className="text-left px-4 py-3">Tipo</th>
                    <th className="text-left px-4 py-3">Status</th>
                    <th className="text-left px-4 py-3">Device</th>
                    <th className="text-left px-4 py-3">Info</th>
                    <th className="text-left px-4 py-3">Duracao</th>
                  </tr>
                </thead>
                <tbody>
                  {pageJobs.map((job) => {
                    const statusColors: Record<string, string> = {
                      completed: "text-green-400",
                      running: "text-blue-400",
                      failed: "text-red-400",
                      queued: "text-yellow-400",
                      cancelled: "text-gray-400",
                    };
                    const config = (job.config || {}) as Record<string, unknown>;
                    const device = String(job.device || "cpu");
                    const jobType = String(config.job_type || "dubbing");
                    const analyzed = Boolean(job.analyzed);
                    const rawTitle = String(job.video_title || "");
                    const inputUrl = String(config.input || config.url || "");
                    const videoLabel = computeVideoLabel(job).substring(0, 50);
                    const infoText = computeInfo(job);

                    return (
                      <tr key={String(job.id)} className={`border-t border-gray-800 hover:bg-gray-900/50 ${analyzed ? "opacity-70" : ""}`}>
                        <td className="px-2 py-3 text-center">
                          <button
                            onClick={(e) => toggleAnalyzed(e, String(job.id), analyzed)}
                            className={`w-5 h-5 rounded border transition-colors flex items-center justify-center ${
                              analyzed
                                ? "bg-green-500/20 border-green-500 text-green-400"
                                : "border-gray-600 text-transparent hover:border-gray-400"
                            }`}
                            title={analyzed ? "Desmarcar como analisado" : "Marcar como analisado"}
                          >
                            ✓
                          </button>
                        </td>
                        <td className="px-4 py-3">
                          <a href={`/jobs/${job.id}`} className="text-blue-400 hover:underline font-mono">
                            {String(job.id)}
                          </a>
                        </td>
                        <td className="px-4 py-3">
                          <JobTypeTag jobType={jobType} />
                        </td>
                        <td className={`px-4 py-3 ${statusColors[String(job.status)] || ""}`}>
                          {String(job.status)}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                            device === "cuda" ? "bg-green-500/20 text-green-400" : "bg-yellow-500/20 text-yellow-400"
                          }`}>
                            {device === "cuda" ? "GPU" : "CPU"}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="text-gray-400">{infoText}</div>
                          {videoLabel && (
                            <div className="text-xs text-gray-600 mt-0.5 truncate max-w-[260px]" title={rawTitle || inputUrl}>
                              {videoLabel}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-gray-400">{String(job.duration_s || 0)}s</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Paginacao */}
            <div className="flex items-center justify-between mt-4">
              <div className="text-xs text-gray-500">
                Pagina {currentPage} de {totalPages} · {PAGE_SIZE}/pagina
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage <= 1}
                  className="px-3 py-1.5 rounded-lg text-sm bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  ← Anterior
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage >= totalPages}
                  className="px-3 py-1.5 rounded-lg text-sm bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Proxima pagina →
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
