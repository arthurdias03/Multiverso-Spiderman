"""spotifiBR Desktop: painel local (abre no navegador) que executa tudo com botões.

Segurança: escuta só em 127.0.0.1, exige um token aleatório por sessão (na URL de abertura e no
cabeçalho de cada chamada), confere o cabeçalho Host (contra DNS rebinding), aceita ações só por
POST/PUT e envia Content-Security-Policy restritiva.
"""

from __future__ import annotations

import hmac
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from collections import deque
from pathlib import Path

from .config import Config
from .library import AUDIO_EXT
from .runner import LINKS_FILE, load_summary, run_links, run_sync
from .spotify import SpotifyClient, parse_playlist_id
from .sync import safe_name

STATIC = Path(__file__).with_name("static")
MAX_UPLOAD = 300 * 1024 * 1024
BITRATES = {"96k", "128k", "160k", "192k", "256k", "320k"}
SETTINGS_KEYS = {"spotify_client_id", "playlists", "library_dirs", "mp3_bitrate"}


class Engine:
    """Estado e tarefas do painel. Tudo que demora roda em thread e escreve no log."""

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path).resolve()
        self.log: deque[tuple[int, float, str]] = deque(maxlen=500)
        self.seq = 0
        self.lock = threading.Lock()
        self.busy: str | None = None
        self.srv = None
        self.srv_info: dict = {}
        self.auto = False
        self.auto_minutes = 10
        self.last_auto = 0.0
        self.fingerprint: tuple | None = None
        self.stop_event = threading.Event()

    # ---------- utilidades ----------
    def cfg(self) -> Config:
        return Config.load(self.config_path)

    def emit(self, msg: str) -> None:
        with self.lock:
            self.seq += 1
            self.log.append((self.seq, time.time(), str(msg)))

    def _task(self, name: str, fn) -> bool:
        with self.lock:
            if self.busy:
                return False
            self.busy = name

        def run():
            try:
                fn()
            except Exception as e:  # noqa: BLE001 - mostra qualquer falha no painel
                self.emit(f"Erro: {e}")
            finally:
                with self.lock:
                    self.busy = None

        threading.Thread(target=run, daemon=True).start()
        return True

    # ---------- ações ----------
    def sync(self, reason: str = "manual") -> bool:
        def job():
            self.emit(f"Sincronização iniciada ({reason})")
            reports = run_sync(self.cfg(), self.emit)
            new = sum(len(r.new) for r in reports)
            miss = sum(len(r.missing) for r in reports)
            self.emit(f"Concluído: {new} nova(s) para o relógio, {miss} sem arquivo")
            self.fingerprint = self._library_fingerprint()
        return self._task("Sincronizando", job)

    def links(self) -> bool:
        def job():
            self.emit("Gerando a lista de links de todas as músicas...")
            run_links(self.cfg(), self.emit)
        return self._task("Gerando lista de links", job)

    def open_output(self, name: str) -> None:
        cfg = self.cfg()
        if name not in (LINKS_FILE, "_FALTANDO.txt"):
            raise ValueError("Arquivo não permitido")
        path = cfg.out / name
        if not path.exists():
            raise ValueError("A lista ainda não foi gerada")
        opener = {"darwin": ["open"], "win32": ["cmd", "/c", "start", ""]}.get(sys.platform, ["xdg-open"])
        subprocess.Popen(opener + [str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def login(self) -> bool:
        def job():
            cfg = self.cfg()
            self.emit("Abrindo o navegador para autorizar o Spotify...")
            SpotifyClient(cfg.spotify_client_id, cfg.token_file, cfg.redirect_uri).login(open_browser=True)
            self.emit("Spotify conectado (somente leitura)")
        return self._task("Conectando ao Spotify", job)

    def start_server(self) -> dict:
        from .server import lan_ip, load_or_create_token, make_server

        if self.srv:
            return self.srv_info
        cfg = self.cfg()
        if not (cfg.out / "manifest.json").exists():
            raise RuntimeError("Sincronize pelo menos uma vez antes de ligar o servidor.")
        token = load_or_create_token(cfg.server_token, cfg.server_token_file)
        host = lan_ip() if cfg.server_bind == "auto" else cfg.server_bind
        tls = str(cfg.resolve(cfg.tls_cert)) if cfg.tls_cert else ""
        key = str(cfg.resolve(cfg.tls_key)) if cfg.tls_key else ""
        srv = make_server(cfg.out, cfg.server_port, token, host, cfg.allow_public_clients, tls, key)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.srv = srv
        shown = lan_ip() if host in ("0.0.0.0", "::") else host
        self.srv_info = {"url": f"{'https' if tls else 'http'}://{shown}:{cfg.server_port}", "token": token}
        self.emit(f"Servidor para o relógio ligado em {self.srv_info['url']}")
        return self.srv_info

    def stop_server(self) -> None:
        if self.srv:
            self.srv.shutdown()
            self.srv.server_close()
            self.srv = None
            self.srv_info = {}
            self.emit("Servidor para o relógio desligado")

    def new_token(self) -> None:
        from .server import rotate_token

        cfg = self.cfg()
        if cfg.server_token:
            raise RuntimeError("server_token está fixo no config.json; apague-o de lá para usar token automático.")
        running = bool(self.srv)
        self.stop_server()
        rotate_token(cfg.server_token_file)
        self.emit("Novo token gerado: atualize nas configurações do app Zepp")
        if running:
            self.start_server()

    def set_auto(self, enabled: bool, minutes: int) -> None:
        self.auto = bool(enabled)
        self.auto_minutes = max(1, min(int(minutes), 24 * 60))
        self.last_auto = time.time()
        self.emit(f"Automático {'ligado' if self.auto else 'desligado'}"
                  + (f": a cada {self.auto_minutes} min e quando entrar música nova na pasta" if self.auto else ""))

    def save_settings(self, data: dict) -> None:
        unknown = set(data) - SETTINGS_KEYS
        if unknown:
            raise ValueError(f"Campos não permitidos: {', '.join(sorted(unknown))}")
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        if "spotify_client_id" in data:
            cid = str(data["spotify_client_id"]).strip()
            if cid and not re.fullmatch(r"[A-Za-z0-9]{16,64}", cid):
                raise ValueError("Client ID inválido")
            raw["spotify_client_id"] = cid
        if "playlists" in data:
            lst = [str(x).strip() for x in data["playlists"] if str(x).strip()][:50]
            for ref in lst:
                parse_playlist_id(ref)  # valida (levanta ValueError)
            raw["playlists"] = lst
        if "library_dirs" in data:
            dirs = [str(x).strip() for x in data["library_dirs"] if str(x).strip()][:20]
            for d in dirs:
                if not Path(d).expanduser().is_dir():
                    raise ValueError(f"Pasta não existe: {d}")
            raw["library_dirs"] = dirs
        if "mp3_bitrate" in data:
            if data["mp3_bitrate"] not in BITRATES:
                raise ValueError("Qualidade inválida")
            raw["mp3_bitrate"] = data["mp3_bitrate"]
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.config_path)
        self.emit("Configurações salvas")

    def save_upload(self, name: str, body: bytes) -> str:
        cfg = self.cfg()
        if not cfg.library_dirs:
            raise ValueError("Defina uma pasta de biblioteca primeiro")
        ext = Path(name).suffix.lower()
        if ext not in AUDIO_EXT:
            raise ValueError("Formato não aceito (use MP3, M4A, FLAC, OGG, OPUS ou WAV)")
        target_dir = cfg.resolve(cfg.library_dirs[0]).expanduser()
        target_dir.mkdir(parents=True, exist_ok=True)
        base = safe_name(Path(name).stem) or "musica"
        dest = target_dir / f"{base}{ext}"
        n = 1
        while dest.exists():
            n += 1
            dest = target_dir / f"{base} ({n}){ext}"
        if dest.resolve().parent != target_dir.resolve():
            raise ValueError("Nome inválido")
        dest.write_bytes(body)
        self.emit(f"Adicionada à biblioteca: {dest.name}")
        return dest.name

    def open_library(self) -> None:
        cfg = self.cfg()
        if not cfg.library_dirs:
            raise ValueError("Nenhuma pasta configurada")
        path = str(cfg.resolve(cfg.library_dirs[0]).expanduser())
        opener = {"darwin": ["open"], "win32": ["explorer"]}.get(sys.platform, ["xdg-open"])
        subprocess.Popen(opener + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---------- automático ----------
    def _library_fingerprint(self) -> tuple:
        try:
            cfg = self.cfg()
        except Exception:  # noqa: BLE001
            return ()
        count, newest = 0, 0.0
        for d in cfg.library_dirs:
            root = cfg.resolve(d).expanduser()
            if not root.is_dir():
                continue
            for p in root.rglob("*"):
                if p.suffix.lower() in AUDIO_EXT:
                    count += 1
                    try:
                        newest = max(newest, p.stat().st_mtime)
                    except OSError:
                        pass
        return (count, newest)

    def auto_loop(self) -> None:
        self.fingerprint = self._library_fingerprint()
        while not self.stop_event.wait(20):
            if not self.auto or self.busy:
                continue
            fp = self._library_fingerprint()
            due = time.time() - self.last_auto >= self.auto_minutes * 60
            if fp != self.fingerprint or due:
                self.last_auto = time.time()
                self.sync("automático: música nova na pasta" if fp != self.fingerprint else "automático: horário")

    # ---------- leitura ----------
    def status(self) -> dict:
        try:
            cfg = self.cfg()
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
        summary = load_summary(cfg)
        return {
            "busy": self.busy,
            "spotify": {"client_id": bool(cfg.spotify_client_id), "connected": cfg.token_file.exists()},
            "settings": {
                "spotify_client_id": cfg.spotify_client_id,
                "playlists": cfg.playlists,
                "library_dirs": cfg.library_dirs,
                "mp3_bitrate": cfg.mp3_bitrate,
            },
            "server": {"running": bool(self.srv), **self.srv_info},
            "auto": {"enabled": self.auto, "minutes": self.auto_minutes},
            "summary": summary,
        }

    def logs_since(self, since: int) -> list[dict]:
        with self.lock:
            return [{"id": i, "t": t, "msg": m} for i, t, m in self.log if i > since]


def make_panel(engine: Engine, port: int = 8770, token: str | None = None):
    token = token or secrets.token_urlsafe(24)

    class H(http.server.BaseHTTPRequestHandler):
        server_version = "spotifiBR"
        sys_version = ""
        timeout = 60

        def log_message(self, *a):
            pass

        # -- respostas --
        def _send(self, code, body=b"", ctype="application/json; charset=utf-8"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                             "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            host = (self.headers.get("Host") or "").lower()
            return host in (f"127.0.0.1:{self.server.server_address[1]}", f"localhost:{self.server.server_address[1]}")

        def _auth(self):
            return hmac.compare_digest(self.headers.get("X-Panel-Token", "").encode(), token.encode())

        def _json_body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                raise ValueError("Requisição grande demais")
            return json.loads(self.rfile.read(n) or b"{}")

        # -- rotas --
        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                return self._send(403, {"error": "host"})
            u = urllib.parse.urlsplit(self.path)
            if u.path == "/":
                q = urllib.parse.parse_qs(u.query)
                if not hmac.compare_digest((q.get("t") or [""])[0].encode(), token.encode()):
                    return self._send(403, "Abra o painel pelo link mostrado no terminal.".encode(), "text/plain; charset=utf-8")
                return self._send(200, (STATIC / "panel.html").read_bytes(), "text/html; charset=utf-8")
            if u.path in ("/panel.js", "/panel.css", "/icon.png"):
                ctype = {".js": "text/javascript", ".css": "text/css", ".png": "image/png"}[Path(u.path).suffix]
                return self._send(200, (STATIC / u.path.lstrip("/")).read_bytes(), ctype)
            if not self._auth():
                return self._send(401, {"error": "token"})
            if u.path == "/api/status":
                return self._send(200, engine.status())
            if u.path == "/api/log":
                since = int((urllib.parse.parse_qs(u.query).get("since") or ["0"])[0] or 0)
                return self._send(200, engine.logs_since(since))
            return self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if not self._host_ok() or not self._auth():
                return self._send(403, {"error": "forbidden"})
            path = urllib.parse.urlsplit(self.path).path
            try:
                data = self._json_body()
                if path == "/api/sync":
                    ok = engine.sync()
                elif path == "/api/links":
                    ok = engine.links()
                elif path == "/api/open-file":
                    engine.open_output(str(data.get("name", "")))
                    ok = True
                elif path == "/api/login":
                    ok = engine.login()
                elif path == "/api/server/start":
                    return self._send(200, engine.start_server())
                elif path == "/api/server/stop":
                    engine.stop_server()
                    ok = True
                elif path == "/api/token/new":
                    engine.new_token()
                    ok = True
                elif path == "/api/auto":
                    engine.set_auto(bool(data.get("enabled")), int(data.get("minutes", 10)))
                    ok = True
                elif path == "/api/settings":
                    engine.save_settings(data)
                    ok = True
                elif path == "/api/open-library":
                    engine.open_library()
                    ok = True
                else:
                    return self._send(404, {"error": "not found"})
                return self._send(200 if ok else 409, {"ok": ok, "busy": engine.busy})
            except (ValueError, RuntimeError, OSError) as e:
                return self._send(400, {"error": str(e)})

        def do_PUT(self):  # noqa: N802
            if not self._host_ok() or not self._auth():
                return self._send(403, {"error": "forbidden"})
            u = urllib.parse.urlsplit(self.path)
            if u.path != "/api/upload":
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_UPLOAD:
                return self._send(413, {"error": "arquivo vazio ou grande demais"})
            name = (urllib.parse.parse_qs(u.query).get("name") or [""])[0]
            try:
                saved = engine.save_upload(name, self.rfile.read(n))
                return self._send(200, {"ok": True, "name": saved})
            except (ValueError, OSError) as e:
                return self._send(400, {"error": str(e)})

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    srv.daemon_threads = True
    return srv, token


def run_panel(config_path: Path, port: int = 8770, open_browser: bool = True) -> None:
    engine = Engine(config_path)
    try:
        srv, token = make_panel(engine, port)
    except OSError:
        srv, token = make_panel(engine, 0)  # porta ocupada: escolhe outra
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={token}"
    threading.Thread(target=engine.auto_loop, daemon=True).start()
    engine.emit("Painel aberto")
    print("spotifiBR Desktop rodando. Abra no navegador (link privado, não compartilhe):")
    print("  " + url)
    print("Ctrl+C para fechar.")
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop_event.set()
        engine.stop_server()
        srv.server_close()
