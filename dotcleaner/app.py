"""Textual TUI for dot-net-files-cleaner.

Layout:
  - Header with title and active filter
  - DataTable listing all dot entries
  - Footer with keyboard shortcuts
  - Confirmation dialog before trashing entries
  - Initial loading screen while scanning runs in a background thread
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Middle, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    LoadingIndicator,
    Select,
)

from dotcleaner.checker import PackageChecker
from dotcleaner.cleaner import trash_entries
from dotcleaner.mapper import map_entries
from dotcleaner.scanner import DotEntry, scan_home

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
Screen {
    background: $surface;
}

#loading-screen {
    align: center middle;
}

#loading-screen LoadingIndicator {
    height: 3;
}

#loading-screen Label {
    text-align: center;
    color: $text-muted;
    margin-top: 1;
}

#main-screen {
    layout: vertical;
}

#toolbar {
    height: 3;
    background: $panel;
    align: left middle;
    padding: 0 2;
}

#toolbar Label {
    margin-right: 1;
    color: $text-muted;
}

#filter-select {
    width: 30;
    margin-right: 2;
}

#stats-label {
    color: $text-muted;
    text-align: right;
    width: 1fr;
}

#table-container {
    height: 1fr;
    border: tall $panel;
    margin: 0 1;
}

DataTable {
    height: 1fr;
}

DataTable > .datatable--header {
    background: $primary;
    color: $text;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: $accent;
    color: $text;
}

/* Row colors by status */
.row-uninstalled {
    color: $error;
}

.row-unknown {
    color: $warning;
}

.row-installed {
    color: $success;
}

/* Confirm dialog */
#confirm-dialog {
    align: center middle;
}

#confirm-box {
    width: 70;
    max-height: 30;
    background: $surface;
    border: thick $primary;
    padding: 1 2;
}

#confirm-title {
    text-style: bold;
    color: $primary;
    margin-bottom: 1;
}

#confirm-body {
    margin-bottom: 1;
    color: $text-muted;
}

#confirm-items {
    height: auto;
    max-height: 12;
    border: tall $panel;
    padding: 0 1;
    margin-bottom: 1;
    overflow-y: auto;
}

#confirm-items Label {
    color: $error;
}

#confirm-size {
    color: $warning;
    margin-bottom: 1;
}

#confirm-buttons {
    align: right middle;
    height: 3;
}

#confirm-buttons Button {
    margin-left: 1;
}

/* Result dialog */
#result-dialog {
    align: center middle;
}

#result-box {
    width: 60;
    background: $surface;
    border: thick $primary;
    padding: 1 2;
}

#result-title {
    text-style: bold;
    margin-bottom: 1;
}

#result-body {
    margin-bottom: 1;
}

#result-close {
    align: right middle;
    height: 3;
}
"""

# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

FILTER_OPTIONS: list[tuple[str, str]] = [
    ("Tutti", "all"),
    ("Solo non installati", "uninstalled"),
    ("Solo sconosciuti", "unknown"),
    ("Non installati + Sconosciuti", "not_installed"),
]

STATUS_LABELS: dict[str, str] = {
    "installed": "[green]Installato[/green]",
    "uninstalled": "[red]NON installato[/red]",
    "unknown": "[yellow]Sconosciuto[/yellow]",
}

TYPE_LABELS: dict[bool, str] = {
    True: "[blue]DIR[/blue]",
    False: "[dim]FILE[/dim]",
}


