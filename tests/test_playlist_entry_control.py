"""Characterization tests for PlaylistEntryControl.

Mirrors TrackControl: volume updates live on every slider tick, but
volume_committed (the persistence signal) only fires once the value settles —
on release for a drag, or immediately for a discrete keyboard/wheel change. The
remaining tests pin the rest of the widget's observable behavior — the toggles
(including the shuffle toggle unique to this control), the set_play_mode no-emit
asymmetry, set_current_track, context-menu removal, the drag MIME payload, and
constructor rendering branches — so the DEBT-01 refactor is provably
behavior-preserving.

Pin OBSERVABLE behavior: signals, the in-memory model, and control.volume_slider
(which survives the refactor as an alias to the VolumeSlider's inner slider).
Do NOT assert on internal widgets the refactor relocates.
"""

import pytest
from PyQt6.QtCore import QPoint

from app.database import Playlist, PlaylistTrack, ScenePlaylistEntry
from app.scenes.playlist_entry_control import PlaylistEntryControl
from app.shared.styles import Styles
from tests.control_helpers import (
    FakeContextEvent,
    FakeDrag,
    FakeMenu,
    FakeMouseEvent,
    mime_payload,
    patch_qt,
    record,
)

PLAYLIST_MIME = "application/x-soundmanager-scene-playlist"


def make_entry(
    *, volume=0.5, play_mode=True, is_repeat=False, is_shuffle=False, playlist=None
):
    return ScenePlaylistEntry(
        id=9,
        scene_id=1,
        playlist_id=1,
        volume=volume,
        is_shuffle=is_shuffle,
        is_repeat=is_repeat,
        play_mode=play_mode,
        playlist=playlist,
    )


def make_playlist(name="My Playlist", track_count=2):
    tracks = [
        PlaylistTrack(id=i, playlist_id=1, position=i) for i in range(track_count)
    ]
    return Playlist(id=1, name=name, tracks=tracks)


@pytest.fixture
def entry():
    # playlist=None is rendered as "Unknown Playlist"; fine for the volume tests.
    return ScenePlaylistEntry(id=9, scene_id=1, playlist_id=1, volume=0.5)


def _capture(control):
    live, committed = [], []
    control.volume_changed.connect(lambda eid, v: live.append((eid, v)))
    control.volume_committed.connect(lambda eid, v: committed.append((eid, v)))
    return live, committed


class TestVolumeCommit:
    def test_discrete_change_commits_immediately(self, qapp, entry):
        control = PlaylistEntryControl(entry)
        live, committed = _capture(control)

        control.volume_slider.setValue(80)

        assert live[-1][0] == 9 and live[-1][1] == pytest.approx(0.8)
        assert committed[-1][0] == 9 and committed[-1][1] == pytest.approx(0.8)

    def test_drag_defers_commit_until_release(self, qapp, entry):
        control = PlaylistEntryControl(entry)
        live, committed = _capture(control)

        control.volume_slider.setSliderDown(True)
        control.volume_slider.setValue(30)
        control.volume_slider.setValue(20)

        assert (9, pytest.approx(0.3)) in live
        assert (9, pytest.approx(0.2)) in live
        assert committed == []

        control.volume_slider.sliderReleased.emit()
        assert len(committed) == 1
        assert committed[0][0] == 9 and committed[0][1] == pytest.approx(0.2)

    def test_in_memory_volume_stays_fresh(self, qapp, entry):
        control = PlaylistEntryControl(entry)
        assert control.entry is entry

        control.volume_slider.setValue(80)  # discrete
        assert entry.volume == pytest.approx(0.8)

        control.volume_slider.setSliderDown(True)  # mid-drag, not yet committed
        control.volume_slider.setValue(30)
        assert entry.volume == pytest.approx(0.3)


