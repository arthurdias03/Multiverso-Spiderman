"""Servidor HTTP(S) que entrega manifest.json e os MP3 ao app do relógio (via app Zepp no celular).

Modelo de ameaça e defesas:
- Outros aparelhos na mesma rede: token obrigatório (256 bits) enviado SÓ no cabeçalho
  X-Trex-Token (nunca na URL, que acaba em logs), comparação em tempo constante e bloqueio
  por IP após tentativas erradas.
- Vazamento de arquivos do PC: serve SOMENTE manifest.json e os arquivos listados nele
  (allowlist), confere o caminho real (sem symlink saindo da pasta) e não lista diretórios.
- Exposição à internet: escuta só na interface da rede local por padrão e recusa clientes com IP
  público, a menos que você libere explicitamente.
- Escuta na rede (Wi-Fi público/compartilhado): use TLS (tls_cert/tls_key) ou Tailscale.
"""

from __future__ import annotations

import hmac
import http.server
import ipaddress
import json
import os
import secrets
import socket
import ssl
import threading
import time
import urllib.parse
from pathlib import Path

TOKEN_HEADER = "X-Trex-Token"
MIN_TOKEN_LEN = 32
PLACEHOLDER_TOKENS = {"", "TROQUE-POR-UMA-SENHA-LONGA"}
MAX_FAILS = 10
FAIL_WINDOW = 600  # s
LOCKOUT = 900  # s
_CGNAT = ipaddress.ip_network("100.64.0.0/10")  # faixa usada pelo Tailscale


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # não envia nada; só descobre a interface de saída
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def is_local_client(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if getattr(addr, "ipv4_mapped", None):
        addr = addr.ipv4_mapped
    return addr.is_loopback or addr.is_private or addr.is_link_local or (addr.version == 4 and addr in _CGNAT)


def load_or_create_token(configured: str, token_file: Path) -> str:
    """Usa o token do config se for forte; senão gera um aleatório e guarda com permissão 0600."""
    from .spotify import write_private

    configured = (configured or "").strip()
    if configured not in PLACEHOLDER_TOKENS:
        if len(configured) < MIN_TOKEN_LEN:
            raise RuntimeError(f"server_token precisa ter pelo menos {MIN_TOKEN_LEN} caracteres "
                               "(ou deixe vazio para gerar um automaticamente).")
        return configured
    token_file = Path(token_file)
    if token_file.exists():
        tok = token_file.read_text(encoding="utf-8").strip()
        if len(tok) >= MIN_TOKEN_LEN:
            os.chmod(token_file, 0o600)
            return tok
    tok = secrets.token_urlsafe(32)
    write_private(token_file, tok)
    return tok


def rotate_token(token_file: Path) -> str:
    from .spotify import write_private

    tok = secrets.token_urlsafe(32)
    write_private(Path(token_file), tok)
    return tok


class Allowlist:
    """Caminhos servíveis = os listados no manifest.json (recarrega quando o arquivo muda)."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self._mtime = -1.0
        self._paths: set[str] = set()
        self._lock = threading.Lock()

    def paths(self) -> set[str]:
        mf = self.root / "manifest.json"
        try:
            mtime = mf.stat().st_mtime
        except OSError:
            return set()
        with self._lock:
            if mtime != self._mtime:
                data = json.loads(mf.read_text(encoding="utf-8"))
                self._paths = {t["p"] for pl in data.get("playlists", []) for t in pl.get("tracks", [])
                               if isinstance(t.get("p"), str)}
                self._mtime = mtime
            return self._paths

    def resolve(self, rel: str) -> Path | None:
        if rel == "manifest.json":
            target = self.root / rel
        elif rel in self.paths():
            target = self.root / rel
        else:
            return None
        real = target.resolve()
        if self.root not in real.parents or not real.is_file():
            return None  # symlink apontando para fora, ou arquivo sumiu
        return real


class Guard:
    """Conta falhas de autenticação por IP e bloqueia temporariamente (anti força bruta)."""

    def __init__(self):
        self.fails: dict[str, list[float]] = {}
        self.blocked: dict[str, float] = {}
        self.lock = threading.Lock()

    def is_blocked(self, ip: str) -> bool:
        with self.lock:
            until = self.blocked.get(ip, 0)
            if until and time.monotonic() < until:
                return True
            self.blocked.pop(ip, None)
            return False

    def fail(self, ip: str) -> None:
        now = time.monotonic()
        with self.lock:
            lst = [t for t in self.fails.get(ip, []) if now - t < FAIL_WINDOW] + [now]
            self.fails[ip] = lst
            if len(lst) >= MAX_FAILS:
                self.blocked[ip] = now + LOCKOUT
                self.fails[ip] = []

    def ok(self, ip: str) -> None:
        with self.lock:
            self.fails.pop(ip, None)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "spotifiBR"
    sys_version = ""
    timeout = 30  # evita conexões penduradas (slowloris)
    token: bytes = b""
    allow: Allowlist
    guard: Guard
    allow_public: bool = False

    # ---- utilidades ----
    def _send(self, code: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8", head=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body and not head:
            self.wfile.write(body)

    def _authorized(self) -> bool:
        given = self.headers.get(TOKEN_HEADER, "").encode("utf-8", "ignore")
        return bool(self.token) and hmac.compare_digest(given, self.token)

    def _handle(self, head: bool):
        ip = self.client_address[0]
        if not self.allow_public and not is_local_client(ip):
            return self._send(403, b"forbidden", head=head)
        if self.guard.is_blocked(ip):
            return self._send(429, b"too many attempts", head=head)
        if not self._authorized():
            self.guard.fail(ip)
            return self._send(401, b"unauthorized", head=head)
        self.guard.ok(ip)

        raw = urllib.parse.urlsplit(self.path).path
        rel = urllib.parse.unquote(raw).lstrip("/")
        if "\x00" in rel or any(part in ("", ".", "..") for part in rel.split("/")):
            return self._send(404, b"not found", head=head)
        target = self.allow.resolve(rel)
        if target is None:
            return self._send(404, b"not found", head=head)

        ctype = "application/json" if rel == "manifest.json" else "audio/mpeg"
        size = target.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store" if rel == "manifest.json" else "private, max-age=0")
        self.end_headers()
        if head:
            return
        with open(target, "rb") as f:
            while chunk := f.read(64 * 1024):
                self.wfile.write(chunk)

    def do_GET(self):  # noqa: N802
        self._handle(head=False)

    def do_HEAD(self):  # noqa: N802
        self._handle(head=True)

    def _deny(self):
        self._send(405, b"method not allowed")

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _deny  # noqa: N815

    def log_message(self, fmt, *args):
        pass  # não loga request line (poderia conter dados); usamos log_request abaixo

    def log_request(self, code="-", size="-"):
        path = urllib.parse.urlsplit(getattr(self, "path", "")).path  # sem query string
        print(f"  {self.client_address[0]} {getattr(self, 'command', '-')} {path[:120]} {code}")


def make_server(directory: Path, port: int, token: str, bind: str = "127.0.0.1",
                allow_public: bool = False, tls_cert: str = "", tls_key: str = ""):
    if len(token or "") < MIN_TOKEN_LEN:
        raise RuntimeError("token ausente ou fraco")
    handler = type("TrexHandler", (Handler,), {
        "token": token.encode("utf-8"),
        "allow": Allowlist(directory),
        "guard": Guard(),
        "allow_public": allow_public,
    })
    srv = http.server.ThreadingHTTPServer((bind, port), handler)
    srv.daemon_threads = True
    if tls_cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(tls_cert, tls_key or None)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    return srv


def serve(directory: Path, port: int, token: str, bind: str = "auto", allow_public: bool = False,
          tls_cert: str = "", tls_key: str = "") -> None:
    directory = Path(directory)
    if not (directory / "manifest.json").exists():
        raise RuntimeError("manifest.json não existe. Rode 'python -m spotifibr sync' antes.")
    host = lan_ip() if bind == "auto" else bind
    if host in ("0.0.0.0", "::"):
        print("AVISO: escutando em todas as interfaces. Prefira server_bind \"auto\".")
    srv = make_server(directory, port, token, host, allow_public, tls_cert, tls_key)
    scheme = "https" if tls_cert else "http"
    shown = lan_ip() if host in ("0.0.0.0", "::") else host
    print(f"Servindo {directory} em {scheme}://{shown}:{port}  (só manifest.json e as músicas dele)")
    print("No app Zepp > spotifiBR > Configurações, use:")
    print(f"   Endereço: {scheme}://{shown}:{port}")
    print(f"   Token:    {token}")
    print("Não compartilhe o token. Para trocar: python -m spotifibr novo-token")
    if scheme == "http":
        print("Sem TLS: use só na sua rede de casa (nunca em Wi-Fi público).")
    print("Ctrl+C para parar.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
