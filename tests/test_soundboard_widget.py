"""Tests for the soundboard board UI (Plan 008 Phases 4-5).

SoundboardContent is driven against a real temporary database and a real
SoundboardPlayer QObject whose action methods (trigger/stop/clear/
set_current_volume) are replaced with MagicMocks — its signals stay real so
the highlight wiring can be exercised by emitting them. The reorder tests
lay out a real SoundboardGrid at a width that forces wrapping, so the 2D
hit-test runs against genuine FlowLayout geometry.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QByteArray, QMimeData, QPointF, QSettings, Qt
from PyQt6.QtGui import QDropEvent

from app.audio.soundboard_player import SoundboardPlayer
from app.database import AudioFile, DatabaseConnection, Soundboard, SoundboardButton
from app.shared.icons import IconLibrary
from app.soundboard.board_widget import (
    SOUNDBOARD_BUTTON_MIME,
    SoundboardButtonCell,
    SoundboardContent,
    SoundboardGrid,
)


@pytest.fixture(autouse=True)
def clean_soundboard_settings(qapp):
    settings = QSettings()
    settings.remove(SoundboardContent.SETTINGS_GROUP)
    yield
    settings.remove(SoundboardContent.SETTINGS_GROUP)


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
def audio_ids(db):
    return [
        db.add_audio_file(AudioFile(file_path=f"/sfx/effect{i}.mp3", title=f"FX {i}"))
        for i in range(3)
    ]


@pytest.fixture
def player(qapp):
    engine = MagicMock()
    engine.available = False
    engine.master_volume = 100
    sp = SoundboardPlayer(engine=engine)
    sp.trigger = MagicMock(name="trigger")
    sp.stop = MagicMock(name="stop")
    sp.clear = MagicMock(name="clear")
    sp.set_current_volume = MagicMock(name="set_current_volume")
    return sp


def make_content(db, player):
    return SoundboardContent(db, audio_engine=None, player=player)


def cells_of(content):
    return list(content._cells_by_button_id.values())


class TestEmptyStates:
    def test_no_boards_shows_hint_and_disables_edit(self, qapp, db, player):
        content = make_content(db, player)
        assert content.board_combo.count() == 0
        assert "No soundboards yet" in content.empty_label.text()
        assert not content.edit_btn.isEnabled()

    def test_empty_board_shows_hint(self, qapp, db, player):
        db.add_soundboard(Soundboard(name="Combat"))
        content = make_content(db, player)
        assert "no sounds" in content.empty_label.text()


class TestBoardSelection:
    def test_boards_populate_alphabetically(self, qapp, db, player):
        for name in ["tavern", "Ambush", "combat"]:
            db.add_soundboard(Soundboard(name=name))
        content = make_content(db, player)
        names = [content.board_combo.itemText(i) for i in range(3)]
        assert names == ["Ambush", "combat", "tavern"]

    def test_last_board_id_restored(self, qapp, db, player):
        db.add_soundboard(Soundboard(name="Ambush"))
        tavern_id = db.add_soundboard(Soundboard(name="Tavern"))
        settings = QSettings()
        settings.beginGroup(SoundboardContent.SETTINGS_GROUP)
        settings.setValue(SoundboardContent.SETTINGS_LAST_BOARD_ID, tavern_id)
        settings.endGroup()

        content = make_content(db, player)
        assert content.current_board_id() == tavern_id

    def test_board_switch_clears_player_and_persists(self, qapp, db, player):
        db.add_soundboard(Soundboard(name="Ambush"))
        tavern_id = db.add_soundboard(Soundboard(name="Tavern"))
        content = make_content(db, player)
        player.clear.reset_mock()

        content.board_combo.setCurrentIndex(1)

        player.clear.assert_called_once()
        assert content.current_board_id() == tavern_id
        settings = QSettings()
        settings.beginGroup(SoundboardContent.SETTINGS_GROUP)
        saved = settings.value(SoundboardContent.SETTINGS_LAST_BOARD_ID, type=int)
        settings.endGroup()
        assert saved == tavern_id


class TestGrid:
    def test_cells_render_in_position_order(self, qapp, db, player, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        for file_id in audio_ids:
            db.add_button_to_soundboard(board_id, file_id)
        content = make_content(db, player)
        cells = cells_of(content)
        assert len(cells) == 3
        assert [c.trigger_btn.toolTip() for c in cells] == ["FX 0", "FX 1", "FX 2"]

    def test_trigger_dispatches_with_button_volume(self, qapp, db, player, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        button_id = db.add_button_to_soundboard(board_id, audio_ids[0], volume=0.4)
        content = make_content(db, player)

        cells_of(content)[0].trigger_btn.click()

        player.trigger.assert_called_once_with(button_id, "/sfx/effect0.mp3", 0.4)

    def test_highlight_follows_player_signals(self, qapp, db, player, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        ids = [db.add_button_to_soundboard(board_id, f) for f in audio_ids]
        content = make_content(db, player)
        first = content._cells_by_button_id[ids[0]]
        second = content._cells_by_button_id[ids[1]]

        player.button_started.emit(ids[0])
        assert first.playing and not second.playing

        # Cut-over: old stopped, new started.
        player.button_stopped.emit(ids[0])
        player.button_started.emit(ids[1])
        assert not first.playing and second.playing

    def test_stop_button_stops_player(self, qapp, db, player, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        db.add_button_to_soundboard(board_id, audio_ids[0])
        content = make_content(db, player)
        content.stop_btn.click()
        player.stop.assert_called_once()


class TestButtonActions:
    def test_remove_deletes_and_rebuilds(self, qapp, db, player, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        ids = [db.add_button_to_soundboard(board_id, f) for f in audio_ids]
        content = make_content(db, player)

        content._on_remove_button(content._cells_by_button_id[ids[0]].button)

        remaining = [b.id for b in db.get_soundboard_buttons(board_id)]
        assert remaining == ids[1:]
        assert set(content._cells_by_button_id) == set(ids[1:])

    def test_remove_stops_playing_button(self, qapp, db, player, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        button_id = db.add_button_to_soundboard(board_id, audio_ids[0])
        content = make_content(db, player)
        player._current_button_id = button_id  # simulate it playing

        content._on_remove_button(content._cells_by_button_id[button_id].button)

        player.stop.assert_called_once()

    def test_volume_committed_persists(self, qapp, db, player, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        button_id = db.add_button_to_soundboard(board_id, audio_ids[0])
        content = make_content(db, player)
        button = content._cells_by_button_id[button_id].button

        content._on_volume_committed(button, 0.29)

        assert db.get_soundboard_buttons(board_id)[0].volume == 0.29
        assert button.volume == 0.29

    def test_volume_changed_applies_live(self, qapp, db, player, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        button_id = db.add_button_to_soundboard(board_id, audio_ids[0])
        content = make_content(db, player)

        content._on_volume_changed(content._cells_by_button_id[button_id].button, 0.5)

        player.set_current_volume.assert_called_once_with(button_id, 0.5)


def fake_dialog(name, files):
    dialog = MagicMock()
    dialog.exec.return_value = True
    dialog.get_name.return_value = name
    dialog.get_selected_files.return_value = files
    return dialog


class TestBoardManagement:
    def test_create_flow(self, qapp, db, player, audio_ids):
        content = make_content(db, player)
        files = [db.get_audio_file(audio_ids[0]), db.get_audio_file(audio_ids[1])]
        with patch(
            "app.soundboard.board_widget.SoundboardEditDialog",
            return_value=fake_dialog("Tavern", files),
        ):
            content._add_board()

        assert content.board_combo.count() == 1
        board_id = content.current_board_id()
        buttons = db.get_soundboard_buttons(board_id)
        assert [b.audio_file_id for b in buttons] == audio_ids[:2]
        assert len(cells_of(content)) == 2

    def test_edit_flow_renames_and_appends(self, qapp, db, player, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        db.add_button_to_soundboard(board_id, audio_ids[0])
        content = make_content(db, player)
        with patch(
            "app.soundboard.board_widget.SoundboardEditDialog",
            return_value=fake_dialog("Boss Fight", [db.get_audio_file(audio_ids[1])]),
        ):
            content._edit_board()

        board = db.get_soundboard(board_id)
        assert board.name == "Boss Fight"
        assert [b.audio_file_id for b in board.buttons] == audio_ids[:2]

    def test_rename_keeps_renamed_board_selected(self, qapp, db, player, audio_ids):
        # "Combat" renamed to "Zombie" sorts after "Tavern"; selection must
        # follow the id, not the index.
        combat_id = db.add_soundboard(Soundboard(name="Combat"))
        db.add_soundboard(Soundboard(name="Tavern"))
        content = make_content(db, player)
        assert content.current_board_id() == combat_id
        with patch(
            "app.soundboard.board_widget.SoundboardEditDialog",
            return_value=fake_dialog("Zombie", []),
        ):
            content._edit_board()

        assert content.current_board_id() == combat_id
        assert content.board_combo.currentText() == "Zombie"
        assert content.board_combo.currentIndex() == 1


def make_grid(qapp, count):
    """A shown SoundboardGrid wide enough for exactly two cells per row.

    Cell footprint is 174x34 (150 trigger + 2 spacing + 22 grabber) with
    8px flow spacing, so width 360 wraps after the second cell. Returns
    (grid, button_ids).
    """
    icons = IconLibrary()
    cells = []
    for i in range(count):
        button = SoundboardButton(
            id=100 + i,
            soundboard_id=1,
            audio_file_id=i,
            position=i,
            volume=1.0,
            audio_file=AudioFile(id=i, file_path=f"/sfx/{i}.mp3", title=f"FX {i}"),
        )
        cells.append(SoundboardButtonCell(button, icons))
    grid = SoundboardGrid()
    grid.populate(cells)
    grid.setFixedWidth(360)
    grid.show()
    qapp.processEvents()
    return grid, [100 + i for i in range(count)]


class TestGridHitTest:
    def test_rows_wrap_as_expected(self, qapp):
        # Sanity-check the fixture geometry the assertions below rely on.
        grid, _ = make_grid(qapp, 3)
        cells = grid.cells_in_order()
        assert cells[0].y() == cells[1].y()  # row 0
        assert cells[2].y() > cells[0].y()  # wrapped to row 1
        grid.close()

    def test_points_map_to_reading_order_indices(self, qapp):
        grid, _ = make_grid(qapp, 3)
        c0, c1, c2 = grid.cells_in_order()
        row0_y = c0.y() + 5
        row1_y = c2.y() + 5
        # Left of the first cell's midpoint -> before it.
        assert grid._index_for_pos(c0.x() + 10, row0_y) == 0
        # Between the midpoints of cells 0 and 1 -> between them.
        assert grid._index_for_pos(c1.x() + 10, row0_y) == 1
        # Right of the last cell in row 0 -> start of row 1.
        assert grid._index_for_pos(c1.x() + c1.width() - 5, row0_y) == 2
        # Row 1, left of cell 2's midpoint -> before it.
        assert grid._index_for_pos(c2.x() + 10, row1_y) == 2
        # Right of cell 2 (over the trailing drop zone) -> append.
        assert grid._index_for_pos(c2.x() + c2.width() + 50, row1_y) == 3
        # Below everything -> append.
        assert grid._index_for_pos(10, row1_y + 200) == 3
        grid.close()

    def test_drop_zone_present_only_with_cells(self, qapp):
        grid, _ = make_grid(qapp, 2)
        assert grid._drop_zone is not None
        grid.populate([])
        assert grid._drop_zone is None
        grid.close()


class TestReorder:
    def test_move_first_to_end(self, qapp):
        grid, ids = make_grid(qapp, 3)
        c2 = grid.cells_in_order()[2]
        end_x, end_y = c2.x() + c2.width() + 50, c2.y() + 5
        assert grid._reordered_ids(ids[0], end_x, end_y) == [ids[1], ids[2], ids[0]]
        grid.close()

    def test_insert_shifts_target_down_list(self, qapp):
        # Dropping cell 2 on cell 1 (left of its midpoint) puts 2 in 1's
        # place and shifts 1 down-list.
        grid, ids = make_grid(qapp, 3)
        c1 = grid.cells_in_order()[1]
        assert grid._reordered_ids(ids[2], c1.x() + 5, c1.y() + 5) == [
            ids[0],
            ids[2],
            ids[1],
        ]
        grid.close()

    def test_drop_on_own_position_is_noop(self, qapp):
        grid, ids = make_grid(qapp, 3)
        c0 = grid.cells_in_order()[0]
        assert grid._reordered_ids(ids[0], c0.x() + 5, c0.y() + 5) is None
        grid.close()

    def test_unknown_id_is_noop(self, qapp):
        grid, _ = make_grid(qapp, 2)
        assert grid._reordered_ids(999, 10, 10) is None
        grid.close()

    def test_drop_event_emits_new_order(self, qapp):
        grid, ids = make_grid(qapp, 3)
        emitted = []
        grid.order_changed.connect(emitted.append)
        c2 = grid.cells_in_order()[2]
        mime = QMimeData()
        mime.setData(SOUNDBOARD_BUTTON_MIME, QByteArray(str(ids[0]).encode()))
        event = QDropEvent(
            QPointF(c2.x() + c2.width() + 50, c2.y() + 5),
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        grid.dropEvent(event)
        assert emitted == [[ids[1], ids[2], ids[0]]]
        grid.close()

    def test_foreign_mime_ignored(self, qapp):
        grid, _ = make_grid(qapp, 2)
        emitted = []
        grid.order_changed.connect(emitted.append)
        mime = QMimeData()
        mime.setData("application/x-soundmanager-playlist-track", QByteArray(b"1"))
        event = QDropEvent(
            QPointF(10, 10),
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        grid.dropEvent(event)
        assert emitted == []
        grid.close()

    def test_content_persists_reorder_and_rebuilds(self, qapp, db, player, audio_ids):
        board_id = db.add_soundboard(Soundboard(name="Combat"))
        ids = [db.add_button_to_soundboard(board_id, f) for f in audio_ids]
        content = make_content(db, player)

        content._on_reorder([ids[2], ids[0], ids[1]])

        assert [b.id for b in db.get_soundboard_buttons(board_id)] == [
            ids[2],
            ids[0],
            ids[1],
        ]
        assert content.grid.button_ids_in_order() == [ids[2], ids[0], ids[1]]


class TestMainWindowIntegration:
    def test_player_and_content_wired(self, qapp, tmp_path, monkeypatch):
        import app.main_window as main_window_module

        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr(
            main_window_module,
            "DatabaseConnection",
            lambda: DatabaseConnection(db_path),
        )
        window = main_window_module.MainWindow()
        try:
            assert isinstance(window.soundboard_player, SoundboardPlayer)
            content = window.soundboard_dock.widget()
            assert isinstance(content, SoundboardContent)
            assert content.player is window.soundboard_player
        finally:
            window.db.close()
