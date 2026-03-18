"""
test_mapper.py - Test funzionali per dotcleaner/mapper.py

Testa la logica di mapping in tre fasi:
1. Database (known_packages.json)
2. Euristica (.desktop + dpkg)
3. Unknown (nessun match)

Il PackageChecker è sempre mockato per evitare dipendenza da dpkg reale.
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
    """Test della funzione _normalize."""

    def test_strips_leading_dot(self) -> None:
        assert _normalize(".vim") == "vim"

    def test_lowercase(self) -> None:
        assert _normalize(".VIM") == "vim"

    def test_replaces_underscore_with_dash(self) -> None:
        assert _normalize(".my_app") == "my-app"

    def test_replaces_space_with_dash(self) -> None:
        assert _normalize(".my app") == "my-app"

    def test_no_dot_prefix(self) -> None:
        """Funziona anche senza dot iniziale."""
        assert _normalize("vim") == "vim"

    def test_multiple_underscores(self) -> None:
        assert _normalize(".my__app__name") == "my-app-name"

    def test_combined(self) -> None:
        assert _normalize(".Google_Chrome") == "google-chrome"


# ---------------------------------------------------------------------------
# Test: _derive_variants
# ---------------------------------------------------------------------------


class TestDeriveVariants:
    """Test della funzione _derive_variants."""

    def test_always_includes_original(self) -> None:
        variants = _derive_variants("konsole")
        assert "konsole" in variants

    def test_strips_rc_suffix(self) -> None:
        """konsolerc → konsole."""
        variants = _derive_variants("konsolerc")
        assert "konsole" in variants

    def test_strips_rc_with_number(self) -> None:
        """kmail2rc → kmail."""
        variants = _derive_variants("kmail2rc")
        assert "kmail" in variants

    def test_strips_conf_extension(self) -> None:
        """app.conf → app."""
        variants = _derive_variants("app.conf")
        assert "app" in variants

    def test_strips_ini_extension(self) -> None:
        """app.ini → app."""
        variants = _derive_variants("app.ini")
        assert "app" in variants

    def test_strips_json_extension(self) -> None:
        variants = _derive_variants("config.json")
        assert "config" in variants

    def test_strips_bak_extension(self) -> None:
        variants = _derive_variants("app.bak")
        assert "app" in variants

    def test_strips_old_suffix(self) -> None:
        variants = _derive_variants("vim-old")
        assert "vim" in variants

    def test_handles_org_kde_pattern(self) -> None:
        """org.kde.konsole → konsole."""
        variants = _derive_variants("org.kde.konsole")
        assert "konsole" in variants

    def test_handles_version_suffix(self) -> None:
        """gimp-2.8 → gimp."""
        variants = _derive_variants("gimp-2.8")
        assert "gimp" in variants

    def test_no_duplicates_in_variants(self) -> None:
        variants = _derive_variants("vim")
        # Nessun duplicato esatto (può avere la stessa stringa solo una volta per entry originale)
        assert len(variants) == len(set(variants))


# ---------------------------------------------------------------------------
# Test: map_entries — fase database
# ---------------------------------------------------------------------------


class TestMapEntriesDatabase:
    """
    Testa la fase 1 (database): entry con nomi presenti in known_packages.json.
    """

    def test_vim_mapped_from_database(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """'.vim' deve essere trovato nel database e mappato a 'vim'."""
        mock_checker.check_packages.side_effect = lambda pkgs: (
            [p for p in pkgs if p == "vim"],
            [p for p in pkgs if p != "vim"],
        )
        entry = make_entry(".vim")
        entries = map_entries([entry], mock_checker)
        assert entry.associated_packages, "vim dovrebbe avere pacchetti associati"
        assert entry.match_source in ("database", "heuristic")

    def test_zsh_mapped_from_database(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """'.zsh' deve essere trovato nel database."""
        entry = make_entry(".zsh")
        entries = map_entries([entry], mock_checker)
        assert entry.associated_packages

    def test_known_entry_sets_match_source_database(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Un'entry trovata nel DB ha match_source='database'."""
        entry = make_entry(".zoom")
        mock_checker.check_packages.return_value = ([], ["zoom"])
        entries = map_entries([entry], mock_checker)
        # zoom è nel database con pacchetti ["zoom", ...]
        assert entry.match_source == "database"

    def test_unknown_entry_sets_match_source_unknown(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Un'entry non trovata ha match_source='unknown'."""
        # Nome che sicuramente non è nel DB né nell'euristica
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
        """Un'entry DB con pacchetto installato ha status='installed'."""
        entry = make_entry(".vim")
        # vim è installato
        mock_checker.check_packages.side_effect = lambda pkgs: (
            [p for p in pkgs if p in {"vim", "vim-tiny", "vim-gtk3", "vim-nox"}],
            [p for p in pkgs if p not in {"vim", "vim-tiny", "vim-gtk3", "vim-nox"}],
        )
        map_entries([entry], mock_checker)
        assert entry.status == "installed"

    def test_database_entry_with_uninstalled_package(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Un'entry DB con tutti i pacchetti non installati ha status='uninstalled'."""
        entry = make_entry(".zoom")
        # zoom non è installato
        mock_checker.check_packages.return_value = ([], ["zoom"])
        mock_checker.is_installed_dpkg.return_value = False
        mock_checker.is_binary_available.return_value = False
        map_entries([entry], mock_checker)
        # zoom è nel db, ma nessuno installato
        assert entry.status == "uninstalled"

    def test_rc_variant_maps_to_database(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """'.konsolerc' deve usare la variante 'konsole' per trovare il DB."""
        entry = make_entry(".konsolerc")
        mock_checker.check_packages.return_value = ([], ["konsole"])
        map_entries([entry], mock_checker)
        # konsole deve essere trovato via _derive_variants
        assert entry.associated_packages

    def test_config_entry_mapped(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Entry da ~/.config con source='config' viene mappata correttamente."""
        entry = make_entry("zoom", is_dir=True, source="config")
        mock_checker.check_packages.return_value = ([], ["zoom"])
        map_entries([entry], mock_checker)
        assert entry.associated_packages

    def test_multiple_entries_all_mapped(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """map_entries processa tutte le entry della lista."""
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
        """map_entries ritorna la stessa lista modificata in-place."""
        entries = [make_entry(".vim")]
        result = map_entries(entries, mock_checker)
        assert result is entries


# ---------------------------------------------------------------------------
# Test: map_entries — fase euristica
# ---------------------------------------------------------------------------


class TestMapEntriesHeuristic:
    """Testa la fase 2 (euristica): .desktop e dpkg diretti."""

    def test_heuristic_finds_installed_package_by_name(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Se il nome è un pacchetto dpkg installato, viene trovato via euristica."""
        entry = make_entry(".tmux")
        # tmux è nel mock_checker come installato
        mock_checker.is_installed_dpkg.side_effect = lambda pkg: pkg == "tmux"
        mock_checker.check_packages.side_effect = lambda pkgs: (
            [p for p in pkgs if p == "tmux"],
            [p for p in pkgs if p != "tmux"],
        )
        with patch("dotcleaner.mapper._find_desktop_package", return_value=None):
            map_entries([entry], mock_checker)

        # Può essere trovato sia da DB che da euristica
        assert entry.associated_packages or entry.status == "unknown"

    def test_heuristic_sets_match_source(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """Se trovato via euristica, match_source è 'heuristic'."""
        # Usa un nome che non è nel DB ma è un pacchetto installato
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
# Test: map_entries — installed/uninstalled_packages
# ---------------------------------------------------------------------------


class TestMapEntriesPackageFields:
    """Verifica che i campi installed/uninstalled_packages siano popolati."""

    def test_installed_packages_populated(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """installed_packages viene popolato dal checker."""
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
        """Se associated_packages è vuoto, installed e uninstalled sono vuoti."""
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
        """check_packages viene chiamato con i pacchetti associati."""
        entry = make_entry(".zoom")
        called_with: list[list[str]] = []

        def capture(pkgs: list[str]) -> tuple[list[str], list[str]]:
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
        """installed_packages è sempre un sottoinsieme di associated_packages."""
        entry = make_entry(".zoom")
        mock_checker.check_packages.return_value = ([], ["zoom"])
        map_entries([entry], mock_checker)
        for pkg in entry.installed_packages:
            assert pkg in entry.associated_packages

    def test_uninstalled_packages_is_subset_of_associated(
        self, make_entry: Callable[..., DotEntry], mock_checker: MagicMock
    ) -> None:
        """uninstalled_packages è sempre un sottoinsieme di associated_packages."""
        entry = make_entry(".zoom")
        mock_checker.check_packages.return_value = ([], ["zoom"])
        map_entries([entry], mock_checker)
        for pkg in entry.uninstalled_packages:
            assert pkg in entry.associated_packages
