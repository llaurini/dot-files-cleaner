"""
mapper.py - Associa i dot entries ai pacchetti Debian corrispondenti.

Strategia in tre fasi:
1. Database predefinito (known_packages.json): match esatto o su varianti normalizzate
2. Rilevamento tramite .desktop file: cerca l'app nei file .desktop di sistema
3. Euristica dpkg: cerca il nome normalizzato tra i pacchetti installati
"""

from __future__ import annotations

import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dotcleaner.scanner import DotEntry
    from dotcleaner.checker import PackageChecker

# Percorso del database di mapping
_DB_PATH = Path(__file__).parent / "data" / "known_packages.json"

# Cache del database
_db: dict[str, list[str]] | None = None

# Directory dove si trovano i file .desktop
_DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local" / "share" / "applications",
]


def _load_db() -> dict[str, list[str]]:
    """Carica il database di mapping da JSON."""
    global _db
    if _db is None:
        with _DB_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        # Rimuovi chiavi che iniziano con '_' (commenti/metadati)
        _db = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _db


def _normalize(name: str) -> str:
    """
    Normalizza un nome per il confronto:
    - lowercase
    - rimuove il prefisso '.'
    - sostituisce underscore/spazi con '-'
    """
    n = name.lower().lstrip(".")
    n = re.sub(r"[_\s]+", "-", n)
    return n


def _derive_variants(normalized_name: str) -> list[str]:
    """
    Genera varianti del nome normalizzato da provare nel database.
    Gestisce pattern comuni come:
    - konsolerc -> konsole (suffisso rc)
    - kmail2rc  -> kmail (suffisso numerico + rc)
    - color.jcnf -> color (estensione)
    - kwinrc.bak -> kwinrc -> kwin (backup + rc)
    - org.kde.something -> something
    - plasmadiscoverupdates -> plasmadiscover -> discover
    """
    variants = [normalized_name]
    n = normalized_name

    # Rimuovi estensioni comuni: .conf, .ini, .json, .bak, .old, .jcnf, .binrc
    n_stripped = re.sub(r"\.(conf|ini|json|bak|old|jcnf|binrc|pma|asp|cer)$", "", n)
    if n_stripped != n:
        variants.append(n_stripped)
        n = n_stripped

    # Rimuovi suffisso rc (con eventuale numero prima: kmail2rc -> kmail)
    if n.endswith("rc"):
        without_rc = n[:-2]
        variants.append(without_rc)
        # Rimuovi anche eventuale numero finale: kmail2 -> kmail
        without_num = re.sub(r"\d+$", "", without_rc)
        if without_num != without_rc:
            variants.append(without_num)

    # Gestisci pattern "org.vendor.AppName" -> "appname"
    if n.count(".") >= 2:
        last_part = n.rsplit(".", 1)[-1]
        if len(last_part) >= 3:
            variants.append(last_part)

    # Rimuovi suffissi numerici (es. gimp-2.8 -> gimp, kwin-x11 -> kwin)
    without_num_suffix = re.sub(r"[-_.]\d+.*$", "", n)
    if without_num_suffix != n and len(without_num_suffix) >= 3:
        variants.append(without_num_suffix)

    # Rimuovi .old e .bak come suffissi di directory
    for suffix in ("-old", "-bak", ".old", ".bak"):
        if n.endswith(suffix):
            variants.append(n[: -len(suffix)])

    return variants


@lru_cache(maxsize=512)
def _lookup_database_cached(normalized_name: str) -> tuple[str, ...] | None:
    """Versione cached di _lookup_database. Ritorna tuple per essere hashable."""
    result = _lookup_database(normalized_name)
    return tuple(result) if result is not None else None


def _lookup_database(normalized_name: str) -> list[str] | None:
    """
    Cerca il nome normalizzato nel database.
    Prova multiple varianti del nome.

    Returns:
        Lista di pacchetti se trovato, None altrimenti.
    """
    db = _load_db()
    variants = _derive_variants(normalized_name)

    for variant in variants:
        # 1. Match esatto
        if variant in db:
            return db[variant]

        # 2. Match come prefisso token: "konsole-ssh-config" -> "konsole"
        for key, packages in db.items():
            if len(key) < 3:
                continue
            if variant == key or variant.startswith(key + "-"):
                return packages

        # 3. Match inverso: chiave è un token intero nel nome
        #    Es. "plasma-discover-updates" contiene token "plasma-discover"
        #    ma NON "micro" dentro "microsoft-edge-beta"
        name_tokens = set(re.split(r"[-_.]", variant))
        # Anche token composti (es. "plasma-discover")
        name_bigrams = set()
        parts = re.split(r"[-_.]", variant)
        for i in range(len(parts) - 1):
            name_bigrams.add(f"{parts[i]}-{parts[i+1]}")

        for key, packages in db.items():
            key_tokens = set(re.split(r"[-_.]", key))
            if len(key) >= 4:
                # Match se la chiave è un token esatto O un bigramma del nome
                if key in name_tokens or key in name_bigrams:
                    return packages
                # Match se tutti i token della chiave sono presenti nel nome
                if len(key_tokens) >= 2 and key_tokens.issubset(name_tokens | name_bigrams):
                    return packages

    return None


