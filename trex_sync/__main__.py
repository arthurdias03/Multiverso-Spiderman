"""CLI: python -m trex_sync [login|sync|confirmar|status]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .spotify import SpotifyClient
from .sync import TRANSFER_DIR, State, confirm_transfer


def cmd_login(cfg: Config, args) -> int:
    SpotifyClient(cfg.spotify_client_id, cfg.token_file, cfg.redirect_uri).login(open_browser=not args.no_browser)
    print("Login OK. Token salvo em", cfg.token_file)
    return 0


def cmd_sync(cfg: Config, args) -> int:
    from .runner import run_sync

    reports = run_sync(cfg)
    pending = sum(len(r.new) for r in reports)
    missing = sum(len(r.missing) for r in reports)
    print()
    print(f"{pending} faixa(s) nova(s) prontas em {cfg.out / TRANSFER_DIR}" if pending else "Nada novo.")
    if missing:
        print(f"{missing} faixa(s) sem arquivo local: veja {cfg.out / '_FALTANDO.txt'}")
    return 0


def cmd_confirm(cfg: Config, args) -> int:
    n = confirm_transfer(State(cfg.state_file), cfg.out)
    print(f"{n} faixa(s) marcadas como transferidas.")
    return 0


def cmd_serve(cfg: Config, args) -> int:
    from .server import load_or_create_token, serve

    if args.sync:
        rc = cmd_sync(cfg, args)
        if rc:
            return rc
    token = load_or_create_token(cfg.server_token, cfg.server_token_file)
    serve(cfg.out, args.port or cfg.server_port, token, bind=cfg.server_bind,
          allow_public=cfg.allow_public_clients,
          tls_cert=str(cfg.resolve(cfg.tls_cert)) if cfg.tls_cert else "",
          tls_key=str(cfg.resolve(cfg.tls_key)) if cfg.tls_key else "")
    return 0


def cmd_new_token(cfg: Config, args) -> int:
    from .server import rotate_token

    if cfg.server_token:
        print("server_token está fixo no config.json; apague-o de lá para usar token automático.")
        return 1
    print("Novo token (atualize no app Zepp):", rotate_token(cfg.server_token_file))
    return 0


def cmd_panel(cfg_path: str, args) -> int:
    from .panel import run_panel

    run_panel(Path(cfg_path), port=args.port, open_browser=not args.no_browser)
    return 0


def ensure_config(path: Path) -> None:
    """Cria um config.json inicial (vazio) para o painel poder ser configurado pela interface."""
    if path.exists():
        return
    example = Path(__file__).resolve().parent.parent / "config.example.json"
    data = json.loads(example.read_text(encoding="utf-8")) if example.exists() else {}
    data.update({"spotify_client_id": "", "playlists": [], "library_dirs": [str(Path.home() / "Music")]})
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Criei {path} (configure pelo painel).")


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
    sv = sub.add_parser("servir", help="serve as músicas para o app spotifiBR do relógio")
    sv.add_argument("--port", type=int, default=0)
    sv.add_argument("--sync", action="store_true", help="roda o sync antes de servir")
    sub.add_parser("novo-token", help="gera um novo token do servidor (invalida o antigo)")
    pn = sub.add_parser("painel", help="abre o spotifiBR Desktop (painel no navegador)")
    pn.add_argument("--port", type=int, default=8770)
    pn.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "painel":
        try:
            ensure_config(Path(args.config))
            return cmd_panel(args.config, args)
        except (ValueError, RuntimeError, OSError) as e:
            print("Erro:", e, file=sys.stderr)
            return 2
    try:
        cfg = Config.load(args.config)
        return {"login": cmd_login, "sync": cmd_sync, "confirmar": cmd_confirm, "status": cmd_status, "servir": cmd_serve, "novo-token": cmd_new_token}[args.cmd](cfg, args)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as e:
        print("Erro:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
