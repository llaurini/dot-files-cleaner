"""Shared fixtures for functional tests.

This module provides pytest fixtures used across all test files in this suite.
"""

from __future__ import annotations

from datetime import datetime
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
    """Create a controlled home-directory structure for tests.

    The layout created under ``tmp_path`` is::

        <tmp>/
        ├── .gitconfig          (file, in INCLUDE_SINGLE_FILES)
        ├── .vimrc              (file, in INCLUDE_SINGLE_FILES)
        ├── .zshrc              (file, in INCLUDE_SINGLE_FILES)
        ├── .gitignore_global   (single file, NOT in INCLUDE_SINGLE_FILES)
        ├── .ssh/               (dir, always excluded)
        ├── .gnupg/             (dir, always excluded)
        ├── .cache/             (dir, always excluded)
        ├── .config/
        │   ├── zoom/           (dir, included)
        │   ├── htop/           (dir, excluded via CONFIG_SYSTEM_EXCLUDE)
        │   └── dconf/          (dir, excluded via CONFIG_SYSTEM_EXCLUDE)
        ├── .vim/               (dir, included)
        └── .zoom/              (dir, included)

    Args:
        tmp_path: Pytest-provided temporary directory path.

    Returns:
        The root of the fake home directory (``tmp_path`` itself).
    """
    home = tmp_path

    # Single files that are in INCLUDE_SINGLE_FILES
    (home / ".gitconfig").write_text("[user]\n\tname = Test\n")
    (home / ".vimrc").write_text("set nocompatible\n")
    (home / ".zshrc").write_text("export PATH=$PATH:/usr/local/bin\n")

    # Single file NOT in INCLUDE_SINGLE_FILES — must be excluded
    (home / ".gitignore_global").write_text("*.pyc\n")

    # Directories excluded via ALWAYS_EXCLUDE
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_rsa").write_text("FAKE KEY")
    (home / ".gnupg").mkdir()
    (home / ".cache").mkdir()

    # Directories that should be included
    (home / ".vim").mkdir()
    (home / ".vim" / "autoload").mkdir()
    (home / ".vim" / "autoload" / "plug.vim").write_bytes(b"x" * 1024)
    (home / ".zoom").mkdir()
    (home / ".zoom" / "data.conf").write_text("zoom config\n")

    # ~/.config entries: some included, some excluded
    config_dir = home / ".config"
    config_dir.mkdir()
    (config_dir / "zoom").mkdir()
    (config_dir / "zoom" / "zoom.conf").write_text("zoom settings\n")
    (config_dir / "htop").mkdir()   # excluded via CONFIG_SYSTEM_EXCLUDE
    (config_dir / "dconf").mkdir()  # excluded via CONFIG_SYSTEM_EXCLUDE

    return home


# ---------------------------------------------------------------------------
# Factory: DotEntry
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_entry(tmp_path: Path) -> Callable[..., DotEntry]:
    """Return a factory function that creates ``DotEntry`` instances for tests.

    The returned factory creates the corresponding filesystem path under
    ``tmp_path`` and constructs a :class:`~dotcleaner.scanner.DotEntry` with
    the given attributes.

    Example::

        entry = make_entry(".zoom", is_dir=True, source="home_dot")

    Args:
        tmp_path: Pytest-provided temporary directory path.

    Returns:
        A callable that accepts entry parameters and returns a ``DotEntry``.
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
        modified_at: datetime | None = None,
        accessed_at: datetime | None = None,
    ) -> DotEntry:
        """Build and return a single ``DotEntry`` for use in tests.

        Args:
            name: Filesystem name of the entry (e.g. ``".vim"``).
            is_dir: If ``True``, create a directory; otherwise create a file.
            size_bytes: Reported size in bytes stored on the entry.
            source: Scan source label (``"home_dot"`` or ``"config"``).
            associated_packages: Optional list of package names to assign.
            installed_packages: Optional list of installed package names.
            uninstalled_packages: Optional list of uninstalled package names.
            match_source: Mapping phase that produced the association.
            modified_at: Optional last-modification datetime; defaults to
                ``datetime.now()`` when ``None``.
            accessed_at: Optional last-access datetime; defaults to
                ``datetime.now()`` when ``None``.

        Returns:
            A fully initialised ``DotEntry`` backed by a real filesystem path.
        """
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
            modified_at=modified_at if modified_at is not None else datetime.now(),
            accessed_at=accessed_at if accessed_at is not None else datetime.now(),
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
    """Return a ``MagicMock`` of ``PackageChecker`` with a predefined installed set.

    The mock is pre-configured with the following packages treated as installed:
    ``vim``, ``git``, ``zsh``, ``tmux``, ``curl``, ``wget``, ``npm``.
    Individual tests may override ``side_effect`` or ``return_value`` as needed.

    Returns:
        A ``MagicMock`` that mimics the public interface of
        :class:`~dotcleaner.checker.PackageChecker`.
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
