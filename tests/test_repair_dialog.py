"""Tests for RepairLibraryDialog (app/library/repair_dialog.py)."""

import hashlib

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from app.database import AudioFile, DatabaseConnection
from app.library import repair
from app.library.repair import Confidence
from app.library.repair_dialog import RepairLibraryDialog


@pytest.fixture
def db(tmp_path):
    conn = DatabaseConnection(str(tmp_path / "live.db"))
    conn.connect()
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def no_spotlight(monkeypatch):
    """Default every test to 'Spotlight finds nothing'; tests override."""
    monkeypatch.setattr(repair, "spotlight_search", lambda name: [])


def add_entry(db, file_path: str, content: bytes | None = None) -> AudioFile:
    audio_file = AudioFile(file_path=file_path, title=file_path)
    if content is not None:
        audio_file.file_size = len(content)
        audio_file.content_hash = hashlib.sha256(content).hexdigest()
    file_id = db.add_audio_file(audio_file)
    stored = db.get_audio_file(file_id)
    assert stored is not None
    return stored


def make_dialog(qapp, db) -> RepairLibraryDialog:
    dialog = RepairLibraryDialog(db, audio_engine=None)
    dialog.show()  # fires the automatic Spotlight scan
    qapp.processEvents()
    return dialog


class FakeTrackPlayer(QObject):
    end_reached = pyqtSignal()
    instances: list["FakeTrackPlayer"] = []

    def __init__(self, file_path, engine=None):
        super().__init__()
        self.file_path = file_path
        self.calls: list[str] = []
        FakeTrackPlayer.instances.append(self)

    def fade_in(self, ms):
        self.calls.append("fade_in")

    def fade_out(self, ms):
        self.calls.append("fade_out")

    def stop(self):
        self.calls.append("stop")

    def release(self):
        self.calls.append("release")


class TestStates:
    def test_all_linked_library(self, qapp, db, tmp_path):
        present = tmp_path / "here.mp3"
        present.write_bytes(b"x")
        add_entry(db, str(present))

        dialog = make_dialog(qapp, db)

        assert dialog.entries == []
        assert "All library files are linked" in dialog.header_label.text()
        assert not dialog.search_folder_btn.isEnabled()

    def test_unlinked_without_match_shows_no_match(self, qapp, db, tmp_path):
        add_entry(db, str(tmp_path / "gone.mp3"), b"x")

        dialog = make_dialog(qapp, db)

        assert len(dialog.items) == 1
        assert not dialog.items[0].entry.candidates
        assert "1 library file points" in dialog.header_label.text()
        assert "Matches found for 0" in dialog.header_label.text()


class TestSpotlightFlow:
    def test_exact_match_candidate_and_relink(self, qapp, db, tmp_path, monkeypatch):
        content = b"forest ambience" * 100
        entry = add_entry(db, str(tmp_path / "old/Forest.mp3"), content)
        moved = tmp_path / "new" / "Forest.mp3"
        moved.parent.mkdir()
        moved.write_bytes(content)
        monkeypatch.setattr(repair, "spotlight_search", lambda name: [str(moved)])

        dialog = make_dialog(qapp, db)

        item = dialog.items[0]
        assert item.selected_candidate().confidence is Confidence.CERTAIN
        assert item.confidence_badge.text() == "Exact match"

        item.relink_btn.click()

        stored = db.get_audio_file(entry.id)
        assert stored is not None and stored.file_path == str(moved)
        assert dialog.relinked_count == 1
        assert item.relinked
        assert "All unlinked files have been relinked" in dialog.header_label.text()

    def test_probable_match_badge(self, qapp, db, tmp_path, monkeypatch):
        add_entry(db, str(tmp_path / "old/Theme.mp3"), b"v1")
        lookalike = tmp_path / "Theme.mp3"
        lookalike.write_bytes(b"different bytes")
        monkeypatch.setattr(repair, "spotlight_search", lambda name: [str(lookalike)])

        dialog = make_dialog(qapp, db)

        item = dialog.items[0]
        assert item.selected_candidate().confidence is Confidence.PROBABLE
        assert "preview to confirm" in item.confidence_badge.text()

    def test_relink_refreshes_fingerprint_of_probable(
        self, qapp, db, tmp_path, monkeypatch
    ):
        entry = add_entry(db, str(tmp_path / "old/Theme.mp3"), b"v1")
        lookalike = tmp_path / "Theme.mp3"
        new_content = b"remastered edition"
        lookalike.write_bytes(new_content)
        monkeypatch.setattr(repair, "spotlight_search", lambda name: [str(lookalike)])

        dialog = make_dialog(qapp, db)
        dialog.items[0].relink_btn.click()

        stored = db.get_audio_file(entry.id)
        assert stored is not None
        assert stored.file_size == len(new_content)
        assert stored.content_hash == hashlib.sha256(new_content).hexdigest()


