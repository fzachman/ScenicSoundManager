"""Characterization tests for TrackControl.

The volume tests pin the PERF-02 commit-on-release split (live volume_changed
every tick; volume_committed only when the value settles). The remaining tests
pin the rest of the widget's observable behavior — toggles, the set_play_mode
no-emit asymmetry, context-menu removal, the drag MIME payload, constructor
rendering branches, and the full TrackPlayer integration — so the DEBT-01
refactor (hoisting shared logic into SceneControlCard + VolumeSlider) is
provably behavior-preserving.

Pin OBSERVABLE behavior: signals, the in-memory model, and control.volume_slider
(which survives the refactor as an alias to the component's inner slider). Do
NOT assert on internal widgets the refactor relocates (e.g. the percent label,
which moves into VolumeSlider — its text is covered by test_volume_slider.py).
"""

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QLabel

from app.database import AudioFile, SceneAudioFile
from app.scenes.track_control import TrackControl
from app.shared.styles import Styles
from tests.control_helpers import (
    FakeContextEvent,
    FakeDrag,
    FakeMenu,
    FakeMouseEvent,
    FakeTrackPlayer,
    mime_payload,
    patch_qt,
    record,
)

TRACK_MIME = "application/x-soundmanager-track"


def make_track(
    *,
    volume=0.5,
    play_mode=True,
    is_repeat=False,
    with_audio=True,
    file_path="/fake/track.mp3",
    title="Track",
    duration=120.0,
):
    af = (
        AudioFile(file_path=file_path, title=title, duration_seconds=duration)
        if with_audio
        else None
    )
    return SceneAudioFile(
        id=7,
        scene_id=1,
        audio_file_id=1,
        position=0,
        volume=volume,
        is_repeat=is_repeat,
        play_mode=play_mode,
        audio_file=af,
    )


@pytest.fixture
def track():
    af = AudioFile(file_path="/fake/track.mp3", title="Track", duration_seconds=120.0)
    return SceneAudioFile(
        id=7, scene_id=1, audio_file_id=1, position=0, volume=0.5, audio_file=af
    )


def _capture(control):
    live, committed = [], []
    control.volume_changed.connect(lambda tid, v: live.append((tid, v)))
    control.volume_committed.connect(lambda tid, v: committed.append((tid, v)))
    return live, committed


class TestVolumeCommit:
    def test_discrete_change_commits_immediately(self, qapp, track):
        control = TrackControl(track)
        live, committed = _capture(control)

        # A programmatic/keyboard/wheel change happens with the handle up.
        control.volume_slider.setValue(80)

        assert live[-1][0] == 7 and live[-1][1] == pytest.approx(0.8)
        assert committed[-1][0] == 7 and committed[-1][1] == pytest.approx(0.8)

    def test_drag_defers_commit_until_release(self, qapp, track):
        control = TrackControl(track)
        live, committed = _capture(control)

        # Simulate an in-progress drag: handle down, value moving.
        control.volume_slider.setSliderDown(True)
        control.volume_slider.setValue(30)
        control.volume_slider.setValue(20)

        # Live updates fired for each tick...
        assert (7, pytest.approx(0.3)) in live
        assert (7, pytest.approx(0.2)) in live
        # ...but nothing persisted yet.
        assert committed == []

        # Release persists exactly once, with the final value.
        control.volume_slider.sliderReleased.emit()
        assert len(committed) == 1
        assert committed[0][0] == 7 and committed[0][1] == pytest.approx(0.2)

    def test_in_memory_volume_stays_fresh(self, qapp, track):
        # Playback setup reads track.volume directly, so the in-memory model
        # must reflect the current slider value even mid-drag (before commit).
        control = TrackControl(track)
        assert control.track is track

        control.volume_slider.setValue(80)  # discrete
        assert track.volume == pytest.approx(0.8)

        control.volume_slider.setSliderDown(True)  # mid-drag, not yet committed
        control.volume_slider.setValue(30)
        assert track.volume == pytest.approx(0.3)


class TestConstructor:
    def test_title_uses_display_title(self, qapp):
        control = TrackControl(make_track(title="My Track"))
        assert control.title_label.text() == "My Track"

    def test_title_unknown_without_audio_file(self, qapp):
        control = TrackControl(make_track(with_audio=False))
        assert control.title_label.text() == "Unknown"

    def test_tooltip_is_file_path_when_audio_file(self, qapp):
        control = TrackControl(make_track(file_path="/music/song.mp3"))
        assert control.toolTip() == "/music/song.mp3"

    def test_no_tooltip_without_audio_file(self, qapp):
        control = TrackControl(make_track(with_audio=False))
        assert control.toolTip() == ""

    def test_missing_file_warning_present_when_path_missing(self, qapp):
        control = TrackControl(make_track(file_path="/fake/missing.mp3"))
        labels = [lbl.text() for lbl in control.findChildren(QLabel)]
        assert "⚠️ File not found" in labels

    def test_missing_file_warning_absent_when_path_exists(self, qapp, tmp_path):
        real = tmp_path / "real.mp3"
        real.write_bytes(b"x")
        control = TrackControl(make_track(file_path=str(real)))
        labels = [lbl.text() for lbl in control.findChildren(QLabel)]
        assert "⚠️ File not found" not in labels

    def test_duration_label_formatted(self, qapp):
        assert TrackControl(make_track(duration=120.0)).duration_label.text() == "2:00"

    def test_duration_label_placeholder_when_unknown(self, qapp):
        assert TrackControl(make_track(duration=None)).duration_label.text() == "--:--"

    def test_volume_slider_reflects_initial_volume(self, qapp):
        assert TrackControl(make_track(volume=0.5)).volume_slider.value() == 50

    def test_initial_style_active(self, qapp):
        control = TrackControl(make_track(play_mode=True))
        assert control.play_btn.styleSheet() == Styles.play_button_style(size=28)
        assert control.styleSheet() == Styles.card_frame_style(
            "TrackControl",
            accent_color=Styles.SUCCESS,
            border_color=Styles.SUCCESS,
            background_color=Styles.BACKGROUND_LIGHT,
        )

    def test_initial_style_inactive(self, qapp):
        control = TrackControl(make_track(play_mode=False))
        assert control.play_btn.styleSheet() == Styles.play_button_inactive_style(
            size=28
        )
        assert control.styleSheet() == Styles.card_frame_style("TrackControl")


