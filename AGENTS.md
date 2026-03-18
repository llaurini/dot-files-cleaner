# AGENTS.md — Guide for AI Coding Agents

This file documents the project structure, conventions, and workflows that an AI coding agent must follow when working on **dot-net-files-cleaner**.

---

## Project overview

`dot-net-files-cleaner` is a Python TUI application that:

1. Scans dot files and directories in the user's home (`~/.*` and `~/.config/*`)
2. Maps each entry to its Debian/Ubuntu package(s)
3. Checks whether those packages are currently installed via `dpkg`
4. Presents results in an interactive terminal UI (Textual)
5. Allows moving selected orphaned entries to the FreeDesktop trash (`send2trash`)

Target system: **Debian/Ubuntu** (requires `dpkg-query`).

---

## Repository layout

```
dot-net-files-cleaner/
├── main.py                        # CLI entrypoint (--home, --version)
├── requirements.txt               # Python dependencies
├── AGENTS.md                      # This file
├── README.md                      # End-user documentation
└── dotcleaner/
    ├── __init__.py
    ├── scanner.py                 # Scans ~/. and ~/.config; DotEntry dataclass
    ├── checker.py                 # PackageChecker: wraps dpkg-query + which fallback
    ├── mapper.py                  # 3-phase mapping: DB → .desktop → heuristic
    ├── cleaner.py                 # send2trash wrapper: trash_entries(), get_trash_size()
    ├── app.py                     # Textual TUI: DataTable, ConfirmScreen, ResultScreen
    └── data/
        └── known_packages.json    # 492 verified dot-name → [pkg, ...] mappings
```

---

## Module responsibilities

### `scanner.py`
- Defines `DotEntry` (dataclass): `path`, `name`, `is_dir`, `size_bytes`, `source`, `associated_packages`, `installed_packages`, `uninstalled_packages`, `status`, `size_human`, `display_path`.
- `scan_home(home: Path | None) -> list[DotEntry]` — main entry point.
- Scans `~/.*` (first level) and `~/.config/*` (first level).
- Skips entries in `ALWAYS_EXCLUDE` (security-critical: `.ssh`, `.gnupg`, etc.) and `CONFIG_SYSTEM_EXCLUDE` (desktop-critical: `dconf`, `mimeapps.list`, `autostart`, etc.).
- Single files are only included if listed in `INCLUDE_SINGLE_FILES`.
- Calculates recursive directory sizes (follows no symlinks for the size walk).
- **Never** modify `ALWAYS_EXCLUDE` to include entries that may vary per user. If a new system-level path needs excluding, add it to `CONFIG_SYSTEM_EXCLUDE`.

### `checker.py`
- `PackageChecker` class loads the full installed-package list once via `dpkg-query`.
- `is_installed_dpkg(pkg)` — O(1) frozenset lookup.
- `is_binary_available(binary)` — `shutil.which` fallback for snap/flatpak/AppImage.
- `check_packages(names) -> (installed, uninstalled)` — applies both strategies.
- `find_matching_packages(name)` — token-level substring search (no false positives from partial matches inside longer tokens).
- `get_checker()` — singleton factory.

### `mapper.py`
- `map_entries(entries, checker) -> list[DotEntry]` — populates `associated_packages`, `installed_packages`, `uninstalled_packages`, `match_source` on each entry.
- Three phases per entry:
  1. **Database lookup** via `known_packages.json`, using `_derive_variants()` to try suffixless forms (`rc`, `.conf`, `.json`, `.bak`) and `org.vendor.App` patterns.
  2. **`.desktop` file lookup** — scans `/usr/share/applications` for a matching `.desktop` file and extracts the owning package via `dpkg -S`.
  3. **Heuristic** — `checker.find_matching_packages(normalized_name)`.
- `_normalize(name)` strips leading `.`, lowercases, and replaces `_` / spaces with `-`.
- **Do not** use simple substring matching (`"micro" in "microsoft-edge-beta"`); always use token-level matching.

### `cleaner.py`
- `trash_entries(entries) -> dict[str, bool]` — moves each entry to the FreeDesktop trash via `send2trash`. Returns `{path_str: success}`.
- `get_trash_size() -> int` — returns current trash size in bytes.
- `CleanError` — custom exception for failed trash operations.
- **Never** use `shutil.rmtree` or `os.remove` for deletion. Always use `send2trash`.

### `app.py`
- Textual `App` subclass `DotCleanerApp(home: Path)`.
- Screens: `LoadingScreen` → `MainScreen`. Modal: `ConfirmScreen`, `ResultScreen`.
- Key bindings (defined in `BINDINGS`):

