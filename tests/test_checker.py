"""
test_checker.py - Test funzionali per dotcleaner/checker.py

Testa PackageChecker con subprocess mockato per evitare dipendenza da dpkg.
"""

from __future__ import annotations

from typing import Callable
from unittest.mock import MagicMock, patch

import pytest

from dotcleaner.checker import PackageChecker, get_checker


# ---------------------------------------------------------------------------
# Helpers per costruire output dpkg-query fittizio
# ---------------------------------------------------------------------------


def _dpkg_query_output(packages: list[str]) -> str:
    """
    Genera output del formato 'dpkg-query -f ${Package}\\n${Status}\\n -W *'
    per una lista di pacchetti.
    """
    lines = []
    for pkg in packages:
        lines.append(pkg)
        lines.append("install ok installed")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fixture: checker con pacchetti iniettati
# ---------------------------------------------------------------------------


@pytest.fixture()
def checker_with_packages() -> Callable[[list[str]], PackageChecker]:
    """
    Ritorna una factory che crea un PackageChecker con pacchetti specificati,
    senza invocare dpkg reale.

    Utilizzo:
        checker = checker_with_packages(["vim", "git", "python3"])
    """

    def _factory(installed_list: list[str]) -> PackageChecker:
        checker = PackageChecker()
        checker._installed = frozenset(p.lower() for p in installed_list)
        checker._loaded = True
        return checker

    return _factory


# ---------------------------------------------------------------------------
# Test: load() via dpkg-query mockato
# ---------------------------------------------------------------------------


