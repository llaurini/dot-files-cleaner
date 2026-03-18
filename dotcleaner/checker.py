"""Package-installation checker for Debian/Ubuntu systems.

Loads the full list of installed packages once via ``dpkg-query``, then
offers O(1) membership tests.  Falls back to ``shutil.which`` for packages
distributed as snap, flatpak, or AppImage that are not tracked by dpkg.
"""

from __future__ import annotations

import re
import shutil
import subprocess


class PackageChecker:
    """Verify which Debian packages are installed on the current system.

    The package list is loaded lazily on first access and cached for the
    lifetime of the instance.  Use ``get_checker()`` to obtain a process-wide
    singleton.
    """

    def __init__(self) -> None:
        """Initialise PackageChecker with an empty, unloaded package set."""
        self._installed: frozenset[str] = frozenset()
        self._loaded = False

    def load(self) -> None:
        r"""Load all installed packages via dpkg-query.

        Tries ``dpkg-query -f ${Package}\n${Status}\n -W *`` first, then
        falls back to ``dpkg --get-selections`` if the first command returns
        no results.  Errors (missing binary, timeout) are silently ignored and
        result in an empty package set.

        Returns:
            None.
        """
        packages: set[str] = set()

        try:
            result = subprocess.run(
                ["dpkg-query", "-f", "${Package}\\n${Status}\\n", "-W", "*"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Il formato è:
            #   package-name
            #   install ok installed
            #   ...
            lines = result.stdout.splitlines()
            i = 0
            while i < len(lines) - 1:
                pkg_name = lines[i].strip()
                status_line = lines[i + 1].strip()
                if status_line.endswith("installed") and pkg_name:
                    packages.add(pkg_name.lower())
                i += 2
        except (
            subprocess.TimeoutExpired,
            FileNotFoundError,
            subprocess.SubprocessError,
        ):
            # dpkg non disponibile: fallback vuoto
            pass

        # Tenta anche con 'dpkg --get-selections' come alternativa
        if not packages:
            try:
                result = subprocess.run(
                    ["dpkg", "--get-selections"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "install":
                        # Rimuovi l'eventuale ':arch' suffix
                        pkg = parts[0].split(":")[0].lower()
                        packages.add(pkg)
            except (
                subprocess.TimeoutExpired,
                FileNotFoundError,
                subprocess.SubprocessError,
            ):
                pass

        self._installed = frozenset(packages)
        self._loaded = True

    @property
    def installed_packages(self) -> frozenset[str]:
        """Return the set of all installed package names in lowercase.

        Triggers ``load()`` automatically on first access if the package list
        has not been loaded yet.

        Returns:
            A frozenset of lowercase package name strings.
        """
        if not self._loaded:
            self.load()
        return self._installed

    def is_installed_dpkg(self, package_name: str) -> bool:
        """Check whether a package is installed according to dpkg.

        Args:
            package_name: Debian package name to look up (case-insensitive).

        Returns:
            True if the package is currently installed.
        """
        return package_name.lower() in self.installed_packages

    def is_binary_available(self, binary_name: str) -> bool:
        """Check whether a binary is available on the system PATH.

        Useful as a fallback for snap, AppImage, and other non-dpkg
        distributions.

        Args:
            binary_name: Binary name to search for (e.g. 'firefox', 'code').

        Returns:
            True if the binary is found anywhere on PATH.
        """
        return shutil.which(binary_name) is not None

    def check_packages(self, package_names: list[str]) -> tuple[list[str], list[str]]:
        """Split a list of package names into installed and uninstalled groups.

        Each name is checked first via dpkg, then via binary availability on
        PATH (snap/flatpak/AppImage fallback).

        Args:
            package_names: List of Debian package names to check.

        Returns:
            A tuple ``(installed, uninstalled)`` containing two lists of
            package names.
        """
        installed: list[str] = []
        uninstalled: list[str] = []

        for pkg in package_names:
            pkg_lower = pkg.lower()
            if self.is_installed_dpkg(pkg_lower):
                installed.append(pkg)
            elif self.is_binary_available(pkg_lower):
                # Il binario esiste (snap, flatpak, AppImage, ecc.)
                installed.append(pkg)
            else:
                uninstalled.append(pkg)

        return installed, uninstalled

    def find_matching_packages(self, name: str) -> list[str]:
        """Find installed packages whose name contains *name* as a token.

        Uses token-level matching (splitting on ``-``, ``_``, ``.``) to avoid
        false positives such as matching 'micro' inside 'microsoft-edge-beta'.

        Args:
            name: Token string to search for among installed package names.

        Returns:
            Sorted list of installed packages that contain *name* as an exact
            token or as the base (first) token of their name.
        """
        name_lower = name.lower()
        matches = []
        for pkg in self.installed_packages:
            # Match esatto o come prefisso/suffisso del nome pacchetto
            pkg_base = re.split(r"[-_.]", pkg)[0]  # prima parte del nome
            if pkg_base == name_lower or pkg == name_lower:
                matches.append(pkg)
            elif name_lower in pkg.split("-") or name_lower in pkg.split("_"):
                matches.append(pkg)
        return sorted(matches)


# Istanza singleton
_checker: PackageChecker | None = None


def get_checker() -> PackageChecker:
    """Return the process-wide singleton instance of PackageChecker.

    Creates the instance on first call; subsequent calls return the same
    object without reloading the package list.

    Returns:
        The singleton ``PackageChecker`` instance.
    """
    global _checker
    if _checker is None:
        _checker = PackageChecker()
    return _checker
