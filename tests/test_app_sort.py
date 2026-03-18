"""Tests for the column-sort feature of DotCleanerApp.

Covers:
- Default ordering (status-first, then name) when no column sort is active.
- Ascending sort for every sortable column.
- Descending sort for every sortable column.
- The three-state cycle: ascending → descending → reset-to-default.
- The ``sel`` (checkbox) column does not activate a sort.
- ``_update_column_headers`` labels: active column shows indicator,
  others show their base label.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dotcleaner.app import (
    DotCleanerApp,
    _COLUMN_LABELS,
    _SORTABLE_COLUMNS,
    _filter_entries,
    _sort_entries,
)
from dotcleaner.scanner import DotEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    tmp_path: Path,
    name: str,
    *,
    is_dir: bool = True,
    size_bytes: int = 1024,
    associated_packages: list[str] | None = None,
    installed_packages: list[str] | None = None,
    uninstalled_packages: list[str] | None = None,
    match_source: str = "database",
    modified_at: datetime | None = None,
    accessed_at: datetime | None = None,
) -> DotEntry:
    """Build a ``DotEntry`` backed by a real path under *tmp_path*.

    Args:
        tmp_path: Base directory for the entry's filesystem path.
        name: Entry name (e.g. ``".vim"``).
        is_dir: If ``True``, create a directory; otherwise create a file.
        size_bytes: Reported size in bytes stored on the entry.
        associated_packages: Optional list of package names to assign.
        installed_packages: Optional list of installed package names.
        uninstalled_packages: Optional list of uninstalled package names.
        match_source: Mapping phase that produced the association.
        modified_at: Optional last-modification datetime.
        accessed_at: Optional last-access datetime.

    Returns:
        A fully initialised ``DotEntry``.
    """
    path = tmp_path / name
    if is_dir:
        path.mkdir(exist_ok=True)
    else:
        path.write_text("x")

    entry = DotEntry(
        path=path,
        name=name,
        is_dir=is_dir,
        size_bytes=size_bytes,
        source="home_dot",
        modified_at=modified_at or datetime(2024, 1, 1),
        accessed_at=accessed_at or datetime(2024, 1, 1),
    )
    entry.associated_packages = associated_packages or []
    entry.installed_packages = installed_packages or []
    entry.uninstalled_packages = uninstalled_packages or []
    entry.match_source = match_source
    return entry


def _build_app(tmp_path: Path, entries: list[DotEntry]) -> DotCleanerApp:
    """Instantiate a ``DotCleanerApp`` with pre-loaded entries, bypassing scanning.

    The app is initialised via ``__new__`` so that Textual's ``super().__init__``
    is never called.  This keeps the instance free of the DOM node machinery,
    making it safe to test methods that do **not** access reactive descriptors.

    For methods that *do* read ``self._current_filter`` (a Textual reactive),
    the tests in this module call ``_filter_entries`` and ``_sort_entries``
    directly instead of going through ``_apply_filter``.

    Args:
        tmp_path: Temporary directory (used as the home path).
        entries: Pre-built list of ``DotEntry`` objects.

    Returns:
        A ``DotCleanerApp`` instance with ``_all_entries`` pre-populated.
    """
    app = DotCleanerApp.__new__(DotCleanerApp)
    d = vars(app)
    d["_home"] = tmp_path
    d["_all_entries"] = list(entries)
    d["_filtered_entries"] = []
    d["_is_loading"] = False
    d["_selected_paths"] = set()
    d["_sort_column"] = None
    d["_sort_reverse"] = False
    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def entries(tmp_path: Path) -> list[DotEntry]:
    """Return a list of four ``DotEntry`` objects with varied attributes.

    The entries are::

        .alpha  — installed,   DIR,  size=100,   mtime=2024-01-03
        .beta   — uninstalled, FILE, size=500,   mtime=2024-01-01
        .gamma  — unknown,     DIR,  size=2000,  mtime=2024-01-04
        .delta  — installed,   FILE, size=50,    mtime=2024-01-02

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        List of four pre-built ``DotEntry`` objects.
    """
    return [
        _make_entry(
            tmp_path, ".alpha",
            is_dir=True, size_bytes=100,
            associated_packages=["pkg-a"],
            installed_packages=["pkg-a"],
            match_source="database",
            modified_at=datetime(2024, 1, 3),
            accessed_at=datetime(2024, 6, 1),
        ),
        _make_entry(
            tmp_path, ".beta",
            is_dir=False, size_bytes=500,
            associated_packages=["pkg-b"],
            uninstalled_packages=["pkg-b"],
            match_source="heuristic",
            modified_at=datetime(2024, 1, 1),
            accessed_at=datetime(2024, 6, 3),
        ),
        _make_entry(
            tmp_path, ".gamma",
            is_dir=True, size_bytes=2000,
            associated_packages=[],
            match_source="unknown",
            modified_at=datetime(2024, 1, 4),
            accessed_at=datetime(2024, 6, 2),
        ),
        _make_entry(
            tmp_path, ".delta",
            is_dir=False, size_bytes=50,
            associated_packages=["pkg-d"],
            installed_packages=["pkg-d"],
            match_source="database",
            modified_at=datetime(2024, 1, 2),
            accessed_at=datetime(2024, 6, 4),
        ),
    ]


# ---------------------------------------------------------------------------
# Tests: default sort (no column active)
# ---------------------------------------------------------------------------


class TestDefaultSort:
    """Tests for the default ordering when no column sort is active."""

    def test_default_order_uninstalled_first(
        self, entries: list[DotEntry]
    ) -> None:
        """Assert uninstalled entries appear before unknown and installed ones."""
        result = _sort_entries(_filter_entries(entries, "all"), None, False)

        statuses = [e.status for e in result]
        uninstalled_idx = [i for i, s in enumerate(statuses) if s == "uninstalled"]
        unknown_idx = [i for i, s in enumerate(statuses) if s == "unknown"]
        installed_idx = [i for i, s in enumerate(statuses) if s == "installed"]
        assert max(uninstalled_idx) < min(unknown_idx)
        assert max(unknown_idx) < min(installed_idx)

    def test_default_order_alphabetical_within_status(
        self, entries: list[DotEntry]
    ) -> None:
        """Assert entries within the same status group are sorted alphabetically."""
        result = _sort_entries(_filter_entries(entries, "all"), None, False)

        installed = [e.name for e in result if e.status == "installed"]
        assert installed == sorted(installed, key=str.lower)


# ---------------------------------------------------------------------------
# Tests: ascending sort per column
# ---------------------------------------------------------------------------


class TestAscendingSort:
    """Tests for ascending column sort."""

    def test_sort_by_path_ascending(self, entries: list[DotEntry]) -> None:
        """Assert entries are sorted A→Z by name when 'path' column is active."""
        result = _sort_entries(entries, "path", False)

        names = [e.name.lower() for e in result]
        assert names == sorted(names)

    def test_sort_by_size_ascending(self, entries: list[DotEntry]) -> None:
        """Assert entries are sorted by size_bytes ascending."""
        result = _sort_entries(entries, "size", False)

        sizes = [e.size_bytes for e in result]
        assert sizes == sorted(sizes)

    def test_sort_by_tipo_ascending(self, entries: list[DotEntry]) -> None:
        """Assert directories (is_dir=True → key 0) sort before files (key 1)."""
        result = _sort_entries(entries, "tipo", False)

        is_dirs = [e.is_dir for e in result]
        seen_false = False
        for v in is_dirs:
            if not v:
                seen_false = True
            assert not (seen_false and v), "A DIR appeared after a FILE in ascending sort"

    def test_sort_by_status_ascending(self, entries: list[DotEntry]) -> None:
        """Assert status sort uses semantic order: uninstalled→unknown→installed."""
        STATUS_ORDER = {"uninstalled": 0, "unknown": 1, "installed": 2}
        result = _sort_entries(entries, "status", False)

        keys = [STATUS_ORDER[e.status] for e in result]
        assert keys == sorted(keys)

    def test_sort_by_mtime_ascending(self, entries: list[DotEntry]) -> None:
        """Assert entries are sorted by modification time ascending (oldest first)."""
        result = _sort_entries(entries, "mtime", False)

        mtimes = [e.modified_at for e in result]
        assert mtimes == sorted(mtimes)

    def test_sort_by_atime_ascending(self, entries: list[DotEntry]) -> None:
        """Assert entries are sorted by access time ascending (oldest first)."""
        result = _sort_entries(entries, "atime", False)

        atimes = [e.accessed_at for e in result]
        assert atimes == sorted(atimes)

    def test_sort_by_source_ascending(self, entries: list[DotEntry]) -> None:
        """Assert entries are sorted alphabetically by match_source ascending."""
        result = _sort_entries(entries, "source", False)

        sources = [e.match_source.lower() for e in result]
        assert sources == sorted(sources)

    def test_sort_by_pkg_ascending(self, entries: list[DotEntry]) -> None:
        """Assert entries are sorted alphabetically by joined packages ascending."""
        result = _sort_entries(entries, "pkg", False)

        pkg_keys = [", ".join(e.associated_packages).lower() for e in result]
        assert pkg_keys == sorted(pkg_keys)


# ---------------------------------------------------------------------------
# Tests: descending sort per column
# ---------------------------------------------------------------------------


class TestDescendingSort:
    """Tests for descending column sort."""

    def test_sort_by_path_descending(self, entries: list[DotEntry]) -> None:
        """Assert entries are sorted Z→A by name when sort is reversed."""
        result = _sort_entries(entries, "path", True)

        names = [e.name.lower() for e in result]
        assert names == sorted(names, reverse=True)

    def test_sort_by_size_descending(self, entries: list[DotEntry]) -> None:
        """Assert entries are sorted by size_bytes descending (largest first)."""
        result = _sort_entries(entries, "size", True)

        sizes = [e.size_bytes for e in result]
        assert sizes == sorted(sizes, reverse=True)

    def test_sort_by_mtime_descending(self, entries: list[DotEntry]) -> None:
        """Assert entries are sorted by modification time descending (newest first)."""
        result = _sort_entries(entries, "mtime", True)

        mtimes = [e.modified_at for e in result]
        assert mtimes == sorted(mtimes, reverse=True)

    def test_sort_by_status_descending(self, entries: list[DotEntry]) -> None:
        """Assert status sort descending yields installed→unknown→uninstalled."""
        STATUS_ORDER = {"uninstalled": 0, "unknown": 1, "installed": 2}
        result = _sort_entries(entries, "status", True)

        keys = [STATUS_ORDER[e.status] for e in result]
        assert keys == sorted(keys, reverse=True)


# ---------------------------------------------------------------------------
# Tests: three-state cycle via on_header_selected
# ---------------------------------------------------------------------------


class TestHeaderClickCycle:
    """Tests for the ascending → descending → reset cycle on header clicks."""

    def _make_col_event(self, col_key: str) -> MagicMock:
        """Build a mock ``DataTable.HeaderSelected`` event for *col_key*.

        Args:
            col_key: The string value of the column key to simulate a click on.

        Returns:
            A ``MagicMock`` mimicking ``DataTable.HeaderSelected``.
        """
        event = MagicMock()
        event.column_key.value = col_key
        return event

    def _call_header_selected(self, app: DotCleanerApp, col_key: str) -> None:
        """Invoke ``on_header_selected`` with UI helpers stubbed out.

        Args:
            app: The ``DotCleanerApp`` instance.
            col_key: The column key to simulate clicking.

        Returns:
            None.
        """
        event = self._make_col_event(col_key)
        with (
            patch.object(app, "_apply_filter"),
            patch.object(app, "_update_column_headers"),
        ):
            app.on_header_selected(event)

    def test_first_click_sets_ascending(self, tmp_path: Path) -> None:
        """Assert the first click on a new column sets ascending sort."""
        app = _build_app(tmp_path, [])
        self._call_header_selected(app, "path")

        assert app._sort_column == "path"
        assert app._sort_reverse is False

    def test_second_click_switches_to_descending(self, tmp_path: Path) -> None:
        """Assert the second click on the same column reverses the sort order."""
        app = _build_app(tmp_path, [])
        self._call_header_selected(app, "size")
        self._call_header_selected(app, "size")

        assert app._sort_column == "size"
        assert app._sort_reverse is True

    def test_third_click_resets_to_default(self, tmp_path: Path) -> None:
        """Assert the third click on the same column resets to default sort."""
        app = _build_app(tmp_path, [])
        self._call_header_selected(app, "mtime")
        self._call_header_selected(app, "mtime")
        self._call_header_selected(app, "mtime")

        assert app._sort_column is None
        assert app._sort_reverse is False

    def test_click_different_column_resets_direction(self, tmp_path: Path) -> None:
        """Assert switching to a different column resets to ascending."""
        app = _build_app(tmp_path, [])
        self._call_header_selected(app, "path")
        self._call_header_selected(app, "path")  # now descending
        self._call_header_selected(app, "size")  # switch to different column

        assert app._sort_column == "size"
        assert app._sort_reverse is False

    def test_sel_column_does_not_activate_sort(self, tmp_path: Path) -> None:
        """Assert clicking the checkbox column leaves sort state unchanged."""
        app = _build_app(tmp_path, [])
        self._call_header_selected(app, "sel")

        assert app._sort_column is None
        assert app._sort_reverse is False


# ---------------------------------------------------------------------------
# Tests: column header labels (_update_column_headers)
# ---------------------------------------------------------------------------


class _FakeColumn:
    """Minimal stand-in for a Textual ``Column`` object.

    Holds mutable ``label`` and ``content_width`` attributes so tests can
    inspect the values that ``_update_column_headers`` assigns without
    requiring a live DataTable.
    """

    def __init__(self, initial_label: str = "") -> None:
        """Initialise with an optional initial label.

        Args:
            initial_label: Starting value for the ``label`` attribute.
        """
        self.label: object = initial_label
        self.content_width: int = len(initial_label)


class TestUpdateColumnHeaders:
    """Tests for the visual sort indicators in column headers."""

    def _fake_columns(self) -> dict[object, _FakeColumn]:
        """Build a columns dict keyed by ColumnKey, valued by _FakeColumn.

        Returns:
            A dict mapping each column key to a ``_FakeColumn`` instance
            initialised with the base label from ``_COLUMN_LABELS``.
        """
        from textual.widgets._data_table import ColumnKey

        return {ColumnKey(k): _FakeColumn(v) for k, v in _COLUMN_LABELS.items()}

    def _make_mock_table(self) -> MagicMock:
        """Build a mock DataTable with a real Rich console attached.

        ``_update_column_headers`` calls ``table.app.console`` to measure label
        widths; this method attaches a real ``rich.console.Console`` instance so
        that ``Text.__rich_measure__`` returns proper integers.

        Returns:
            A ``MagicMock`` mimicking a Textual ``DataTable`` with
            ``columns`` pre-populated and ``app.console`` set to a real console.
        """
        from rich.console import Console

        fake_cols = self._fake_columns()
        mock_table = MagicMock()
        mock_table.columns = fake_cols
        mock_table.app.console = Console()
        return mock_table

    def test_active_ascending_column_gets_up_indicator(
        self, tmp_path: Path
    ) -> None:
        """Assert the active ascending column label ends with ' ▲'."""
        from textual.widgets._data_table import ColumnKey

        app = _build_app(tmp_path, [])
        app._sort_column = "path"
        app._sort_reverse = False

        fake_cols = self._fake_columns()
        mock_table = MagicMock()
        mock_table.columns = fake_cols

        with patch.object(app, "query_one", return_value=mock_table):
            app._update_column_headers()

        assigned = fake_cols[ColumnKey("path")].label
        assert str(assigned).endswith("▲")

    def test_active_descending_column_gets_down_indicator(
        self, tmp_path: Path
    ) -> None:
        """Assert the active descending column label ends with ' ▼'."""
        from textual.widgets._data_table import ColumnKey

        app = _build_app(tmp_path, [])
        app._sort_column = "size"
        app._sort_reverse = True

        fake_cols = self._fake_columns()
        mock_table = MagicMock()
        mock_table.columns = fake_cols

        with patch.object(app, "query_one", return_value=mock_table):
            app._update_column_headers()

        assigned = fake_cols[ColumnKey("size")].label
        assert str(assigned).endswith("▼")

    def test_inactive_columns_have_no_indicator(self, tmp_path: Path) -> None:
        """Assert columns other than the active one have no sort indicator."""
        from textual.widgets._data_table import ColumnKey

        app = _build_app(tmp_path, [])
        app._sort_column = "path"
        app._sort_reverse = False

        fake_cols = self._fake_columns()
        mock_table = MagicMock()
        mock_table.columns = fake_cols

        with patch.object(app, "query_one", return_value=mock_table):
            app._update_column_headers()

        for col_key_str in _SORTABLE_COLUMNS:
            if col_key_str == "path":
                continue
            ck = ColumnKey(col_key_str)
            label_str = str(fake_cols[ck].label)
            assert "▲" not in label_str
            assert "▼" not in label_str

    def test_no_active_sort_all_labels_are_base(self, tmp_path: Path) -> None:
        """Assert all column labels show the base text when no sort is active."""
        from textual.widgets._data_table import ColumnKey

        app = _build_app(tmp_path, [])
        app._sort_column = None
        app._sort_reverse = False

        fake_cols = self._fake_columns()
        mock_table = MagicMock()
        mock_table.columns = fake_cols

        with patch.object(app, "query_one", return_value=mock_table):
            app._update_column_headers()

        for col_key_str, base_label in _COLUMN_LABELS.items():
            if col_key_str == "sel":
                continue
            ck = ColumnKey(col_key_str)
            assert str(fake_cols[ck].label) == base_label


# ---------------------------------------------------------------------------
# Tests: _COLUMN_LABELS and _SORTABLE_COLUMNS constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests for module-level constants used by the sort feature."""

    def test_column_labels_has_all_nine_columns(self) -> None:
        """Assert _COLUMN_LABELS defines exactly 9 column entries."""
        assert len(_COLUMN_LABELS) == 9

    def test_sortable_columns_excludes_sel(self) -> None:
        """Assert the 'sel' (checkbox) column is not in _SORTABLE_COLUMNS."""
        assert "sel" not in _SORTABLE_COLUMNS

    def test_sortable_columns_is_subset_of_column_labels(self) -> None:
        """Assert every sortable column key appears in _COLUMN_LABELS."""
        assert _SORTABLE_COLUMNS <= set(_COLUMN_LABELS.keys())

    def test_all_non_sel_columns_are_sortable(self) -> None:
        """Assert every column except 'sel' is in _SORTABLE_COLUMNS."""
        expected = {k for k in _COLUMN_LABELS if k != "sel"}
        assert expected == _SORTABLE_COLUMNS
