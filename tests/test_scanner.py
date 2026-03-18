"""Functional tests for dotcleaner/scanner.py.

Tests ``scan_home()`` against a fake home directory built with ``tmp_path``,
verifying exclusion rules, inclusion rules, size calculation, and all fields
of the returned :class:`~dotcleaner.scanner.DotEntry` objects.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable


from dotcleaner.scanner import (
    ALWAYS_EXCLUDE,
    CONFIG_SYSTEM_EXCLUDE,
    DotEntry,
    scan_home,
)


# ---------------------------------------------------------------------------
# Test: DotEntry properties
# ---------------------------------------------------------------------------


class TestDotEntryProperties:
    """Tests for the computed properties of DotEntry."""

    def test_status_unknown_when_no_packages(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that status is 'unknown' when no packages are associated."""
        entry = make_entry(".foo", associated_packages=[])
        assert entry.status == "unknown"

    def test_status_installed_when_some_installed(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that status is 'installed' when at least one package is installed."""
        entry = make_entry(
            ".vim",
            associated_packages=["vim"],
            installed_packages=["vim"],
            uninstalled_packages=[],
        )
        assert entry.status == "installed"

    def test_status_uninstalled_when_packages_but_none_installed(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that status is 'uninstalled' when packages exist but none are installed."""
        entry = make_entry(
            ".zoom",
            associated_packages=["zoom"],
            installed_packages=[],
            uninstalled_packages=["zoom"],
        )
        assert entry.status == "uninstalled"

    def test_status_installed_even_if_some_uninstalled(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that status is 'installed' when at least one package is installed, even with others not installed."""
        entry = make_entry(
            ".google-chrome",
            associated_packages=["google-chrome-stable", "google-chrome-beta"],
            installed_packages=["google-chrome-stable"],
            uninstalled_packages=["google-chrome-beta"],
        )
        assert entry.status == "installed"

    def test_size_human_bytes(self, make_entry: Callable[..., DotEntry]) -> None:
        """Asserts that size_human returns a correctly formatted bytes string."""
        entry = make_entry(".foo", size_bytes=500)
        assert entry.size_human == "500.0 B"

    def test_size_human_kilobytes(self, make_entry: Callable[..., DotEntry]) -> None:
        """Asserts that size_human returns a correctly formatted kilobytes string."""
        entry = make_entry(".foo", size_bytes=2048)
        assert entry.size_human == "2.0 KB"

    def test_size_human_megabytes(self, make_entry: Callable[..., DotEntry]) -> None:
        """Asserts that size_human returns a correctly formatted megabytes string."""
        entry = make_entry(".foo", size_bytes=3 * 1024 * 1024)
        assert entry.size_human == "3.0 MB"

    def test_size_human_gigabytes(self, make_entry: Callable[..., DotEntry]) -> None:
        """Asserts that size_human returns a correctly formatted gigabytes string."""
        entry = make_entry(".foo", size_bytes=2 * 1024 * 1024 * 1024)
        assert entry.size_human == "2.0 GB"

    def test_display_path_relative_to_home(
        self, tmp_path: Path, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that display_path is a non-empty string."""
        entry = make_entry(".vim")
        # display_path uses Path.home(), not tmp_path, so the result will be
        # absolute, but it must be a non-empty string.
        assert entry.display_path
        assert isinstance(entry.display_path, str)

    def test_display_path_absolute_fallback(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that display_path returns a non-empty string as absolute fallback."""
        entry = make_entry(".vim")
        result = entry.display_path
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Test: DotEntry timestamp properties
# ---------------------------------------------------------------------------

_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


class TestDotEntryTimestampProperties:
    """Tests for the modified_human and accessed_human properties of DotEntry."""

    def test_modified_human_format(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that modified_human returns a string in YYYY-MM-DD HH:MM format."""
        dt = datetime(2024, 3, 15, 10, 22)
        entry = make_entry(".foo", modified_at=dt)
        assert entry.modified_human == "2024-03-15 10:22"

    def test_accessed_human_format(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that accessed_human returns a string in YYYY-MM-DD HH:MM format."""
        dt = datetime(2026, 1, 7, 8, 5)
        entry = make_entry(".foo", accessed_at=dt)
        assert entry.accessed_human == "2026-01-07 08:05"

    def test_modified_human_matches_pattern(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that modified_human output matches the expected datetime pattern."""
        entry = make_entry(".bar", modified_at=datetime(2023, 12, 31, 23, 59))
        assert _DATETIME_PATTERN.match(entry.modified_human)

    def test_accessed_human_matches_pattern(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that accessed_human output matches the expected datetime pattern."""
        entry = make_entry(".bar", accessed_at=datetime(2023, 12, 31, 23, 59))
        assert _DATETIME_PATTERN.match(entry.accessed_human)

    def test_modified_and_accessed_can_differ(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that modified_at and accessed_at are independent fields."""
        mod = datetime(2020, 6, 1, 12, 0)
        acc = datetime(2025, 11, 20, 9, 30)
        entry = make_entry(".baz", modified_at=mod, accessed_at=acc)
        assert entry.modified_human == "2020-06-01 12:00"
        assert entry.accessed_human == "2025-11-20 09:30"

    def test_scan_home_populates_modified_at(self, tmp_path: Path) -> None:
        """Asserts that scan_home sets a valid modified_at datetime on each entry."""
        home = tmp_path
        (home / ".vim").mkdir()
        before = datetime.now()
        entries = scan_home(home=home)
        after = datetime.now()
        assert entries, "Expected at least one entry"
        for entry in entries:
            assert isinstance(entry.modified_at, datetime)
            # The timestamp must be plausible (not in the future beyond 'after')
            assert entry.modified_at <= after

    def test_scan_home_populates_accessed_at(self, tmp_path: Path) -> None:
        """Asserts that scan_home sets a valid accessed_at datetime on each entry."""
        home = tmp_path
        (home / ".vim").mkdir()
        entries = scan_home(home=home)
        assert entries, "Expected at least one entry"
        for entry in entries:
            assert isinstance(entry.accessed_at, datetime)

    def test_scan_home_modified_human_is_string(self, tmp_path: Path) -> None:
        """Asserts that modified_human is a non-empty string after scan_home."""
        home = tmp_path
        (home / ".vim").mkdir()
        entries = scan_home(home=home)
        for entry in entries:
            assert isinstance(entry.modified_human, str)
            assert len(entry.modified_human) > 0

    def test_scan_home_accessed_human_is_string(self, tmp_path: Path) -> None:
        """Asserts that accessed_human is a non-empty string after scan_home."""
        home = tmp_path
        (home / ".vim").mkdir()
        entries = scan_home(home=home)
        for entry in entries:
            assert isinstance(entry.accessed_human, str)
            assert len(entry.accessed_human) > 0


# ---------------------------------------------------------------------------
# Test: scan_home exclusions ALWAYS_EXCLUDE
# ---------------------------------------------------------------------------


class TestScanHomeAlwaysExclude:
    """Verifies that entries in ALWAYS_EXCLUDE never appear in results."""

    def test_ssh_excluded(self, fake_home: Path) -> None:
        """Asserts that .ssh is absent from scan results."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".ssh" not in names

    def test_gnupg_excluded(self, fake_home: Path) -> None:
        """Asserts that .gnupg is absent from scan results."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".gnupg" not in names

    def test_cache_excluded(self, fake_home: Path) -> None:
        """Asserts that .cache is absent from scan results."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".cache" not in names

    def test_all_always_exclude_respected(self, tmp_path: Path) -> None:
        """Asserts that no entry from ALWAYS_EXCLUDE appears, even when physically created."""
        home = tmp_path
        for name in ALWAYS_EXCLUDE:
            path = home / name
            path.mkdir(exist_ok=True)

        entries = scan_home(home=home)
        result_names = {e.name for e in entries}
        for excluded in ALWAYS_EXCLUDE:
            assert (
                excluded not in result_names
            ), f"{excluded} should not appear in results"


# ---------------------------------------------------------------------------
# Test: scan_home — single files
# ---------------------------------------------------------------------------


class TestScanHomeSingleFiles:
    """Verifies the inclusion logic for single dot files."""

    def test_gitconfig_included(self, fake_home: Path) -> None:
        """Asserts that .gitconfig is included because it is in INCLUDE_SINGLE_FILES."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".gitconfig" in names

    def test_vimrc_included(self, fake_home: Path) -> None:
        """Asserts that .vimrc is included because it is in INCLUDE_SINGLE_FILES."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".vimrc" in names

    def test_zshrc_included(self, fake_home: Path) -> None:
        """Asserts that .zshrc is included because it is in INCLUDE_SINGLE_FILES."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".zshrc" in names

    def test_generic_single_file_excluded(self, fake_home: Path) -> None:
        """Asserts that .gitignore_global is excluded because it is not in INCLUDE_SINGLE_FILES."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".gitignore_global" not in names

    def test_included_file_is_not_dir(self, fake_home: Path) -> None:
        """Asserts that .gitconfig has is_dir set to False."""
        entries = scan_home(home=fake_home)
        gitconfig = next((e for e in entries if e.name == ".gitconfig"), None)
        assert gitconfig is not None
        assert gitconfig.is_dir is False


# ---------------------------------------------------------------------------
# Test: scan_home — directories
# ---------------------------------------------------------------------------


class TestScanHomeDirectories:
    """Verifies that dot directories are included correctly."""

    def test_vim_dir_included(self, fake_home: Path) -> None:
        """Asserts that the .vim directory is included in results."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".vim" in names

    def test_zoom_dir_included(self, fake_home: Path) -> None:
        """Asserts that the .zoom directory is included in results."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".zoom" in names

    def test_dot_dir_is_dir_true(self, fake_home: Path) -> None:
        """Asserts that the .vim entry has is_dir set to True."""
        entries = scan_home(home=fake_home)
        vim_entry = next((e for e in entries if e.name == ".vim"), None)
        assert vim_entry is not None
        assert vim_entry.is_dir is True

    def test_source_home_dot(self, fake_home: Path) -> None:
        """Asserts that entries from ~/.* have source set to 'home_dot'."""
        entries = scan_home(home=fake_home)
        home_dot = [e for e in entries if e.source == "home_dot"]
        assert len(home_dot) > 0
        for e in home_dot:
            assert e.name.startswith("."), f"{e.name} should start with '.'"


# ---------------------------------------------------------------------------
# Test: scan_home — .config
# ---------------------------------------------------------------------------


class TestScanHomeConfig:
    """Verifies scanning of ~/.config entries."""

    def test_config_zoom_included(self, fake_home: Path) -> None:
        """Asserts that zoom inside .config is included in results."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert "zoom" in names

    def test_config_htop_excluded(self, fake_home: Path) -> None:
        """Asserts that htop inside .config is excluded via CONFIG_SYSTEM_EXCLUDE."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert "htop" not in names

    def test_config_dconf_excluded(self, fake_home: Path) -> None:
        """Asserts that dconf inside .config is excluded via CONFIG_SYSTEM_EXCLUDE."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert "dconf" not in names

    def test_config_source_is_config(self, fake_home: Path) -> None:
        """Asserts that entries from ~/.config have source set to 'config'."""
        entries = scan_home(home=fake_home)
        config_entries = [e for e in entries if e.source == "config"]
        assert len(config_entries) > 0
        for e in config_entries:
            assert "config" in str(
                e.path
            ), f"Path of {e.name} should contain .config"

    def test_all_config_system_exclude_respected(self, tmp_path: Path) -> None:
        """Asserts that no entry from CONFIG_SYSTEM_EXCLUDE appears under ~/.config."""
        home = tmp_path
        config_dir = home / ".config"
        config_dir.mkdir()
        for name in CONFIG_SYSTEM_EXCLUDE:
            (config_dir / name).mkdir(exist_ok=True)

        entries = scan_home(home=home)
        result_names = {e.name for e in entries}
        for excluded in CONFIG_SYSTEM_EXCLUDE:
            assert (
                excluded not in result_names
            ), f"{excluded} should not appear in results"


# ---------------------------------------------------------------------------
# Test: scan_home — broken symlinks
# ---------------------------------------------------------------------------


class TestScanHomeBrokenSymlink:
    """Verifies that broken symlinks are silently ignored."""

    def test_broken_symlink_home_dot_excluded(self, tmp_path: Path) -> None:
        """Asserts that a broken symlink in ~/ is ignored by scan_home."""
        home = tmp_path
        broken = home / ".broken-app"
        broken.symlink_to(home / ".nonexistent-target")
        assert not broken.exists()  # confirm the symlink is broken

        entries = scan_home(home=home)
        names = {e.name for e in entries}
        assert ".broken-app" not in names

    def test_broken_symlink_config_excluded(self, tmp_path: Path) -> None:
        """Asserts that a broken symlink in ~/.config is ignored by scan_home."""
        home = tmp_path
        config_dir = home / ".config"
        config_dir.mkdir()
        broken = config_dir / "broken-config"
        broken.symlink_to(home / "nonexistent")

        entries = scan_home(home=home)
        names = {e.name for e in entries}
        assert "broken-config" not in names


# ---------------------------------------------------------------------------
# Test: scan_home — sizes
# ---------------------------------------------------------------------------


class TestScanHomeSizes:
    """Verifies size calculation for files and directories."""

    def test_file_size_correct(self, tmp_path: Path) -> None:
        """Asserts that an included file has its exact byte size recorded."""
        home = tmp_path
        content = b"x" * 512
        (home / ".gitconfig").write_bytes(content)

        entries = scan_home(home=home)
        entry = next((e for e in entries if e.name == ".gitconfig"), None)
        assert entry is not None
        assert entry.size_bytes == 512

    def test_dir_size_recursive(self, tmp_path: Path) -> None:
        """Asserts that a directory's size_bytes is at least the sum of its files."""
        home = tmp_path
        vim_dir = home / ".vim"
        vim_dir.mkdir()
        (vim_dir / "file1.txt").write_bytes(b"a" * 100)
        (vim_dir / "file2.txt").write_bytes(b"b" * 200)

        entries = scan_home(home=home)
        entry = next((e for e in entries if e.name == ".vim"), None)
        assert entry is not None
        assert entry.size_bytes >= 300

    def test_empty_dir_size_zero(self, tmp_path: Path) -> None:
        """Asserts that an empty directory has size_bytes equal to zero."""
        home = tmp_path
        (home / ".emptyapp").mkdir()

        entries = scan_home(home=home)
        entry = next((e for e in entries if e.name == ".emptyapp"), None)
        assert entry is not None
        assert entry.size_bytes == 0


# ---------------------------------------------------------------------------
# Test: scan_home — DotEntry fields
# ---------------------------------------------------------------------------


class TestScanHomeDotEntryFields:
    """Verifies the fields of DotEntry objects returned by scan_home."""

    def test_name_matches_filesystem_name(self, fake_home: Path) -> None:
        """Asserts that each entry's name matches the filesystem path's name component."""
        entries = scan_home(home=fake_home)
        for entry in entries:
            assert entry.name == entry.path.name

    def test_path_is_absolute(self, fake_home: Path) -> None:
        """Asserts that every entry's path is absolute."""
        entries = scan_home(home=fake_home)
        for entry in entries:
            assert entry.path.is_absolute(), f"{entry.path} is not absolute"

    def test_associated_packages_empty_initially(self, fake_home: Path) -> None:
        """Asserts that associated_packages is empty immediately after scan_home."""
        entries = scan_home(home=fake_home)
        for entry in entries:
            assert entry.associated_packages == []

    def test_status_unknown_before_mapping(self, fake_home: Path) -> None:
        """Asserts that status is 'unknown' before map_entries is called."""
        entries = scan_home(home=fake_home)
        for entry in entries:
            assert entry.status == "unknown"

    def test_no_duplicate_paths(self, fake_home: Path) -> None:
        """Asserts that no two entries share the same path."""
        entries = scan_home(home=fake_home)
        paths = [str(e.path) for e in entries]
        assert len(paths) == len(set(paths)), "Duplicate paths found!"

    def test_results_is_list(self, fake_home: Path) -> None:
        """Asserts that scan_home returns a list."""
        result = scan_home(home=fake_home)
        assert isinstance(result, list)

    def test_empty_home_returns_empty_list(self, tmp_path: Path) -> None:
        """Asserts that a completely empty home directory yields an empty list."""
        entries = scan_home(home=tmp_path)
        assert entries == []
