"""CLI: python -m trex_sync [login|sync|confirmar|status]"""

from __future__ import annotations

import argparse
import sys

from .config import Config
from .library import Library
from .spotify import SpotifyClient, parse_playlist_id
from .sync import TRANSFER_DIR, State, confirm_transfer, sync_playlist, write_manifest, write_missing


def cmd_login(cfg: Config, args) -> int:
    SpotifyClient(cfg.spotify_client_id, cfg.token_file, cfg.redirect_uri).login(open_browser=not args.no_browser)
    print("Login OK. Token salvo em", cfg.token_file)
    return 0


def cmd_sync(cfg: Config, args) -> int:
    if not cfg.playlists:
        print("Nenhuma playlist em 'playlists' no config.json.")
        return 1
    sp = SpotifyClient(cfg.spotify_client_id, cfg.token_file, cfg.redirect_uri)
    dirs = list(cfg.library_dirs) + ([cfg.download_dir] if cfg.downloader_command else [])
    print("Indexando biblioteca local...")
    library = Library.scan([cfg.resolve(d) for d in dirs])
    print(f"  {len(library.files)} arquivos de áudio encontrados")
    state = State(cfg.state_file)
    reports = []
    for ref in cfg.playlists:
        pid = parse_playlist_id(ref)
        name = sp.playlist_name(pid)
        tracks = sp.playlist_tracks(pid)
        r = sync_playlist(
            pid, name, tracks, library, state, cfg.out,
            convert=cfg.convert_to_mp3, bitrate=cfg.mp3_bitrate,
            downloader=cfg.downloader_command or None,
            download_dir=cfg.resolve(cfg.download_dir),
        )
        reports.append(r)
        print(f"\n[{r.name}] {r.total} faixas | novas p/ relógio: {len(r.new)} | "
              f"sem arquivo: {len(r.missing)} | removidas: {len(r.removed)}")
        for f in r.removed:
            print(f"   - REMOVA do relógio: {f}")
    missing = write_missing(reports, cfg.out)
    write_manifest(reports, cfg.out)
    pending = sum(len(r.new) for r in reports)
    print()
    if pending:
        print(f"{pending} faixa(s) em {cfg.out / TRANSFER_DIR}")
        print("Transfira pelo app Zepp (Perfil > relógio > Música > Transferir) e depois rode:")
        print("   python -m trex_sync confirmar")
    else:
        print("Nada novo para transferir.")
    if missing:
        print(f"Faixas sem arquivo local listadas em {missing}")
    return 0


def cmd_confirm(cfg: Config, args) -> int:
    n = confirm_transfer(State(cfg.state_file), cfg.out)
    print(f"{n} faixa(s) marcadas como transferidas.")
    return 0


def cmd_serve(cfg: Config, args) -> int:
    from .server import serve

    if args.sync:
        rc = cmd_sync(cfg, args)
        if rc:
            return rc
    serve(cfg.out, args.port or cfg.server_port, cfg.server_token)
    return 0


def cmd_status(cfg: Config, args) -> int:
    state = State(cfg.state_file)
    if not state.data["playlists"]:
        print("Nenhuma sincronização feita ainda.")
    for pl in state.data["playlists"].values():
        print(f"[{pl['name']}] no relógio: {len(pl['transferred'])} | pendentes: {len(pl['pending'])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="trex_sync", description="Playlists do Spotify -> MP3 para Amazfit T-Rex 3")
    ap.add_argument("-c", "--config", default="config.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("login", help="autoriza acesso às suas playlists do Spotify")
    lg.add_argument("--no-browser", action="store_true")
    sub.add_parser("sync", help="gera a pasta com as músicas novas de cada playlist")
    sub.add_parser("confirmar", help="marca as pendentes como já transferidas para o relógio")
    sub.add_parser("status", help="mostra o estado por playlist")
    sv = sub.add_parser("servir", help="serve as músicas para o app T-Rex Music do relógio")
    sv.add_argument("--port", type=int, default=0)
    sv.add_argument("--sync", action="store_true", help="roda o sync antes de servir")
    args = ap.parse_args(argv)
    try:
        cfg = Config.load(args.config)
        return {"login": cmd_login, "sync": cmd_sync, "confirmar": cmd_confirm, "status": cmd_status, "servir": cmd_serve}[args.cmd](cfg, args)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print("Erro:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