class ConfirmScreen(ModalScreen[bool]):
    """Modal dialog asking the user to confirm a trash operation.

    Displays the list of entries to be deleted and their total size.
    Resolves with ``True`` if the user confirms, ``False`` if cancelled.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Annulla"),
        Binding("enter", "confirm", "Conferma"),
    ]

    def __init__(self, entries: list[DotEntry]) -> None:
        """Initialise ConfirmScreen with the entries to be trashed.

        Args:
            entries: List of ``DotEntry`` objects pending deletion.
        """
        super().__init__()
        self.entries = entries

    def compose(self) -> ComposeResult:
        """Build the confirmation dialog layout.

        Returns:
            A generator of Textual widgets forming the dialog.
        """
        total_size = sum(e.size_bytes for e in self.entries)
        size_human = _human_size(total_size)

        with Center(id="confirm-dialog"):
            with Vertical(id="confirm-box"):
                yield Label("Conferma eliminazione", id="confirm-title")
                yield Label(
                    f"Stai per spostare nel cestino {len(self.entries)} elemento/i:",
                    id="confirm-body",
                )
                with VerticalScroll(id="confirm-items"):
                    for entry in self.entries:
                        yield Label(f"  {entry.display_path}")
                yield Label(
                    f"Spazio totale liberato: {size_human}",
                    id="confirm-size",
                )
                yield Label(
                    "[dim]Gli elementi saranno spostati nel cestino e potranno essere recuperati.[/dim]"
                )
                with Horizontal(id="confirm-buttons"):
                    yield Button("Annulla", variant="default", id="btn-cancel")
                    yield Button(
                        "Sposta nel cestino", variant="error", id="btn-confirm"
                    )

    @on(Button.Pressed, "#btn-cancel")
    def action_cancel(self) -> None:
        """Dismiss the dialog with False when the Cancel button is pressed.

        Returns:
            None.
        """
        self.dismiss(False)

    @on(Button.Pressed, "#btn-confirm")
    def action_confirm(self) -> None:
        """Dismiss the dialog with True when the Confirm button is pressed.

        Returns:
            None.
        """
        self.dismiss(True)


class ResultScreen(ModalScreen[None]):
    """Modal dialog that displays the outcome of a trash operation.

    Shows a count of successes and, when present, a list of failures with
    their error messages.
    """

    BINDINGS = [Binding("escape,enter,q", "close", "Chiudi")]

    def __init__(self, results: dict[str, str | None]) -> None:
        """Initialise ResultScreen with the trash-operation results.

        Args:
            results: Mapping of ``{path_str: error_message | None}`` as
                returned by ``trash_entries()``.
        """
        super().__init__()
        self.results = results

    def compose(self) -> ComposeResult:
        """Build the result dialog layout.

        Returns:
            A generator of Textual widgets forming the result dialog.
        """
        successes = [p for p, e in self.results.items() if e is None]
        failures = [(p, e) for p, e in self.results.items() if e is not None]

        with Center(id="result-dialog"):
            with Vertical(id="result-box"):
                title = "Operazione completata"
                yield Label(title, id="result-title")
                lines = []
                if successes:
                    lines.append(
                        f"[green]Spostati nel cestino: {len(successes)}[/green]"
                    )
                if failures:
                    lines.append(f"[red]Errori: {len(failures)}[/red]")
                    for path, err in failures:
                        lines.append(f"  [red]{Path(path).name}: {err}[/red]")
                yield Label("\n".join(lines), id="result-body")
                with Horizontal(id="result-close"):
                    yield Button("Chiudi", variant="primary", id="btn-close")

    @on(Button.Pressed, "#btn-close")
    def action_close(self) -> None:
        """Dismiss the result dialog when the Close button is pressed.

        Returns:
            None.
        """
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------


def _human_size(size: int) -> str:
    """Convert a byte count to a human-readable size string.

    Args:
        size: Size in bytes.

    Returns:
        A formatted string such as ``'1.5 MB'`` or ``'300.0 B'``.
    """
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size //= 1024
    return f"{size:.1f} TB"


class DotCleanerApp(App[None]):
    """Main Textual application for dot-net-files-cleaner.

    Displays a filterable DataTable of dot entries with their associated
    Debian packages and installation status.  Allows selecting entries and
    moving them to the FreeDesktop trash.
    """

    TITLE = "dot-net-files-cleaner"
    SUB_TITLE = "Pulizia dei dot files orfani"
    CSS = CSS

    BINDINGS: ClassVar[list[Binding]] = [  # type: ignore[assignment]
        Binding("q", "quit", "Esci"),
        Binding("d", "delete_selected", "Elimina selezionati"),
        Binding("a", "select_uninstalled", "Seleziona non installati"),
        Binding("space", "toggle_row", "Seleziona/Deseleziona"),
        Binding("1", "filter_all", "Mostra tutti"),
        Binding("2", "filter_uninstalled", "Solo non installati"),
        Binding("3", "filter_unknown", "Solo sconosciuti"),
        Binding("4", "filter_not_installed", "Non inst. + Sconosciuti"),
        Binding("r", "reload", "Ricarica"),
    ]

    # Stato reattivo
    _current_filter: reactive[str] = reactive("all")
    _selected_keys: reactive[set[str]] = reactive(set, init=False)

    def __init__(self, home: Path | None = None) -> None:
        """Initialise DotCleanerApp.

        Args:
            home: Home directory to scan.  Defaults to ``Path.home()`` when
                ``None``.
        """
        super().__init__()
        self._home = home or Path.home()
        self._all_entries: list[DotEntry] = []
        self._filtered_entries: list[DotEntry] = []
        self._is_loading = True
        self._selected_paths: set[str] = set()

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        """Build the main application layout with loading and main screens.

        Returns:
            A generator of Textual widgets for the full application layout.
        """
        yield Header(show_clock=True)

        # Schermata di caricamento (visibile all'avvio)
        with Vertical(id="loading-screen"):
            yield Middle(
                LoadingIndicator(),
                Label("Scansione in corso...\nAnalisi dei pacchetti installati"),
            )

        # Schermata principale (nascosta fino al termine del caricamento)
        with Vertical(id="main-screen"):
            with Horizontal(id="toolbar"):
                yield Label("Filtro:")
                yield Select(
                    options=[(label, value) for label, value in FILTER_OPTIONS],
                    value="all",
                    id="filter-select",
                    allow_blank=False,
                )
                yield Label("", id="stats-label")

            with Vertical(id="table-container"):
                table: DataTable[str] = DataTable(
                    id="main-table", cursor_type="row", zebra_stripes=True
                )
                table.add_columns(
                    "",  # checkbox
                    "Path",
                    "Tipo",
                    "Dimensione",
                    "Pacchetto/i",
                    "Stato",
                    "Fonte",
                    "Ultima modifica",
                    "Ultimo accesso",
                )
                yield table

        yield Footer()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Hide the main screen and start background data loading on mount.

        Returns:
            None.
        """
        # Nascondi la main screen e mostra il loading
        self.query_one("#main-screen").display = False
        self.query_one("#loading-screen").display = True
        self._load_data()

    @work(thread=True)
    def _load_data(self) -> None:
        """Load scan data in a background thread to keep the UI responsive.

        Steps performed:
        1. Initialise ``PackageChecker`` and load installed packages.
        2. Scan the home directory with ``scan_home``.
        3. Map entries to packages with ``map_entries``.
        4. Schedule ``_on_data_loaded`` on the main thread.

        Returns:
            None.
        """

        def update_label(text: str) -> None:
            """Update the loading-screen status label from any thread.

            Args:
                text: New label text to display.

            Returns:
                None.
            """
            try:
                lbl = self.query_one("#loading-screen Label", Label)
                lbl.update(text)
            except NoMatches:
                pass

        self.call_from_thread(update_label, "Scansione dei dot files in corso...")

        # 1. Inizializza il checker e carica i pacchetti
        checker = PackageChecker()
        self.call_from_thread(
            update_label, "Caricamento pacchetti Debian installati..."
        )
        checker.load()

        # 2. Scansiona la home
        self.call_from_thread(update_label, "Scansione della home directory...")
        entries = scan_home(self._home)

        # 3. Mappa i pacchetti
        self.call_from_thread(
            update_label, f"Analisi di {len(entries)} elementi trovati..."
        )
        entries = map_entries(entries, checker)

        # 4. Aggiorna la UI nel thread principale
        self._all_entries = entries
        self.call_from_thread(self._on_data_loaded)

    def _on_data_loaded(self) -> None:
        """Switch from the loading screen to the main screen once data is ready.

        Returns:
            None.
        """
        self._is_loading = False
        self.query_one("#loading-screen").display = False
        self.query_one("#main-screen").display = True
        self._apply_filter()

    # ------------------------------------------------------------------
    # Tabella
    # ------------------------------------------------------------------

    def _apply_filter(self) -> None:
        """Apply the current filter to the entry list and refresh the table.

        Entries are sorted uninstalled-first, then unknown, then installed.
        Calls ``_rebuild_table`` and ``_update_stats`` after filtering.

        Returns:
            None.
        """
        f = self._current_filter
        if f == "all":
            self._filtered_entries = list(self._all_entries)
        elif f == "uninstalled":
            self._filtered_entries = [
                e for e in self._all_entries if e.status == "uninstalled"
            ]
        elif f == "unknown":
            self._filtered_entries = [
                e for e in self._all_entries if e.status == "unknown"
            ]
        elif f == "not_installed":
            self._filtered_entries = [
                e for e in self._all_entries if e.status in ("uninstalled", "unknown")
            ]
        else:
            self._filtered_entries = list(self._all_entries)

        # Ordina: non installati prima, poi sconosciuti, poi installati
        STATUS_ORDER = {"uninstalled": 0, "unknown": 1, "installed": 2}
        self._filtered_entries.sort(
            key=lambda e: (STATUS_ORDER.get(e.status, 9), e.name.lower())
        )

        self._rebuild_table()
        self._update_stats()

    def _rebuild_table(self) -> None:
        """Clear and repopulate the DataTable from the filtered entry list.

        Returns:
            None.
        """
        table = self.query_one("#main-table", DataTable)
        table.clear()

        for entry in self._filtered_entries:
            key = str(entry.path)
            selected = key in self._selected_paths
            checkbox = "[X]" if selected else "[ ]"

            packages_str = (
                ", ".join(entry.associated_packages)
                if entry.associated_packages
                else "-"
            )
            if len(packages_str) > 35:
                packages_str = packages_str[:32] + "..."

            status = entry.status
            status_label = STATUS_LABELS.get(status, status)
            type_label = TYPE_LABELS.get(entry.is_dir, "?")
            source_label = {
                "database": "[dim]DB[/dim]",
                "heuristic": "[dim]euris.[/dim]",
                "unknown": "[dim]-[/dim]",
            }.get(entry.match_source, "")

            # Tronca il path se troppo lungo
            display = entry.display_path
            if len(display) > 45:
                display = "..." + display[-42:]

            table.add_row(
                checkbox,
                display,
                type_label,
                entry.size_human,
                packages_str,
                status_label,
                source_label,
                entry.modified_human,
                entry.accessed_human,
                key=key,
            )

    def _update_stats(self) -> None:
        """Refresh the statistics label in the toolbar.

        Returns:
            None.
        """
        total = len(self._all_entries)
        uninstalled = sum(1 for e in self._all_entries if e.status == "uninstalled")
        unknown = sum(1 for e in self._all_entries if e.status == "unknown")
        selected = len(self._selected_paths)

        selected_entries = [
            e for e in self._all_entries if str(e.path) in self._selected_paths
        ]
        selected_size = sum(e.size_bytes for e in selected_entries)

        stats = (
            f"Totale: {total}  |  "
            f"[red]Non inst.: {uninstalled}[/red]  |  "
            f"[yellow]Sconosciuti: {unknown}[/yellow]  |  "
            f"[bold]Selezionati: {selected}[/bold]"
        )
        if selected > 0:
            stats += f" ({_human_size(selected_size)})"

        try:
            self.query_one("#stats-label", Label).update(stats)
        except NoMatches:
            pass

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_toggle_row(self) -> None:
        """Toggle the selection state of the currently focused table row.

        Returns:
            None.
        """
        table = self.query_one("#main-table", DataTable)
        if table.cursor_row < 0 or table.cursor_row >= len(self._filtered_entries):
            return
        entry = self._filtered_entries[table.cursor_row]
        key = str(entry.path)
        if key in self._selected_paths:
            self._selected_paths.discard(key)
        else:
            self._selected_paths.add(key)
        self._rebuild_table()
        self._update_stats()
        # Riposiziona il cursore
        try:
            table.move_cursor(row=table.cursor_row)
        except Exception:
            pass

    def action_select_uninstalled(self) -> None:
        """Select all currently visible uninstalled and unknown entries.

        Returns:
            None.
        """
        for entry in self._filtered_entries:
            if entry.status in ("uninstalled", "unknown"):
                self._selected_paths.add(str(entry.path))
        self._rebuild_table()
        self._update_stats()

    def action_delete_selected(self) -> None:
        """Open the confirmation dialog and trash the selected entries on confirm.

        Shows a warning notification if nothing is selected.

        Returns:
            None.
        """
        if not self._selected_paths:
            self.notify("Nessun elemento selezionato.", severity="warning")
            return

        to_delete = [
            e for e in self._all_entries if str(e.path) in self._selected_paths
        ]
        if not to_delete:
            return

        def handle_confirm(confirmed: bool | None) -> None:
            """Proceed with trashing if the user confirmed.

            Args:
                confirmed: ``True`` if the user clicked Confirm, else falsy.

            Returns:
                None.
            """
            if confirmed:
                self._do_trash(to_delete)

        self.push_screen(ConfirmScreen(to_delete), handle_confirm)

    @work(thread=True)
    def _do_trash(self, entries: list[DotEntry]) -> None:
        """Move the given entries to the trash in a background thread.

        Args:
            entries: List of ``DotEntry`` objects to trash.

        Returns:
            None.
        """
        results = trash_entries(entries)
        self.call_from_thread(self._after_trash, entries, results)

    def _after_trash(
        self, entries: list[DotEntry], results: dict[str, str | None]
    ) -> None:
        """Update the application state after a trash operation completes.

        Removes successfully trashed entries from the internal list, refreshes
        the table, and shows the result dialog.

        Args:
            entries: The entries that were submitted for trashing.
            results: Mapping of ``{path_str: error_message | None}`` from
                ``trash_entries()``.

        Returns:
            None.
        """
        # Rimuovi gli entry eliminati con successo
        removed_paths = {p for p, err in results.items() if err is None}
        self._selected_paths -= removed_paths
        self._all_entries = [
            e for e in self._all_entries if str(e.path) not in removed_paths
        ]
        self._apply_filter()

        def close_result(_: None) -> None:
            """No-op callback to satisfy the push_screen signature.

            Args:
                _: Ignored result value from ResultScreen.

            Returns:
                None.
            """
            pass

        self.push_screen(ResultScreen(results), close_result)

    def action_filter_all(self) -> None:
        """Switch the active filter to show all entries.

        Returns:
            None.
        """
        self._current_filter = "all"
        self._apply_filter()
        self._sync_select("all")

    def action_filter_uninstalled(self) -> None:
        """Switch the active filter to show only uninstalled entries.

        Returns:
            None.
        """
        self._current_filter = "uninstalled"
        self._apply_filter()
        self._sync_select("uninstalled")

    def action_filter_unknown(self) -> None:
        """Switch the active filter to show only unknown entries.

        Returns:
            None.
        """
        self._current_filter = "unknown"
        self._apply_filter()
        self._sync_select("unknown")

    def action_filter_not_installed(self) -> None:
        """Switch the active filter to show uninstalled and unknown entries.

        Returns:
            None.
        """
        self._current_filter = "not_installed"
        self._apply_filter()
        self._sync_select("not_installed")

    def action_reload(self) -> None:
        """Reset all state and restart the background scan from scratch.

        Returns:
            None.
        """
        self._all_entries = []
        self._filtered_entries = []
        self._selected_paths = set()
        self.query_one("#main-screen").display = False
        self.query_one("#loading-screen").display = True
        self._load_data()

    def _sync_select(self, value: str) -> None:
        """Synchronise the filter Select widget to match the current filter value.

        Args:
            value: The filter value to set on the Select widget.

        Returns:
            None.
        """
        try:
            sel = self.query_one("#filter-select", Select)
            sel.value = value
        except NoMatches:
            pass

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @on(Select.Changed, "#filter-select")
    def on_filter_changed(self, event: Select.Changed) -> None:
        """Apply a new filter when the Select widget value changes.

        Args:
            event: The ``Select.Changed`` event carrying the new value.

        Returns:
            None.
        """
        if event.value and event.value != self._current_filter:
            self._current_filter = str(event.value)
            self._apply_filter()

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Toggle row selection when a table row is activated via click or Enter.

        Args:
            event: The ``DataTable.RowSelected`` event carrying the row key.

        Returns:
            None.
        """
        if event.row_key and event.row_key.value:
            key = str(event.row_key.value)
            if key in self._selected_paths:
                self._selected_paths.discard(key)
            else:
                self._selected_paths.add(key)
            self._rebuild_table()
            self._update_stats()
