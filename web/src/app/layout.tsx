import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "inemaVOX 1.9.1 - Suite de Voz com IA",
  description: "Suite de voz local com IA: dubla, transcreve, corta e baixa videos com GPU",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="bg-gray-950 text-gray-100 min-h-screen">
        <nav className="border-b border-gray-800 bg-gray-900/50 backdrop-blur-sm sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
            <a href="/" className="text-xl font-bold text-white flex items-baseline gap-1">
              inema<span className="text-blue-400">VOX</span> <span className="text-gray-500 text-sm font-normal">1.9.1</span>
            </a>
            <div className="flex gap-5 text-sm">
              <a href="/" className="hover:text-white transition-colors text-gray-400">Dashboard</a>
              <a href="/new" className="hover:text-blue-400 transition-colors text-blue-300">🎙 Dublagem</a>
              <a href="/tts" className="hover:text-cyan-400 transition-colors text-cyan-300">🔊 Gerar Audio</a>
              <a href="/voice-clone" className="hover:text-pink-400 transition-colors text-pink-300">🎤 Clonar Voz</a>
              <a href="/transcribe" className="hover:text-purple-400 transition-colors text-purple-300">📝 Transcrever</a>
              <a href="/cut" className="hover:text-orange-400 transition-colors text-orange-300">✂ Cortar</a>
              <a href="/download" className="hover:text-green-400 transition-colors text-green-300">⬇ Baixar</a>
              <a href="/jobs" className="hover:text-white transition-colors text-gray-400">Jobs</a>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
