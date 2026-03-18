"""
test_cleaner.py - Test funzionali per dotcleaner/cleaner.py

Testa trash_entry(), trash_entries(), CleanError, get_trash_dir(), get_trash_size()
con send2trash mockato per evitare modifiche reali al filesystem.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock, patch

import pytest

from dotcleaner.cleaner import CleanError, get_trash_dir, get_trash_size, trash_entries, trash_entry
from dotcleaner.scanner import DotEntry


# ---------------------------------------------------------------------------
# Test: trash_entry — comportamento base
# ---------------------------------------------------------------------------

class TestTrashEntry:
    """Test di trash_entry() con send2trash mockato."""

    def test_calls_send2trash_with_string_path(self, make_entry: Callable[..., DotEntry]) -> None:
        """trash_entry() chiama send2trash con il path come stringa."""
        entry = make_entry(".zoom", is_dir=True)
        assert entry.path.exists()

        with patch("dotcleaner.cleaner._send2trash") as mock_trash, \
             patch("dotcleaner.cleaner.HAS_SEND2TRASH", True):
            trash_entry(entry)

        mock_trash.assert_called_once_with(str(entry.path))

    def test_raises_clean_error_for_nonexistent_path(self, tmp_path: Path) -> None:
        """trash_entry() solleva CleanError se il path non esiste."""
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

    def test_raises_clean_error_if_send2trash_missing(self, make_entry: Callable[..., DotEntry]) -> None:
        """trash_entry() solleva CleanError se send2trash non è installato."""
        entry = make_entry(".zoom")

        with patch("dotcleaner.cleaner.HAS_SEND2TRASH", False):
            with pytest.raises(CleanError, match="send2trash"):
                trash_entry(entry)

    def test_raises_clean_error_on_send2trash_exception(self, make_entry: Callable[..., DotEntry]) -> None:
        """trash_entry() wrappa le eccezioni di send2trash in CleanError."""
        entry = make_entry(".zoom")

        with patch("dotcleaner.cleaner._send2trash", side_effect=OSError("permission denied")), \
             patch("dotcleaner.cleaner.HAS_SEND2TRASH", True):
            with pytest.raises(CleanError, match="Impossibile spostare"):
                trash_entry(entry)

    def test_does_not_use_shutil_rmtree(self, make_entry: Callable[..., DotEntry]) -> None:
        """trash_entry() non chiama mai shutil.rmtree."""
        import shutil
        entry = make_entry(".zoom")

        original_rmtree = shutil.rmtree
        rmtree_called: list[tuple[object, ...]] = []

        def mock_rmtree(*args: object, **kwargs: object) -> None:
            rmtree_called.append(args)

        with patch("dotcleaner.cleaner._send2trash"), \
             patch("dotcleaner.cleaner.HAS_SEND2TRASH", True), \
             patch("shutil.rmtree", side_effect=mock_rmtree):
            trash_entry(entry)

        assert len(rmtree_called) == 0, "shutil.rmtree non deve mai essere chiamato!"

    def test_does_not_use_os_remove(self, make_entry: Callable[..., DotEntry]) -> None:
        """trash_entry() non chiama mai os.remove."""
        entry = make_entry(".gitconfig", is_dir=False)
        os_remove_called: list[tuple[object, ...]] = []

        def mock_os_remove(*args: object, **kwargs: object) -> None:
            os_remove_called.append(args)

        with patch("dotcleaner.cleaner._send2trash"), \
             patch("dotcleaner.cleaner.HAS_SEND2TRASH", True), \
             patch("os.remove", side_effect=mock_os_remove):
            trash_entry(entry)

        assert len(os_remove_called) == 0, "os.remove non deve mai essere chiamato!"

    def test_works_with_file_entry(self, make_entry: Callable[..., DotEntry]) -> None:
        """trash_entry() funziona anche su file singoli."""
        entry = make_entry(".gitconfig", is_dir=False)
        with patch("dotcleaner.cleaner._send2trash") as mock_trash, \
             patch("dotcleaner.cleaner.HAS_SEND2TRASH", True):
            trash_entry(entry)
        mock_trash.assert_called_once()

    def test_works_with_symlink(self, tmp_path: Path) -> None:
        """trash_entry() funziona su symlink validi."""
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
        with patch("dotcleaner.cleaner._send2trash") as mock_trash, \
             patch("dotcleaner.cleaner.HAS_SEND2TRASH", True):
            trash_entry(entry)
        mock_trash.assert_called_once_with(str(link))


# ---------------------------------------------------------------------------
# Test: trash_entries — operazioni batch
# ---------------------------------------------------------------------------

class TestTrashEntries:
    """Test di trash_entries() con lista di DotEntry."""

    def test_returns_dict_with_none_on_success(self, make_entry: Callable[..., DotEntry]) -> None:
        """Ogni entry riuscita ha valore None nel dict risultato."""
        entries = [
            make_entry(".vim", is_dir=True),
            make_entry(".zoom", is_dir=True),
        ]
        with patch("dotcleaner.cleaner._send2trash"), \
             patch("dotcleaner.cleaner.HAS_SEND2TRASH", True):
            results = trash_entries(entries)

        for entry in entries:
            assert str(entry.path) in results
            assert results[str(entry.path)] is None

    def test_returns_error_message_on_failure(self, make_entry: Callable[..., DotEntry]) -> None:
        """Entry fallite hanno un messaggio d'errore nel dict risultato."""
        entry = make_entry(".zoom", is_dir=True)

        with patch("dotcleaner.cleaner._send2trash", side_effect=OSError("disk full")), \
             patch("dotcleaner.cleaner.HAS_SEND2TRASH", True):
            results = trash_entries([entry])

        path_str = str(entry.path)
        assert path_str in results
        assert results[path_str] is not None  # messaggio d'errore
        assert isinstance(results[path_str], str)

    def test_partial_failure_continues(self, make_entry: Callable[..., DotEntry]) -> None:
        """Se una entry fallisce, le altre vengono comunque processate."""
        entry_ok = make_entry(".vim", is_dir=True)
        entry_fail = make_entry(".nonexistent-really-12345", is_dir=True)
        # Rimuovi la directory per renderla inesistente
        entry_fail.path.rmdir()

        with patch("dotcleaner.cleaner._send2trash"), \
             patch("dotcleaner.cleaner.HAS_SEND2TRASH", True):
            results = trash_entries([entry_ok, entry_fail])

        # entry_ok deve avere successo
        assert results[str(entry_ok.path)] is None
        # entry_fail deve avere un errore
        assert results[str(entry_fail.path)] is not None

    def test_empty_list_returns_empty_dict(self) -> None:
        """Lista vuota → dizionario vuoto."""
        results = trash_entries([])
        assert results == {}

    def test_all_entries_appear_in_result(self, make_entry: Callable[..., DotEntry]) -> None:
        """Ogni entry appare nel dizionario risultato, riuscita o no."""
        entries = [
            make_entry(".vim"),
            make_entry(".zoom"),
            make_entry(".tmux"),
        ]
        with patch("dotcleaner.cleaner._send2trash"), \
             patch("dotcleaner.cleaner.HAS_SEND2TRASH", True):
            results = trash_entries(entries)

        assert len(results) == len(entries)
        for entry in entries:
            assert str(entry.path) in results

    def test_uses_path_string_as_key(self, make_entry: Callable[..., DotEntry]) -> None:
        """Le chiavi del dict sono stringhe (non Path objects)."""
        entry = make_entry(".vim")
        with patch("dotcleaner.cleaner._send2trash"), \
             patch("dotcleaner.cleaner.HAS_SEND2TRASH", True):
            results = trash_entries([entry])

        for key in results:
            assert isinstance(key, str)


