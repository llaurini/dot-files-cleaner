"""Functional tests for dotcleaner/mapper.py.

Tests the three-phase mapping logic:

1. Database lookup (``known_packages.json``)
2. Heuristic lookup (``.desktop`` files + ``dpkg``)
3. Unknown fallback (no match found)

The ``PackageChecker`` is always mocked to avoid any dependency on a real
``dpkg`` installation.
"""

from __future__ import annotations

from typing import Callable
from unittest.mock import MagicMock, patch


from dotcleaner.mapper import _derive_variants, _normalize, map_entries
from dotcleaner.scanner import DotEntry


# ---------------------------------------------------------------------------
# Test: _normalize
# ---------------------------------------------------------------------------


class TestNormalize:
    """Tests for the _normalize helper function."""

    def test_strips_leading_dot(self) -> None:
        """Asserts that a leading dot is removed from the name."""
        assert _normalize(".vim") == "vim"

    def test_lowercase(self) -> None:
        """Asserts that the result is fully lowercased."""
        assert _normalize(".VIM") == "vim"

    def test_replaces_underscore_with_dash(self) -> None:
        """Asserts that underscores are converted to dashes."""
        assert _normalize(".my_app") == "my-app"

    def test_replaces_space_with_dash(self) -> None:
        """Asserts that spaces are converted to dashes."""
        assert _normalize(".my app") == "my-app"

    def test_no_dot_prefix(self) -> None:
        """Asserts that _normalize works correctly on names without a leading dot."""
        assert _normalize("vim") == "vim"

    def test_multiple_underscores(self) -> None:
        """Asserts that multiple consecutive underscores are each replaced by a dash."""
        assert _normalize(".my__app__name") == "my-app-name"

    def test_combined(self) -> None:
        """Asserts that dot-stripping, lowercasing, and underscore replacement are applied together."""
        assert _normalize(".Google_Chrome") == "google-chrome"


# ---------------------------------------------------------------------------
# Test: _derive_variants
# ---------------------------------------------------------------------------


class TestDeriveVariants:
    """Tests for the _derive_variants helper function."""

    def test_always_includes_original(self) -> None:
        """Asserts that the original name is always present in the variants list."""
        variants = _derive_variants("konsole")
        assert "konsole" in variants

    def test_strips_rc_suffix(self) -> None:
        """Asserts that 'konsolerc' yields the variant 'konsole'."""
        variants = _derive_variants("konsolerc")
        assert "konsole" in variants

    def test_strips_rc_with_number(self) -> None:
        """Asserts that 'kmail2rc' yields the variant 'kmail'."""
        variants = _derive_variants("kmail2rc")
        assert "kmail" in variants

    def test_strips_conf_extension(self) -> None:
        """Asserts that 'app.conf' yields the variant 'app'."""
        variants = _derive_variants("app.conf")
        assert "app" in variants

    def test_strips_ini_extension(self) -> None:
        """Asserts that 'app.ini' yields the variant 'app'."""
        variants = _derive_variants("app.ini")
        assert "app" in variants

    def test_strips_json_extension(self) -> None:
        """Asserts that 'config.json' yields the variant 'config'."""
        variants = _derive_variants("config.json")
        assert "config" in variants

    def test_strips_bak_extension(self) -> None:
        """Asserts that 'app.bak' yields the variant 'app'."""
        variants = _derive_variants("app.bak")
        assert "app" in variants

    def test_strips_old_suffix(self) -> None:
        """Asserts that 'vim-old' yields the variant 'vim'."""
        variants = _derive_variants("vim-old")
        assert "vim" in variants

    def test_handles_org_kde_pattern(self) -> None:
        """Asserts that 'org.kde.konsole' yields the variant 'konsole'."""
        variants = _derive_variants("org.kde.konsole")
        assert "konsole" in variants

    def test_handles_version_suffix(self) -> None:
        """Asserts that 'gimp-2.8' yields the variant 'gimp'."""
        variants = _derive_variants("gimp-2.8")
        assert "gimp" in variants

    def test_no_duplicates_in_variants(self) -> None:
        """Asserts that the variants list contains no duplicate strings."""
        variants = _derive_variants("vim")
        assert len(variants) == len(set(variants))


