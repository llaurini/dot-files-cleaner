#!/usr/bin/env python3
"""
dot-net-files-cleaner
=====================
Trova e rimuove i dot files/directory nella home che appartengono
a programmi non più installati sul sistema Debian/Ubuntu.

Uso:
    ./venv/bin/python main.py [--home /percorso/home]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="dot-net-files-cleaner",
        description="Pulizia dei dot files orfani nella home directory.",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="Percorso della home directory da scansionare (default: home dell'utente corrente)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="dot-net-files-cleaner 0.1.0",
    )
    args = parser.parse_args()

    # Verifica che la home esista
    home = args.home or Path.home()
    if not home.is_dir():
        print(
            f"Errore: la directory '{home}' non esiste o non è accessibile.",
            file=sys.stderr,
        )
        return 1

    # Avvia la TUI
    try:
        from dotcleaner.app import DotCleanerApp

        app = DotCleanerApp(home=home)
        app.run()
    except KeyboardInterrupt:
        pass
    except ImportError as e:
        print(
            f"Errore: dipendenze mancanti: {e}\n"
            "Esegui: pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