# ---------------------------------------------------------------------------
# Test: get_trash_dir
# ---------------------------------------------------------------------------

class TestGetTrashDir:
    """Test di get_trash_dir()."""

    def test_returns_xdg_data_home_trash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Se XDG_DATA_HOME è impostato, usa quello."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        result = get_trash_dir()
        assert result == tmp_path / "Trash"

    def test_returns_default_trash_when_no_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Senza XDG_DATA_HOME, usa ~/.local/share/Trash."""
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        result = get_trash_dir()
        assert result == Path.home() / ".local" / "share" / "Trash"

    def test_returns_path_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_trash_dir() ritorna un Path, non una stringa."""
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        result = get_trash_dir()
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# Test: get_trash_size
# ---------------------------------------------------------------------------

class TestGetTrashSize:
    """Test di get_trash_size()."""

    def test_returns_zero_when_trash_not_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Se il cestino non esiste, ritorna 0."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        # Non crea la directory Trash/files
        result = get_trash_size()
        assert result == 0

    def test_returns_correct_size_for_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_trash_size() calcola correttamente la dimensione dei file nel cestino."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        trash_files = tmp_path / "Trash" / "files"
        trash_files.mkdir(parents=True)

        # Crea file con dimensioni note
        (trash_files / "file1.txt").write_bytes(b"a" * 1000)
        (trash_files / "file2.txt").write_bytes(b"b" * 500)

        result = get_trash_size()
        assert result == 1500

    def test_returns_correct_size_for_directories(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_trash_size() calcola ricorsivamente le directory nel cestino."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        trash_files = tmp_path / "Trash" / "files"
        trash_files.mkdir(parents=True)

        # Crea una directory con file dentro
        sub = trash_files / "my-app-dir"
        sub.mkdir()
        (sub / "data.db").write_bytes(b"x" * 2000)
        (sub / "config.json").write_bytes(b"y" * 100)

        result = get_trash_size()
        assert result == 2100

    def test_returns_zero_for_empty_trash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cestino vuoto (directory esistente ma senza file) → 0."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        trash_files = tmp_path / "Trash" / "files"
        trash_files.mkdir(parents=True)
        # Nessun file

        result = get_trash_size()
        assert result == 0

    def test_returns_int(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_trash_size() ritorna sempre un int."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        result = get_trash_size()
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Test: CleanError
# ---------------------------------------------------------------------------

class TestCleanError:
    """Test dell'eccezione CleanError."""

    def test_is_exception(self) -> None:
        """CleanError è una sottoclasse di Exception."""
        assert issubclass(CleanError, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        """CleanError può essere sollevata e catturata."""
        with pytest.raises(CleanError, match="test error"):
            raise CleanError("test error")

    def test_message_preserved(self) -> None:
        """Il messaggio d'errore è preservato."""
        err = CleanError("specific error message")
        assert "specific error message" in str(err)
