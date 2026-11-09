"""Comando `spotifibr`: sem argumentos abre o painel; com argumentos funciona como a linha de comando.

Exemplos: `spotifibr` (painel) · `spotifibr links` · `spotifibr servir --sync`
"""

import sys

from .__main__ import main as _main


def main() -> int:
    args = sys.argv[1:]
    return _main(args if args else ["painel"])
