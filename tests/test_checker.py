"""Functional tests for dotcleaner/checker.py.

Tests ``PackageChecker`` with a mocked ``subprocess`` to avoid any dependency
on a real ``dpkg`` installation.
"""

from __future__ import annotations

from typing import Callable
from unittest.mock import MagicMock, patch

import pytest

from dotcleaner.checker import PackageChecker, get_checker


# ---------------------------------------------------------------------------
# Helpers for building fake dpkg-query output
# ---------------------------------------------------------------------------


def _dpkg_query_output(packages: list[str]) -> str:
    """Generate fake output in the format produced by ``dpkg-query -f '${Package}\\n${Status}\\n' -W '*'``.

    Args:
        packages: List of package names to mark as installed.

    Returns:
        A newline-delimited string alternating package name and install status.
    """
    lines = []
    for pkg in packages:
        lines.append(pkg)
        lines.append("install ok installed")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fixture: checker with injected packages
# ---------------------------------------------------------------------------


@pytest.fixture()
def checker_with_packages() -> Callable[[list[str]], PackageChecker]:
    """Return a factory that creates a ``PackageChecker`` pre-loaded with specific packages.

    The returned factory bypasses the real ``dpkg`` invocation, making tests
    fully hermetic.

    Example::

        checker = checker_with_packages(["vim", "git", "python3"])

    Returns:
        A callable that accepts a list of installed package names and returns
        a pre-configured :class:`~dotcleaner.checker.PackageChecker`.
    """

    def _factory(installed_list: list[str]) -> PackageChecker:
        """Build a ``PackageChecker`` pre-loaded with the given installed packages.

        Args:
            installed_list: Package names to treat as installed.

        Returns:
            A ``PackageChecker`` instance with ``_loaded`` set to ``True``.
        """
        checker = PackageChecker()
        checker._installed = frozenset(p.lower() for p in installed_list)
        checker._loaded = True
        return checker

    return _factory


# ---------------------------------------------------------------------------
# Test: load() via mocked dpkg-query
# ---------------------------------------------------------------------------