class TestConstructor:
    def test_title_uses_playlist_name(self, qapp):
        control = PlaylistEntryControl(make_entry(playlist=make_playlist("Tavern")))
        assert control.title_label.text() == "Tavern"

    def test_title_unknown_without_playlist(self, qapp):
        control = PlaylistEntryControl(make_entry(playlist=None))
        assert control.title_label.text() == "Unknown Playlist"

    def test_tooltip_when_playlist(self, qapp):
        control = PlaylistEntryControl(make_entry(playlist=make_playlist("Tavern")))
        assert control.toolTip() == "Playlist: Tavern"

    def test_no_tooltip_without_playlist(self, qapp):
        control = PlaylistEntryControl(make_entry(playlist=None))
        assert control.toolTip() == ""

    def test_info_label_plural(self, qapp):
        control = PlaylistEntryControl(
            make_entry(playlist=make_playlist(track_count=2))
        )
        assert control.info_label.text() == "2 tracks"

    def test_info_label_singular(self, qapp):
        control = PlaylistEntryControl(
            make_entry(playlist=make_playlist(track_count=1))
        )
        assert control.info_label.text() == "1 track"

    def test_info_label_unknown_without_playlist(self, qapp):
        control = PlaylistEntryControl(make_entry(playlist=None))
        assert control.info_label.text() == "Unknown"

    def test_volume_slider_reflects_initial_volume(self, qapp):
        assert PlaylistEntryControl(make_entry(volume=0.5)).volume_slider.value() == 50

    def test_now_playing_starts_hidden(self, qapp):
        control = PlaylistEntryControl(make_entry())
        assert control.now_playing_label.isHidden() is True
        assert control.now_playing_label.text() == ""

    def test_initial_style_active(self, qapp):
        control = PlaylistEntryControl(make_entry(play_mode=True))
        assert control.play_btn.styleSheet() == Styles.play_button_style(size=28)
        assert control.styleSheet() == Styles.card_frame_style(
            "PlaylistEntryControl",
            accent_color=Styles.PRIMARY,
            border_color=Styles.PRIMARY,
        )

    def test_initial_style_inactive(self, qapp):
        control = PlaylistEntryControl(make_entry(play_mode=False))
        assert control.play_btn.styleSheet() == Styles.play_button_inactive_style(
            size=28
        )
        assert control.styleSheet() == Styles.card_frame_style(
            "PlaylistEntryControl",
            border_color=Styles.BORDER,
            background_color=Styles.BACKGROUND_LIGHT,
        )


class TestToggles:
    def test_toggle_play_flips_and_emits_once(self, qapp):
        control = PlaylistEntryControl(make_entry(play_mode=True))
        rec = record(control.play_mode_changed)

        control._toggle_play()

        assert control._play_mode is False
        assert control.entry.play_mode is False
        assert rec == [(9, False)]

    def test_toggle_shuffle_flips_and_emits_once(self, qapp):
        # Shuffle is unique to PlaylistEntryControl and the only place is_shuffle
        # flips — it has no equivalent on TrackControl or the shared base.
        control = PlaylistEntryControl(make_entry(is_shuffle=False))
        rec = record(control.shuffle_changed)

        control._toggle_shuffle()

        assert control._shuffle_mode is True
        assert control.entry.is_shuffle is True
        assert rec == [(9, True)]

    def test_toggle_repeat_flips_and_emits_once(self, qapp):
        control = PlaylistEntryControl(make_entry(is_repeat=False))
        rec = record(control.repeat_changed)

        control._toggle_repeat()

        assert control._repeat_mode is True
        assert control.entry.is_repeat is True
        assert rec == [(9, True)]


class TestSetPlayMode:
    def test_set_play_mode_updates_state_without_emitting(self, qapp):
        control = PlaylistEntryControl(make_entry(play_mode=True))
        rec = record(control.play_mode_changed)

        control.set_play_mode(False)

        assert control._play_mode is False
        assert control.entry.play_mode is False
        assert rec == []


class TestSetCurrentTrack:
    def test_set_current_track_shows_title(self, qapp):
        control = PlaylistEntryControl(make_entry())

        control.set_current_track("Goblin Ambush")

        assert control.now_playing_label.isHidden() is False
        assert control.now_playing_label.text() == "Now playing: Goblin Ambush"

    def test_set_current_track_empty_hides(self, qapp):
        control = PlaylistEntryControl(make_entry())
        control.set_current_track("Goblin Ambush")

        control.set_current_track("")

        assert control.now_playing_label.isHidden() is True


def _vlayout_row_index(control, widget):
    """Top-level vertical-layout row index containing ``widget`` (-1 if absent).

    Looks one level into row sub-layouts so a widget nested in an HBox row
    (scrubber, volume) resolves to that row's index.
    """
    layout = control.layout()
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is widget:
            return i
        sub = item.layout()
        if sub is not None:
            for j in range(sub.count()):
                if sub.itemAt(j).widget() is widget:
                    return i
    return -1


