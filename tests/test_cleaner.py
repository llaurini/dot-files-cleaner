"""Functional tests for dotcleaner/cleaner.py.

Tests ``trash_entry()``, ``trash_entries()``, ``CleanError``, ``get_trash_dir()``,
and ``get_trash_size()`` with ``send2trash`` mocked to avoid any real filesystem
modifications.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable
from unittest.mock import patch

import pytest

from dotcleaner.cleaner import (
    CleanError,
    get_trash_dir,
    get_trash_size,
    trash_entries,
    trash_entry,
)
from dotcleaner.scanner import DotEntry


# ---------------------------------------------------------------------------
# Test: trash_entry — basic behaviour
# ---------------------------------------------------------------------------


class TestTrashEntry:
    """Tests for trash_entry() with send2trash mocked."""

    def test_calls_send2trash_with_string_path(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that trash_entry() calls send2trash with the entry path as a string."""
        entry = make_entry(".zoom", is_dir=True)
        assert entry.path.exists()

        with patch("dotcleaner.cleaner._send2trash") as mock_trash, patch(
            "dotcleaner.cleaner.HAS_SEND2TRASH", True
        ):
            trash_entry(entry)

        mock_trash.assert_called_once_with(str(entry.path))

    def test_raises_clean_error_for_nonexistent_path(self, tmp_path: Path) -> None:
        """Asserts that trash_entry() raises CleanError when the path does not exist."""
        fake_path = tmp_path / ".nonexistent-app"
        entry = DotEntry(
            path=fake_path,
            name=".nonexistent-app",
            is_dir=True,
            size_bytes=0,
            source="home_dot",
        )
        with pytest.raises(CleanError, match="non esiste"):
            trash_entry(entry)

    def test_raises_clean_error_if_send2trash_missing(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that trash_entry() raises CleanError when send2trash is not installed."""
        entry = make_entry(".zoom")

        with patch("dotcleaner.cleaner.HAS_SEND2TRASH", False):
            with pytest.raises(CleanError, match="send2trash"):
                trash_entry(entry)

    def test_raises_clean_error_on_send2trash_exception(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that trash_entry() wraps send2trash exceptions in CleanError."""
        entry = make_entry(".zoom")

        with patch(
            "dotcleaner.cleaner._send2trash", side_effect=OSError("permission denied")
        ), patch("dotcleaner.cleaner.HAS_SEND2TRASH", True):
            with pytest.raises(CleanError, match="Impossibile spostare"):
                trash_entry(entry)

    def test_does_not_use_shutil_rmtree(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that trash_entry() never calls shutil.rmtree."""
        import shutil

        entry = make_entry(".zoom")

        original_rmtree = shutil.rmtree
        rmtree_called: list[tuple[object, ...]] = []

        def mock_rmtree(*args: object, **kwargs: object) -> None:
            """Record any invocation of shutil.rmtree to detect forbidden calls.

            Args:
                *args: Positional arguments forwarded from the patch.
                **kwargs: Keyword arguments forwarded from the patch.
            """
            rmtree_called.append(args)

        with patch("dotcleaner.cleaner._send2trash"), patch(
            "dotcleaner.cleaner.HAS_SEND2TRASH", True
        ), patch("shutil.rmtree", side_effect=mock_rmtree):
            trash_entry(entry)

        assert len(rmtree_called) == 0, "shutil.rmtree must never be called!"

    def test_does_not_use_os_remove(self, make_entry: Callable[..., DotEntry]) -> None:
        """Asserts that trash_entry() never calls os.remove."""
        entry = make_entry(".gitconfig", is_dir=False)
        os_remove_called: list[tuple[object, ...]] = []

        def mock_os_remove(*args: object, **kwargs: object) -> None:
            """Record any invocation of os.remove to detect forbidden calls.

            Args:
                *args: Positional arguments forwarded from the patch.
                **kwargs: Keyword arguments forwarded from the patch.
            """
            os_remove_called.append(args)

        with patch("dotcleaner.cleaner._send2trash"), patch(
            "dotcleaner.cleaner.HAS_SEND2TRASH", True
        ), patch("os.remove", side_effect=mock_os_remove):
            trash_entry(entry)

        assert len(os_remove_called) == 0, "os.remove must never be called!"

    def test_works_with_file_entry(self, make_entry: Callable[..., DotEntry]) -> None:
        """Asserts that trash_entry() works correctly on single-file entries."""
        entry = make_entry(".gitconfig", is_dir=False)
        with patch("dotcleaner.cleaner._send2trash") as mock_trash, patch(
            "dotcleaner.cleaner.HAS_SEND2TRASH", True
        ):
            trash_entry(entry)
        mock_trash.assert_called_once()

    def test_works_with_symlink(self, tmp_path: Path) -> None:
        """Asserts that trash_entry() works correctly on valid symlinks."""
        target = tmp_path / "real_dir"
        target.mkdir()
        link = tmp_path / ".my-link"
        link.symlink_to(target)

        entry = DotEntry(
            path=link,
            name=".my-link",
            is_dir=False,
            size_bytes=0,
            source="home_dot",
        )
        with patch("dotcleaner.cleaner._send2trash") as mock_trash, patch(
            "dotcleaner.cleaner.HAS_SEND2TRASH", True
        ):
            trash_entry(entry)
        mock_trash.assert_called_once_with(str(link))


# ---------------------------------------------------------------------------
# Test: trash_entries — batch operations
# ---------------------------------------------------------------------------


class TestTrashEntries:
    """Tests for trash_entries() operating on a list of DotEntry objects."""

    def test_returns_dict_with_none_on_success(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that each successfully trashed entry maps to None in the result dict."""
        entries = [
            make_entry(".vim", is_dir=True),
            make_entry(".zoom", is_dir=True),
        ]
        with patch("dotcleaner.cleaner._send2trash"), patch(
            "dotcleaner.cleaner.HAS_SEND2TRASH", True
        ):
            results = trash_entries(entries)

        for entry in entries:
            assert str(entry.path) in results
            assert results[str(entry.path)] is None

    def test_returns_error_message_on_failure(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that a failed entry maps to a non-empty error string in the result dict."""
        entry = make_entry(".zoom", is_dir=True)

        with patch(
            "dotcleaner.cleaner._send2trash", side_effect=OSError("disk full")
        ), patch("dotcleaner.cleaner.HAS_SEND2TRASH", True):
            results = trash_entries([entry])

        path_str = str(entry.path)
        assert path_str in results
        assert results[path_str] is not None  # error message string
        assert isinstance(results[path_str], str)

    def test_partial_failure_continues(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that trash_entries continues processing remaining entries after one failure."""
        entry_ok = make_entry(".vim", is_dir=True)
        entry_fail = make_entry(".nonexistent-really-12345", is_dir=True)
        # Remove the directory to make the path non-existent
        entry_fail.path.rmdir()

        with patch("dotcleaner.cleaner._send2trash"), patch(
            "dotcleaner.cleaner.HAS_SEND2TRASH", True
        ):
            results = trash_entries([entry_ok, entry_fail])

        # entry_ok must succeed
        assert results[str(entry_ok.path)] is None
        # entry_fail must contain an error
        assert results[str(entry_fail.path)] is not None

    def test_empty_list_returns_empty_dict(self) -> None:
        """Asserts that an empty input list yields an empty result dict."""
        results = trash_entries([])
        assert results == {}

    def test_all_entries_appear_in_result(
        self, make_entry: Callable[..., DotEntry]
    ) -> None:
        """Asserts that every entry appears in the result dict regardless of success or failure."""
        entries = [
            make_entry(".vim"),
            make_entry(".zoom"),
            make_entry(".tmux"),
        ]
        with patch("dotcleaner.cleaner._send2trash"), patch(
            "dotcleaner.cleaner.HAS_SEND2TRASH", True
        ):
            results = trash_entries(entries)

        assert len(results) == len(entries)
        for entry in entries:
            assert str(entry.path) in results

    def test_uses_path_string_as_key(self, make_entry: Callable[..., DotEntry]) -> None:
        """Asserts that result dict keys are plain strings, not Path objects."""
        entry = make_entry(".vim")
        with patch("dotcleaner.cleaner._send2trash"), patch(
            "dotcleaner.cleaner.HAS_SEND2TRASH", True
        ):
            results = trash_entries([entry])

        for key in results:
            assert isinstance(key, str)


# ---------------------------------------------------------------------------
# Test: get_trash_dir
# ---------------------------------------------------------------------------


class TestGetTrashDir:
    """Tests for get_trash_dir()."""

    def test_returns_xdg_data_home_trash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Asserts that get_trash_dir() uses XDG_DATA_HOME when set."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        result = get_trash_dir()
        assert result == tmp_path / "Trash"

    def test_returns_default_trash_when_no_xdg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Asserts that get_trash_dir() falls back to ~/.local/share/Trash when XDG_DATA_HOME is unset."""
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        result = get_trash_dir()
        assert result == Path.home() / ".local" / "share" / "Trash"

    def test_returns_path_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Asserts that get_trash_dir() returns a Path instance, not a string."""
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        result = get_trash_dir()
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# Test: get_trash_size
# ---------------------------------------------------------------------------


class TestGetTrashSize:
    """Tests for get_trash_size()."""

    def test_returns_zero_when_trash_not_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Asserts that get_trash_size() returns 0 when the trash directory does not exist."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        # Do not create the Trash/files directory
        result = get_trash_size()
        assert result == 0

    def test_returns_correct_size_for_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Asserts that get_trash_size() correctly sums the sizes of files in the trash."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        trash_files = tmp_path / "Trash" / "files"
        trash_files.mkdir(parents=True)

        (trash_files / "file1.txt").write_bytes(b"a" * 1000)
        (trash_files / "file2.txt").write_bytes(b"b" * 500)

        result = get_trash_size()
        assert result == 1500

    def test_returns_correct_size_for_directories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Asserts that get_trash_size() recursively sums directory contents in the trash."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        trash_files = tmp_path / "Trash" / "files"
        trash_files.mkdir(parents=True)

        sub = trash_files / "my-app-dir"
        sub.mkdir()
        (sub / "data.db").write_bytes(b"x" * 2000)
        (sub / "config.json").write_bytes(b"y" * 100)

        result = get_trash_size()
        assert result == 2100

    def test_returns_zero_for_empty_trash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Asserts that get_trash_size() returns 0 when the trash directory exists but is empty."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        trash_files = tmp_path / "Trash" / "files"
        trash_files.mkdir(parents=True)
        # No files placed inside

        result = get_trash_size()
        assert result == 0

    def test_returns_int(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Asserts that get_trash_size() always returns an int."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        result = get_trash_size()
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Test: CleanError
# ---------------------------------------------------------------------------


class TestCleanError:
    """Tests for the CleanError exception class."""

    def test_is_exception(self) -> None:
        """Asserts that CleanError is a subclass of Exception."""
        assert issubclass(CleanError, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        """Asserts that CleanError can be raised and caught normally."""
        with pytest.raises(CleanError, match="test error"):
            raise CleanError("test error")

    def test_message_preserved(self) -> None:
        """Asserts that the error message passed to CleanError is preserved in str() output."""
        err = CleanError("specific error message")
        assert "specific error message" in str(err)
