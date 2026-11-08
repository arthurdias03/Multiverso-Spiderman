from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    spotify_client_id: str = ""
    redirect_uri: str = "http://127.0.0.1:8888/callback"
    playlists: list[str] = field(default_factory=list)
    library_dirs: list[str] = field(default_factory=list)
    output_dir: str = "saida"
    convert_to_mp3: bool = True
    mp3_bitrate: str = "128k"
    downloader_command: list[str] = field(default_factory=list)
    download_dir: str = "downloads"
    server_port: int = 8765
    server_token: str = ""
    base: Path = Path(".")

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"{path} não existe. Copie config.example.json para {path.name} e edite.")
        raw = json.loads(path.read_text(encoding="utf-8"))
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__ and not k.startswith("_")}
        cfg = cls(**known)
        cfg.base = path.resolve().parent
        return cfg

    def resolve(self, p: str) -> Path:
        q = Path(p).expanduser()
        return q if q.is_absolute() else self.base / q

    @property
    def out(self) -> Path:
        return self.resolve(self.output_dir)

    @property
    def state_file(self) -> Path:
        return self.out / ".trex_state.json"

    @property
    def token_file(self) -> Path:
        return self.base / ".spotify_token.json"
