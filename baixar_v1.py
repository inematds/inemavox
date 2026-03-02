#!/usr/bin/env python3
"""Baixador de videos usando yt-dlp (YouTube, TikTok, Instagram, Facebook, etc.)
   Tambem converte/extrai audio de arquivos locais via ffmpeg."""

import argparse
import glob as _glob
import json
import subprocess
import sys
import urllib.request
from pathlib import Path


def write_checkpoint(dub_work_dir: Path, step: int):
    cp = {"last_step_num": step}
    (dub_work_dir / "checkpoint.json").write_text(json.dumps(cp))


def process_local_file(local_file: Path, quality: str, outdir: Path) -> Path:
    """Converte/extrai audio de um arquivo local usando ffmpeg."""
    print(f"[baixar] Arquivo local: {local_file}", flush=True)
    print(f"[baixar] Qualidade/modo: {quality}", flush=True)

    if quality == "audio":
        out_path = outdir / "video.mp3"
        cmd = [
            "ffmpeg", "-y", "-i", str(local_file),
            "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
            str(out_path),
        ]
        print("[baixar] Extraindo audio em MP3 192kbps...", flush=True)
    elif quality in ("1080p", "720p", "480p"):
        height = {"1080p": 1080, "720p": 720, "480p": 480}[quality]
        out_path = outdir / "video.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", str(local_file),
            "-vf", f"scale=-2:{height}",
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-c:a", "aac", "-b:a", "128k",
            str(out_path),
        ]
        print(f"[baixar] Convertendo para {quality}...", flush=True)
    else:  # best — remux para MP4 sem re-encode
        out_path = outdir / "video.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", str(local_file),
            "-c", "copy",
            str(out_path),
        ]
        print("[baixar] Remuxando para MP4...", flush=True)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback: tentar sem copy se remux falhou (container format incompativel)
        if quality == "best":
            print("[baixar] Remux falhou, tentando com re-encode...", flush=True)
            cmd2 = [
                "ffmpeg", "-y", "-i", str(local_file),
                "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                "-c:a", "aac", "-b:a", "128k",
                str(out_path),
            ]
            result2 = subprocess.run(cmd2, capture_output=True, text=True)
            if result2.returncode != 0:
                raise RuntimeError(f"ffmpeg falhou: {result2.stderr[-400:]}")
        else:
            raise RuntimeError(f"ffmpeg falhou: {result.stderr[-400:]}")

    return out_path


def _find_firefox_profile() -> str | None:
    """Detecta o profile padrao do Firefox, incluindo instalacoes via snap."""
    import os
    candidates = [
        # Firefox snap (Ubuntu)
        os.path.expanduser("~/snap/firefox/common/.mozilla/firefox"),
        # Firefox normal
        os.path.expanduser("~/.mozilla/firefox"),
    ]
    for base in candidates:
        if not Path(base).exists():
            continue
        # Preferir profile com cookies.sqlite
        profiles = _glob.glob(f"{base}/*.default*") + _glob.glob(f"{base}/*.default")
        for p in sorted(profiles):
            if Path(p, "cookies.sqlite").exists():
                return p
    return None


