# dot-files-cleaner

A terminal UI (TUI) for finding and removing orphaned dot files from your home directory on Debian/Ubuntu systems.

Over time, installing and uninstalling applications leaves behind configuration directories and files in `~/` and `~/.config/`. This tool scans those locations, maps each entry to its Debian package, checks whether that package is still installed, and lets you safely move orphaned entries to the trash.

---

## Features

- Scans `~/.*` and `~/.config/*` (first level)
- Maps each entry to its Debian/Ubuntu package(s) using a database of 492 verified mappings, `.desktop` file lookup, and a heuristic fallback
- Checks installation status via `dpkg-query` with a `which`-based fallback for snap/flatpak/AppImage packages
- Interactive table with color-coded status (red = uninstalled, yellow = unknown, green = installed)
- Displays **last-modification** and **last-access** timestamps for each entry
- **Click any column header to sort** by that column; click again to reverse; click a third time to reset to default order
- Filter by status: All / Uninstalled / Installed / Unknown
- Select individual entries or select all uninstalled at once
- Moves selected entries to the FreeDesktop trash (`~/.local/share/Trash`) — **never permanent deletion**
- Shows entry sizes to help prioritize cleanup
- Never touches security-critical paths (`.ssh`, `.gnupg`, `.pki`)
- Never touches desktop-system files (`dconf`, `mimeapps.list`, `autostart`, etc.)

---

## Requirements

- **OS**: Debian or Ubuntu (requires `dpkg-query`)
- **Python**: 3.10 or newer
- **Dependencies**: `textual >= 0.47`, `send2trash`

---

## Installation

```bash
git clone https://github.com/youruser/dot-net-files-cleaner.git
cd dot-net-files-cleaner

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

```bash
# Scan your own home directory
./venv/bin/python main.py

# Scan a specific home directory (useful for testing)
./venv/bin/python main.py --home /path/to/home

# Show version
./venv/bin/python main.py --version
```

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Space` / `Enter` | Toggle selection on the focused row |
| `A` | Select all uninstalled entries |
| `D` | Move selected entries to trash |
| `1` | Show all entries |
| `2` | Show uninstalled only |
| `3` | Show installed only |
| `4` | Show unknown only |
| `R` | Reload / rescan |
| `Q` | Quit |

### Sorting

Click a **column header** to sort by that column. The active column shows a `▲` (ascending) or `▼` (descending) indicator. Clicking the same header a third time resets to the default order (uninstalled first, then unknown, then installed; alphabetical within each group). The checkbox column (`sel`) is not sortable.

---

## How it works

### Scanning

The scanner collects two sets of entries:

- `~/.*` — dot files and directories at the first level of the home directory
- `~/.config/*` — first-level entries inside `~/.config`

Certain paths are always excluded:

- **Security-critical** (`ALWAYS_EXCLUDE`): `.ssh`, `.gnupg`, `.pki`, `.Xauthority`, `.bash_history`, and similar — these are never shown.
- **Desktop-system** (`CONFIG_SYSTEM_EXCLUDE`): `dconf`, `mimeapps.list`, `autostart`, `gtk-3.0`, `pulse`, `systemd`, and similar — removing these would break the desktop environment.
- **Single files** are only included if explicitly listed (`.gitconfig`, `.vimrc`, `.zshrc`, etc.).

For each included directory, the size is computed recursively.  The
last-modification time (`st_mtime`) and last-access time (`st_atime`) of each
entry are also recorded at scan time and shown in the table as
**Ultima modifica** and **Ultimo accesso**.

### Package mapping

Each entry goes through three phases:

1. **Database lookup** — checks `data/known_packages.json` (492 verified mappings). Tries the exact normalized name and derived variants (strips `rc`, `.conf`, `.json`, `.bak` suffixes; handles `org.vendor.App` patterns).
2. **`.desktop` file lookup** — searches `/usr/share/applications` for a matching `.desktop` file and resolves the owning package via `dpkg -S`.
3. **Heuristic** — searches the list of installed packages for a token-level match against the normalized entry name (avoids false positives like matching `micro` inside `microsoft-edge-beta`).

### Installation check

- Primary: `dpkg-query` — loads all installed packages into a `frozenset` for O(1) lookup.
- Fallback: `shutil.which` — detects binaries installed outside dpkg (snap, flatpak, AppImage, manual installs).

### Deletion

Selected entries are moved to the FreeDesktop trash using `send2trash`. **No files are ever permanently deleted.**

---

## Project structure

```
dot-net-files-cleaner/
├── main.py                        # CLI entrypoint
├── requirements.txt
├── AGENTS.md                      # Guide for AI coding agents
└── dotcleaner/
    ├── scanner.py                 # Home directory scanner + DotEntry dataclass
    ├── checker.py                 # PackageChecker (dpkg + which)
    ├── mapper.py                  # 3-phase package mapper
    ├── cleaner.py                 # send2trash wrapper
    ├── app.py                     # Textual TUI
    └── data/
        └── known_packages.json    # Verified dot-name → package mappings
```

---

## Adding package mappings

If an entry shows as "unknown" and you know the owning package:

1. Verify the package name: `dpkg -l <package-name>`
2. Find the normalized key: strip the leading `.`, lowercase, replace `_`/spaces with `-`.
3. Add an entry to `dotcleaner/data/known_packages.json`:

```json
"app-name": ["package-name"]
```

Multiple packages are supported — the entry is marked installed if **any** of them is installed:

```json
"pgadmin": ["pgadmin4", "pgadmin3"]
```

---

## License

MIT
