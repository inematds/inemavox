"use client";

import { useEffect, useState } from "react";
import { listJobs } from "@/lib/api";

type Job = Record<string, unknown>;

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    const load = () => {
      listJobs()
        .then(setJobs)
        .catch(() => setError("API offline"));
    };
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  const filtered = filter === "all" ? jobs : jobs.filter((j) => j.status === filter);

  const statusColors: Record<string, string> = {
    completed: "bg-green-500/20 text-green-400 border-green-500/30",
    running: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    failed: "bg-red-500/20 text-red-400 border-red-500/30",
    queued: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    cancelled: "bg-gray-500/20 text-gray-400 border-gray-500/30",
  };

  const counts = {
    all: jobs.length,
    running: jobs.filter((j) => j.status === "running").length,
    completed: jobs.filter((j) => j.status === "completed").length,
    failed: jobs.filter((j) => j.status === "failed").length,
    queued: jobs.filter((j) => j.status === "queued").length,
  };

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">Jobs</h1>
        <a
          href="/new"
          className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-lg font-medium transition-colors"
        >
          + Nova Dublagem
        </a>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 text-red-400">{error}</div>
      )}

      {/* Filters */}
      <div className="flex gap-2 mb-6">
        {(["all", "running", "queued", "completed", "failed"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              filter === f
                ? "bg-blue-600 text-white"
                : "bg-gray-800 text-gray-400 hover:text-white"
            }`}
          >
            {f === "all" ? "Todos" : f.charAt(0).toUpperCase() + f.slice(1)} ({counts[f] || 0})
          </button>
        ))}
      </div>

      {/* Jobs List */}
      {filtered.length === 0 ? (
        <div className="border border-gray-800 rounded-lg p-12 text-center text-gray-500">
          {jobs.length === 0 ? (
            <>Nenhum job ainda. <a href="/new" className="text-blue-400 hover:underline">Criar nova dublagem</a></>
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
            return (
              <a
                key={String(job.id)}
                href={`/jobs/${job.id}`}
                className="block border border-gray-800 rounded-lg p-4 hover:bg-gray-900/50 transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-medium text-blue-400">{String(job.id)}</span>
                    <span className={`px-2 py-0.5 rounded-full text-xs border ${statusColors[String(job.status)] || ""}`}>
                      {String(job.status)}
                    </span>
                    <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                      String(job.device || "cpu") === "cuda"
                        ? "bg-green-500/20 text-green-400 border border-green-500/30"
                        : "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30"
                    }`}>
                      {String(job.device || "cpu") === "cuda" ? "GPU" : "CPU"}
                    </span>
                  </div>
                  <div className="text-sm text-gray-500">
                    {String(config.src_lang || "auto")} &rarr; {String(config.tgt_lang || "pt")}
                    <span className="mx-2">|</span>
                    {String(config.tts_engine || "edge")}
                    <span className="mx-2">|</span>
                    {String(config.translation_engine || "m2m100")}
                  </div>
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
                        {String(progress.total_stages || 10)})
                      </span>
                      <div className="flex items-center gap-3">
                        {!!progress.eta_text && (
                          <span>ETA: {String(progress.eta_text)}</span>
                        )}
                        <span className="font-mono">{String(progress.percent || 0)}%</span>
                      </div>
                    </div>
                  </>
                )}

                {job.status === "completed" && (
                  <div className="text-sm text-gray-500">
                    Duracao: {String(job.duration_s || 0)}s
                    {String(config.input || "").length > 0 && (
                      <span className="ml-3">Input: {String(config.input).substring(0, 60)}...</span>
                    )}
                  </div>
                )}

                {job.status === "failed" && !!job.error && (
                  <div className="text-sm text-red-400 mt-1">{String(job.error).substring(0, 100)}</div>
                )}
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
