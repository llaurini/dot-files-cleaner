"""
checker.py - Verifica quali pacchetti Debian sono installati nel sistema.

Carica l'elenco completo dei pacchetti installati tramite dpkg-query una sola volta,
e offre un metodo rapido per controllare se un dato pacchetto è installato.
Come fallback per pacchetti non-dpkg (snap, AppImage, pip, ecc.)
verifica anche la presenza del binario nel PATH tramite 'which'.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import lru_cache


class PackageChecker:
    """Gestisce la verifica dei pacchetti installati."""

    def __init__(self) -> None:
        self._installed: frozenset[str] = frozenset()
        self._loaded = False

    def load(self) -> None:
        """
        Carica tutti i pacchetti installati tramite dpkg-query.
        Deve essere chiamato una volta prima di usare is_installed().
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
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
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
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
                pass

        self._installed = frozenset(packages)
        self._loaded = True

    @property
    def installed_packages(self) -> frozenset[str]:
        """Set di tutti i pacchetti installati (nomi in lowercase)."""
        if not self._loaded:
            self.load()
        return self._installed

    def is_installed_dpkg(self, package_name: str) -> bool:
        """
        Controlla se il pacchetto è installato tramite dpkg.

        Args:
            package_name: Nome del pacchetto Debian (case-insensitive).

        Returns:
            True se il pacchetto è installato.
        """
        return package_name.lower() in self.installed_packages

    def is_binary_available(self, binary_name: str) -> bool:
        """
        Controlla se un binario è disponibile nel PATH di sistema.
        Utile come fallback per snap, AppImage, ecc.

        Args:
            binary_name: Nome del binario (es. 'firefox', 'code').

        Returns:
            True se il binario è trovato nel PATH.
        """
        return shutil.which(binary_name) is not None

    def check_packages(self, package_names: list[str]) -> tuple[list[str], list[str]]:
        """
        Data una lista di nomi di pacchetti, ritorna (installati, non_installati).

        Strategia:
        1. Controlla prima tramite dpkg
        2. Se non trovato via dpkg, controlla se esiste il binario nel PATH

        Args:
            package_names: Lista di nomi di pacchetti da controllare.

        Returns:
            Tupla (installed, uninstalled) con le liste di pacchetti.
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
        """
        Cerca pacchetti installati il cui nome contiene 'name' come sottostringa.
        Utile per l'euristica nel mapper.

        Args:
            name: Stringa da cercare nei nomi dei pacchetti.

        Returns:
            Lista di pacchetti installati che contengono 'name' nel nome.
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
    """Ritorna l'istanza singleton di PackageChecker."""
    global _checker
    if _checker is None:
        _checker = PackageChecker()
    return _checker
