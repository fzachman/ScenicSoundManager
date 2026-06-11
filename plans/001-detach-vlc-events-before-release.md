# Plan 001: Detach VLC event handlers before releasing the MediaPlayer

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat d64c771..HEAD -- app/audio/player.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `d64c771`, 2026-06-11

## Why this matters

`TrackPlayer` attaches four libVLC event callbacks in its constructor but never
detaches them. `release()` calls `media_player.release()` with the callbacks
still attached. libVLC fires events from its own background threads, so a
callback can fire *during or after* the release — calling methods on a
released native player object (e.g. `get_state()` in `_on_state_change`) is
undefined behavior in libVLC and can crash the whole app, not just throw a
Python exception. Players are created and released constantly in this app
(every playlist track advance creates a fresh `TrackPlayer` and releases the
old one — see `app/audio/scene_playlist_player.py:144-146`), so the race
window is hit routinely during normal use.

## Current state

- `app/audio/player.py` — `TrackPlayer`, the single-track VLC player wrapper.
  All changes happen in this file.
- `app/audio/engine.py` — `AudioEngine` singleton; exports `vlc` (the module,
  or `None` if import failed) and `VLC_AVAILABLE`. Read-only context.

Event attachment, `app/audio/player.py:53-59`:

```python
                # Set up end-reached event
                events = self.media_player.event_manager()
                events.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_end_reached)
                events.event_attach(vlc.EventType.MediaPlayerPlaying, self._on_state_change)
                events.event_attach(vlc.EventType.MediaPlayerPaused, self._on_state_change)
                events.event_attach(vlc.EventType.MediaPlayerStopped, self._on_state_change)
                self.engine.register_player(self)
```

Release with no detach, `app/audio/player.py:234-242`:

```python
    def release(self) -> None:
        """Release player resources"""
        self._stop_fade()
        self._position_timer.stop()
        if self.media_player:
            self.media_player.stop()
            self.media_player.release()
            self.media_player = None
        self.engine.unregister_player(self)
```

One of the callbacks that can fire from a VLC thread mid-release,
`app/audio/player.py:226-232`:

```python
    def _on_state_change(self, event) -> None:
        """Handle state change events"""
        if self.media_player:
            # Capture state immediately to avoid race condition if player is released
            # before the callback executes
            state = self.media_player.get_state()
            QTimer.singleShot(0, lambda s=state: self.state_changed.emit(s))
```

Conventions: `vlc` is imported at the top of `player.py` via
`from .engine import AudioEngine, vlc, VLC_AVAILABLE` (line 6). `vlc` is
`None` when the libVLC import failed (see `app/audio/engine.py:13-22`), so any
use of `vlc.EventType` must be guarded. Logging convention (if you need it):
`from app.shared.logging import get_logger` then `_log = get_logger(__name__)`
— see `app/audio/engine.py:8-10`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| All tests | `venv/bin/pytest tests/ -q` | all pass (82 before this plan) |
| New test file only | `venv/bin/pytest tests/test_track_player.py -v` | all pass |

There is no lint/typecheck tooling in this repo. Use the venv's pytest, not a
global one.

## Scope

**In scope** (the only files you should modify):
- `app/audio/player.py` (the `release` method only)
- `tests/test_track_player.py` (create)

**Out of scope** (do NOT touch, even though they look related):
- `app/audio/engine.py` — the engine's own `release()` is a separate concern.
- `app/audio/scene_playlist_player.py`, `app/audio/mixer.py` — callers of
  `TrackPlayer.release()`; no signature change happens, so they need no edits.
- The `_handle_end_reached` / `_on_state_change` callback bodies — their
  defensive `if self.media_player` checks stay as a second line of defense.

## Git workflow

- Branch: `advisor/001-detach-vlc-events` (branched from the current branch).
- Single commit; message style matches repo history (short imperative
  sentence, e.g. `Detach VLC event handlers before releasing media players.`).
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Detach events in `release()`

In `app/audio/player.py`, modify `release()` so the four attached event types
are detached before the player is stopped and released:

```python
    def release(self) -> None:
        """Release player resources"""
        self._stop_fade()
        self._position_timer.stop()
        if self.media_player:
            if vlc is not None:
                events = self.media_player.event_manager()
                events.event_detach(vlc.EventType.MediaPlayerEndReached)
                events.event_detach(vlc.EventType.MediaPlayerPlaying)
                events.event_detach(vlc.EventType.MediaPlayerPaused)
                events.event_detach(vlc.EventType.MediaPlayerStopped)
            self.media_player.stop()
            self.media_player.release()
            self.media_player = None
        self.engine.unregister_player(self)
```

The `vlc is not None` guard matters: when libVLC failed to import,
`self.media_player` is always `None` anyway (constructor sets it only when
`self.available`), but the guard keeps the method safe under mocked engines in
tests, where `media_player` is a MagicMock while the real `vlc` module may be
absent.

**Verify**: `venv/bin/pytest tests/ -q` → all existing tests still pass.

### Step 2: Add unit tests

Create `tests/test_track_player.py`. Use a `MagicMock` engine the way
`tests/test_scene_playlist_player.py` does (see its `mock_engine` fixture at
lines 53-59), but with `available = True` so a (mock) media player is created:

```python
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
```

Note: `TrackPlayer.__init__` runs `events.event_attach(...)` against the
MagicMock, so `event_attach.call_args_list` records the exact event types that
must later be detached — the test asserts the detach set equals the attach
set rather than hardcoding the four names.

**Verify**: `venv/bin/pytest tests/test_track_player.py -v` → 2 passed (or
2 skipped if VLC is genuinely unavailable on the machine — on this Mac it is
available and they should run).

## Test plan

Covered by Step 2: detach-matches-attach, release ordering (detach happens on
the same mock before `release()` — implicitly verified because `release()` is
asserted called once and `media_player` is `None` afterward), idempotent double
release. Pattern source: `tests/test_scene_playlist_player.py` (MagicMock
engine fixture).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `venv/bin/pytest tests/ -q` exits 0 (84+ tests, no failures)
- [ ] `grep -n "event_detach" app/audio/player.py` shows 4 matches inside `release()`
- [ ] `git status --porcelain` shows changes only to `app/audio/player.py`, `tests/test_track_player.py`, and `plans/README.md`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `release()` in `app/audio/player.py` no longer matches the excerpt above
  (drift since `d64c771`).
- The existing 82 tests do not pass *before* you change anything (broken
  baseline is not yours to fix).
- `events.event_attach` calls in `__init__` have changed (more/fewer than 4
  event types) — the detach list must mirror them; report instead of guessing.
- Importing `vlc` in the test crashes the interpreter (libVLC ABI issue) —
  report the error output.

## Maintenance notes

- If anyone adds a new `event_attach` in `TrackPlayer.__init__`, the matching
  `event_detach` must be added in `release()`. A reviewer should check this
  pairing in any PR touching `player.py`.
- Consider (future, not this plan) storing the attached event types in a list
  on the instance so attach/detach can never drift apart.
- The defensive `if self.media_player` checks inside the callbacks remain
  intentionally — events already queued by VLC's thread can still arrive
  in-flight even after detach.