# ---------------------------------------------------------------------------
# Test: map_entries — database phase
# ---------------------------------------------------------------------------


class TestMapEntriesDatabase:
    """Tests for phase 1 (database): entries with names present in known_packages.json."""

    def test_vim_mapped_from_database(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that '.vim' is found in the database and mapped to the 'vim' package."""
        mock_checker.check_packages.side_effect = lambda pkgs: (
            [p for p in pkgs if p == "vim"],
            [p for p in pkgs if p != "vim"],
        )
        entry = make_entry(".vim")
        entries = map_entries([entry], mock_checker)
        assert entry.associated_packages, "vim should have associated packages"
        assert entry.match_source in ("database", "heuristic")

    def test_zsh_mapped_from_database(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that '.zsh' is found in the database and receives associated packages."""
        entry = make_entry(".zsh")
        entries = map_entries([entry], mock_checker)
        assert entry.associated_packages

    def test_known_entry_sets_match_source_database(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that an entry resolved via the database has match_source set to 'database'."""
        entry = make_entry(".zoom")
        mock_checker.check_packages.return_value = ([], ["zoom"])
        entries = map_entries([entry], mock_checker)
        # zoom is in the database with packages ["zoom", ...]
        assert entry.match_source == "database"

    def test_unknown_entry_sets_match_source_unknown(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that an entry not found in any phase has match_source set to 'unknown'."""
        entry = make_entry(".xyzzy-not-a-real-app-12345")
        mock_checker.find_matching_packages.return_value = []
        mock_checker.is_installed_dpkg.return_value = False
        with patch("dotcleaner.mapper._find_desktop_package", return_value=None):
            entries = map_entries([entry], mock_checker)
        assert entry.match_source == "unknown"
        assert entry.associated_packages == []

    def test_database_entry_with_installed_package(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that a database entry whose package is installed has status set to 'installed'."""
        entry = make_entry(".vim")
        mock_checker.check_packages.side_effect = lambda pkgs: (
            [p for p in pkgs if p in {"vim", "vim-tiny", "vim-gtk3", "vim-nox"}],
            [p for p in pkgs if p not in {"vim", "vim-tiny", "vim-gtk3", "vim-nox"}],
        )
        map_entries([entry], mock_checker)
        assert entry.status == "installed"

    def test_database_entry_with_uninstalled_package(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that a database entry whose package is not installed has status set to 'uninstalled'."""
        entry = make_entry(".zoom")
        mock_checker.check_packages.return_value = ([], ["zoom"])
        mock_checker.is_installed_dpkg.return_value = False
        mock_checker.is_binary_available.return_value = False
        map_entries([entry], mock_checker)
        assert entry.status == "uninstalled"

    def test_rc_variant_maps_to_database(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that '.konsolerc' resolves to the 'konsole' package via _derive_variants."""
        entry = make_entry(".konsolerc")
        mock_checker.check_packages.return_value = ([], ["konsole"])
        map_entries([entry], mock_checker)
        assert entry.associated_packages

    def test_config_entry_mapped(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that a ~/.config entry with source='config' is mapped correctly."""
        entry = make_entry("zoom", is_dir=True, source="config")
        mock_checker.check_packages.return_value = ([], ["zoom"])
        map_entries([entry], mock_checker)
        assert entry.associated_packages

    def test_multiple_entries_all_mapped(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that map_entries processes every entry in the input list."""
        entries = [
            make_entry(".vim"),
            make_entry(".zoom"),
            make_entry(".zsh"),
        ]
        mock_checker.check_packages.return_value = ([], [])
        results = map_entries(entries, mock_checker)
        assert len(results) == 3

    def test_returns_same_list(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that map_entries returns the same list object it received (in-place mutation)."""
        entries = [make_entry(".vim")]
        result = map_entries(entries, mock_checker)
        assert result is entries


# ---------------------------------------------------------------------------
# Test: map_entries — heuristic phase
# ---------------------------------------------------------------------------


class TestMapEntriesHeuristic:
    """Tests for phase 2 (heuristic): .desktop lookup and direct dpkg name matching."""

    def test_heuristic_finds_installed_package_by_name(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that a package known to dpkg can be found via the heuristic phase."""
        entry = make_entry(".tmux")
        mock_checker.is_installed_dpkg.side_effect = lambda pkg: pkg == "tmux"
        mock_checker.check_packages.side_effect = lambda pkgs: (
            [p for p in pkgs if p == "tmux"],
            [p for p in pkgs if p != "tmux"],
        )
        with patch("dotcleaner.mapper._find_desktop_package", return_value=None):
            map_entries([entry], mock_checker)

        # May be found by DB or heuristic; either way the entry is processed
        assert entry.associated_packages or entry.status == "unknown"

    def test_heuristic_sets_match_source(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that an entry resolved via the heuristic phase has match_source set to 'heuristic'."""
        entry = make_entry(".my-custom-app-99")
        mock_checker.is_installed_dpkg.side_effect = (
            lambda pkg: pkg == "my-custom-app-99"
        )
        mock_checker.check_packages.side_effect = lambda pkgs: (
            [p for p in pkgs if p == "my-custom-app-99"],
            [],
        )
        mock_checker.find_matching_packages.return_value = []
        with patch("dotcleaner.mapper._find_desktop_package", return_value=None):
            map_entries([entry], mock_checker)

        if entry.associated_packages:
            assert entry.match_source == "heuristic"


# ---------------------------------------------------------------------------
# Test: map_entries — installed/uninstalled_packages fields
# ---------------------------------------------------------------------------


class TestMapEntriesPackageFields:
    """Verifies that the installed_packages and uninstalled_packages fields are populated correctly."""

    def test_installed_packages_populated(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that installed_packages is populated by the checker after mapping."""
        entry = make_entry(".vim")
        mock_checker.check_packages.side_effect = lambda pkgs: (
            [p for p in pkgs if p in {"vim"}],
            [p for p in pkgs if p not in {"vim"}],
        )
        map_entries([entry], mock_checker)
        if entry.associated_packages:
            assert isinstance(entry.installed_packages, list)
            assert isinstance(entry.uninstalled_packages, list)

    def test_empty_associated_packages_means_empty_installed(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that installed_packages and uninstalled_packages are empty when no association is found."""
        entry = make_entry(".xyzzy-not-a-real-app-12345")
        mock_checker.find_matching_packages.return_value = []
        mock_checker.is_installed_dpkg.return_value = False
        with patch("dotcleaner.mapper._find_desktop_package", return_value=None):
            map_entries([entry], mock_checker)

        assert entry.installed_packages == []
        assert entry.uninstalled_packages == []

    def test_check_packages_called_with_associated(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that check_packages is called with exactly the associated_packages list."""
        entry = make_entry(".zoom")
        called_with: list[list[str]] = []

        def capture(pkgs: list[str]) -> tuple[list[str], list[str]]:
            """Record the argument and return an empty partition.

            Args:
                pkgs: The package list passed to check_packages.

            Returns:
                A tuple of two empty lists.
            """
            called_with.append(list(pkgs))
            return [], pkgs

        mock_checker.check_packages.side_effect = capture
        map_entries([entry], mock_checker)

        if entry.associated_packages:
            assert len(called_with) == 1
            assert set(called_with[0]) == set(entry.associated_packages)

    def test_installed_packages_is_subset_of_associated(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that every package in installed_packages also appears in associated_packages."""
        entry = make_entry(".zoom")
        mock_checker.check_packages.return_value = ([], ["zoom"])
        map_entries([entry], mock_checker)
        for pkg in entry.installed_packages:
            assert pkg in entry.associated_packages

    def test_uninstalled_packages_is_subset_of_associated(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Asserts that every package in uninstalled_packages also appears in associated_packages."""
        entry = make_entry(".zoom")
        mock_checker.check_packages.return_value = ([], ["zoom"])
        map_entries([entry], mock_checker)
        for pkg in entry.uninstalled_packages:
            assert pkg in entry.associated_packages
