"""Cliente mínimo da Spotify Web API (OAuth Authorization Code + PKCE, só stdlib)."""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
SCOPES = "playlist-read-private playlist-read-collaborative user-library-read"
LIKED = "liked"  # id especial para "Músicas Curtidas"
# Escopos mínimos e SOMENTE LEITURA: mesmo que o token vaze, não dá para alterar a conta,
# playlists, senha ou e-mail.
_ID = re.compile(r"^[A-Za-z0-9]{1,64}$")
_LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}


def write_private(path: Path, text: str) -> None:
    """Grava arquivo com permissão 0600 (só o dono lê), de forma atômica."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    artists: tuple[str, ...]
    album: str
    duration_ms: int
    url: str
    isrc: str = ""       # código único da gravação: identifica a versão exata
    year: str = ""

    @property
    def artist(self) -> str:
        return self.artists[0] if self.artists else ""

    @property
    def display(self) -> str:
        return f"{', '.join(self.artists)} - {self.title}"


def parse_playlist_id(ref: str) -> str:
    """Aceita link, URI spotify:playlist:..., id puro ou 'liked'."""
    ref = ref.strip()
    if ref.lower() in (LIKED, "curtidas"):
        return LIKED
    if ref.startswith("spotify:playlist:"):
        pid = ref.split(":")[-1]
    elif "open.spotify.com" in ref:
        u = urllib.parse.urlparse(ref)
        path = u.path.rstrip("/").split("/")
        if u.hostname != "open.spotify.com" or "playlist" not in path or path.index("playlist") + 1 >= len(path):
            raise ValueError(f"Link não é de playlist do Spotify: {ref}")
        pid = path[path.index("playlist") + 1]
    else:
        pid = ref
    if not _ID.match(pid):
        raise ValueError(f"ID de playlist inválido: {ref}")
    return pid


def track_from_json(obj: dict | None) -> Track | None:
    """Converte um item da API em Track; ignora episódios, arquivos locais e faixas removidas."""
    if not obj or obj.get("type", "track") != "track" or obj.get("is_local") or not obj.get("id"):
        return None
    if not _ID.match(str(obj["id"])):
        return None
    return Track(
        id=obj["id"],
        title=obj.get("name", ""),
        artists=tuple(a.get("name", "") for a in obj.get("artists", [])),
        album=(obj.get("album") or {}).get("name", ""),
        duration_ms=int(obj.get("duration_ms") or 0),
        url=f"https://open.spotify.com/track/{obj['id']}",
        isrc=_clean_code((obj.get("external_ids") or {}).get("isrc", "")),
        year=str((obj.get("album") or {}).get("release_date") or "")[:4],
    )


def _clean_code(value) -> str:
    v = str(value or "").strip().upper()
    return v if re.fullmatch(r"[A-Z0-9]{12}", v) else ""


class SpotifyClient:
    def __init__(self, client_id: str, token_file: Path, redirect_uri: str = "http://127.0.0.1:8888/callback"):
        if not client_id:
            raise ValueError("Defina 'spotify_client_id' no config.json")
        u = urllib.parse.urlparse(redirect_uri)
        if u.scheme != "http" or u.hostname not in _LOOPBACK:
            # o código de autorização só pode voltar para esta máquina
            raise ValueError("redirect_uri deve ser http://127.0.0.1:<porta>/... (loopback)")
        self.client_id = client_id
        self.token_file = Path(token_file)
        self.redirect_uri = redirect_uri
        self._token: dict | None = None

    # ---------- autenticação ----------
    def login(self, open_browser: bool = True) -> None:
        verifier = secrets.token_urlsafe(64)[:128]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "scope": SCOPES,
            "state": state,
        }
        url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
        code = self._wait_for_code(url, state, open_browser)
        tok = self._post_token({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": verifier,
        })
        self._save(tok)

    def _wait_for_code(self, url: str, state: str, open_browser: bool) -> str:
        parsed = urllib.parse.urlparse(self.redirect_uri)
        result: dict[str, str] = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                result.update({k: v[0] for k, v in q.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<h2>Pronto! Pode fechar esta aba e voltar ao terminal.</h2>".encode())

            def log_message(self, *args):
                pass

        host = "127.0.0.1" if parsed.hostname in ("localhost", None) else parsed.hostname.strip("[]")
        server = http.server.HTTPServer((host, parsed.port or 8888), Handler)
        server.timeout = 300
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        print("Abra este link para autorizar o acesso às suas playlists:\n" + url)
        if open_browser:
            webbrowser.open(url)
        thread.join(timeout=300)
        server.server_close()
        if not secrets.compare_digest(str(result.get("state", "")), state):
            raise RuntimeError("Login falhou ou expirou (state inválido).")
        if "error" in result:
            raise RuntimeError(f"Spotify recusou o login: {result['error']}")
        return result["code"]

    def _post_token(self, data: dict) -> dict:
        req = urllib.request.Request(
            TOKEN_URL,
            data=urllib.parse.urlencode(data).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            tok = json.load(r)
        tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
        return tok

    def _save(self, tok: dict) -> None:
        old = self._load() or {}
        tok.setdefault("refresh_token", old.get("refresh_token"))
        write_private(self.token_file, json.dumps(tok, indent=2))
        self._token = tok

    def _load(self) -> dict | None:
        if self._token is None and self.token_file.exists():
            try:
                os.chmod(self.token_file, 0o600)  # corrige arquivos antigos com permissão aberta
            except OSError:
                pass
            self._token = json.loads(self.token_file.read_text())
        return self._token

    def access_token(self) -> str:
        tok = self._load()
        if not tok:
            raise RuntimeError("Não autenticado. Rode: python -m trex_sync login")
        if time.time() >= tok.get("expires_at", 0):
            self._save(self._post_token({
                "grant_type": "refresh_token",
                "refresh_token": tok["refresh_token"],
                "client_id": self.client_id,
            }))
        return self._token["access_token"]

    # ---------- API ----------
    def get(self, path_or_url: str, params: dict | None = None) -> dict:
        url = path_or_url if path_or_url.startswith("http") else API + path_or_url
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        for attempt in range(5):
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.access_token()}"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 429:  # rate limit
                    time.sleep(int(e.headers.get("Retry-After", "2")) + 1)
                    continue
                if e.code == 401 and attempt == 0:
                    self._token["expires_at"] = 0
                    continue
                raise
        raise RuntimeError(f"Falha repetida ao chamar {url}")

    def playlist_name(self, pid: str) -> str:
        if pid == LIKED:
            return "Musicas Curtidas"
        return self.get(f"/playlists/{pid}", {"fields": "name"})["name"]

    def playlist_tracks(self, pid: str) -> list[Track]:
        if pid == LIKED:
            return self._paged("/me/tracks", {"limit": 50})
        try:  # endpoint novo (/items); cai para o antigo (/tracks) se não existir
            return self._paged(f"/playlists/{pid}/items", {"limit": 50})
        except urllib.error.HTTPError as e:
            if e.code not in (403, 404):
                raise
            return self._paged(f"/playlists/{pid}/tracks", {"limit": 50})

    def _paged(self, path: str, params: dict) -> list[Track]:
        out: list[Track] = []
        page = self.get(path, params)
        while True:
            for it in page.get("items", []):
                t = track_from_json(it.get("item") or it.get("track"))
                if t:
                    out.append(t)
            if not page.get("next"):
                return out
            page = self.get(page["next"])