| Key | Action |
|-----|--------|
| `Space` / `Enter` | Toggle selection on focused row |
| `A` | Select all uninstalled entries |
| `D` | Delete (trash) selected entries |
| `1` | Filter: All |
| `2` | Filter: Uninstalled only |
| `3` | Filter: Installed only |
| `4` | Filter: Unknown only |
| `R` | Reload / rescan |
| `Q` | Quit |

- Row colors: red = uninstalled, yellow = unknown, green = installed.
- Loading is done in a `@work` worker to keep the UI responsive.

### `data/known_packages.json`
- Maps normalized dot-entry names to lists of Debian package names.
- Keys beginning with `_` are treated as comments/metadata and ignored.
- All mappings must be **verified** against the actual system (`dpkg -l <pkg>`).
- When adding new entries, prefer the most specific package name (e.g. `pidgin` over `libpurple0`).
- KDE rc files follow the pattern `<app>rc` → strip `rc` → package is usually `<app>` or `kde-<app>`.

---

## Development environment

```bash
# Create and activate virtualenv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the TUI
./venv/bin/python main.py

# Run against a specific home directory (for testing)
./venv/bin/python main.py --home /tmp/fake-home

# Check version
./venv/bin/python main.py --version
```

Python **3.10+** is required (uses `X | Y` union syntax in type hints).

---

## Documentation and tests policy

**Every code change must be accompanied by:**

1. **Documentation update** — update `README.md` and/or the relevant module docstrings to reflect any change in behaviour, public API, CLI flags, key bindings, or configuration format. If a new module or public function is added, document it in this file under [Module responsibilities](#module-responsibilities) as well.
2. **Test update** — add or update tests to cover the changed behaviour. New functions must have at least one unit test. Bug fixes must include a regression test. Tests must pass before committing.

Changes that touch only comments, formatting, or this `AGENTS.md` file are exempt.

---

## Conventions

### Code style
- Follow **PEP 8**. Use `black` formatting if available.
- All public functions and classes must have docstrings.
- Type hints are required on all function signatures.
- Use `from __future__ import annotations` at the top of every module.
- **mypy** is used for static type checking with `strict = True`. Every code change must leave `mypy` error-free. Run it with:
  ```bash
  ./venv/bin/python -m mypy dotcleaner/ main.py tests/
  ```
  `mypy` is a dev dependency (listed in `requirements-dev.txt`).

### Adding a new package mapping
1. Verify the package exists: `dpkg -l <package-name>`
2. Add the entry to `dotcleaner/data/known_packages.json` using the normalized dot-name as key.
3. If multiple packages could own the dot entry, list all of them — the checker will mark the entry installed if any one is installed.

### Adding a new exclusion
- If the entry is a security-sensitive path (keys, certificates, auth tokens): add to `ALWAYS_EXCLUDE` in `scanner.py`.
- If the entry is a desktop-system file (display config, MIME associations, autostart): add to `CONFIG_SYSTEM_EXCLUDE` in `scanner.py`.
- Document the reason in a comment on the same line.

### Modifying the TUI
- CSS is embedded in `app.py` in the `CSS` constant. Keep it there — do not create external `.tcss` files unless the CSS grows beyond ~150 lines.
- All user-facing strings should be in English.
- Do not add persistent storage (no SQLite, no config files written to disk by the app itself).

---

## Key invariants (never break these)

1. **No permanent deletion** — always use `send2trash`. Never call `shutil.rmtree` or `os.remove` on user data.
2. **`ALWAYS_EXCLUDE` is sacred** — `.ssh` and `.gnupg` must never be scanned or shown to the user.
3. **No false positives in package matching** — substring match must be token-level only (split on `-`, `_`, `.`).
4. **Scan is read-only** — `scan_home()` and `map_entries()` must never modify the filesystem.
5. **No network access** — all package lookups use local `dpkg` only. No HTTP calls.

---

## Running checks before committing

```bash
# Type checking (must return 0 errors)
./venv/bin/python -m mypy dotcleaner/ main.py tests/

# Import sanity check
./venv/bin/python -c "from dotcleaner.app import DotCleanerApp; print('OK')"

# Quick scan smoke test
./venv/bin/python -c "
from dotcleaner.scanner import scan_home
from dotcleaner.checker import PackageChecker
from dotcleaner.mapper import map_entries
entries = map_entries(scan_home(), PackageChecker())
counts = {s: sum(1 for e in entries if e.status == s) for s in ('installed','uninstalled','unknown')}
print(counts)
assert sum(counts.values()) == len(entries)
print('smoke test passed')
"
```
