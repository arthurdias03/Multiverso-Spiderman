"""Atalho: `spotifibr` abre o painel (equivale a `python -m trex_sync painel`)."""

import sys

from .__main__ import main as _main


def main() -> int:
    return _main(["painel", *sys.argv[1:]])
