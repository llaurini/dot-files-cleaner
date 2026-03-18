#!/usr/bin/env python3
"""CLI entrypoint for dot-net-files-cleaner.

Finds and removes dot files and directories in the home directory that
belong to programs no longer installed on the Debian/Ubuntu system.

Example:
    ./venv/bin/python main.py [--home /path/to/home]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    """Parse CLI arguments and launch the TUI application.

    Validates the home directory, then starts the Textual TUI.  Handles
    missing dependencies gracefully by printing an actionable error message.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
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
