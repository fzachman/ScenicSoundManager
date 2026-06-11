# Plan 005: Characterization tests for MainWindow playback mutual exclusivity

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat d64c771..HEAD -- app/main_window.py tests/`
> If `app/main_window.py` changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (test-only — no production code changes)
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `d64c771`, 2026-06-11

## Why this matters

The app's core playback invariant — *only one scene OR one playlist plays at a
time* — is enforced by exactly one piece of code: the signal handlers in
`MainWindow` (`_on_scene_playback_changed` / `_on_playlist_playback_changed`).
It has zero test coverage. Any regression (both playing at once, the
"Currently Playing" indicator stuck or wrong, a stale stop-signal clearing the
wrong state) only surfaces at user runtime. There is also appetite for future
refactors of playback code (a shared playback controller has been considered);
these characterization tests must exist *before* any such refactor is safe.
This plan adds tests only — it must not change any file under `app/`.

## Current state

The coordinator, `app/main_window.py:211-243` (line numbers from `d64c771`):

```python
    def _on_scene_playback_changed(self, scene_id, scene_title, is_playing: bool):
        if is_playing and scene_id:
            # Mutual exclusivity: stop any active playlist before activating scene
            if self._current_playing_type == "playlist":
                self.playlists_widget.stop_all_playback()
            self._current_scene_id = scene_id
            self._current_playing_type = "scene"
            self.current_scene_btn.setText(f"Scene: {scene_title or 'Untitled Scene'}")
            self.currently_playing_widget.show()
        else:
            if self._current_playing_type == "scene":
                self._current_scene_id = scene_id if scene_id else None
                self._current_playing_type = None
                self.currently_playing_widget.hide()

    def _on_playlist_playback_changed(self, playlist_id, playlist_name, is_playing: bool):
        if is_playing and playlist_id:
            # Mutual exclusivity: stop any active scene before activating playlist
            if self._current_playing_type == "scene":
                self.scenes_widget.stop_all_playback()
            self._current_playlist_playing_id = playlist_id
            self._current_playing_type = "playlist"
            self.current_scene_btn.setText(f"Playlist: {playlist_name or 'Untitled Playlist'}")
            self.currently_playing_widget.show()
        else:
            if self._current_playing_type == "playlist":
                self._current_playlist_playing_id = None
                self._current_playing_type = None
                self.currently_playing_widget.hide()
```

Wiring (`app/main_window.py:127-137`): `self.scenes_widget.playback_state_changed`
→ `_on_scene_playback_changed`; `self.playlists_widget.playback_state_changed`
→ `_on_playlist_playback_changed`. The signals are declared as
`pyqtSignal(object, object, bool)` on `ScenesWidget`
(`app/scenes/scenes_widget.py:15`) and `PlaylistsWidget`
(`app/playlists/playlists_widget.py:16`), so emitting them directly from a
test drives the real slots synchronously.

Two test-environment hazards the fixture MUST handle:

1. **Database**: `MainWindow.__init__` calls `DatabaseConnection()` with no
   argument (`app/main_window.py:37`), and the no-arg default is the user's
   REAL database at `~/Library/Application Support/SoundManager/soundmanager.db`
   (`app/database/connection.py:14-19`). The test must monkeypatch the
   `DatabaseConnection` name *in the `app.main_window` module namespace*
   (it's imported there via `from .database import DatabaseConnection`) to a
   factory returning a temp-file DB.
2. **QSettings**: `MainWindow` reads/writes `QSettings()` (master volume,
   active tab, last scene/playlist). Set a test-only organization/application
   name before constructing the window so test runs never touch the user's
   real settings.

Existing Qt-widget test conventions to copy — `tests/test_tag_filters.py:1-40`:
`os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")` BEFORE PyQt imports,
a session-scoped `qapp` fixture returning `QApplication.instance() or QApplication([])`,
temp-file DB fixture.

`AudioEngine.get_instance()` (`app/main_window.py:40`) is a real singleton; on
this machine VLC is available and constructing it offscreen is fine. The tests
below never start actual playback (they emit the coordination signals
directly), so no audio plays.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| All tests | `venv/bin/pytest tests/ -q` | all pass (82 before this plan) |
| New file only | `venv/bin/pytest tests/test_main_window.py -v` | all new tests pass |

## Scope

**In scope** (the only files you should modify):
- `tests/test_main_window.py` (create)

**Out of scope** (do NOT touch):
- ANYTHING under `app/` — this is a characterization plan; if the production
  code seems to need a change to be testable, that's a STOP condition.
- Other test files.

## Git workflow

- Branch: `advisor/005-main-window-exclusivity-tests`.
- Single commit; message style: short imperative sentence, e.g.
  `Add characterization tests for playback mutual exclusivity.`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Fixture scaffolding

Create `tests/test_main_window.py`:

```python
"""Characterization tests for MainWindow playback mutual exclusivity."""

import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from app.database import DatabaseConnection
import app.main_window as main_window_module


@pytest.fixture(scope="session")
def qapp():
    QCoreApplication.setOrganizationName("SoundManagerTests")
    QCoreApplication.setApplicationName("SoundManagerTests")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(
        main_window_module, "DatabaseConnection", lambda: DatabaseConnection(db_path)
    )
    window = main_window_module.MainWindow()
    yield window
    window.db.close()
```

