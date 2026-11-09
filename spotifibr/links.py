"""Listas de links para ouvir/conferir cada música (sem baixar nada).

Para cada faixa: link exato no Spotify, song.link (a MESMA gravação em Apple Music, YouTube Music,
Deezer, Amazon…), dados para conferir a versão (álbum, ano, duração, ISRC) e buscas prontas.
"""

from __future__ import annotations

import csv
import time
import urllib.parse
from pathlib import Path

from .spotify import Track


def duration(ms: int) -> str:
    s = int(ms or 0) // 1000
    return f"{s // 60}:{s % 60:02d}" if s else "?"


def links_for(t: Track) -> dict[str, str]:
    q = urllib.parse.quote(f"{t.artist} {t.title}")
    return {
        "spotify": t.url,
        "todas_plataformas": f"https://song.link/s/{t.id}",
        "apple_music": f"https://music.apple.com/br/search?term={q}",
        "bandcamp": f"https://bandcamp.com/search?q={q}",
        "youtube_music": f"https://music.youtube.com/search?q={q}",
    }


def _block(i: int, t: Track) -> str:
    lk = links_for(t)
    info = [f"Álbum: {t.album or '?'}" + (f" ({t.year})" if t.year else ""), duration(t.duration_ms)]
    if t.isrc:
        info.append(f"ISRC: {t.isrc}")
    return (
        f"{i}. {', '.join(t.artists) or '?'} – {t.title}\n"
        f"   {' · '.join(info)}\n"
        f"   Spotify (versão exata) ......: {lk['spotify']}\n"
        f"   Mesma gravação em outros apps: {lk['todas_plataformas']}\n"
        f"   Buscar no Apple Music .......: {lk['apple_music']}\n"
        f"   Buscar no Bandcamp ..........: {lk['bandcamp']}\n"
        f"   Buscar no YouTube Music .....: {lk['youtube_music']}\n"
    )


def write_links(groups: list[tuple[str, list[Track]]], txt_path: Path, title: str) -> tuple[Path, Path] | None:
    """groups = [(nome da playlist, [faixas])]. Gera .txt (leitura) e .csv (planilha)."""
    total = sum(len(ts) for _, ts in groups)
    csv_path = txt_path.with_suffix(".csv")
    if not total:
        txt_path.unlink(missing_ok=True)
        csv_path.unlink(missing_ok=True)
        return None
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    head = (
        f"spotifiBR · {title}\n"
        f"Gerado em {time.strftime('%d/%m/%Y %H:%M')} · {total} música(s)\n"
        "Dica: abra o link do Spotify para ouvir a versão exata e confira álbum, ano, duração e ISRC\n"
        "na loja antes de comprar. O link 'Mesma gravação' abre essa versão em outros apps.\n"
    )
    parts = [head]
    for name, tracks in groups:
        if not tracks:
            continue
        parts.append(f"\n== {name} ({len(tracks)}) ==\n")
        parts.extend("\n" + _block(i, t) for i, t in enumerate(tracks, 1))
    txt_path.write_text("".join(parts), encoding="utf-8")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: abre certo no Excel
        w = csv.writer(f, delimiter=";")
        w.writerow(["playlist", "artistas", "musica", "album", "ano", "duracao", "isrc",
                    "spotify", "mesma_gravacao", "apple_music", "bandcamp", "youtube_music"])
        for name, tracks in groups:
            for t in tracks:
                lk = links_for(t)
                w.writerow([name, ", ".join(t.artists), t.title, t.album, t.year, duration(t.duration_ms), t.isrc,
                            lk["spotify"], lk["todas_plataformas"], lk["apple_music"], lk["bandcamp"], lk["youtube_music"]])
    return txt_path, csv_path
