"""Tests for the library file table's title-cell progress bar / scrubber.

The playing row's Title cell doubles as a seek bar: a translucent fill tracks
playback position, and press/drag/release on the cell scrubs (commit on
release, matching the VolumeSlider/PositionScrubber convention). All other
rows keep their normal click/select/edit behavior.

TrackPlayer is a MagicMock (no VLC needed); position updates are driven by
calling the table's _on_position_changed handler directly.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractItemView

from app.database import AudioFile, DatabaseConnection
from app.library.file_table import FileTableWidget

DURATION_MS = 200_000


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
def files(db):
    """Three files in the db; the last one has no known duration."""
    out = []
    for i, duration in enumerate([200.0, 200.0, None]):
        af = AudioFile(
            file_path=f"/fake/track_{i}.mp3",
            title=f"Track {i}",
            artist="Test Artist",
            duration_seconds=duration,
        )
        af.id = db.add_audio_file(af)
        out.append(af)
    return out


@pytest.fixture
def table(qapp, db, files):
    engine = MagicMock()
    engine.available = False
    engine.master_volume = 100
    with (
        patch("app.library.file_table.TrackPlayer", MagicMock()),
        patch("app.library.file_table.os.path.exists", return_value=True),
    ):
        table = FileTableWidget(db, engine)
        table.resize(900, 400)
        table.set_files(files)
        table.show()
        qapp.processEvents()
        yield table
        table.close()


def _start_playing(table, audio_file, duration_ms=DURATION_MS):
    table._toggle_play_by_file_id(audio_file.id)
    table._current_player.get_duration.return_value = duration_ms


def _title_rect(table, audio_file):
    row = table._find_row_for_file_id(audio_file.id)
    assert row >= 0
    return table.visualItemRect(table.item(row, table.COL_TITLE))


def _title_index(table, audio_file):
    row = table._find_row_for_file_id(audio_file.id)
    return table.model().index(row, table.COL_TITLE)


def _point_at_fraction(rect, fraction):
    return rect.center().__class__(
        rect.left() + int(rect.width() * fraction), rect.center().y()
    )


def _drag_move(table, pos):
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(pos),
        QPointF(table.viewport().mapToGlobal(pos)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    table.mouseMoveEvent(event)


class TestProgressFill:
    def test_position_ticks_move_the_fill(self, table, files):
        _start_playing(table, files[0])

        table._on_position_changed(DURATION_MS // 4)

        assert table._title_progress == 0.25
        assert table.title_progress_fraction(_title_index(table, files[0])) == 0.25

    def test_fraction_is_none_for_other_rows(self, table, files):
        _start_playing(table, files[0])
        table._on_position_changed(DURATION_MS // 4)

        assert table.title_progress_fraction(_title_index(table, files[1])) is None

    def test_fraction_is_none_when_idle(self, table, files):
        assert table.title_progress_fraction(_title_index(table, files[0])) is None

    def test_metadata_duration_fallback_before_vlc_parse(self, table, files):
        # VLC reports 0/-1 until the media is parsed; the bar must still move
        # using the library's metadata duration (200s here).
        _start_playing(table, files[0], duration_ms=0)

        table._on_position_changed(100_000)

        assert table._title_progress == 0.5

    def test_progress_resets_when_stopped(self, table, files):
        _start_playing(table, files[0])
        table._on_position_changed(DURATION_MS // 2)

        table.stop_playback()

        assert table._title_progress == 0.0
        assert table.title_progress_fraction(_title_index(table, files[0])) is None

    def test_progress_resets_when_track_ends(self, table, files):
        _start_playing(table, files[0])
        table._on_position_changed(DURATION_MS // 2)

        table._on_playback_ended(files[0].id)

        assert table._title_progress == 0.0


class TestScrubbing:
    def test_click_jumps_to_position(self, table, files):
        _start_playing(table, files[0])
        rect = _title_rect(table, files[0])
        pos = _point_at_fraction(rect, 0.5)

        QTest.mouseClick(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )

        expected_fraction = (pos.x() - rect.left()) / rect.width()
        table._current_player.set_position.assert_called_once_with(
            int(expected_fraction * DURATION_MS)
        )

    def test_drag_scrubs_and_commits_on_release(self, table, files):
        _start_playing(table, files[0])
        rect = _title_rect(table, files[0])

        QTest.mousePress(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            _point_at_fraction(rect, 0.25),
        )
        assert table._scrubbing is True
        # Player ticks must not fight the drag
        table._on_position_changed(1_000)
        end_pos = _point_at_fraction(rect, 0.75)
        _drag_move(table, end_pos)
        expected_fraction = (end_pos.x() - rect.left()) / rect.width()
        assert table._title_progress == pytest.approx(expected_fraction)

        table._current_player.set_position.assert_not_called()
        QTest.mouseRelease(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            end_pos,
        )

        assert table._scrubbing is False
        table._current_player.set_position.assert_called_once_with(
            int(expected_fraction * DURATION_MS)
        )

    def test_click_on_non_playing_row_selects_normally(self, table, files):
        _start_playing(table, files[0])
        rect = _title_rect(table, files[1])

        QTest.mouseClick(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            rect.center(),
        )

        table._current_player.set_position.assert_not_called()
        selected = [f.id for f in table.get_selected_files()]
        assert selected == [files[1].id]

    def test_click_without_any_duration_falls_through(self, table, files):
        # files[2] has no metadata duration and VLC hasn't parsed: seeking is
        # meaningless, so the click behaves like a normal row click.
        _start_playing(table, files[2], duration_ms=0)
        rect = _title_rect(table, files[2])

        QTest.mouseClick(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            rect.center(),
        )

        table._current_player.set_position.assert_not_called()
        assert table._scrubbing is False

    def test_double_click_seeks_instead_of_opening_editor(self, table, files):
        # A real double-click arrives as press/release/dblclick/release; QTest
        # only synthesizes the bare DblClick, so send the full sequence.
        _start_playing(table, files[0])
        rect = _title_rect(table, files[0])
        pos = _point_at_fraction(rect, 0.5)

        QTest.mouseClick(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )
        QTest.mouseDClick(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )
        QTest.mouseRelease(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )

        assert table.state() != QAbstractItemView.State.EditingState
        assert table._current_player.set_position.called

    def test_double_click_on_other_rows_still_edits(self, table, files, qapp):
        _start_playing(table, files[0])
        rect = _title_rect(table, files[1])

        QTest.mouseClick(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            rect.center(),
        )
        QTest.mouseDClick(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            rect.center(),
        )
        qapp.processEvents()

        assert table.state() == QAbstractItemView.State.EditingState


class TestDeadDragRemoved:
    def test_table_no_longer_advertises_drag(self, table):
        # The old setDragEnabled(True) produced a drag payload nothing in the
        # app accepts; it also would have fought the title-cell scrubber.
        assert table.dragEnabled() is False
