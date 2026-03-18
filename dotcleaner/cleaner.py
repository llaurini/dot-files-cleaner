"""FreeDesktop Trash helper for moving dot entries to the recycle bin.

Uses ``send2trash`` to respect the XDG Trash specification
(``~/.local/share/Trash``).  Moved items can be recovered via any
file manager (Nautilus, Dolphin, etc.).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from dotcleaner.scanner import DotEntry

# ---------------------------------------------------------------------------
# send2trash import — graceful fallback when library is absent
# ---------------------------------------------------------------------------

_send2trash_fn: Callable[[str], None] | None = None
HAS_SEND2TRASH: bool = False

try:
    from send2trash import send2trash as _imported_send2trash

    _send2trash_fn = _imported_send2trash
    HAS_SEND2TRASH = True
except ImportError:
    pass

# Keep the original name as an alias so existing tests that patch
# "dotcleaner.cleaner._send2trash" continue to work.
_send2trash = _send2trash_fn


class CleanError(Exception):
    """Raised when a dot entry cannot be moved to the trash."""

    pass


def trash_entry(entry: DotEntry) -> None:
    """Move a single DotEntry to the FreeDesktop trash.

    Args:
        entry: The ``DotEntry`` whose path should be trashed.

    Raises:
        CleanError: If the path does not exist, if ``send2trash`` is not
            installed, or if ``send2trash`` raises any exception.
    """
    path = entry.path

    if not path.exists() and not path.is_symlink():
        raise CleanError(f"Il percorso non esiste: {path}")

    if not HAS_SEND2TRASH or _send2trash is None:
        raise CleanError(
            "La libreria 'send2trash' non è installata. "
            "Esegui: pip install send2trash"
        )

    try:
        _send2trash(str(path))
    except Exception as e:
        raise CleanError(f"Impossibile spostare nel cestino '{path}': {e}") from e


def trash_entries(entries: list[DotEntry]) -> dict[str, str | None]:
    """Move a list of DotEntry objects to the FreeDesktop trash.

    Each entry is processed independently; a failure on one entry does not
    prevent subsequent entries from being attempted.

    Args:
        entries: List of ``DotEntry`` objects to trash.

    Returns:
        A mapping of ``{path_str: error_message | None}`` where ``None``
        indicates success and a non-``None`` string contains the error
        description.
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
    """Return the path to the FreeDesktop Trash directory.

    Respects the ``XDG_DATA_HOME`` environment variable when set; otherwise
    falls back to ``~/.local/share/Trash``.

    Returns:
        ``Path`` object pointing to the Trash directory (may not yet exist).
    """
    xdg_data = os.environ.get("XDG_DATA_HOME", "")
    if xdg_data:
        return Path(xdg_data) / "Trash"
    return Path.home() / ".local" / "share" / "Trash"


def get_trash_size() -> int:
    """Compute the total size of files currently in the trash.

    Walks ``<trash_dir>/files`` recursively.  Any unreadable entries are
    silently skipped.

    Returns:
        Total size in bytes, or ``0`` if the trash directory does not exist
        or is inaccessible.
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
