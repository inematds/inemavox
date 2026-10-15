#!/usr/bin/env python3
"""
Whisper residente: carrega o modelo UMA vez e atende várias transcrições curtas (15/10/2026).

Antes, cada fala narrada (cardshorts, eventosextremospub) abria um processo novo e recarregava o
large-v3 (duas vezes por fala: conferir a voz e medir as palavras). Com a máquina cheia isso levava
mais de 1 h por vídeo. Aqui o modelo fica na memória e sai sozinho depois de OCIOSO segundos parado.

Rodar no conda chatterbox (mesmo do whisper_gpu_worker.py):
  ~/miniconda3/envs/chatterbox/bin/python3 whisper_daemon.py [--porta 7871] [--modelo large-v3] [--ocioso 600]
API (só 127.0.0.1):
  GET  /saude                                   -> {"ok": true, "modelo": ...}
  POST /transcrever {"audio": caminho, "lang": "pt", "words": true}
       -> {"language": ..., "segments": [...]}   (mesmo formato do whisper_gpu_worker.py)
Uma transcrição por vez (trava): pedidos simultâneos esperam na fila.
"""
import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
import whisper

ap = argparse.ArgumentParser()
ap.add_argument("--porta", type=int, default=7871)
ap.add_argument("--modelo", default="large-v3")
ap.add_argument("--ocioso", type=int, default=600, help="sai depois de N s sem pedido (libera a memória)")
args = ap.parse_args()

# a porta antes do modelo: se outro processo já subiu o daemon, este sai na hora sem carregar 3 GB à toa
import socket
_s = socket.socket()
_s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    _s.bind(("127.0.0.1", args.porta))
except OSError:
    raise SystemExit(f"[whisper_daemon] porta {args.porta} ocupada: outro daemon já está no ar")
_s.close()
device = "cuda" if torch.cuda.is_available() else "cpu"
t0 = time.time()
model = whisper.load_model(args.modelo, device=device)
print(f"[whisper_daemon] {args.modelo} em {device}, carregado em {time.time()-t0:.1f}s, porta {args.porta}", flush=True)

trava = threading.Lock()
ultimo = time.time()


def transcrever(audio, lang, words):
    # mesmos parâmetros do whisper_gpu_worker.py
    result = model.transcribe(
        audio, language=lang or None, fp16=device == "cuda", verbose=None,
        condition_on_previous_text=False, no_speech_threshold=0.6,
        compression_ratio_threshold=2.0, word_timestamps=words,
    )
    segs = []
    for seg in result["segments"]:
        item = {"start": round(seg["start"], 3), "end": round(seg["end"], 3), "text": seg["text"].strip()}
        if words:
            item["words"] = [{"word": w["word"].strip(), "start": round(w["start"], 3), "end": round(w["end"], 3)}
                             for w in seg.get("words", []) if w.get("word", "").strip()]
        segs.append(item)
    return {"language": result.get("language", ""), "segments": segs}


class H(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/saude":
            return self._json(200, {"ok": True, "modelo": args.modelo, "device": device})
        self._json(404, {"erro": "rota"})

    def do_POST(self):
        global ultimo
        if self.path != "/transcrever":
            return self._json(404, {"erro": "rota"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            with trava:
                t = time.time()
                out = transcrever(req["audio"], req.get("lang"), bool(req.get("words")))
                ultimo = time.time()
            print(f"[whisper_daemon] {os.path.basename(req['audio'])} em {time.time()-t:.1f}s", flush=True)
            self._json(200, out)
        except Exception as e:  # noqa: BLE001 — devolve o erro ao cliente, que cai no caminho antigo
            self._json(500, {"erro": str(e)})

    def log_message(self, *a):
        pass


def vigia():
    while True:
        time.sleep(30)
        if not trava.locked() and time.time() - ultimo > args.ocioso:
            print("[whisper_daemon] ocioso, saindo", flush=True)
            srv.shutdown()
            return


srv = ThreadingHTTPServer(("127.0.0.1", args.porta), H)
threading.Thread(target=vigia, daemon=True).start()
srv.serve_forever()
