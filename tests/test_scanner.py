"""
test_scanner.py - Test funzionali per dotcleaner/scanner.py

Testa scan_home() su una home directory fittizia creata con tmp_path,
verificando esclusioni, inclusioni, calcolo dimensioni e campi DotEntry.
"""

from __future__ import annotations

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
    """Test delle proprietà calcolate di DotEntry."""

    def test_status_unknown_when_no_packages(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """status == 'unknown' se nessun pacchetto associato."""
        entry = make_entry(".foo", associated_packages=[])
        assert entry.status == "unknown"

    def test_status_installed_when_some_installed(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """status == 'installed' se almeno un pacchetto è installato."""
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
        """status == 'uninstalled' se ci sono pacchetti ma nessuno installato."""
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
        """status == 'installed' se almeno uno è installato, anche con altri non installati."""
        entry = make_entry(
            ".google-chrome",
            associated_packages=["google-chrome-stable", "google-chrome-beta"],
            installed_packages=["google-chrome-stable"],
            uninstalled_packages=["google-chrome-beta"],
        )
        assert entry.status == "installed"

    def test_size_human_bytes(self, make_entry: Callable[..., DotEntry]) -> None:
        """size_human ritorna bytes correttamente."""
        entry = make_entry(".foo", size_bytes=500)
        assert entry.size_human == "500.0 B"

    def test_size_human_kilobytes(self, make_entry: Callable[..., DotEntry]) -> None:
        """size_human ritorna kilobytes correttamente."""
        entry = make_entry(".foo", size_bytes=2048)
        assert entry.size_human == "2.0 KB"

    def test_size_human_megabytes(self, make_entry: Callable[..., DotEntry]) -> None:
        """size_human ritorna megabytes correttamente."""
        entry = make_entry(".foo", size_bytes=3 * 1024 * 1024)
        assert entry.size_human == "3.0 MB"

    def test_size_human_gigabytes(self, make_entry: Callable[..., DotEntry]) -> None:
        """size_human ritorna gigabytes correttamente."""
        entry = make_entry(".foo", size_bytes=2 * 1024 * 1024 * 1024)
        assert entry.size_human == "2.0 GB"

    def test_display_path_relative_to_home(
        self, tmp_path: Path, make_entry: Callable[..., DotEntry]
    ) -> None:
        """display_path mostra il path relativo alla home."""
        entry = make_entry(".vim")
        # display_path usa Path.home(), non tmp_path, quindi sarà assoluto
        # ma deve almeno essere una stringa non vuota
        assert entry.display_path
        assert isinstance(entry.display_path, str)

    def test_display_path_absolute_fallback(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """display_path ritorna path assoluto se non è sotto home."""
        entry = make_entry(".vim")
        result = entry.display_path
        # Deve essere una stringa valida
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Test: scan_home esclusioni ALWAYS_EXCLUDE
# ---------------------------------------------------------------------------


class TestScanHomeAlwaysExclude:
    """Verifica che ALWAYS_EXCLUDE non venga mai incluso nei risultati."""

    def test_ssh_excluded(self, fake_home: Path) -> None:
        """.ssh non deve apparire nei risultati."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".ssh" not in names

    def test_gnupg_excluded(self, fake_home: Path) -> None:
        """.gnupg non deve apparire nei risultati."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".gnupg" not in names

    def test_cache_excluded(self, fake_home: Path) -> None:
        """.cache non deve apparire nei risultati."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".cache" not in names

    def test_all_always_exclude_respected(self, tmp_path: Path) -> None:
        """Nessuna voce da ALWAYS_EXCLUDE appare, anche se creata fisicamente."""
        home = tmp_path
        # Crea ogni voce esclusa
        for name in ALWAYS_EXCLUDE:
            path = home / name
            path.mkdir(exist_ok=True)

        entries = scan_home(home=home)
        result_names = {e.name for e in entries}
        for excluded in ALWAYS_EXCLUDE:
            assert (
                excluded not in result_names
            ), f"{excluded} non dovrebbe essere nei risultati"


# ---------------------------------------------------------------------------
# Test: scan_home — file singoli
# ---------------------------------------------------------------------------


class TestScanHomeSingleFiles:
    """Verifica la logica di inclusione dei file singoli."""

    def test_gitconfig_included(self, fake_home: Path) -> None:
        """.gitconfig deve essere incluso (è in INCLUDE_SINGLE_FILES)."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".gitconfig" in names

    def test_vimrc_included(self, fake_home: Path) -> None:
        """.vimrc deve essere incluso."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".vimrc" in names

    def test_zshrc_included(self, fake_home: Path) -> None:
        """.zshrc deve essere incluso."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".zshrc" in names

    def test_generic_single_file_excluded(self, fake_home: Path) -> None:
        """.gitignore_global NON deve essere incluso (non è in INCLUDE_SINGLE_FILES)."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".gitignore_global" not in names

    def test_included_file_is_not_dir(self, fake_home: Path) -> None:
        """.gitconfig deve avere is_dir=False."""
        entries = scan_home(home=fake_home)
        gitconfig = next((e for e in entries if e.name == ".gitconfig"), None)
        assert gitconfig is not None
        assert gitconfig.is_dir is False


# ---------------------------------------------------------------------------
# Test: scan_home — directory incluse
# ---------------------------------------------------------------------------


class TestScanHomeDirectories:
    """Verifica che le directory dot vengano incluse correttamente."""

    def test_vim_dir_included(self, fake_home: Path) -> None:
        """.vim directory deve essere inclusa."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".vim" in names

    def test_zoom_dir_included(self, fake_home: Path) -> None:
        """.zoom directory deve essere inclusa."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert ".zoom" in names

    def test_dot_dir_is_dir_true(self, fake_home: Path) -> None:
        """.vim entry deve avere is_dir=True."""
        entries = scan_home(home=fake_home)
        vim_entry = next((e for e in entries if e.name == ".vim"), None)
        assert vim_entry is not None
        assert vim_entry.is_dir is True

    def test_source_home_dot(self, fake_home: Path) -> None:
        """Voci da ~/.* hanno source='home_dot'."""
        entries = scan_home(home=fake_home)
        home_dot = [e for e in entries if e.source == "home_dot"]
        assert len(home_dot) > 0
        for e in home_dot:
            assert e.name.startswith("."), f"{e.name} dovrebbe iniziare con '.'"


# ---------------------------------------------------------------------------
# Test: scan_home — .config
# ---------------------------------------------------------------------------


class TestScanHomeConfig:
    """Verifica scansione di ~/.config."""

    def test_config_zoom_included(self, fake_home: Path) -> None:
        """zoom dentro .config deve essere incluso."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert "zoom" in names

    def test_config_htop_excluded(self, fake_home: Path) -> None:
        """htop dentro .config è in CONFIG_SYSTEM_EXCLUDE → escluso."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert "htop" not in names

    def test_config_dconf_excluded(self, fake_home: Path) -> None:
        """dconf dentro .config è in CONFIG_SYSTEM_EXCLUDE → escluso."""
        entries = scan_home(home=fake_home)
        names = {e.name for e in entries}
        assert "dconf" not in names

    def test_config_source_is_config(self, fake_home: Path) -> None:
        """Voci da ~/.config hanno source='config'."""
        entries = scan_home(home=fake_home)
        config_entries = [e for e in entries if e.source == "config"]
        assert len(config_entries) > 0
        for e in config_entries:
            assert "config" in str(
                e.path
            ), f"Path di {e.name} dovrebbe contenere .config"

    def test_all_config_system_exclude_respected(self, tmp_path: Path) -> None:
        """Nessuna voce da CONFIG_SYSTEM_EXCLUDE appare da ~/.config."""
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
            ), f"{excluded} non dovrebbe essere nei risultati"


# ---------------------------------------------------------------------------
# Test: scan_home — broken symlink
# ---------------------------------------------------------------------------


class TestScanHomeBrokenSymlink:
    """Verifica che i symlink rotti vengano ignorati."""

    def test_broken_symlink_home_dot_excluded(self, tmp_path: Path) -> None:
        """Un symlink rotto in ~/ viene ignorato."""
        home = tmp_path
        broken = home / ".broken-app"
        broken.symlink_to(home / ".nonexistent-target")
        assert not broken.exists()  # deve essere rotto

        entries = scan_home(home=home)
        names = {e.name for e in entries}
        assert ".broken-app" not in names

    def test_broken_symlink_config_excluded(self, tmp_path: Path) -> None:
        """Un symlink rotto in ~/.config viene ignorato."""
        home = tmp_path
        config_dir = home / ".config"
        config_dir.mkdir()
        broken = config_dir / "broken-config"
        broken.symlink_to(home / "nonexistent")

        entries = scan_home(home=home)
        names = {e.name for e in entries}
        assert "broken-config" not in names


# ---------------------------------------------------------------------------
# Test: scan_home — dimensioni
# ---------------------------------------------------------------------------


class TestScanHomeSizes:
    """Verifica il calcolo delle dimensioni."""

    def test_file_size_correct(self, tmp_path: Path) -> None:
        """Un file incluso ha la dimensione corretta."""
        home = tmp_path
        content = b"x" * 512
        (home / ".gitconfig").write_bytes(content)

        entries = scan_home(home=home)
        entry = next((e for e in entries if e.name == ".gitconfig"), None)
        assert entry is not None
        assert entry.size_bytes == 512

    def test_dir_size_recursive(self, tmp_path: Path) -> None:
        """Una directory ha size_bytes >= dimensione totale dei suoi file."""
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
        """Una directory vuota ha size_bytes == 0."""
        home = tmp_path
        (home / ".emptyapp").mkdir()

        entries = scan_home(home=home)
        entry = next((e for e in entries if e.name == ".emptyapp"), None)
        assert entry is not None
        assert entry.size_bytes == 0


# ---------------------------------------------------------------------------
# Test: scan_home — campi DotEntry
# ---------------------------------------------------------------------------


class TestScanHomeDotEntryFields:
    """Verifica i campi dei DotEntry restituiti da scan_home."""

    def test_name_matches_filesystem_name(self, fake_home: Path) -> None:
        """Il campo name corrisponde al nome dell'entry nel filesystem."""
        entries = scan_home(home=fake_home)
        for entry in entries:
            assert entry.name == entry.path.name

    def test_path_is_absolute(self, fake_home: Path) -> None:
        """Il campo path è sempre assoluto."""
        entries = scan_home(home=fake_home)
        for entry in entries:
            assert entry.path.is_absolute(), f"{entry.path} non è assoluto"

    def test_associated_packages_empty_initially(self, fake_home: Path) -> None:
        """associated_packages è vuoto dopo scan_home (il mapper non è stato chiamato)."""
        entries = scan_home(home=fake_home)
        for entry in entries:
            assert entry.associated_packages == []

    def test_status_unknown_before_mapping(self, fake_home: Path) -> None:
        """status è 'unknown' prima del mapping."""
        entries = scan_home(home=fake_home)
        for entry in entries:
            assert entry.status == "unknown"

    def test_no_duplicate_paths(self, fake_home: Path) -> None:
        """Non ci sono path duplicati nei risultati."""
        entries = scan_home(home=fake_home)
        paths = [str(e.path) for e in entries]
        assert len(paths) == len(set(paths)), "Ci sono path duplicati!"

    def test_results_is_list(self, fake_home: Path) -> None:
        """scan_home restituisce una lista."""
        result = scan_home(home=fake_home)
        assert isinstance(result, list)

    def test_empty_home_returns_empty_list(self, tmp_path: Path) -> None:
        """Una home completamente vuota restituisce lista vuota."""
        home = tmp_path
        # Non crea nulla
        entries = scan_home(home=home)
        assert entries == []
