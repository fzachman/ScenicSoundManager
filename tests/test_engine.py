"""Tests for AudioEngine (app/audio/engine.py)."""

import gc
import os
from unittest.mock import MagicMock

import pytest

from app.audio import engine as engine_mod
from app.audio.engine import AudioEngine, VLC_AVAILABLE


@pytest.fixture
def restore_singleton():
    """Snapshot & restore the AudioEngine singleton so tests stay hermetic."""
    saved = AudioEngine._instance
    AudioEngine._instance = None
    try:
        yield
    finally:
        AudioEngine._instance = saved


def make_mock_engine():
    """Build a real AudioEngine, then swap in a MagicMock vlc_instance.

    This isolates delegation behavior from a live VLC instance while keeping
    the real method bodies under test.
    """
    eng = AudioEngine()
    eng.vlc_instance = MagicMock()
    eng.available = True
    return eng


class TestSingleton:
    def test_get_instance_returns_same_object(self, restore_singleton):
        first = AudioEngine.get_instance()
        second = AudioEngine.get_instance()
        assert first is second

    def test_get_instance_creates_when_none(self, restore_singleton):
        AudioEngine._instance = None
        inst = AudioEngine.get_instance()
        assert inst is not None
        assert AudioEngine._instance is inst

    def test_is_available_true_when_vlc_and_instance_available(self, restore_singleton):
        # In this environment python-vlc is importable, so a real engine is
        # available and is_available() must concretely be True. Guarding on
        # VLC_AVAILABLE keeps the test honest if VLC ever becomes unavailable.
        if not VLC_AVAILABLE:
            pytest.skip("python-vlc not importable in this environment")
        AudioEngine._instance = None
        # Force the singleton's .available True so we exercise the True path
        # without depending on a live vlc.Instance() succeeding.
        eng = AudioEngine()
        eng.available = True
        AudioEngine._instance = eng
        assert AudioEngine.is_available() is True

    def test_is_available_false_when_instance_unavailable(self, restore_singleton):
        # Force a singleton whose .available is False.
        eng = AudioEngine()
        eng.available = False
        AudioEngine._instance = eng
        assert AudioEngine.is_available() is False


class TestCreateMedia:
    def test_returns_none_when_unavailable(self):
        eng = AudioEngine()
        eng.available = False
        eng.vlc_instance = MagicMock()
        assert eng.create_media("/some/path.mp3") is None

    def test_returns_none_when_no_vlc_instance(self):
        eng = AudioEngine()
        eng.available = True
        eng.vlc_instance = None
        assert eng.create_media("/some/path.mp3") is None

    def test_delegates_to_media_new_with_path(self):
        eng = make_mock_engine()
        result = eng.create_media("/music/song.flac")
        eng.vlc_instance.media_new.assert_called_once_with("/music/song.flac")
        assert result is eng.vlc_instance.media_new.return_value


class TestCreatePlayer:
    def test_returns_none_when_unavailable(self):
        eng = AudioEngine()
        eng.available = False
        eng.vlc_instance = MagicMock()
        assert eng.create_player() is None

    def test_returns_none_when_no_vlc_instance(self):
        eng = AudioEngine()
        eng.available = True
        eng.vlc_instance = None
        assert eng.create_player() is None

    def test_delegates_to_media_player_new(self):
        eng = make_mock_engine()
        result = eng.create_player()
        eng.vlc_instance.media_player_new.assert_called_once_with()
        assert result is eng.vlc_instance.media_player_new.return_value


class TestMasterVolume:
    def test_getter_default(self):
        eng = AudioEngine()
        assert eng.master_volume == 100

    def test_setter_clamps_below_zero(self):
        eng = AudioEngine()
        eng.master_volume = -10
        assert eng.master_volume == 0

    def test_setter_clamps_above_hundred(self):
        eng = AudioEngine()
        eng.master_volume = 250
        assert eng.master_volume == 100

    def test_setter_passes_through_in_range(self):
        eng = AudioEngine()
        eng.master_volume = 60
        assert eng.master_volume == 60

    def test_setter_updates_every_registered_player(self):
        eng = AudioEngine()
        p1 = MagicMock()
        p2 = MagicMock()
        eng.register_player(p1)
        eng.register_player(p2)

        eng.master_volume = 42

        p1.apply_master_volume.assert_called_once_with()
        p2.apply_master_volume.assert_called_once_with()


