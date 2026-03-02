"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createDownloadJob, createDownloadJobWithUpload } from "@/lib/api";

const QUALITY_OPTIONS = [
  { value: "best",  label: "Melhor qualidade",  desc: "Video + audio na melhor resolucao disponivel" },
  { value: "1080p", label: "1080p (Full HD)",    desc: "Limitar a 1920x1080" },
  { value: "720p",  label: "720p (HD)",          desc: "Limitar a 1280x720" },
  { value: "480p",  label: "480p (SD)",          desc: "Limitar a 854x480" },
  { value: "audio", label: "So audio (MP3)",     desc: "Extrair apenas o audio em MP3 192kbps" },
];

const SUPPORTED_SITES = [
  { name: "YouTube",    color: "text-red-400" },
  { name: "TikTok",     color: "text-pink-400" },
  { name: "Instagram",  color: "text-purple-400" },
  { name: "Facebook",   color: "text-blue-400" },
  { name: "Twitter/X",  color: "text-sky-400" },
  { name: "Twitch",     color: "text-violet-400" },
  { name: "+1000 sites",color: "text-gray-400" },
];

function DownloadPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<"url" | "file">("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [quality, setQuality] = useState("best");
  const [loading, setLoading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [prefilled, setPrefilled] = useState(false);

  const isFacebookReel = mode === "url" && (
    url.includes("/share/r/") || url.includes("/reel/")
  );

  useEffect(() => {
    const raw = searchParams.get("prefill");
    if (!raw) return;
    try {
      const cfg = JSON.parse(decodeURIComponent(raw));
      if (cfg.url) { setUrl(cfg.url); setMode("url"); }
      if (cfg.quality) setQuality(cfg.quality);
      setPrefilled(true);
    } catch { /* ignorar parse errors */ }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setUploadPct(0);

    try {
      let job: Record<string, unknown>;
      if (mode === "url") {
        if (!url.trim()) return;
        job = await createDownloadJob({ url: url.trim(), quality }) as Record<string, unknown>;
      } else {
        if (!file) return;
        job = await createDownloadJobWithUpload(
          file,
          { quality },
          (pct) => setUploadPct(pct),
        ) as Record<string, unknown>;
      }
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      setError(String(err));
      setLoading(false);
    }
  };

  const canSubmit = mode === "url" ? !!url.trim() : !!file;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Baixar / Converter Video</h1>
        <p className="text-gray-400">Cole um link ou envie um arquivo para extrair audio ou mudar a qualidade</p>
      </div>

      {prefilled && (
        <div className="mb-4 px-4 py-2 bg-blue-500/10 border border-blue-500/30 rounded-lg text-blue-300 text-sm">
          Configuracao restaurada do job anterior
        </div>
      )}

      {/* Mode toggle */}
      <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-lg p-1 mb-6">
        <button
          type="button"
          onClick={() => setMode("url")}
          className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
            mode === "url" ? "bg-green-600 text-white" : "text-gray-400 hover:text-white"
          }`}
        >
          Link (URL)
        </button>
        <button
          type="button"
          onClick={() => setMode("file")}
          className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
            mode === "file" ? "bg-green-600 text-white" : "text-gray-400 hover:text-white"
          }`}
        >
          Arquivo Local
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 text-red-400">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">

        {/* URL mode */}
        {mode === "url" && (
          <section className="border border-gray-800 rounded-lg p-5">
            <h2 className="text-lg font-semibold mb-3">Link do Video</h2>
            <div className="flex flex-wrap gap-2 mb-4">
              {SUPPORTED_SITES.map((site) => (
                <span key={site.name} className={`text-xs px-2 py-1 bg-gray-800 rounded-full border border-gray-700 ${site.color}`}>
                  {site.name}
                </span>
              ))}
            </div>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:border-green-500 focus:outline-none"
              autoFocus
            />
            <p className="text-xs text-gray-500 mt-2">Suporta qualquer plataforma compativel com yt-dlp</p>

            {isFacebookReel && (
              <div className="mt-3 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-sm text-yellow-300">
                <strong>⚠ Facebook Reel</strong> — Downloads de Reels requerem login.{" "}
                Se falhar, baixe em{" "}
                <a
                  href="https://fdownloader.net"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline text-yellow-200 hover:text-white"
                >
                  fdownloader.net
                </a>{" "}
                e use <strong>Arquivo Local</strong>.
              </div>
            )}
          </section>
        )}

        {/* File mode */}
        {mode === "file" && (
          <section className="border border-gray-800 rounded-lg p-5">
            <h2 className="text-lg font-semibold mb-3">Arquivo de Video</h2>
            <label className={`flex flex-col items-center justify-center border-2 border-dashed rounded-lg p-8 cursor-pointer transition-colors ${
              file ? "border-green-500/50 hover:border-green-500/70" : "border-gray-700 hover:border-green-500/50"
            }`}>
              {file ? (
                <div className="text-center">
                  <div className="text-green-400 font-medium">{file.name}</div>
                  <div className="text-gray-500 text-xs mt-1">{(file.size / 1024 / 1024).toFixed(1)} MB</div>
                </div>
              ) : (
                <div className="text-center text-gray-500">
                  <div className="text-3xl mb-2">📁</div>
                  <div className="text-sm">Clique para selecionar o arquivo</div>
                  <div className="text-xs mt-1 text-gray-600">MP4, MKV, AVI, MOV, WebM...</div>
                </div>
              )}
              <input
                type="file"
                accept="video/*,audio/*,.mkv,.avi,.mov,.webm,.mp4,.m4v"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <p className="text-xs text-gray-500 mt-2">
              Use a qualidade <strong className="text-gray-300">So audio</strong> para extrair apenas o MP3 do video.
            </p>
          </section>
        )}

        {/* Qualidade */}
        <section className="border border-gray-800 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-3">Qualidade</h2>
          <div className="space-y-2">
            {QUALITY_OPTIONS.map((opt) => (
              <label key={opt.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                quality === opt.value
                  ? "border-green-500 bg-green-500/10"
                  : "border-gray-700 hover:border-gray-600"
              }`}>
                <input
                  type="radio"
                  name="quality"
                  value={opt.value}
                  checked={quality === opt.value}
                  onChange={() => setQuality(opt.value)}
                  className="mt-0.5"
                />
                <div>
                  <div className="font-medium text-sm">{opt.label}</div>
                  <div className="text-xs text-gray-500">{opt.desc}</div>
                </div>
              </label>
            ))}
          </div>
        </section>

        {/* Upload progress */}
        {mode === "file" && loading && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-gray-400">
              <span>{uploadPct < 100 ? "Enviando arquivo..." : "Processando..."}</span>
              {uploadPct < 100 && <span>{uploadPct}%</span>}
            </div>
            <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 transition-all"
                style={{ width: uploadPct < 100 ? `${uploadPct}%` : "100%" }}
              />
            </div>
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={loading || !canSubmit}
          className="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white px-6 py-3 rounded-lg font-medium text-lg transition-colors"
        >
          {loading
            ? mode === "file" && uploadPct < 100
              ? `Enviando... ${uploadPct}%`
              : "Processando..."
            : mode === "url"
            ? "Baixar Video"
            : "Converter / Extrair Audio"}
        </button>
      </form>
    </div>
  );
}

export default function DownloadPage() {
  return (
    <Suspense>
      <DownloadPageInner />
    </Suspense>
  );
}
