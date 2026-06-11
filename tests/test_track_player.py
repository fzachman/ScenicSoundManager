"""Tests for TrackPlayer release behavior."""

from unittest.mock import MagicMock

import pytest

from app.audio.engine import vlc
from app.audio.player import TrackPlayer


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.available = True
    engine.master_volume = 100
    return engine


@pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
def test_release_detaches_all_attached_events(mock_engine):
    player = TrackPlayer("/fake/track.mp3", engine=mock_engine)
    events = player.media_player.event_manager.return_value
    attached_types = {c.args[0] for c in events.event_attach.call_args_list}
    media_player = player.media_player

    player.release()

    detached_types = {c.args[0] for c in events.event_detach.call_args_list}
    assert detached_types == attached_types
    assert len(attached_types) == 4
    media_player.release.assert_called_once()
    assert player.media_player is None
    mock_engine.unregister_player.assert_called_once_with(player)


@pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
def test_release_is_idempotent(mock_engine):
    player = TrackPlayer("/fake/track.mp3", engine=mock_engine)
    player.release()
    player.release()  # second call must not raise
