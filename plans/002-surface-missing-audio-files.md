# Plan 002: Log missing audio files and skip them instead of silently stalling playback

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat d64c771..HEAD -- app/audio/scene_playlist_player.py app/playlists/playlist_editor.py app/library/file_table.py app/scenes/scene_editor.py tests/test_scene_playlist_player.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `d64c771`, 2026-06-11

## Why this matters

Audio files referenced by scenes and playlists can be deleted or moved on disk
after import. Four playback paths check `os.path.exists(...)` and silently
`return` when the file is gone — no log line, no user feedback. Worse, in the
two *sequential* players (playlist-in-scene and the Playlists tab), the silent
return happens mid-auto-advance: the previous track has already ended, the
internal state still says "playing", and playback just stops dead while the UI
shows a playing state. For a DM mid-session this looks like the app randomly
broke. After this plan: every missing file is logged via structlog, and the
two sequential players skip over missing tracks to the next playable one
(stopping cleanly only when nothing is playable).

## Current state

The four silent-return sites:

1. `app/audio/scene_playlist_player.py:136-159` — `ScenePlaylistPlayer._play_file`:

```python
    def _play_file(self, audio_file_id: int, fade_ms: int = 500) -> None:
        """Play a specific audio file by its ID."""
        track = self._find_track(audio_file_id)
        if not track or not track.audio_file:
            return
        if not os.path.exists(track.audio_file.file_path):
            return

        self._release_player()
        ...
        self.track_changed.emit(audio_file_id)
```

Auto-advance callers in the same file — `_on_track_ended` (lines 161-176),
`start` (lines 95-111), `_restart` (lines 196-210). `_on_track_ended` shape:

```python
    def _on_track_ended(self) -> None:
        """Handle track end - advance to next or finish."""
        if not self._is_playing:
            return

        next_id = self._get_next_audio_file_id()
        if next_id is not None:
            self._play_file(next_id)
        else:
            # Playlist exhausted
            if self._is_repeat:
                self._restart()
            else:
                self._is_playing = False
                self._current_audio_file_id = None
                self.playback_finished.emit()
```

`_get_next_audio_file_id` (lines 178-194) returns `None` when the sequential
list is exhausted or the shuffle cycle completes.

2. `app/playlists/playlist_editor.py:589-601` — `PlaylistEditor._play_audio_file`:

```python
    def _play_audio_file(self, audio_file_id: int):
        """Play a specific audio file from the playlist"""
        # Find the track in the current playlist
        track = None
        for t in self._current_playlist.tracks:
            if t.audio_file_id == audio_file_id:
                track = t
                break
        if not track or not track.audio_file:
            return

        if not os.path.exists(track.audio_file.file_path):
            return
```

Its auto-advance callers — `_next_track` (lines ~620-632) and
`_on_track_ended` (lines ~650-658), both shaped like:

```python
        audio_file_id = self._get_next_audio_file_id()
        if audio_file_id is not None:
            self._play_audio_file(audio_file_id)
        else:
            self._stop_playback()
```

IMPORTANT: `PlaylistEditor._get_next_audio_file_id` (lines ~634-648) **wraps
around to index 0** in sequential mode — it never returns `None` for a
non-empty playlist. Any skip loop here MUST be bounded by the track count or
it will loop forever when all files are missing.

3. `app/library/file_table.py:242-244` — Library tab inline play:

```python
        # Start new playback
        audio_file = self._get_file_by_id(file_id)
        if audio_file and os.path.exists(audio_file.file_path):
            self._current_player = TrackPlayer(audio_file.file_path, self.audio_engine)
```

(no `else` — clicking play on a missing file does nothing, silently).

4. `app/scenes/scene_editor.py:482-488` — `SceneEditor._play_track`:

```python
    def _play_track(self, track: SceneAudioFile):
        """Ensure a track has a player and start playback"""
        if not track.audio_file:
            return
        import os
        if not os.path.exists(track.audio_file.file_path):
            return
```

(Scene tracks layer simultaneously, so "skip" doesn't apply — but the silent
return needs a log line. Note the scene editor already shows a visual
"⚠️ File not found" badge per track — see `app/scenes/track_control.py:61-65`
— so logging is sufficient there.)

Conventions:
- Logging: `from app.shared.logging import get_logger` at top of module, then
  `_log = get_logger(__name__)` at module level; call style is
  `_log.warning("event_name", key=value)`. Exemplar: `app/audio/engine.py:8-22`.
- Tests for `ScenePlaylistPlayer` live in `tests/test_scene_playlist_player.py`
  and use a `MagicMock` engine with `available = False` plus DB-backed
  playlists with fake paths like `/fake/path/track_0.mp3`; playback tests
  patch `os.path.exists`. Follow that file's fixtures exactly.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| All tests | `venv/bin/pytest tests/ -q` | all pass (82 before this plan) |
| Player tests only | `venv/bin/pytest tests/test_scene_playlist_player.py -v` | all pass |
| Run the app (manual check) | `./run.sh` | window opens |