class TestToggles:
    def test_toggle_play_flips_and_emits_once(self, qapp):
        control = TrackControl(make_track(play_mode=True))
        rec = record(control.play_mode_changed)

        control._toggle_play()

        assert control._play_mode is False
        assert control.track.play_mode is False
        assert rec == [(7, False)]

    def test_toggle_repeat_flips_and_emits_once(self, qapp):
        control = TrackControl(make_track(is_repeat=False))
        rec = record(control.repeat_changed)

        control._toggle_repeat()

        assert control._repeat_mode is True
        assert control.track.is_repeat is True
        assert rec == [(7, True)]


class TestSetPlayMode:
    def test_set_play_mode_updates_state_without_emitting(self, qapp):
        control = TrackControl(make_track(play_mode=True))
        rec = record(control.play_mode_changed)

        control.set_play_mode(False)

        assert control._play_mode is False
        assert control.track.play_mode is False
        assert rec == []  # setter must NOT emit (only _toggle_play emits)


class TestRemove:
    def test_context_menu_remove_emits_track_id(self, qapp, monkeypatch):
        control = TrackControl(make_track())
        patch_qt(monkeypatch, QMenu=FakeMenu)
        FakeMenu.created.clear()
        rec = record(control.remove_requested)

        control.contextMenuEvent(FakeContextEvent())

        # The only action offered is "Remove from scene", and triggering it
        # emits the track id.
        assert [a.text() for a in FakeMenu.created[-1].actions()] == [
            "Remove from scene"
        ]
        assert rec == [(7,)]


class TestDrag:
    def test_drag_carries_track_mime_and_id(self, qapp, monkeypatch):
        control = TrackControl(make_track())
        patch_qt(monkeypatch, QDrag=FakeDrag)
        FakeDrag.created.clear()
        control._drag_start_pos = QPoint(0, 0)

        control.mouseMoveEvent(FakeMouseEvent(100, 100))

        assert FakeDrag.created, "mouseMoveEvent should have started a drag"
        mime = FakeDrag.created[-1].mime_data
        assert TRACK_MIME in mime.formats()
        assert mime_payload(mime, TRACK_MIME) == "7"


class TestPlayerIntegration:
    def test_set_player_applies_volume_and_repeat(self, qapp):
        player = FakeTrackPlayer()
        control = TrackControl(make_track(volume=0.5, is_repeat=True))

        control.set_player(player)

        assert player.target_volume == 50
        assert player.repeat is True

    def test_set_player_connects_position_and_end_signals(self, qapp):
        player = FakeTrackPlayer(duration_ms=60000)
        control = TrackControl(make_track())
        control.set_player(player)

        player.position_changed.emit(30000)
        assert control.position_slider.value() == 500
        assert control.position_label.text() == "0:30"

        player.end_reached.emit()
        assert control.position_slider.value() == 0
        assert control.position_label.text() == "0:00"

    def test_volume_change_pushes_exact_int_to_player(self, qapp):
        # Pins the CONTROL's own push in isolation (what this refactor changed:
        # the base reconstructs the 0-100 int from the emitted float). 0.29 * 100
        # == 28.9999...; round() must give 29, not int()'s 28. This does NOT
        # model the full live SceneEditor path, where scene_editor's own
        # int(volume*100) conversion independently sets the mixer volume — that
        # conversion is pre-existing and out of scope for DEBT-01 (see the
        # plan's follow-up note).
        player = FakeTrackPlayer()
        control = TrackControl(make_track(), player)

        control.volume_slider.setValue(29)
        assert player.target_volume == 29

        control.volume_slider.setValue(80)
        assert player.target_volume == 80

    def test_toggle_repeat_pushes_to_player(self, qapp):
        player = FakeTrackPlayer()
        control = TrackControl(make_track(is_repeat=False), player)

        control._toggle_repeat()

        assert player.repeat is True

    def test_position_seek_round_trips_through_player(self, qapp):
        player = FakeTrackPlayer(duration_ms=60000)
        control = TrackControl(make_track(), player)

        # While the handle is pressed, position updates from the player no-op.
        control._on_position_pressed()
        control.position_slider.setValue(123)
        control._update_position(30000)
        assert control.position_slider.value() == 123

        # Releasing maps slider -> ms via duration and seeks the player.
        control.position_slider.setValue(500)
        control._on_position_released()
        assert player.set_position_calls == [30000]
        assert control._updating_position is False