class TestPackageCheckerLoad:
    """Tests for package loading via dpkg-query."""

    def test_load_parses_dpkg_query_output(self) -> None:
        """Asserts that load() correctly parses standard dpkg-query output."""
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
        """Asserts that load() omits packages with a deinstall status."""
        fake_output = "vim\ninstall ok installed\ngit\ndeinstall ok config-files\n"
        mock_result = MagicMock()
        mock_result.stdout = fake_output

        with patch("subprocess.run", return_value=mock_result):
            checker = PackageChecker()
            checker.load()

        assert "vim" in checker.installed_packages
        assert "git" not in checker.installed_packages

    def test_load_normalizes_to_lowercase(self) -> None:
        """Asserts that package names are stored in lowercase after load()."""
        fake_output = "VIM\ninstall ok installed\n"
        mock_result = MagicMock()
        mock_result.stdout = fake_output

        with patch("subprocess.run", return_value=mock_result):
            checker = PackageChecker()
            checker.load()

        assert "vim" in checker.installed_packages

    def test_load_fallback_on_dpkg_get_selections(self) -> None:
        """Asserts that load() falls back to dpkg --get-selections when dpkg-query returns nothing."""
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
        """Asserts that load() yields an empty frozenset when dpkg is not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            checker = PackageChecker()
            checker.load()

        assert checker.installed_packages == frozenset()

    def test_load_graceful_on_timeout(self) -> None:
        """Asserts that load() yields an empty frozenset when dpkg times out."""
        import subprocess

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="dpkg-query", timeout=30),
        ):
            checker = PackageChecker()
            checker.load()

        assert checker.installed_packages == frozenset()

    def test_installed_packages_lazy_loads(self) -> None:
        """Asserts that accessing installed_packages triggers an automatic load() call."""
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
    """Tests for is_installed_dpkg()."""

    def test_returns_true_for_installed_package(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that is_installed_dpkg returns True for a known-installed package."""
        checker = checker_with_packages(["vim", "git"])
        assert checker.is_installed_dpkg("vim") is True

    def test_returns_false_for_missing_package(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that is_installed_dpkg returns False for a package not in the installed set."""
        checker = checker_with_packages(["vim"])
        assert checker.is_installed_dpkg("zoom") is False

    def test_case_insensitive(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that the installed check is case-insensitive."""
        checker = checker_with_packages(["vim"])
        assert checker.is_installed_dpkg("VIM") is True
        assert checker.is_installed_dpkg("Vim") is True

    def test_empty_packages_returns_false(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that is_installed_dpkg returns False when no packages are loaded."""
        checker = checker_with_packages([])
        assert checker.is_installed_dpkg("vim") is False


# ---------------------------------------------------------------------------
# Test: is_binary_available
# ---------------------------------------------------------------------------


class TestIsBinaryAvailable:
    """Tests for is_binary_available()."""

    def test_returns_true_for_existing_binary(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that is_binary_available returns True when the binary is found in PATH."""
        checker = checker_with_packages([])
        with patch("shutil.which", return_value="/usr/bin/vim"):
            assert checker.is_binary_available("vim") is True

    def test_returns_false_for_missing_binary(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that is_binary_available returns False when the binary is not in PATH."""
        checker = checker_with_packages([])
        with patch("shutil.which", return_value=None):
            assert checker.is_binary_available("nonexistent-app") is False


# ---------------------------------------------------------------------------
# Test: check_packages
# ---------------------------------------------------------------------------


class TestCheckPackages:
    """Tests for check_packages()."""

    def test_splits_installed_and_uninstalled(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that check_packages correctly partitions installed and uninstalled packages."""
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
        """Asserts that check_packages returns all packages as installed when all are present."""
        checker = checker_with_packages(["vim", "git"])
        installed, uninstalled = checker.check_packages(["vim", "git"])
        assert installed == ["vim", "git"]
        assert uninstalled == []

    def test_all_uninstalled(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that check_packages returns all packages as uninstalled when none are present."""
        checker = checker_with_packages(["vim"])
        installed, uninstalled = checker.check_packages(["zoom", "slack"])
        assert installed == []
        assert "zoom" in uninstalled
        assert "slack" in uninstalled

    def test_empty_input_returns_empty_lists(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that check_packages returns two empty lists for an empty input."""
        checker = checker_with_packages(["vim"])
        installed, uninstalled = checker.check_packages([])
        assert installed == []
        assert uninstalled == []

    def test_binary_fallback_marks_as_installed(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that a package absent from dpkg but found via which is treated as installed."""
        checker = checker_with_packages([])  # empty dpkg
        with patch("shutil.which", return_value="/snap/bin/zoom"):
            installed, uninstalled = checker.check_packages(["zoom"])
        assert "zoom" in installed
        assert uninstalled == []


# ---------------------------------------------------------------------------
# Test: find_matching_packages — token-level matching (no false positives)
# ---------------------------------------------------------------------------


class TestFindMatchingPackages:
    """Critical tests verifying that find_matching_packages uses token-level matching.

    Simple substring matching (e.g. ``"micro" in "microsoft-edge-beta"``) must
    never produce false positives.  All matching must be done at the token
    boundary level (split on ``-``, ``_``, ``.``).
    """

    def test_exact_name_matches(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that an exact package name is returned as a match."""
        checker = checker_with_packages(["vim", "git", "python3"])
        result = checker.find_matching_packages("vim")
        assert "vim" in result

    def test_name_as_first_token_matches(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that a base name matches packages where it appears as a token (e.g. vim-tiny)."""
        checker = checker_with_packages(["vim-tiny", "vim-gtk3", "vim-nox"])
        result = checker.find_matching_packages("vim")
        assert "vim-tiny" in result or "vim-gtk3" in result or "vim-nox" in result

    def test_no_false_positive_micro_in_microsoft(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that 'micro' does not match 'microsoft-edge-beta' (critical anti-false-positive invariant)."""
        checker = checker_with_packages(
            ["microsoft-edge-beta", "microsoft-edge-stable"]
        )
        result = checker.find_matching_packages("micro")
        assert "microsoft-edge-beta" not in result
        assert "microsoft-edge-stable" not in result

    def test_no_false_positive_git_in_gitk(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that 'git' as an exact token does not match 'gitk' but does match 'git-core'."""
        checker = checker_with_packages(["gitk", "git-core"])
        result = checker.find_matching_packages("git")
        # 'gitk' has base token 'gitk', not 'git'
        assert "gitk" not in result
        # 'git-core' has 'git' as a token, so it MUST match
        assert "git-core" in result

    def test_returns_sorted_list(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that find_matching_packages returns results in sorted order."""
        checker = checker_with_packages(
            ["zsh-syntax-highlighting", "zsh-autosuggestions", "zsh"]
        )
        result = checker.find_matching_packages("zsh")
        assert result == sorted(result)

    def test_empty_packages_returns_empty(
        self, checker_with_packages: Callable[[list[str]], PackageChecker]
    ) -> None:
        """Asserts that an empty installed set yields an empty match list."""
        checker = checker_with_packages([])
        result = checker.find_matching_packages("vim")
        assert result == []


# ---------------------------------------------------------------------------
# Test: singleton get_checker
# ---------------------------------------------------------------------------


class TestGetChecker:
    """Tests for the get_checker() singleton factory."""

    def test_get_checker_returns_same_instance(self) -> None:
        """Asserts that successive calls to get_checker() return the identical instance."""
        import dotcleaner.checker as checker_module

        # Reset the singleton for test isolation
        checker_module._checker = None
        a = get_checker()
        b = get_checker()
        assert a is b

    def test_get_checker_returns_package_checker(self) -> None:
        """Asserts that get_checker() returns an instance of PackageChecker."""
        import dotcleaner.checker as checker_module

        checker_module._checker = None
        checker = get_checker()
        assert isinstance(checker, PackageChecker)
