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
from PyQt6.QtCore import QEvent, QItemSelectionModel, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractItemView, QMenu

from app.database import AudioFile, DatabaseConnection, Playlist, Scene
from app.library.file_table import FileTableWidget
from tests.control_helpers import record

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


def _open_context_menu(table, rows):
    """Select ``rows`` and open the context menu without blocking; return it."""
    table.clearSelection()
    flags = (
        QItemSelectionModel.SelectionFlag.Select
        | QItemSelectionModel.SelectionFlag.Rows
    )
    for row in rows:
        table.selectionModel().select(table.model().index(row, 0), flags)
    shown = []

    class RecordingMenu(QMenu):
        def exec(self, *args, **kwargs):
            shown.append(self)

    with patch("app.library.file_table.QMenu", RecordingMenu):
        table._show_context_menu(QPoint(0, 0))
    assert len(shown) == 1
    return shown[0]


def _submenu(menu, title):
    return next(a for a in menu.actions() if a.text() == title).menu()


class TestAddToMenus:
    """Right-click "Add to Playlist ▸" / "Add to Scene ▸": one entry per
    playlist/scene (sidebar order), checkmarks on targets that already hold
    the whole selection, and a request signal carrying the file IDs."""

    def test_submenus_sit_between_play_and_info(self, table):
        menu = _open_context_menu(table, [0])

        assert [a.text() for a in menu.actions()] == [
            "Play",
            "Add to Playlist",
            "Add to Scene",
            "Info (1)",
            "Remove (1 files)",
        ]

    def test_submenus_list_targets_in_sidebar_order(self, table, db):
        db.add_playlist(Playlist(name="Battle Mix"))
        db.add_playlist(Playlist(name="Tavern Tunes"))
        db.add_scene(Scene(title="Ambush"))

        menu = _open_context_menu(table, [0])

        # Newest-first, same as the sidebar (add_* inserts at position 0).
        playlists = _submenu(menu, "Add to Playlist").actions()
        assert [a.text() for a in playlists] == ["Tavern Tunes", "Battle Mix"]
        scenes = _submenu(menu, "Add to Scene").actions()
        assert [a.text() for a in scenes] == ["Ambush"]

    def test_empty_submenus_show_a_disabled_placeholder(self, table):
        menu = _open_context_menu(table, [0])

        for title, placeholder in [
            ("Add to Playlist", "No Playlists"),
            ("Add to Scene", "No Scenes"),
        ]:
            actions = _submenu(menu, title).actions()
            assert [a.text() for a in actions] == [placeholder]
            assert not actions[0].isEnabled()

    def test_targets_holding_the_whole_selection_are_checked(self, table, db, files):
        holding = db.add_playlist(Playlist(name="Holding"))
        db.add_playlist(Playlist(name="Other"))
        db.add_track_to_playlist(holding, files[0].id)
        scene_id = db.add_scene(Scene(title="Scene"))
        db.add_track_to_scene(scene_id, files[0].id)

        menu = _open_context_menu(table, [0])
        checked = [
            a.text()
            for a in _submenu(menu, "Add to Playlist").actions()
            if a.isChecked()
        ]
        assert checked == ["Holding"]
        assert _submenu(menu, "Add to Scene").actions()[0].isChecked()

        # A partial match (only one of two selected files) is not checked.
        menu = _open_context_menu(table, [0, 1])
        assert not any(
            a.isChecked() for a in _submenu(menu, "Add to Playlist").actions()
        )

    def test_choosing_a_playlist_requests_files_in_table_order(self, table, db, files):
        playlist_id = db.add_playlist(Playlist(name="Battle Mix"))
        requests = record(table.add_to_playlist_requested)

        menu = _open_context_menu(table, [2, 0])  # selected bottom-up
        _submenu(menu, "Add to Playlist").actions()[0].trigger()

        assert requests == [(playlist_id, [files[0].id, files[2].id])]

    def test_choosing_a_scene_requests_the_files(self, table, db, files):
        scene_id = db.add_scene(Scene(title="Ambush"))
        requests = record(table.add_to_scene_requested)

        menu = _open_context_menu(table, [1])
        _submenu(menu, "Add to Scene").actions()[0].trigger()

        assert requests == [(scene_id, [files[1].id])]

    def test_choosing_a_checked_target_still_requests(self, table, db, files):
        # The no-op lives in the add itself (it skips held files), so the
        # menu never has to guess; a checked entry sends the same request.
        playlist_id = db.add_playlist(Playlist(name="Holding"))
        db.add_track_to_playlist(playlist_id, files[0].id)
        requests = record(table.add_to_playlist_requested)

        menu = _open_context_menu(table, [0])
        _submenu(menu, "Add to Playlist").actions()[0].trigger()

        assert requests == [(playlist_id, [files[0].id])]

    def test_ampersand_in_a_name_is_shown_literally(self, table, db):
        db.add_playlist(Playlist(name="Rock & Roll"))

        menu = _open_context_menu(table, [0])

        # "&&" renders as a literal "&" instead of a mnemonic marker.
        assert _submenu(menu, "Add to Playlist").actions()[0].text() == "Rock && Roll"