class TestPositionScrubberRow:
    def test_scrubber_and_next_button_present(self, qapp):
        control = PlaylistEntryControl(make_entry())
        assert control.scrubber is not None
        assert control.next_btn is not None
        # Starts blank: nothing playing yet.
        assert control.scrubber.slider.value() == 0
        assert control.scrubber.duration_label.text() == "--:--"

    def test_row_sits_below_now_playing_and_above_volume(self, qapp):
        # The user-facing requirement: the position/Next row goes under the
        # now-playing line and over the volume slider.
        control = PlaylistEntryControl(make_entry())
        now_playing = _vlayout_row_index(control, control.now_playing_label)
        scrubber = _vlayout_row_index(control, control.scrubber)
        volume = _vlayout_row_index(control, control.volume)
        assert now_playing != -1 and scrubber != -1 and volume != -1
        assert now_playing < scrubber < volume

    def test_next_button_uses_accent_blue_style(self, qapp):
        # The Next button carries the active-accent (PRIMARY blue) look so it
        # matches shuffle/repeat and the black skip glyph stays legible (it was
        # invisible on the dark card with the transparent utility style).
        control = PlaylistEntryControl(make_entry())
        assert control.next_btn.styleSheet() == Styles.icon_toggle_button_style(
            True, size=28
        )

    def test_next_button_emits_next_requested(self, qapp):
        control = PlaylistEntryControl(make_entry())
        rec = record(control.next_requested)

        control.next_btn.click()

        assert rec == [(9,)]

    def test_scrubber_release_emits_seek_requested(self, qapp):
        control = PlaylistEntryControl(make_entry())
        rec = record(control.seek_requested)

        control.scrubber.slider.sliderPressed.emit()
        control.scrubber.slider.setValue(250)
        control.scrubber.slider.sliderReleased.emit()

        assert len(rec) == 1
        assert rec[0][0] == 9
        assert rec[0][1] == pytest.approx(0.25)

    def test_update_position_drives_scrubber(self, qapp):
        control = PlaylistEntryControl(make_entry())

        control.update_position(30000, 60000)

        assert control.scrubber.slider.value() == 500
        assert control.scrubber.position_label.text() == "0:30"
        assert control.scrubber.duration_label.text() == "1:00"

    def test_reset_position_clears_scrubber(self, qapp):
        control = PlaylistEntryControl(make_entry())
        control.update_position(30000, 60000)

        control.reset_position()

        assert control.scrubber.slider.value() == 0
        assert control.scrubber.position_label.text() == "0:00"
        assert control.scrubber.duration_label.text() == "--:--"


class TestRemove:
    def test_context_menu_remove_emits_entry_id(self, qapp, monkeypatch):
        control = PlaylistEntryControl(make_entry())
        patch_qt(monkeypatch, QMenu=FakeMenu)
        FakeMenu.created.clear()
        rec = record(control.remove_requested)

        control.contextMenuEvent(FakeContextEvent())

        # The only action offered is "Remove from scene", and triggering it
        # emits the entry id.
        assert [a.text() for a in FakeMenu.created[-1].actions()] == [
            "Remove from scene"
        ]
        assert rec == [(9,)]


class TestDrag:
    def test_mime_type_constant_is_stable(self, qapp):
        assert PlaylistEntryControl.MIME_TYPE == PLAYLIST_MIME

    def test_drag_carries_entry_mime_and_id(self, qapp, monkeypatch):
        control = PlaylistEntryControl(make_entry())
        patch_qt(monkeypatch, QDrag=FakeDrag)
        FakeDrag.created.clear()
        control._drag_start_pos = QPoint(0, 0)

        control.mouseMoveEvent(FakeMouseEvent(100, 100))

        assert FakeDrag.created, "mouseMoveEvent should have started a drag"
        mime = FakeDrag.created[-1].mime_data
        assert PLAYLIST_MIME in mime.formats()
        assert mime_payload(mime, PLAYLIST_MIME) == "9"


class TestSilentSetters:
    """set_volume / set_repeat / set_shuffle update state + UI without
    emitting (preset apply)."""

    def test_set_volume_updates_ui_and_model_without_emitting(self, qapp, entry):
        control = PlaylistEntryControl(entry)
        rec_live = record(control.volume_changed)
        rec_committed = record(control.volume_committed)

        control.set_volume(0.75)

        assert rec_live == []
        assert rec_committed == []
        assert entry.volume == pytest.approx(0.75)
        assert control.volume_slider.value() == 75

    def test_set_repeat_updates_ui_and_model_without_emitting(self, qapp, entry):
        control = PlaylistEntryControl(entry)
        rec = record(control.repeat_changed)

        control.set_repeat(True)

        assert rec == []
        assert entry.is_repeat is True

    def test_set_shuffle_updates_ui_and_model_without_emitting(self, qapp, entry):
        control = PlaylistEntryControl(entry)
        rec = record(control.shuffle_changed)

        control.set_shuffle(True)

        assert rec == []
        assert entry.is_shuffle is True
        assert control._shuffle_mode is True
