"""Indexa arquivos de áudio locais e casa faixas do Spotify com eles."""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .spotify import Track

AUDIO_EXT = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wav"}
MATCH_THRESHOLD = 0.86

_NOISE = re.compile(
    r"\s*[\(\[][^)\]]*(feat\.?|ft\.?|with|remaster(ed)?|ao vivo|live|radio edit|version|versão|explicit)[^)\]]*[\)\]]"
    r"|\s+-\s+.*(remaster(ed)?|live|ao vivo|radio edit|version|versão|mono|stereo).*$",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    text = _NOISE.sub("", text or "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"\b(feat|ft)\.?\b.*$", "", text.lower())
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def key(artist: str, title: str) -> str:
    return f"{normalize(artist)} | {normalize(title)}"


@dataclass(frozen=True)
class LocalFile:
    path: Path
    artist: str
    title: str

    @property
    def key(self) -> str:
        return key(self.artist, self.title)


def read_tags(path: Path) -> tuple[str, str]:
    """Lê artista/título das tags (se mutagen estiver instalado) ou do nome 'Artista - Título'."""
    try:
        import mutagen  # type: ignore

        f = mutagen.File(path, easy=True)
        if f and f.tags:
            artist = (f.tags.get("artist") or [""])[0]
            title = (f.tags.get("title") or [""])[0]
            if artist and title:
                return artist, title
    except Exception:
        pass
    stem = re.sub(r"^\d+[\s.\-_]+", "", path.stem)  # remove número de faixa
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return path.parent.name, stem


class Library:
    def __init__(self, files: list[LocalFile]):
        self.files = files
        self.by_key: dict[str, LocalFile] = {}
        for f in files:
            self.by_key.setdefault(f.key, f)
        self._keys = list(self.by_key)

    @classmethod
    def scan(cls, dirs: list[str | Path]) -> "Library":
        files = []
        for d in dirs:
            d = Path(d).expanduser()
            if not d.exists():
                continue
            for p in sorted(d.rglob("*")):
                if p.is_file() and p.suffix.lower() in AUDIO_EXT:
                    files.append(LocalFile(p, *read_tags(p)))
        return cls(files)

    def find(self, track: Track) -> LocalFile | None:
        # 1) exato por qualquer artista creditado
        for a in track.artists or ("",):
            hit = self.by_key.get(key(a, track.title))
            if hit:
                return hit
        # 2) aproximado (grafia diferente, acentos, etc.)
        target = key(track.artist, track.title)
        best = difflib.get_close_matches(target, self._keys, n=1, cutoff=MATCH_THRESHOLD)
        if best:
            return self.by_key[best[0]]
        # 3) título idêntico + artista contido (ex.: "Artista X e Y")
        t_title = normalize(track.title)
        t_art = normalize(track.artist)
        for f in self.files:
            if normalize(f.title) == t_title and t_art and t_art in normalize(f.artist):
                return f
        return None
