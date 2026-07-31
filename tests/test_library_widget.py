"""Tests for LibraryWidget's empty-state / import-hint toggling.

An empty library shows the big drop placeholder; once files exist the table
takes over and a persistent one-line hint below it tells users they can still
drag files in (beta feedback: users didn't realize drops work after the
placeholder disappears).
"""

import os
import tempfile
from unittest.mock import MagicMock

import pytest

from app.database import AudioFile, DatabaseConnection
from app.library.library_widget import LibraryWidget


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = DatabaseConnection(db_path)
    conn.connect()
    yield conn
    conn.close()
    os.unlink(db_path)


@pytest.fixture
def widget(qapp, db):
    widget = LibraryWidget(db, MagicMock())
    widget.resize(1000, 600)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()


def _add_file(db, i=0):
    db.add_audio_file(AudioFile(file_path=f"/fake/track_{i}.mp3", title=f"Track {i}"))


class TestEmptyStateToggle:
    def test_empty_library_shows_placeholder_not_hint(self, widget):
        assert widget.drop_hint.isVisible()
        assert not widget.file_table.isVisible()
        assert not widget.import_hint.isVisible()

    def test_populated_library_shows_table_and_import_hint(self, qapp, widget, db):
        _add_file(db)
        widget._load_files()
        qapp.processEvents()
        assert not widget.drop_hint.isVisible()
        assert widget.file_table.isVisible()
        assert widget.import_hint.isVisible()

    def test_deleting_last_file_restores_placeholder(self, qapp, widget, db):
        _add_file(db)
        widget._load_files()
        for f in db.get_all_audio_files():
            db.delete_audio_file(f.id)
        widget._refresh_current_view()
        qapp.processEvents()
        assert widget.drop_hint.isVisible()
        assert not widget.import_hint.isVisible()