Do NOT call `window.close()`/`closeEvent` in teardown — `closeEvent` releases
the `AudioEngine` singleton, which would poison any later test that touches
audio in the same pytest process.

**Verify**: `venv/bin/pytest tests/test_main_window.py -v` with one trivial
test (`def test_window_constructs(main_window): assert main_window.db is not None`)
→ 1 passed. Also confirm the user DB was not touched:
`ls -l ~/Library/Application\ Support/SoundManager/soundmanager.db` has an
unchanged modification time (or doesn't exist).

### Step 2: The characterization tests

Add these tests (keep the trivial constructor test from Step 1):

```python
def test_scene_playing_sets_state_and_indicator(main_window, qapp):
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    qapp.processEvents()
    assert main_window._current_playing_type == "scene"
    assert main_window.current_scene_btn.text() == "Scene: Tavern"
    assert not main_window.currently_playing_widget.isHidden()


def test_scene_stop_clears_state(main_window, qapp):
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", False)
    qapp.processEvents()
    assert main_window._current_playing_type is None
    assert main_window.currently_playing_widget.isHidden()


def test_playlist_start_stops_active_scene(main_window, qapp, monkeypatch):
    stopped = []
    monkeypatch.setattr(
        main_window.scenes_widget, "stop_all_playback", lambda: stopped.append(True)
    )
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    main_window.playlists_widget.playback_state_changed.emit(7, "Battle Mix", True)
    qapp.processEvents()
    assert stopped == [True]
    assert main_window._current_playing_type == "playlist"
    assert main_window.current_scene_btn.text() == "Playlist: Battle Mix"


def test_scene_start_stops_active_playlist(main_window, qapp, monkeypatch):
    stopped = []
    monkeypatch.setattr(
        main_window.playlists_widget, "stop_all_playback", lambda: stopped.append(True)
    )
    main_window.playlists_widget.playback_state_changed.emit(7, "Battle Mix", True)
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    qapp.processEvents()
    assert stopped == [True]
    assert main_window._current_playing_type == "scene"
    assert main_window.current_scene_btn.text() == "Scene: Tavern"


def test_stale_playlist_stop_does_not_clear_scene_state(main_window, qapp):
    # A playlist's stop signal arriving while a scene is active must not
    # clear the scene's now-playing state.
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    main_window.playlists_widget.playback_state_changed.emit(7, None, False)
    qapp.processEvents()
    assert main_window._current_playing_type == "scene"
    assert not main_window.currently_playing_widget.isHidden()


def test_untitled_scene_fallback_label(main_window, qapp):
    main_window.scenes_widget.playback_state_changed.emit(3, None, True)
    qapp.processEvents()
    assert main_window.current_scene_btn.text() == "Scene: Untitled Scene"
```

Notes for the executor:
- The asserts use `isHidden()` (explicit-hide flag), not `isVisible()` —
  `isVisible()` is `False` for children of a never-shown window even after
  `.show()`, so it cannot distinguish the states under offscreen testing.
- These are *characterization* tests: they pin down behavior as it exists at
  `d64c771`. If an assertion fails, the test is wrong, not the app — re-read
  the excerpt in "Current state", fix the test, and only STOP if the live
  code genuinely contradicts the excerpt.

**Verify**: `venv/bin/pytest tests/test_main_window.py -v` → 7 passed.

### Step 3: Full-suite check

**Verify**: `venv/bin/pytest tests/ -q` → all pass (89 total expected:
82 existing + 7 new; adjust if other plans landed first). Run it twice to
check for cross-test contamination from the QSettings org-name change
(the other test files don't read QSettings, so both runs must be green).

## Test plan

This plan *is* the test plan. Cases covered: scene start (state + label +
indicator), scene stop (state cleared), both mutual-exclusivity directions
(via monkeypatched `stop_all_playback` recorders), stale-stop ordering, and
the untitled-name fallback. Pattern source: `tests/test_tag_filters.py`
(offscreen platform, session `qapp`).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `venv/bin/pytest tests/ -q` exits 0, total test count ≥ 89
- [ ] `git status --porcelain` shows only `tests/test_main_window.py` (new) and `plans/README.md` (modified)
- [ ] `git diff --stat HEAD -- app/` is empty (no production code touched)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `_on_scene_playback_changed` / `_on_playlist_playback_changed` don't match
  the excerpts (drift since `d64c771`) — characterizing drifted code needs a
  fresh read, not guesswork.
- `MainWindow()` construction fails offscreen (e.g. VLC/AudioEngine error in
  this environment) — report the traceback; do not stub out `AudioEngine`
  inside `app/`.
- You feel the need to modify anything under `app/` to make a test pass.
- The user's real database file's mtime changes after a test run.

## Maintenance notes

- These tests are the safety net required before any refactor that merges
  scene/playlist playback control into a shared controller (a known candidate
  refactor). Whoever attempts that refactor must keep these green.
- If a third playable type is ever added (e.g. one-shot soundboard effects),
  every test here that asserts `_current_playing_type` needs a counterpart
  for the new type.
- The session-scoped QSettings org-name override means all tests in one
  pytest process share the test settings scope; if a future test needs
  pristine settings, give it its own `QSettings` group cleanup.
