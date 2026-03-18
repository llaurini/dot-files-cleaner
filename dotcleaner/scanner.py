"""
scanner.py - Scansione della home directory alla ricerca di dot files e directory.

Scansiona:
  - ~/.*  (file e directory al primo livello che iniziano con '.')
  - ~/.config/*  (primo livello di subdirectory/file dentro .config)

Per le directory, calcola la dimensione totale ricorsiva.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Directory/file da escludere sempre dalla lista (troppo di sistema o troppo grandi)
ALWAYS_EXCLUDE: frozenset[str] = frozenset(
    {
        ".cache",
        ".dbus",
        ".gvfs",
        ".local",        # gestito separatamente se necessario
        ".Trash",
        ".Trash-1000",
        ".thumbnails",
        ".recently-used",
        ".recently-used.xbel",
        ".xsession-errors",
        ".xsession-errors.old",
        ".bash_history",
        ".bash_logout",
        ".bashrc",
        ".profile",
        ".bash_profile",
        ".zshenv",
        ".zsh_history",
        ".zsh_sessions",
        ".lesshst",
        ".viminfo",
        ".python_history",
        ".wget-wgetrc",
        ".hushlogin",
        ".motd_shown",
        ".sudo_as_admin_successful",
        ".ICEauthority",
        ".Xauthority",
        ".xscreensaver",
        ".dmrc",
        ".gtk-bookmarks",
        ".face",
        ".face.icon",
        ".ecryptfs",
        ".Private",
        ".ssh",          # sicurezza: non toccare mai ssh
        ".gnupg",        # sicurezza: non toccare mai gnupg/gpg
        ".pki",          # certificati
    }
)

# File/directory in ~/.config da escludere sempre: appartengono al sistema desktop
# e la loro rimozione causerebbe danni (perdita shortcut, impostazioni display, ecc.)
CONFIG_SYSTEM_EXCLUDE: frozenset[str] = frozenset(
    {
        "autostart",        # file .desktop di autostart
        "dconf",            # database GNOME/GTK settings (binario)
        "fontconfig",       # cache font sistema
        "menus",            # menu applicazioni XDG
        "plasma-localerc",  # impostazioni locale KDE
        "plasma-nm",        # NetworkManager Plasma applet
        "plasma-org.kde.plasma.desktop-appletsrc",  # layout desktop
        "session",          # sessioni desktop
        "Trolltech.conf",   # Qt framework config
        "QtProject.conf",   # Qt framework config
        "mimeapps.list",    # associazioni file MIME (sistema)
        "user-dirs.dirs",   # directory XDG utente
        "user-dirs.locale", # locale directory XDG
        "xdg-mimeapps.list",
        "ibus",             # input method
        "gtk-3.0",          # temi GTK3 (modificati dall'utente/sistema)
        "gtk-4.0",          # temi GTK4
        "pulse",            # PulseAudio
        "systemd",          # servizi utente systemd
        "environment.d",    # variabili ambiente systemd
        "procps",           # configurazione procps
        "htop",             # htop config (piccolo, inutile da rimuovere)
        "libaccounts-glib", # accounts SSO
        "goa-1.0",          # GNOME Online Accounts
        "enchant",          # dizionari spell check
        "libreoffice",      # LibreOffice: gestito separatamente nel DB
    }
)

# File di config che vogliamo includere anche se singoli file
INCLUDE_SINGLE_FILES: frozenset[str] = frozenset(
    {
        ".gitconfig",
        ".gtkrc-2.0",
        ".inputrc",
        ".nanorc",
        ".vimrc",
        ".nvimrc",
        ".tmux.conf",
        ".wgetrc",
        ".curlrc",
        ".npmrc",
        ".yarnrc",
        ".gemrc",
        ".zshrc",
        ".zprofile",
    }
)


@dataclass
class DotEntry:
    """Rappresenta un dot file o directory trovato nella home."""

    path: Path
    name: str
    is_dir: bool
    size_bytes: int
    source: str  # "home_dot" | "config"

    # Campi popolati dal mapper
    associated_packages: list[str] = field(default_factory=list)
    match_source: str = ""  # "database" | "heuristic" | "unknown"

    # Campi popolati dal checker
    installed_packages: list[str] = field(default_factory=list)
    uninstalled_packages: list[str] = field(default_factory=list)

    @property
    def display_path(self) -> str:
        """Ritorna il path relativo alla home."""
        home = Path.home()
        try:
            return "~/" + str(self.path.relative_to(home))
        except ValueError:
            return str(self.path)

    @property
    def status(self) -> str:
        """
        Ritorna lo stato del dot entry:
        - 'installed'   : almeno un pacchetto associato è installato
        - 'uninstalled' : pacchetti trovati ma nessuno installato
        - 'unknown'     : nessun pacchetto associato trovato
        """
        if not self.associated_packages:
            return "unknown"
        if self.installed_packages:
            return "installed"
        return "uninstalled"

    @property
    def size_human(self) -> str:
        """Dimensione human-readable."""
        size = self.size_bytes
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size //= 1024
        return f"{size:.1f} TB"


def _dir_size(path: Path) -> int:
    """Calcola la dimensione totale ricorsiva di una directory in bytes."""
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_symlink():
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += _dir_size(Path(entry.path))
                else:
                    total += entry.stat(follow_symlinks=False).st_size
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return total


def _entry_size(path: Path) -> int:
    """Dimensione di un file o di una directory (ricorsiva)."""
    try:
        if path.is_symlink():
            return path.lstat().st_size
        if path.is_dir():
            return _dir_size(path)
        return path.stat().st_size
    except (PermissionError, OSError):
        return 0


def scan_home(home: Path | None = None) -> list[DotEntry]:
    """
    Scansiona la home directory e ritorna tutti i dot entries trovati.

    Args:
        home: Percorso della home directory. Se None, usa Path.home().

    Returns:
        Lista di DotEntry ordinata per status (uninstalled prima) e poi per nome.
    """
    if home is None:
        home = Path.home()

    entries: list[DotEntry] = []
    seen_paths: set[Path] = set()

    # --- 1. Scansiona ~/.*  (primo livello) ---
    try:
        for item in home.iterdir():
            if not item.name.startswith("."):
                continue
            if item.name in ALWAYS_EXCLUDE:
                continue
            # Escludi file banali (non di config) a meno che non siano esplicitamente inclusi
            if item.is_file() and item.name not in INCLUDE_SINGLE_FILES:
                continue
            # Escludi symlink rotti
            if item.is_symlink() and not item.exists():
                continue

            resolved = item.resolve() if not item.is_symlink() else item
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)

            entries.append(
                DotEntry(
                    path=item,
                    name=item.name,
                    is_dir=item.is_dir(),
                    size_bytes=_entry_size(item),
                    source="home_dot",
                )
            )
    except (PermissionError, OSError):
        pass

    # --- 2. Scansiona ~/.config/*  (primo livello) ---
    config_dir = home / ".config"
    if config_dir.is_dir():
        try:
            for item in config_dir.iterdir():
                # Escludi voci di sistema desktop che non vanno mai rimosse
                if item.name in CONFIG_SYSTEM_EXCLUDE:
                    continue
                # Escludi symlink rotti
                if item.is_symlink() and not item.exists():
                    continue

                resolved = item.resolve() if not item.is_symlink() else item
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)

                entries.append(
                    DotEntry(
                        path=item,
                        name=item.name,
                        is_dir=item.is_dir(),
                        size_bytes=_entry_size(item),
                        source="config",
                    )
                )
        except (PermissionError, OSError):
            pass

    return entries