class TestPlayerRegistration:
    def test_unregister_removes_player(self):
        eng = AudioEngine()
        p1 = MagicMock()
        p2 = MagicMock()
        eng.register_player(p1)
        eng.register_player(p2)

        eng.unregister_player(p1)

        # Only p2 should still receive volume updates.
        eng.master_volume = 30
        p1.apply_master_volume.assert_not_called()
        p2.apply_master_volume.assert_called_once_with()

    def test_unregister_non_member_is_noop(self):
        eng = AudioEngine()
        stranger = MagicMock()
        # Must not raise even though stranger was never registered.
        eng.unregister_player(stranger)
        stranger.apply_master_volume.assert_not_called()

    def test_players_set_is_weak(self):
        eng = AudioEngine()

        class FakePlayer:
            def apply_master_volume(self):
                pass

        p = FakePlayer()
        eng.register_player(p)
        assert len(list(eng._players)) == 1

        # Drop the only strong reference; the WeakSet should let it go.
        del p
        gc.collect()

        assert len(list(eng._players)) == 0

        # Setting volume must not touch the collected player (no error, no calls).
        eng.master_volume = 55  # should iterate over an empty set safely


class TestRelease:
    def test_release_releases_vlc_and_clears_state(self, restore_singleton):
        eng = AudioEngine()
        mock_vlc = MagicMock()
        eng.vlc_instance = mock_vlc
        AudioEngine._instance = eng

        eng.release()

        mock_vlc.release.assert_called_once_with()
        assert eng.vlc_instance is None
        assert AudioEngine._instance is None

    def test_release_without_vlc_instance_resets_singleton(self, restore_singleton):
        eng = AudioEngine()
        eng.vlc_instance = None
        AudioEngine._instance = eng

        eng.release()  # must not raise even with no vlc_instance

        assert AudioEngine._instance is None

    def test_get_instance_rebuilds_after_release(self, restore_singleton):
        AudioEngine._instance = None
        first = AudioEngine.get_instance()
        first.vlc_instance = None  # avoid releasing the shared live VLC instance
        first.release()
        # release() nulled the singleton, so the next get_instance must build
        # a genuinely new object rather than handing back the released one.
        second = AudioEngine.get_instance()
        assert second is not first


class TestConfigureVlcPaths:
    """Exercise _configure_vlc_paths directly without constructing a live VLC
    instance (which itself mutates VLC_PLUGIN_PATH as a libvlc side effect).

    AudioEngine.__new__ produces an instance without running __init__, so no
    real vlc.Instance is created and the only env writes come from the method
    under test. monkeypatch.setenv/delenv restore os.environ afterward.
    """

    def _bare_engine(self):
        return AudioEngine.__new__(AudioEngine)

    def test_sets_env_when_frozen_and_paths_exist(self, monkeypatch):
        monkeypatch.delenv("PYTHON_VLC_LIB_PATH", raising=False)
        monkeypatch.delenv("VLC_PLUGIN_PATH", raising=False)
        monkeypatch.setattr(engine_mod.sys, "frozen", True, raising=False)
        monkeypatch.setattr(
            engine_mod.sys, "executable", "/Apps/SoundManager.app/Contents/MacOS/app"
        )
        monkeypatch.setattr(engine_mod.os.path, "exists", lambda p: True)

        self._bare_engine()._configure_vlc_paths()

        lib = os.environ["PYTHON_VLC_LIB_PATH"]
        plugins = os.environ["VLC_PLUGIN_PATH"]
        assert lib.endswith(os.path.join("Resources", "lib", "libvlc.dylib"))
        assert plugins.endswith(os.path.join("Resources", "plugins"))

    def test_does_nothing_when_not_frozen(self, monkeypatch):
        monkeypatch.delenv("PYTHON_VLC_LIB_PATH", raising=False)
        monkeypatch.delenv("VLC_PLUGIN_PATH", raising=False)
        monkeypatch.setattr(engine_mod.sys, "frozen", False, raising=False)
        # exists() returning True would only matter inside the frozen branch.
        monkeypatch.setattr(engine_mod.os.path, "exists", lambda p: True)

        self._bare_engine()._configure_vlc_paths()

        assert "PYTHON_VLC_LIB_PATH" not in os.environ
        assert "VLC_PLUGIN_PATH" not in os.environ

    def test_skips_env_when_paths_missing(self, monkeypatch):
        monkeypatch.delenv("PYTHON_VLC_LIB_PATH", raising=False)
        monkeypatch.delenv("VLC_PLUGIN_PATH", raising=False)
        monkeypatch.setattr(engine_mod.sys, "frozen", True, raising=False)
        monkeypatch.setattr(
            engine_mod.sys, "executable", "/Apps/SoundManager.app/Contents/MacOS/app"
        )
        monkeypatch.setattr(engine_mod.os.path, "exists", lambda p: False)

        self._bare_engine()._configure_vlc_paths()

        assert "PYTHON_VLC_LIB_PATH" not in os.environ
        assert "VLC_PLUGIN_PATH" not in os.environ
