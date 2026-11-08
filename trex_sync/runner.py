"""Sincronização completa reaproveitável (linha de comando e painel)."""

from __future__ import annotations

import json
import time
from typing import Callable

from .config import Config
from .library import Library
from .spotify import SpotifyClient, parse_playlist_id, write_private
from .sync import PlaylistReport, State, sync_playlist, write_manifest, write_missing

SUMMARY_FILE = ".panel_summary.json"


def run_sync(cfg: Config, log: Callable[[str], None] = print) -> list[PlaylistReport]:
    if not cfg.playlists:
        raise RuntimeError("Nenhuma playlist configurada.")
    sp = SpotifyClient(cfg.spotify_client_id, cfg.token_file, cfg.redirect_uri)
    dirs = list(cfg.library_dirs) + ([cfg.download_dir] if cfg.downloader_command else [])
    log("Indexando a biblioteca local...")
    library = Library.scan([cfg.resolve(d) for d in dirs])
    log(f"{len(library.files)} arquivos de áudio encontrados")
    state = State(cfg.state_file)
    reports = []
    for ref in cfg.playlists:
        pid = parse_playlist_id(ref)
        name = sp.playlist_name(pid)
        log(f"Lendo a playlist \"{name}\" no Spotify...")
        tracks = sp.playlist_tracks(pid)
        r = sync_playlist(
            pid, name, tracks, library, state, cfg.out,
            convert=cfg.convert_to_mp3, bitrate=cfg.mp3_bitrate,
            downloader=cfg.downloader_command or None,
            download_dir=cfg.resolve(cfg.download_dir),
        )
        reports.append(r)
        log(f"[{r.name}] {len(r.entries)} de {r.total} prontas para o relógio · "
            f"{len(r.new)} novas · {len(r.missing)} sem arquivo · {len(r.removed)} removidas")
    write_missing(reports, cfg.out)
    write_manifest(reports, cfg.out)
    save_summary(cfg, reports)
    return reports


def save_summary(cfg: Config, reports: list[PlaylistReport]) -> None:
    data = {
        "time": int(time.time()),
        "playlists": [
            {
                "id": r.playlist_id, "name": r.name, "total": r.total, "ready": len(r.entries),
                "missing": [{"artist": t.artist, "title": t.title, "url": t.url} for t in r.missing],
            }
            for r in reports
        ],
    }
    cfg.out.mkdir(parents=True, exist_ok=True)
    write_private(cfg.out / SUMMARY_FILE, json.dumps(data, ensure_ascii=False))


def load_summary(cfg: Config) -> dict:
    try:
        return json.loads((cfg.out / SUMMARY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"time": 0, "playlists": []}