class TestFolderFlow:
    def test_folder_scan_finds_renamed_file(self, qapp, db, tmp_path, monkeypatch):
        content = b"battle drums" * 200
        entry = add_entry(db, str(tmp_path / "old/Drums.mp3"), content)
        renamed = tmp_path / "root" / "Renamed Drums.mp3"
        renamed.parent.mkdir()
        renamed.write_bytes(content)
        monkeypatch.setattr(
            "app.library.repair_dialog.QFileDialog.getExistingDirectory",
            staticmethod(lambda *a, **k: str(tmp_path / "root")),
        )

        dialog = make_dialog(qapp, db)
        assert not dialog.items[0].entry.candidates

        dialog.search_folder_btn.click()

        item = dialog.items[0]
        assert [c.path for c in item.entry.candidates] == [str(renamed)]
        assert item.selected_candidate().confidence is Confidence.CERTAIN

        item.relink_btn.click()
        stored = db.get_audio_file(entry.id)
        assert stored is not None and stored.file_path == str(renamed)

    def test_cancelled_picker_is_a_noop(self, qapp, db, tmp_path, monkeypatch):
        add_entry(db, str(tmp_path / "gone.mp3"), b"x")
        monkeypatch.setattr(
            "app.library.repair_dialog.QFileDialog.getExistingDirectory",
            staticmethod(lambda *a, **k: ""),
        )
        dialog = make_dialog(qapp, db)

        dialog.search_folder_btn.click()

        assert not dialog.items[0].entry.candidates


class TestPreview:
    @pytest.fixture(autouse=True)
    def fake_player(self, monkeypatch):
        FakeTrackPlayer.instances = []
        monkeypatch.setattr("app.audio.TrackPlayer", FakeTrackPlayer)

    def _dialog_with_candidate(self, qapp, db, tmp_path, monkeypatch):
        content = b"wind howl" * 50
        add_entry(db, str(tmp_path / "old/Wind.mp3"), content)
        moved = tmp_path / "Wind.mp3"
        moved.write_bytes(content)
        monkeypatch.setattr(repair, "spotlight_search", lambda name: [str(moved)])
        return make_dialog(qapp, db), str(moved)

    def test_preview_toggles_playback(self, qapp, db, tmp_path, monkeypatch):
        dialog, moved = self._dialog_with_candidate(qapp, db, tmp_path, monkeypatch)
        item = dialog.items[0]

        item.preview_btn.click()
        player = FakeTrackPlayer.instances[-1]
        assert player.file_path == moved
        assert "fade_in" in player.calls

        item.preview_btn.click()  # same button stops
        assert "fade_out" in player.calls and "release" in player.calls
        assert dialog._preview_player is None

    def test_close_stops_preview(self, qapp, db, tmp_path, monkeypatch):
        dialog, _ = self._dialog_with_candidate(qapp, db, tmp_path, monkeypatch)
        dialog.items[0].preview_btn.click()
        player = FakeTrackPlayer.instances[-1]

        dialog.reject()

        assert "stop" in player.calls and "release" in player.calls

    def test_relink_stops_preview(self, qapp, db, tmp_path, monkeypatch):
        dialog, _ = self._dialog_with_candidate(qapp, db, tmp_path, monkeypatch)
        item = dialog.items[0]
        item.preview_btn.click()
        player = FakeTrackPlayer.instances[-1]

        item.relink_btn.click()

        assert "release" in player.calls
        assert dialog._preview_player is None
