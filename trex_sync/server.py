"""Servidor HTTP que entrega manifest.json e os MP3 para o app do relógio (via app Zepp no celular)."""

from __future__ import annotations

import functools
import hmac
import http.server
import socket
import urllib.parse
from pathlib import Path


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # não envia nada; só descobre a interface de saída
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class Handler(http.server.SimpleHTTPRequestHandler):
    token = ""

    def _authorized(self) -> bool:
        if not self.token:
            return True
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        given = (q.get("k") or [""])[0] or self.headers.get("X-Trex-Token", "")
        return hmac.compare_digest(given, self.token)

    def _blocked(self) -> bool:
        parts = urllib.parse.unquote(urllib.parse.urlparse(self.path).path).split("/")
        return any(p.startswith(".") for p in parts if p)  # esconde estado/tokens

    def do_GET(self):  # noqa: N802
        if self._blocked():
            self.send_error(404)
        elif not self._authorized():
            self.send_error(401, "token inválido")
        else:
            super().do_GET()

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def end_headers(self):
        if self.path.split("?")[0].endswith("manifest.json"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        print("  " + fmt % args)


def make_server(directory: Path, port: int, token: str) -> http.server.ThreadingHTTPServer:
    handler = type("TrexHandler", (Handler,), {"token": token})
    return http.server.ThreadingHTTPServer(("0.0.0.0", port), functools.partial(handler, directory=str(directory)))


def serve(directory: Path, port: int, token: str) -> None:
    directory = Path(directory)
    if not (directory / "manifest.json").exists():
        raise RuntimeError("manifest.json não existe. Rode 'python -m trex_sync sync' antes.")
    srv = make_server(directory, port, token)
    print(f"Servindo {directory} em http://{lan_ip()}:{port}")
    print("No app Zepp > T-Rex Music > Configurações, use:")
    print(f"   Endereço: http://{lan_ip()}:{port}")
    print(f"   Token:    {token or '(sem token)'}")
    print("Ctrl+C para parar.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