## Scope

**In scope** (the only files you should modify):
- `app/audio/scene_playlist_player.py`
- `app/playlists/playlist_editor.py`
- `app/library/file_table.py`
- `app/scenes/scene_editor.py`
- `tests/test_scene_playlist_player.py` (extend)

**Out of scope** (do NOT touch, even though they look related):
- `app/scenes/track_control.py` — its "File not found" badge already works.
- `app/shared/dialogs.py` — no new user-facing dialog in this plan; logging +
  skip only. (A visual indicator for the Library tab is deferred — see
  Maintenance notes.)
- `app/audio/player.py` — `TrackPlayer` itself; missing-file handling happens
  before a player is constructed.
- Any database code.

## Git workflow

- Branch: `advisor/002-surface-missing-audio-files`.
- One commit per step is fine; message style: short imperative sentence
  (matches repo history, e.g. `Log and skip missing audio files during playback.`).
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: ScenePlaylistPlayer — log, return bool, and skip

In `app/audio/scene_playlist_player.py`:

a. Add the logging imports/module logger per the convention above.

b. Change `_play_file` to return `bool`: `True` when playback started, `False`
   on either early return. At the two early returns, log:

```python
        if not track or not track.audio_file:
            _log.warning("playlist_track_missing_data", audio_file_id=audio_file_id)
            return False
        if not os.path.exists(track.audio_file.file_path):
            _log.warning(
                "audio_file_missing",
                audio_file_id=audio_file_id,
                file_path=track.audio_file.file_path,
            )
            return False
```

   The success path ends with `return True` (after `self.track_changed.emit(...)`).

c. Add a bounded skip helper:

```python
    def _play_file_or_advance(self, audio_file_id: Optional[int], fade_ms: int = 500) -> None:
        """Try to play the given file; on failure (e.g. missing file), advance
        through the playlist until something plays or all tracks were tried."""
        attempts = 0
        max_attempts = len(self._audio_file_ids)
        next_id = audio_file_id
        while next_id is not None and attempts < max_attempts:
            if self._play_file(next_id, fade_ms):
                return
            attempts += 1
            next_id = self._get_next_audio_file_id()
        # Nothing playable
        self._is_playing = False
        self._current_audio_file_id = None
        self.playback_finished.emit()
```

d. Replace the direct `self._play_file(...)` calls in `start` (line 111),
   `_on_track_ended` (line 168), and `_restart` (line 207) with
   `self._play_file_or_advance(...)` passing the same arguments. Do NOT change
   the exhaustion/repeat branching that already exists in `_on_track_ended` —
   only the call that plays a concrete id.

**Verify**: `venv/bin/pytest tests/test_scene_playlist_player.py -v` → all
existing tests pass (they patch `os.path.exists` to `True`, so `_play_file`
returns `True` and behavior is unchanged).

### Step 2: PlaylistEditor — log, return bool, and skip

In `app/playlists/playlist_editor.py`:

a. Add the logging imports/module logger (top of file; module-level `_log`).

b. Change `_play_audio_file` to return `bool` with the same two logged early
   returns as Step 1b (event names `playlist_track_missing_data` /
   `audio_file_missing`), and `return True` at the end of the success path.

c. First run `grep -n "_play_audio_file(" app/playlists/playlist_editor.py`.
   Expected callers: `_next_track`, `_on_track_ended`, plus one or two
   direct-selection sites (play button / track double-click). If you find
   callers that are clearly auto-advance beyond `_next_track` and
   `_on_track_ended`, treat that as a STOP condition.

d. In `_next_track` and `_on_track_ended` ONLY, replace the
   `if audio_file_id is not None: self._play_audio_file(...) else: self._stop_playback()`
   shape with a bounded skip loop (bounded because sequential mode wraps
   around forever):

```python
        attempts = 0
        max_attempts = len(self._current_playlist.tracks) if self._current_playlist else 0
        audio_file_id = self._get_next_audio_file_id()
        while audio_file_id is not None and attempts < max_attempts:
            if self._play_audio_file(audio_file_id):
                return
            attempts += 1
            audio_file_id = self._get_next_audio_file_id()
        self._stop_playback()
```

   Extract this loop into a small private method `_advance_to_next_playable(self)`
   and call it from both `_next_track` and `_on_track_ended` (replacing their
   existing `audio_file_id = self._get_next_audio_file_id(); if ... else
   self._stop_playback()` blocks) so the logic exists exactly once.

   Direct-selection callers (user clicked a specific track) keep calling
   `_play_audio_file(...)` directly and ignore the return value — clicking a
   missing track should not jump to a different track; it now logs a warning.

**Verify**: `venv/bin/pytest tests/ -q` → all pass.
**Verify (grep)**: `grep -c "audio_file_missing" app/playlists/playlist_editor.py` → at least 1.

### Step 3: Library file table and scene editor — log only

a. `app/library/file_table.py` — add the module logger; restructure the play
   site (lines 242-244) to log when the file is missing:

```python
        audio_file = self._get_file_by_id(file_id)
        if audio_file and not os.path.exists(audio_file.file_path):
            _log.warning("audio_file_missing", audio_file_id=file_id, file_path=audio_file.file_path)
            return
        if audio_file:
            ... # existing playback block unchanged
```

b. `app/scenes/scene_editor.py` — add the module logger; in `_play_track`
   (line 487), log before the early return:

```python
        if not os.path.exists(track.audio_file.file_path):
            _log.warning(
                "audio_file_missing",
                audio_file_id=track.audio_file.id,
                file_path=track.audio_file.file_path,
            )
            return
```

   Leave the `import os` oddity inside the function as-is if moving it would
   touch unrelated lines; moving it to the top of the file is acceptable but
   optional.

**Verify**: `venv/bin/pytest tests/ -q` → all pass. `./run.sh` → app launches,
Library/Scenes/Playlists tabs render (close it after).

### Step 4: Tests for the skip behavior

Extend `tests/test_scene_playlist_player.py` with a new test class. Reuse the
existing `db`, `playlist_with_tracks`, `mock_engine` fixtures and the existing
`os.path.exists` patching pattern (`unittest.mock.patch` is already imported
there). Cases:

```python
class TestMissingFiles:
    def test_skips_missing_track_on_advance(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        missing_path = "/fake/path/track_1.mp3"
        with patch(
            "app.audio.scene_playlist_player.os.path.exists",
            side_effect=lambda p: p != missing_path,
        ):
            player = _make_player(playlist_id, db, mock_engine)
            player.start()
            assert player.current_audio_file_id == file_ids[0]
            player._on_track_ended()  # track_1 is missing -> skip to track_2
            assert player.current_audio_file_id == file_ids[2]
            assert player.is_playing

    def test_start_skips_missing_first_track(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        with patch(
            "app.audio.scene_playlist_player.os.path.exists",
            side_effect=lambda p: p != "/fake/path/track_0.mp3",
        ):
            player = _make_player(playlist_id, db, mock_engine)
            player.start()
            assert player.current_audio_file_id == file_ids[1]

    def test_all_missing_finishes_cleanly(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        finished = []
        with patch(
            "app.audio.scene_playlist_player.os.path.exists",
            return_value=False,
        ):
            player = _make_player(playlist_id, db, mock_engine)
            player.playback_finished.connect(lambda: finished.append(True))
            player.start()
            assert not player.is_playing
            assert player.current_audio_file_id is None
            assert finished == [True]
```

Adjust assertions to match the actual fixture paths if they differ — read the
fixture first (`playlist_with_tracks` creates `/fake/path/track_{i}.mp3`,
i = 0..4).

**Verify**: `venv/bin/pytest tests/test_scene_playlist_player.py -v` → all
pass including 3 new tests.

## Test plan

- Automated: the three `TestMissingFiles` cases above (skip mid-playlist, skip
  at start, all-missing clean finish), modeled on the existing fixtures in
  `tests/test_scene_playlist_player.py`.
- `PlaylistEditor` is a heavyweight widget without existing test coverage;
  its skip loop shares the same shape and is verified by grep done-criteria
  plus a manual check: run `./run.sh`, create a playlist containing a track
  whose file you've renamed on disk between two valid tracks, press play, and
  confirm playback skips the missing one and the log (stderr) shows
  `audio_file_missing`.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `venv/bin/pytest tests/ -q` exits 0 (85+ tests)
- [ ] `grep -l "audio_file_missing" app/audio/scene_playlist_player.py app/playlists/playlist_editor.py app/library/file_table.py app/scenes/scene_editor.py` lists all 4 files
- [ ] `grep -n "return$" app/audio/scene_playlist_player.py` shows no bare `return` left between the `os.path.exists` check and player creation in `_play_file` (it returns `False` now)
- [ ] `git status --porcelain` shows changes only to the 5 in-scope files plus `plans/README.md`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Any "Current state" excerpt doesn't match the live code (drift since `d64c771`).
- `grep -n "_play_audio_file(" app/playlists/playlist_editor.py` reveals
  auto-advance callers other than `_next_track` and `_on_track_ended`.
- The existing `os.path.exists` patching pattern is absent from
  `tests/test_scene_playlist_player.py` (meaning playback tests work some
  other way — re-read before writing new tests).
- A skip loop you wrote can recurse into `_restart`/`start` (re-entrancy) —
  the helper must be iterative, never re-entering itself.

## Maintenance notes

- Known accepted edge: with repeat enabled and the playlist's *last* playable
  pass exhausting into all-missing tracks, playback now stops cleanly instead
  of restarting. That beats the old behavior (silent stall in "playing"
  state), but a future change could route exhaustion through the repeat logic.
- Deferred on purpose: a visible "file missing" indicator in the Library tab
  rows and Playlists track list (the scene editor already has one in
  `track_control.py`). If someone adds it, follow the `track_control.py:61-65`
  badge pattern.
- If a future "relink missing files" feature lands, these `audio_file_missing`
  log events mark every code path it must hook into.