@lru_cache(maxsize=256)
def _find_desktop_package(app_name: str) -> str | None:
    """
    Cerca nei file .desktop di sistema se esiste un'applicazione con
    questo nome e trova il pacchetto Debian che la fornisce.

    Args:
        app_name: Nome normalizzato dell'applicazione.

    Returns:
        Nome del pacchetto Debian o None.
    """
    # Genera possibili nomi di file .desktop da cercare
    desktop_candidates = [
        f"{app_name}.desktop",
        f"org.kde.{app_name}.desktop",
        f"org.gnome.{app_name}.desktop",
        f"com.{app_name}.{app_name}.desktop",
    ]

    for desktop_dir in _DESKTOP_DIRS:
        if not desktop_dir.is_dir():
            continue
        for candidate in desktop_candidates:
            desktop_file = desktop_dir / candidate
            if desktop_file.exists():
                # Trovato il .desktop: cerca il pacchetto con dpkg -S
                try:
                    result = subprocess.run(
                        ["dpkg", "-S", str(desktop_file)],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        pkg = result.stdout.split(":")[0].strip()
                        if pkg:
                            return pkg
                except (subprocess.TimeoutExpired, OSError):
                    pass

        # Ricerca parziale: cerca file .desktop che contengono app_name nel nome
        try:
            for df in desktop_dir.iterdir():
                if app_name in df.name.lower() and df.suffix == ".desktop":
                    try:
                        result = subprocess.run(
                            ["dpkg", "-S", str(df)],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if result.returncode == 0:
                            pkg = result.stdout.split(":")[0].strip()
                            if pkg:
                                return pkg
                    except (subprocess.TimeoutExpired, OSError):
                        pass
        except OSError:
            pass

    return None


def _heuristic_lookup(normalized_name: str, checker: PackageChecker) -> list[str]:
    """
    Cerca pacchetti installati che corrispondono euristicamente al nome.

    Strategia:
    1. Verifica se esiste un .desktop file e da quale pacchetto proviene
    2. Il nome stesso come nome di pacchetto dpkg
    3. La prima parola del nome come pacchetto dpkg
    4. Ricerca per sottostringa tra i pacchetti installati

    Returns:
        Lista di pacchetti trovati (può essere vuota).
    """
    candidates: list[str] = []
    variants = _derive_variants(normalized_name)

    for variant in variants:
        # 1. Cerca via .desktop file (solo per varianti senza 'rc')
        if not variant.endswith("rc"):
            desktop_pkg = _find_desktop_package(variant)
            if desktop_pkg and desktop_pkg not in candidates:
                candidates.append(desktop_pkg)
                return candidates  # Alta confidenza

        # 2. Il nome stesso come pacchetto
        if checker.is_installed_dpkg(variant):
            if variant not in candidates:
                candidates.append(variant)
            return candidates

        # 3. Prima parola come pacchetto
        first_word = variant.split("-")[0]
        if len(first_word) >= 3 and checker.is_installed_dpkg(first_word):
            if first_word not in candidates:
                candidates.append(first_word)
            return candidates

    # 4. Ricerca per sottostringa come ultima risorsa
    #    Usa solo il nome principale (prima variante senza 'rc')
    search_name = variants[0]
    if search_name.endswith("rc"):
        search_name = search_name[:-2]

    if len(search_name) >= 5:  # Evita match troppo generici
        matches = checker.find_matching_packages(search_name)
        for m in matches:
            if m not in candidates:
                candidates.append(m)

    return candidates[:5]  # Limita a 5 candidati per non intasare la UI


def map_entries(entries: list[DotEntry], checker: PackageChecker) -> list[DotEntry]:
    """
    Associa ogni DotEntry ai pacchetti Debian corrispondenti.
    Popola i campi:
      - associated_packages
      - match_source
      - installed_packages
      - uninstalled_packages

    Args:
        entries: Lista di DotEntry da processare.
        checker: Istanza di PackageChecker con pacchetti già caricati.

    Returns:
        La stessa lista con i campi popolati.
    """
    for entry in entries:
        normalized = _normalize(entry.name)

        # Fase 1: database predefinito
        db_packages = _lookup_database(normalized)
        if db_packages:
            entry.associated_packages = list(db_packages)
            entry.match_source = "database"
        else:
            # Fase 2: euristica (desktop file + dpkg)
            heuristic_packages = _heuristic_lookup(normalized, checker)
            if heuristic_packages:
                entry.associated_packages = heuristic_packages
                entry.match_source = "heuristic"
            else:
                entry.associated_packages = []
                entry.match_source = "unknown"

        # Verifica stato installazione
        if entry.associated_packages:
            installed, uninstalled = checker.check_packages(entry.associated_packages)
            entry.installed_packages = installed
            entry.uninstalled_packages = uninstalled
        else:
            entry.installed_packages = []
            entry.uninstalled_packages = []

    return entries
