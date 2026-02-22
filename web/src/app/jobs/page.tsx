"use client";

import { useEffect, useState } from "react";
import { listJobs, deleteJob } from "@/lib/api";

type Job = Record<string, unknown>;

function JobTypeTag({ jobType }: { jobType: string }) {
  const tags: Record<string, { label: string; className: string }> = {
    dubbing: { label: "Dublagem", className: "bg-blue-500/20 text-blue-400 border border-blue-500/30" },
    cutting: { label: "Cortar", className: "bg-orange-500/20 text-orange-400 border border-orange-500/30" },
    transcription: { label: "Transcrever", className: "bg-purple-500/20 text-purple-400 border border-purple-500/30" },
    download: { label: "Download", className: "bg-green-500/20 text-green-400 border border-green-500/30" },
    tts_generate: { label: "Gerar Audio", className: "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30" },
    voice_clone: { label: "Clonar Voz", className: "bg-pink-500/20 text-pink-400 border border-pink-500/30" },
  };
  const tag = tags[jobType] || { label: jobType, className: "bg-gray-500/20 text-gray-400 border border-gray-500/30" };
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs font-medium border ${tag.className}`}>
      {tag.label}
    </span>
  );
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = () => {
    listJobs()
      .then(setJobs)
      .catch(() => setError("API offline"));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleDelete = async (e: React.MouseEvent, jobId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`Excluir job ${jobId} e todos os arquivos? Esta ação não pode ser desfeita.`)) return;
    setDeleting(jobId);
    try {
      await deleteJob(jobId);
      load();
    } catch {
      setError("Erro ao excluir job");
    }
    setDeleting(null);
  };

  const filtered = jobs
    .filter((j) => statusFilter === "all" || j.status === statusFilter)
    .filter((j) => {
      if (typeFilter === "all") return true;
      const jType = String(((j.config || {}) as Record<string, unknown>).job_type || "dubbing");
      return jType === typeFilter;
    });

  const statusColors: Record<string, string> = {
    completed: "bg-green-500/20 text-green-400 border-green-500/30",
    running: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    failed: "bg-red-500/20 text-red-400 border-red-500/30",
    queued: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    cancelled: "bg-gray-500/20 text-gray-400 border-gray-500/30",
  };

  const statusCounts = {
    all: jobs.length,
    running: jobs.filter((j) => j.status === "running").length,
    completed: jobs.filter((j) => j.status === "completed").length,
    failed: jobs.filter((j) => j.status === "failed").length,
    queued: jobs.filter((j) => j.status === "queued").length,
  };

  const typeCounts = {
    all: jobs.length,
    dubbing: jobs.filter((j) => String(((j.config || {}) as Record<string, unknown>).job_type || "dubbing") === "dubbing").length,
    cutting: jobs.filter((j) => String(((j.config || {}) as Record<string, unknown>).job_type || "dubbing") === "cutting").length,
    transcription: jobs.filter((j) => String(((j.config || {}) as Record<string, unknown>).job_type || "dubbing") === "transcription").length,
    download: jobs.filter((j) => String(((j.config || {}) as Record<string, unknown>).job_type || "dubbing") === "download").length,
    tts_generate: jobs.filter((j) => String(((j.config || {}) as Record<string, unknown>).job_type || "dubbing") === "tts_generate").length,
    voice_clone: jobs.filter((j) => String(((j.config || {}) as Record<string, unknown>).job_type || "dubbing") === "voice_clone").length,
  };

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-4">Jobs</h1>

        {/* Filtro por tipo */}
        <div className="flex gap-2 flex-wrap mb-3">
          {([
            { key: "all", label: "Todos" },
            { key: "dubbing", label: "Dublagem" },
            { key: "cutting", label: "Corte" },
            { key: "transcription", label: "Transcricao" },
            { key: "download", label: "Download" },
            { key: "tts_generate", label: "Gerar Audio" },
            { key: "voice_clone", label: "Clonar Voz" },
          ] as const).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setTypeFilter(key)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                typeFilter === key
                  ? "bg-white text-gray-900"
                  : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {label} ({typeCounts[key] || 0})
            </button>
          ))}
        </div>

        {/* Filtro por status */}
        <div className="flex gap-2 flex-wrap">
          {(["all", "running", "queued", "completed", "failed"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setStatusFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                statusFilter === f
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {f === "all" ? "Todos status" : f.charAt(0).toUpperCase() + f.slice(1)} ({statusCounts[f] || 0})
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 text-red-400">{error}</div>
      )}

      {/* Jobs List */}
      {filtered.length === 0 ? (
        <div className="border border-gray-800 rounded-lg p-12 text-center text-gray-500">
          {jobs.length === 0 ? (
            <>Nenhum job ainda. <a href="/new" className="text-blue-400 hover:underline">Dublagem</a>,{" "}
              <a href="/transcribe" className="text-purple-400 hover:underline">Transcrever</a> ou{" "}
              <a href="/cut" className="text-orange-400 hover:underline">Cortar</a> um vídeo.</>
          ) : (
            "Nenhum job com este filtro"
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((job) => {
            const config = (job.config || {}) as Record<string, unknown>;
            const progress = (job.progress || {}) as Record<string, unknown>;
            const isActive = job.status === "running";
            const jobType = String(config.job_type || "dubbing");

            let infoText = "";
            if (jobType === "dubbing") {
              infoText = `${config.src_lang || "auto"} → ${config.tgt_lang || "pt"} | ${config.tts_engine || "edge"} | ${config.translation_engine || "m2m100"}`;
            } else if (jobType === "cutting") {
              infoText = `Modo: ${config.mode || "manual"}`;
            } else if (jobType === "transcription") {
              infoText = `ASR: ${config.asr_engine || "whisper"}${config.src_lang ? ` | ${config.src_lang}` : ""}`;
            }

            return (
              <div key={String(job.id)} className="relative">
                <a
                  href={`/jobs/${job.id}`}
                  className="block border border-gray-800 rounded-lg p-4 hover:bg-gray-900/50 transition-colors"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="font-mono font-medium text-blue-400">{String(job.id)}</span>
                      <JobTypeTag jobType={jobType} />
                      <span className={`px-2 py-0.5 rounded-full text-xs border ${statusColors[String(job.status)] || ""}`}>
                        {String(job.status)}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-xs font-bold border ${
                        String(job.device || "cpu") === "cuda"
                          ? "bg-green-500/20 text-green-400 border-green-500/30"
                          : "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                      }`}>
                        {String(job.device || "cpu") === "cuda" ? "GPU" : "CPU"}
                      </span>
                      <span className="text-xs text-gray-600">
                        {job.created_at ? new Date(Number(job.created_at) * 1000).toLocaleString("pt-BR") : ""}
                      </span>
                    </div>
                    <div className="text-sm text-gray-500">{infoText}</div>
                  </div>

                  {isActive && (
                    <>
                      <div className="bg-gray-800 rounded-full h-2 mb-1">
                        <div
                          className="bg-blue-500 h-2 rounded-full transition-all"
                          style={{ width: `${progress.percent || 0}%` }}
                        />
                      </div>
                      <div className="flex justify-between text-xs text-gray-500">
                        <span>
                          Etapa: {String(progress.stage_name || "...")} ({String(progress.current_stage || 0)}/
                          {String(progress.total_stages || 0)})
                        </span>
                        <div className="flex items-center gap-3">
                          {!!progress.eta_text && <span>ETA: {String(progress.eta_text)}</span>}
                          <span className="font-mono">{String(progress.percent || 0)}%</span>
                        </div>
                      </div>
                    </>
                  )}

                  {job.status === "completed" && (
                    <div className="text-sm text-gray-500">
                      Duração: {String(job.duration_s || 0)}s
                      {String(config.input || "").length > 0 && (
                        <span className="ml-3 truncate">
                          {String(config.input).substring(0, 80)}
                        </span>
                      )}
                    </div>
                  )}

                  {job.status === "failed" && !!job.error && (
                    <div className="text-sm text-red-400 mt-1">{String(job.error).substring(0, 120)}</div>
                  )}
                </a>

                {/* Botão excluir (fora do <a> para não navegar) */}
                <button
                  onClick={(e) => handleDelete(e, String(job.id))}
                  disabled={deleting === String(job.id)}
                  className="absolute top-3 right-3 px-2 py-1 rounded text-xs text-gray-600 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                  title="Excluir job"
                >
                  {deleting === String(job.id) ? "..." : "🗑"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