def main():
    parser = argparse.ArgumentParser(description="Baixar video com yt-dlp ou processar arquivo local")
    parser.add_argument("--url", default=None, help="URL do video (YouTube, TikTok, etc.)")
    parser.add_argument("--local-file", default=None, dest="local_file", help="Arquivo local para converter/extrair audio")
    parser.add_argument("--outdir", required=True, help="Diretorio de saida")
    parser.add_argument(
        "--quality",
        default="best",
        choices=["best", "1080p", "720p", "480p", "audio"],
        help="Qualidade do download",
    )
    args = parser.parse_args()

    if not args.url and not args.local_file:
        print("[baixar] ERRO: Informe --url ou --local-file", flush=True)
        sys.exit(1)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # dub_work para checkpoint (compativel com job_manager)
    dub_work = outdir.parent / "dub_work"
    dub_work.mkdir(parents=True, exist_ok=True)

    print(f"[baixar] Qualidade: {args.quality}", flush=True)
    print(f"[baixar] Saida: {outdir}", flush=True)

    write_checkpoint(dub_work, 0)

    # --- Arquivo local ---
    if args.local_file:
        local_path = Path(args.local_file)
        if not local_path.exists():
            print(f"[baixar] ERRO: Arquivo nao encontrado: {args.local_file}", flush=True)
            sys.exit(1)
        try:
            out = process_local_file(local_path, args.quality, outdir)
            size_mb = out.stat().st_size // 1024 // 1024
            print(f"[baixar] Concluido: {out.name} ({size_mb}MB)", flush=True)
            write_checkpoint(dub_work, 1)
        except Exception as e:
            print(f"[baixar] ERRO: {e}", flush=True)
            sys.exit(1)
        return

    # --- Download via URL ---
    url = args.url

    # Resolver redirect de URLs curtas do Facebook (share/r/, share/v/, etc.)
    # O extrator do Facebook falha com essas URLs — precisa da URL real do video
    if "facebook.com/share/" in url:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
            )
            resp = urllib.request.urlopen(req, timeout=15)
            resolved = resp.url
            if resolved != url:
                print(f"[baixar] URL Facebook resolvida: {resolved}", flush=True)
                url = resolved
        except Exception as e:
            print(f"[baixar] Aviso: nao foi possivel resolver redirect ({e}), tentando URL original", flush=True)

    print(f"[baixar] URL: {url}", flush=True)

    try:
        import yt_dlp
    except ImportError:
        print("[baixar] ERRO: yt-dlp nao instalado. Instale com: pip install yt-dlp", flush=True)
        sys.exit(1)

    outtmpl = str(outdir / "video.%(ext)s")

    if args.quality == "audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }
    elif args.quality == "1080p":
        ydl_opts = {
            "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
        }
    elif args.quality == "720p":
        ydl_opts = {
            "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
        }
    elif args.quality == "480p":
        ydl_opts = {
            "format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best",
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
        }
    else:  # best
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
        }

    # Para URLs do Facebook: impersonacao + cookies do Firefox
    is_facebook = "facebook.com" in url or "fb.com" in url
    is_reel = "/reel/" in url or "/share/r/" in url
    if is_facebook:
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            ydl_opts["impersonate"] = ImpersonateTarget("chrome", None, None, None)
        except ImportError:
            pass

        # Tentar cookies do Firefox (incluindo instalacao via snap)
        firefox_profile = _find_firefox_profile()
        cookies_file = Path(__file__).parent / "facebook_cookies.txt"

        if firefox_profile:
            ydl_opts["cookiesfrombrowser"] = ("firefox", firefox_profile, None, None)
            print(f"[baixar] Facebook: usando cookies do Firefox ({Path(firefox_profile).name})", flush=True)
        elif cookies_file.exists():
            ydl_opts["cookiefile"] = str(cookies_file)
            print(f"[baixar] Facebook: usando cookies de {cookies_file.name}", flush=True)
        elif is_reel:
            print("[baixar] Facebook Reel detectado — faca login no Firefox para melhor resultado", flush=True)

    print("[baixar] Iniciando download...", flush=True)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        err_str = str(e)
        if "Cannot parse data" in err_str and is_reel:
            print(
                "[baixar] ERRO: Facebook Reel requer login para download.\n"
                "[baixar] Para resolver: exporte seus cookies do Chrome/Firefox para\n"
                f"[baixar]   {Path(__file__).parent / 'facebook_cookies.txt'}\n"
                "[baixar] Use a extensao 'Get cookies.txt LOCALLY' no Chrome.\n"
                "[baixar] Alternativa rapida: baixe em fdownloader.net e use 'Arquivo Local'.",
                flush=True,
            )
        elif "Cannot parse data" in err_str and is_facebook:
            print(
                "[baixar] ERRO: Facebook bloqueou o download.\n"
                "[baixar] Alternativa: use fdownloader.net e depois 'Arquivo Local'.",
                flush=True,
            )
        else:
            print(f"[baixar] ERRO: {err_str}", flush=True)
        sys.exit(1)

    # Verificar se arquivo foi criado
    files = list(outdir.glob("video.*"))
    if not files:
        print("[baixar] ERRO: Nenhum arquivo baixado encontrado", flush=True)
        sys.exit(1)

    print(f"[baixar] Download concluido: {files[0].name} ({files[0].stat().st_size // 1024 // 1024}MB)", flush=True)
    write_checkpoint(dub_work, 1)


if __name__ == "__main__":
    main()