class TestPackageCheckerLoad:
    """Test del caricamento dei pacchetti via dpkg-query."""

    def test_load_parses_dpkg_query_output(self) -> None:
        """load() deve parsare correttamente l'output di dpkg-query."""
        fake_output = _dpkg_query_output(["vim", "git", "zsh"])
        mock_result = MagicMock()
        mock_result.stdout = fake_output

        with patch("subprocess.run", return_value=mock_result):
            checker = PackageChecker()
            checker.load()

        assert "vim" in checker.installed_packages
        assert "git" in checker.installed_packages
        assert "zsh" in checker.installed_packages

    def test_load_excludes_deinstalled_packages(self) -> None:
        """load() non include pacchetti non installati."""
        fake_output = "vim\ninstall ok installed\ngit\ndeinstall ok config-files\n"
        mock_result = MagicMock()
        mock_result.stdout = fake_output

        with patch("subprocess.run", return_value=mock_result):
            checker = PackageChecker()
            checker.load()

        assert "vim" in checker.installed_packages
        assert "git" not in checker.installed_packages

    def test_load_normalizes_to_lowercase(self) -> None:
        """I nomi pacchetti sono normalizzati in lowercase."""
        fake_output = "VIM\ninstall ok installed\n"
        mock_result = MagicMock()
        mock_result.stdout = fake_output

        with patch("subprocess.run", return_value=mock_result):
            checker = PackageChecker()
            checker.load()

        assert "vim" in checker.installed_packages

    def test_load_fallback_on_dpkg_get_selections(self) -> None:
        """Se dpkg-query non restituisce risultati, usa dpkg --get-selections."""
        empty_result = MagicMock()
        empty_result.stdout = ""

        fallback_result = MagicMock()
        fallback_result.stdout = "vim\tinstall\ngit\tinstall\n"

        with patch("subprocess.run", side_effect=[empty_result, fallback_result]):
            checker = PackageChecker()
            checker.load()

        assert "vim" in checker.installed_packages
        assert "git" in checker.installed_packages

    def test_load_graceful_on_file_not_found(self) -> None:
        """Se dpkg non esiste, installed_packages è frozenset vuoto."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            checker = PackageChecker()
            checker.load()

        assert checker.installed_packages == frozenset()

    def test_load_graceful_on_timeout(self) -> None:
        """Se dpkg va in timeout, installed_packages è frozenset vuoto."""
        import subprocess

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="dpkg-query", timeout=30),
        ):
            checker = PackageChecker()
            checker.load()

        assert checker.installed_packages == frozenset()

    def test_installed_packages_lazy_loads(self) -> None:
        """installed_packages chiama load() automaticamente se non ancora caricato."""
        fake_output = _dpkg_query_output(["vim"])
        mock_result = MagicMock()
        mock_result.stdout = fake_output

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            checker = PackageChecker()
            assert not checker._loaded
            _ = checker.installed_packages
            assert checker._loaded
            mock_run.assert_called()


# ---------------------------------------------------------------------------
# Test: is_installed_dpkg
# ---------------------------------------------------------------------------


class TestIsInstalledDpkg:
    """Test di is_installed_dpkg()."""

    def test_returns_true_for_installed_package(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        checker = checker_with_packages(["vim", "git"])
        assert checker.is_installed_dpkg("vim") is True

    def test_returns_false_for_missing_package(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        checker = checker_with_packages(["vim"])
        assert checker.is_installed_dpkg("zoom") is False

    def test_case_insensitive(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """La verifica è case-insensitive."""
        checker = checker_with_packages(["vim"])
        assert checker.is_installed_dpkg("VIM") is True
        assert checker.is_installed_dpkg("Vim") is True

    def test_empty_packages_returns_false(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        checker = checker_with_packages([])
        assert checker.is_installed_dpkg("vim") is False


# ---------------------------------------------------------------------------
# Test: is_binary_available
# ---------------------------------------------------------------------------


class TestIsBinaryAvailable:
    """Test di is_binary_available()."""

    def test_returns_true_for_existing_binary(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Se il binario è nel PATH, ritorna True."""
        checker = checker_with_packages([])
        with patch("shutil.which", return_value="/usr/bin/vim"):
            assert checker.is_binary_available("vim") is True

    def test_returns_false_for_missing_binary(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Se il binario non è nel PATH, ritorna False."""
        checker = checker_with_packages([])
        with patch("shutil.which", return_value=None):
            assert checker.is_binary_available("nonexistent-app") is False


# ---------------------------------------------------------------------------
# Test: check_packages
# ---------------------------------------------------------------------------


class TestCheckPackages:
    """Test di check_packages()."""

    def test_splits_installed_and_uninstalled(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        checker = checker_with_packages(["vim", "git"])
        installed, uninstalled = checker.check_packages(
            ["vim", "git", "zoom", "nonexistent"]
        )
        assert "vim" in installed
        assert "git" in installed
        assert "zoom" in uninstalled
        assert "nonexistent" in uninstalled

    def test_all_installed(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        checker = checker_with_packages(["vim", "git"])
        installed, uninstalled = checker.check_packages(["vim", "git"])
        assert installed == ["vim", "git"]
        assert uninstalled == []

    def test_all_uninstalled(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        checker = checker_with_packages(["vim"])
        installed, uninstalled = checker.check_packages(["zoom", "slack"])
        assert installed == []
        assert "zoom" in uninstalled
        assert "slack" in uninstalled

    def test_empty_input_returns_empty_lists(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        checker = checker_with_packages(["vim"])
        installed, uninstalled = checker.check_packages([])
        assert installed == []
        assert uninstalled == []

    def test_binary_fallback_marks_as_installed(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Un pacchetto non in dpkg ma con binario nel PATH è 'installed'."""
        checker = checker_with_packages([])  # dpkg vuoto
        with patch("shutil.which", return_value="/snap/bin/zoom"):
            installed, uninstalled = checker.check_packages(["zoom"])
        assert "zoom" in installed
        assert uninstalled == []


# ---------------------------------------------------------------------------
# Test: find_matching_packages — token-level matching (no falsi positivi)
# ---------------------------------------------------------------------------


class TestFindMatchingPackages:
    """
    Test critico: verifica che find_matching_packages usi token-level matching
    e non il semplice substring matching.
    """

    def test_exact_name_matches(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        checker = checker_with_packages(["vim", "git", "python3"])
        result = checker.find_matching_packages("vim")
        assert "vim" in result

    def test_name_as_first_token_matches(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """'vim' dovrebbe trovare 'vim-tiny', 'vim-gtk3' ecc. tramite token base."""
        checker = checker_with_packages(["vim-tiny", "vim-gtk3", "vim-nox"])
        result = checker.find_matching_packages("vim")
        assert "vim-tiny" in result or "vim-gtk3" in result or "vim-nox" in result

    def test_no_false_positive_micro_in_microsoft(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """
        'micro' NON deve trovare 'microsoft-edge-beta'.
        Questo è l'invariante critico anti-falsi-positivi.
        """
        checker = checker_with_packages(
            ["microsoft-edge-beta", "microsoft-edge-stable"]
        )
        result = checker.find_matching_packages("micro")
        assert "microsoft-edge-beta" not in result
        assert "microsoft-edge-stable" not in result

    def test_no_false_positive_git_in_gitk(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """'git' come token esatto non deve matchare 'gitk' (diverso token)."""
        checker = checker_with_packages(["gitk", "git-core"])
        result = checker.find_matching_packages("git")
        # 'gitk' ha token base 'gitk', non 'git'
        assert "gitk" not in result
        # 'git-core' ha 'git' come token, quindi DEVE matchare
        assert "git-core" in result

    def test_returns_sorted_list(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        checker = checker_with_packages(
            ["zsh-syntax-highlighting", "zsh-autosuggestions", "zsh"]
        )
        result = checker.find_matching_packages("zsh")
        assert result == sorted(result)

    def test_empty_packages_returns_empty(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        checker = checker_with_packages([])
        result = checker.find_matching_packages("vim")
        assert result == []


# ---------------------------------------------------------------------------
# Test: singleton get_checker
# ---------------------------------------------------------------------------


class TestGetChecker:
    """Test del singleton get_checker()."""

    def test_get_checker_returns_same_instance(self) -> None:
        """get_checker() ritorna sempre la stessa istanza."""
        import dotcleaner.checker as checker_module

        # Reset del singleton per isolamento test
        checker_module._checker = None
        a = get_checker()
        b = get_checker()
        assert a is b

    def test_get_checker_returns_package_checker(self) -> None:
        """get_checker() ritorna un'istanza di PackageChecker."""
        import dotcleaner.checker as checker_module

        checker_module._checker = None
        checker = get_checker()
        assert isinstance(checker, PackageChecker)
