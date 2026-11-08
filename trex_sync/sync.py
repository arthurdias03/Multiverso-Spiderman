"""Lógica de sincronização: diferença entre playlist e o que já está no relógio."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .library import Library
from .spotify import Track

TRANSFER_DIR = "_PARA_TRANSFERIR"
MISSING_FILE = "_FALTANDO.txt"


def safe_name(text: str, limit: int = 120) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip().rstrip(".")
    return (text or "sem nome")[:limit]


def file_name_for(track: Track) -> str:
    return safe_name(f"{track.artist} - {track.title}") + ".mp3"


class State:
    """Estado persistente: o que já foi transferido e o que está pendente, por playlist."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict = {"playlists": {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def playlist(self, pid: str) -> dict:
        pl = self.data["playlists"].setdefault(pid, {})
        pl.setdefault("name", pid)
        pl.setdefault("transferred", {})
        pl.setdefault("pending", {})
        return pl

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


@dataclass
class PlaylistReport:
    name: str
    total: int = 0
    new: list[str] = field(default_factory=list)
    missing: list[Track] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def export_audio(src: Path, dst: Path, convert: bool, bitrate: str) -> Path:
    """Copia (ou converte para MP3) e devolve o caminho efetivamente gravado."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() != ".mp3" and not convert:
        dst = dst.with_suffix(src.suffix.lower())
    if dst.exists():
        return dst
    if src.suffix.lower() == ".mp3" or not convert:
        shutil.copy2(src, dst)
        return dst
    if not shutil.which("ffmpeg"):
        raise RuntimeError(f"ffmpeg não encontrado para converter {src.name} em MP3")
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-codec:a", "libmp3lame",
         "-b:a", bitrate, "-map_metadata", "0", "-id3v2_version", "3", str(dst)],
        check=True,
    )
    return dst


def run_downloader(cmd_template: list[str], track: Track, out_dir: Path) -> None:
    """Executa o comando externo configurado pelo usuário para obter uma faixa ausente."""
    out_dir.mkdir(parents=True, exist_ok=True)
    values = {"url": track.url, "dir": str(out_dir), "artist": track.artist, "title": track.title}
    # substitui só os marcadores conhecidos; outros (ex.: {output-ext} do spotDL) ficam intactos
    pattern = re.compile(r"\{(" + "|".join(values) + r")\}")
    cmd = [pattern.sub(lambda m: values[m.group(1)], part) for part in cmd_template]
    subprocess.run(cmd, check=False)


def sync_playlist(
    pid: str,
    name: str,
    tracks: list[Track],
    library: Library,
    state: State,
    out_root: Path,
    convert: bool = True,
    bitrate: str = "192k",
    downloader: list[str] | None = None,
    download_dir: Path | None = None,
) -> PlaylistReport:
    pl = state.playlist(pid)
    pl["name"] = name
    folder = safe_name(name)
    mirror = out_root / folder
    transfer = out_root / TRANSFER_DIR / folder
    report = PlaylistReport(name=name, total=len(tracks))

    # Remove duplicatas mantendo a ordem da playlist
    seen: set[str] = set()
    tracks = [t for t in tracks if not (t.id in seen or seen.add(t.id))]
    current_ids = {t.id for t in tracks}

    for t in tracks:
        if t.id in pl["transferred"]:
            continue
        fname = pl["pending"].get(t.id) or file_name_for(t)
        if (mirror / fname).exists() and t.id in pl["pending"]:
            report.new.append(fname)
            continue
        src = library.find(t)
        if src is None and downloader and download_dir:
            run_downloader(downloader, t, download_dir)
            library = Library(library.files + Library.scan([download_dir]).files)
            src = library.find(t)
        if src is None:
            report.missing.append(t)
            continue
        exported = export_audio(src.path, mirror / fname, convert, bitrate)
        transfer.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exported, transfer / exported.name)
        pl["pending"][t.id] = exported.name
        report.new.append(exported.name)

    # Faixas que saíram da playlist: avisar para remover do relógio e limpar o espelho
    for tid in [tid for tid in pl["transferred"] if tid not in current_ids]:
        fname = pl["transferred"].pop(tid)
        (mirror / fname).unlink(missing_ok=True)
        report.removed.append(fname)
    for tid in [tid for tid in pl["pending"] if tid not in current_ids]:
        fname = pl["pending"].pop(tid)
        (mirror / fname).unlink(missing_ok=True)
        (transfer / fname).unlink(missing_ok=True)

    state.save()
    return report


def confirm_transfer(state: State, out_root: Path) -> int:
    """Marca todas as faixas pendentes como já transferidas e esvazia a pasta de transferência."""
    count = 0
    for pl in state.data["playlists"].values():
        pl.setdefault("transferred", {}).update(pl.get("pending", {}))
        count += len(pl.get("pending", {}))
        pl["pending"] = {}
    shutil.rmtree(out_root / TRANSFER_DIR, ignore_errors=True)
    state.save()
    return count


def write_missing(reports: list[PlaylistReport], out_root: Path) -> Path | None:
    path = out_root / MISSING_FILE
    lines = []
    for r in reports:
        for t in r.missing:
            lines.append(f"[{r.name}] {t.display}  ->  {t.url}")
    if not lines:
        path.unlink(missing_ok=True)
        return None
    out_root.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
