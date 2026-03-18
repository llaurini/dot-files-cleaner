"""
cleaner.py - Spostamento di dot files/directory nel cestino FreeDesktop.

Usa send2trash per rispettare le specifiche XDG Trash (~/.local/share/Trash).
Il cestino è recuperabile tramite qualsiasi file manager (Nautilus, Dolphin, ecc.)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from send2trash import send2trash as _send2trash  # type: ignore[import]
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False
    _send2trash = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from dotcleaner.scanner import DotEntry


class CleanError(Exception):
    """Errore durante l'eliminazione di un dot entry."""
    pass


def trash_entry(entry: DotEntry) -> None:
    """
    Sposta un DotEntry nel cestino FreeDesktop (~/.local/share/Trash).

    Args:
        entry: Il DotEntry da spostare nel cestino.

    Raises:
        CleanError: Se l'operazione fallisce.
    """
    path = entry.path

    if not path.exists() and not path.is_symlink():
        raise CleanError(f"Il percorso non esiste: {path}")

    if not HAS_SEND2TRASH:
        raise CleanError(
            "La libreria 'send2trash' non è installata. "
            "Esegui: pip install send2trash"
        )

    try:
        _send2trash(str(path))  # type: ignore[misc]
    except Exception as e:
        raise CleanError(f"Impossibile spostare nel cestino '{path}': {e}") from e


def trash_entries(entries: list[DotEntry]) -> dict[str, str | None]:
    """
    Sposta una lista di DotEntry nel cestino.

    Args:
        entries: Lista di DotEntry da spostare.

    Returns:
        Dizionario {path_str: error_message | None}
        dove None indica successo.
    """
    results: dict[str, str | None] = {}

    for entry in entries:
        path_str = str(entry.path)
        try:
            trash_entry(entry)
            results[path_str] = None
        except CleanError as e:
            results[path_str] = str(e)

    return results


def get_trash_dir() -> Path:
    """Ritorna il percorso della directory del cestino FreeDesktop."""
    xdg_data = os.environ.get("XDG_DATA_HOME", "")
    if xdg_data:
        return Path(xdg_data) / "Trash"
    return Path.home() / ".local" / "share" / "Trash"


def get_trash_size() -> int:
    """
    Calcola la dimensione totale del cestino in bytes.

    Returns:
        Dimensione in bytes, 0 se il cestino non esiste o non è accessibile.
    """
    trash_files = get_trash_dir() / "files"
    if not trash_files.is_dir():
        return 0

    total = 0
    try:
        for item in trash_files.iterdir():
            try:
                if item.is_dir():
                    for root, dirs, files in os.walk(item):
                        for f in files:
                            try:
                                total += os.path.getsize(os.path.join(root, f))
                            except OSError:
                                pass
                else:
                    total += item.stat(follow_symlinks=False).st_size
            except OSError:
                pass
    except OSError:
        pass

    return total
