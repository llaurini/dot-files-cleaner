"""
conftest.py - Fixture condivise per i test funzionali.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import pytest

from dotcleaner.scanner import DotEntry


# ---------------------------------------------------------------------------
# Fixture: home directory fittizia
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_home(tmp_path: Path) -> Path:
    """
    Crea una struttura di home directory controllata per i test.

    Struttura creata:
        <tmp>/
        ├── .gitconfig          (file, incluso in INCLUDE_SINGLE_FILES)
        ├── .vimrc              (file, incluso in INCLUDE_SINGLE_FILES)
        ├── .zshrc              (file, incluso in INCLUDE_SINGLE_FILES)
        ├── .gitignore_global   (file singolo → NON incluso, non in INCLUDE_SINGLE_FILES)
        ├── .ssh/               (dir → SEMPRE esclusa)
        ├── .gnupg/             (dir → SEMPRE esclusa)
        ├── .cache/             (dir → SEMPRE esclusa)
        ├── .config/
        │   ├── zoom/           (dir → inclusa)
        │   ├── htop/           (dir → esclusa da CONFIG_SYSTEM_EXCLUDE)
        │   └── dconf/          (dir → esclusa da CONFIG_SYSTEM_EXCLUDE)
        ├── .vim/               (dir → inclusa)
        └── .zoom/              (dir → inclusa)
    """
    home = tmp_path

    # File singoli inclusi
    (home / ".gitconfig").write_text("[user]\n\tname = Test\n")
    (home / ".vimrc").write_text("set nocompatible\n")
    (home / ".zshrc").write_text("export PATH=$PATH:/usr/local/bin\n")

    # File singolo non incluso (non in INCLUDE_SINGLE_FILES)
    (home / ".gitignore_global").write_text("*.pyc\n")

    # Directory escluse da ALWAYS_EXCLUDE
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_rsa").write_text("FAKE KEY")
    (home / ".gnupg").mkdir()
    (home / ".cache").mkdir()

    # Directory incluse
    (home / ".vim").mkdir()
    (home / ".vim" / "autoload").mkdir()
    (home / ".vim" / "autoload" / "plug.vim").write_bytes(b"x" * 1024)
    (home / ".zoom").mkdir()
    (home / ".zoom" / "data.conf").write_text("zoom config\n")

    # .config con voci incluse ed escluse
    config_dir = home / ".config"
    config_dir.mkdir()
    (config_dir / "zoom").mkdir()
    (config_dir / "zoom" / "zoom.conf").write_text("zoom settings\n")
    (config_dir / "htop").mkdir()        # esclusa da CONFIG_SYSTEM_EXCLUDE
    (config_dir / "dconf").mkdir()       # esclusa da CONFIG_SYSTEM_EXCLUDE

    return home


# ---------------------------------------------------------------------------
# Factory: DotEntry
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_entry(tmp_path: Path) -> Callable[..., DotEntry]:
    """
    Factory fixture che restituisce una funzione per creare DotEntry di test.

    Utilizzo:
        entry = make_entry(".zoom", is_dir=True, source="home_dot")
    """
    def _factory(
        name: str,
        *,
        is_dir: bool = True,
        size_bytes: int = 1024,
        source: str = "home_dot",
        associated_packages: list[str] | None = None,
        installed_packages: list[str] | None = None,
        uninstalled_packages: list[str] | None = None,
        match_source: str = "",
    ) -> DotEntry:
        path = tmp_path / name
        if is_dir:
            path.mkdir(exist_ok=True)
        else:
            path.write_text("test content")

        entry = DotEntry(
            path=path,
            name=name,
            is_dir=is_dir,
            size_bytes=size_bytes,
            source=source,
        )
        if associated_packages is not None:
            entry.associated_packages = associated_packages
        if installed_packages is not None:
            entry.installed_packages = installed_packages
        if uninstalled_packages is not None:
            entry.uninstalled_packages = uninstalled_packages
        entry.match_source = match_source
        return entry

    return _factory


# ---------------------------------------------------------------------------
# Fixture: PackageChecker mockato
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_checker() -> MagicMock:
    """
    Ritorna un MagicMock di PackageChecker con un set di pacchetti installati
    predefiniti, configurabile per i singoli test.

    Pacchetti "installati" di default:
        - vim, git, zsh, tmux, curl, wget, npm
    """
    installed = frozenset({"vim", "git", "zsh", "tmux", "curl", "wget", "npm"})
    checker = MagicMock()
    checker.installed_packages = installed
    checker.is_installed_dpkg.side_effect = lambda pkg: pkg.lower() in installed
    checker.is_binary_available.return_value = False
    checker.check_packages.side_effect = lambda pkgs: (
        [p for p in pkgs if p.lower() in installed],
        [p for p in pkgs if p.lower() not in installed],
    )
    checker.find_matching_packages.return_value = []
    return checker
