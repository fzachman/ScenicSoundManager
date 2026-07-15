"""Tests for soundboard database operations (Plan 008 Phase 2).

Covers board/button CRUD round-trips, alphabetical board ordering, cascade
deletes (board -> buttons, audio file -> buttons), button reorder
persistence, volume updates, the unique-track-per-board constraint, and tag
batch-loading on get_soundboard_buttons.
"""

import os
import sqlite3
import tempfile

import pytest

from app.database import (
    AudioFile,
    DatabaseConnection,
    Soundboard,
    Tag,
)


@pytest.fixture
def db():
    """Create a temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = DatabaseConnection(db_path)
    conn.connect()

    yield conn

    conn.close()
    os.unlink(db_path)


@pytest.fixture
def audio_ids(db):
    """Three library files to put on boards"""
    return [
        db.add_audio_file(AudioFile(file_path=f"/sfx/effect{i}.mp3", title=f"FX {i}"))
        for i in range(3)
    ]


class TestSoundboards:
    def test_add_and_get_soundboard(self, db):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        assert board_id > 0
        board = db.get_soundboard(board_id)
        assert board is not None
        assert board.name == "Combat"
        assert board.buttons == []

    def test_get_missing_soundboard_returns_none(self, db):
        assert db.get_soundboard(999) is None

    def test_get_all_soundboards_alphabetical_case_insensitive(self, db):
        for name in ["tavern", "Ambush", "combat"]:
            db.add_soundboard(Soundboard(name=name))
        names = [b.name for b in db.get_all_soundboards()]
        assert names == ["Ambush", "combat", "tavern"]

    def test_update_soundboard_renames(self, db):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        board = db.get_soundboard(board_id)
        board.name = "Boss Fight"
        db.update_soundboard(board)
        assert db.get_soundboard(board_id).name == "Boss Fight"

    def test_delete_soundboard(self, db):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        db.delete_soundboard(board_id)
        assert db.get_soundboard(board_id) is None

    def test_delete_soundboard_cascades_to_buttons(self, db, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        db.add_button_to_soundboard(board_id, audio_ids[0])
        db.add_button_to_soundboard(board_id, audio_ids[1])
        db.delete_soundboard(board_id)
        cursor = db._conn.execute(
            "SELECT COUNT(*) AS n FROM soundboard_buttons WHERE soundboard_id = ?",
            (board_id,),
        )
        assert cursor.fetchone()["n"] == 0


class TestSoundboardButtons:
    def test_add_buttons_appends_positions(self, db, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        for file_id in audio_ids:
            db.add_button_to_soundboard(board_id, file_id)
        buttons = db.get_soundboard_buttons(board_id)
        assert [b.position for b in buttons] == [0, 1, 2]
        assert [b.audio_file_id for b in buttons] == audio_ids

    def test_buttons_carry_audio_file_data(self, db, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        db.add_button_to_soundboard(board_id, audio_ids[0], volume=0.5)
        button = db.get_soundboard_buttons(board_id)[0]
        assert button.volume == 0.5
        assert button.audio_file is not None
        assert button.audio_file.title == "FX 0"
        assert button.audio_file.file_path == "/sfx/effect0.mp3"

    def test_buttons_batch_load_tags(self, db, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        tag_id = db.add_tag(Tag(name="stinger", color="#ff0000"))
        db.add_tag_to_audio_file(audio_ids[0], tag_id)
        db.add_button_to_soundboard(board_id, audio_ids[0])
        db.add_button_to_soundboard(board_id, audio_ids[1])
        buttons = db.get_soundboard_buttons(board_id)
        assert [t.name for t in buttons[0].audio_file.tags] == ["stinger"]
        assert buttons[1].audio_file.tags == []

    def test_same_track_twice_on_board_rejected(self, db, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        db.add_button_to_soundboard(board_id, audio_ids[0])
        with pytest.raises(sqlite3.IntegrityError):
            db.add_button_to_soundboard(board_id, audio_ids[0])

    def test_same_track_on_different_boards_allowed(self, db, audio_ids):
        board_a = db.add_soundboard(Soundboard(name="Combat"))
        board_b = db.add_soundboard(Soundboard(name="Tavern"))
        db.add_button_to_soundboard(board_a, audio_ids[0])
        db.add_button_to_soundboard(board_b, audio_ids[0])
        assert len(db.get_soundboard_buttons(board_a)) == 1
        assert len(db.get_soundboard_buttons(board_b)) == 1

    def test_update_button_volume(self, db, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        button_id = db.add_button_to_soundboard(board_id, audio_ids[0])
        db.update_soundboard_button_volume(button_id, 0.29)
        assert db.get_soundboard_buttons(board_id)[0].volume == 0.29

    def test_remove_button(self, db, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        button_id = db.add_button_to_soundboard(board_id, audio_ids[0])
        db.remove_soundboard_button(button_id)
        assert db.get_soundboard_buttons(board_id) == []

    def test_reorder_buttons_persists(self, db, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        ids = [db.add_button_to_soundboard(board_id, f) for f in audio_ids]
        db.reorder_soundboard_buttons(board_id, [ids[2], ids[0], ids[1]])
        buttons = db.get_soundboard_buttons(board_id)
        assert [b.id for b in buttons] == [ids[2], ids[0], ids[1]]
        assert [b.position for b in buttons] == [0, 1, 2]

    def test_reorder_ignores_buttons_of_other_boards(self, db, audio_ids):
        board_a = db.add_soundboard(Soundboard(name="Combat"))
        board_b = db.add_soundboard(Soundboard(name="Tavern"))
        a_button = db.add_button_to_soundboard(board_a, audio_ids[0])
        b_button = db.add_button_to_soundboard(board_b, audio_ids[1])
        db.reorder_soundboard_buttons(board_a, [b_button, a_button])
        assert db.get_soundboard_buttons(board_b)[0].position == 0

    def test_deleting_audio_file_cascades_to_buttons(self, db, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        db.add_button_to_soundboard(board_id, audio_ids[0])
        db.add_button_to_soundboard(board_id, audio_ids[1])
        db.delete_audio_file(audio_ids[0])
        buttons = db.get_soundboard_buttons(board_id)
        assert [b.audio_file_id for b in buttons] == [audio_ids[1]]

    def test_get_soundboard_includes_buttons(self, db, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        for file_id in audio_ids:
            db.add_button_to_soundboard(board_id, file_id)
        board = db.get_soundboard(board_id)
        assert len(board.buttons) == 3
        assert board.buttons[0].audio_file.title == "FX 0"
