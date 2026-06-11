# Plan 004: Batch-load playlist tracks in get_scene_playlist_entries (fix N+1)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat d64c771..HEAD -- app/database/connection.py tests/test_database.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (textually adjacent to plan 003 in `connection.py`;
  execute either order, rebase trivially)
- **Category**: perf
- **Planned at**: commit `d64c771`, 2026-06-11

## Why this matters

`get_scene_playlist_entries` issues one query for a scene's playlist entries,
then calls `get_playlist_tracks(...)` **inside the row loop** — one extra
query batch per playlist entry. Scene loading calls this every time the scene
editor refreshes (selection change, track add/remove, modification), so a
scene with several playlist entries pays N+1 on every refresh. The repo
already solved this exact pattern for tags with `_batch_load_tags` (commit
`b3b6cdc` "Fix N+1 tag queries..."); this plan applies the same convention to
playlist tracks.

## Current state

All changes are in `app/database/connection.py`.

The N+1, `app/database/connection.py:559-594` (the loop call at line 581):

```python
    def get_scene_playlist_entries(self, scene_id: int) -> list[ScenePlaylistEntry]:
        """Get all playlist entries in a scene with their playlist data"""
        cursor = self.connection.execute(
            """
            SELECT spe.*, p.name, p.position AS playlist_position,
                   p.created_at AS playlist_created_at, p.updated_at AS playlist_updated_at
            FROM scene_playlist_entries spe
            JOIN playlists p ON spe.playlist_id = p.id
            WHERE spe.scene_id = ?
            ORDER BY spe.position
            """,
            (scene_id,)
        )
        entries = []
        for row in cursor.fetchall():
            playlist = Playlist(
                id=row["playlist_id"],
                name=row["name"],
                position=row["playlist_position"],
                created_at=row["playlist_created_at"],
                updated_at=row["playlist_updated_at"]
            )
            playlist.tracks = self.get_playlist_tracks(row["playlist_id"])
            entry = ScenePlaylistEntry(...)
            entries.append(entry)
        return entries
```

The single-playlist loader to mirror, `app/database/connection.py:713-747`:

```python
    def get_playlist_tracks(self, playlist_id: int) -> list[PlaylistTrack]:
        """Get all tracks in a playlist with their audio file data and tags"""
        cursor = self.connection.execute(
            """
            SELECT pt.*, af.file_path, af.title, af.artist, af.duration_seconds
            FROM playlist_tracks pt
            JOIN audio_files af ON pt.audio_file_id = af.id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
            """,
            (playlist_id,)
        )
        rows = cursor.fetchall()
        audio_file_ids = [row["audio_file_id"] for row in rows]
        tags_by_file = self._batch_load_tags(audio_file_ids)

        tracks = []
        for row in rows:
            audio_file = AudioFile(
                id=row["audio_file_id"],
                file_path=row["file_path"],
                title=row["title"],
                artist=row["artist"],
                duration_seconds=row["duration_seconds"]
            )
            audio_file.tags = tags_by_file.get(audio_file.id, [])
            track = PlaylistTrack(
                id=row["id"],
                playlist_id=row["playlist_id"],
                audio_file_id=row["audio_file_id"],
                position=row["position"],
                audio_file=audio_file
            )
            tracks.append(track)
        return tracks
```

The batching convention to follow, `app/database/connection.py:346-378`
(`_batch_load_tags`): empty-input short-circuit returning `{}`, IN-clause
placeholders built with `",".join("?" * len(ids))`, returns
`dict[id, list[...]]` pre-seeded with empty lists for every requested id.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| All tests | `venv/bin/pytest tests/ -q` | all pass (82 before this plan) |
| DB tests only | `venv/bin/pytest tests/test_database.py -v` | all pass |
| Scene-playlist tests | `venv/bin/pytest tests/test_scene_playlist_player.py -q` | all pass |

## Scope

**In scope** (the only files you should modify):
- `app/database/connection.py`
- `tests/test_database.py` (extend)

**Out of scope** (do NOT touch, even though they look related):
- `get_playlist_tracks` — keep the single-playlist method; other callers
  (`ScenePlaylistPlayer._load_tracks`, playlist editor) use it directly.
- `app/database/schema.sql` — no index changes in this plan.
- Any UI code.

## Git workflow

- Branch: `advisor/004-batch-scene-playlist-tracks`.
- Single commit; message style: short imperative sentence, e.g.
  `Batch-load playlist tracks when loading scene playlist entries.`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add `_batch_load_playlist_tracks`

In `app/database/connection.py`, next to `get_playlist_tracks`, add a private
method mirroring `_batch_load_tags`:

```python
    def _batch_load_playlist_tracks(self, playlist_ids: list[int]) -> dict[int, list[PlaylistTrack]]:
        """Load tracks for multiple playlists in a single query.

        Returns a dict mapping playlist_id -> list of PlaylistTracks
        (ordered by position).
        """
        if not playlist_ids:
            return {}

        placeholders = ",".join("?" * len(playlist_ids))
        cursor = self.connection.execute(
            f"""
            SELECT pt.*, af.file_path, af.title, af.artist, af.duration_seconds
            FROM playlist_tracks pt
            JOIN audio_files af ON pt.audio_file_id = af.id
            WHERE pt.playlist_id IN ({placeholders})
            ORDER BY pt.playlist_id, pt.position
            """,
            playlist_ids,
        )
        rows = cursor.fetchall()
        audio_file_ids = [row["audio_file_id"] for row in rows]
        tags_by_file = self._batch_load_tags(audio_file_ids)

        tracks_by_playlist: dict[int, list[PlaylistTrack]] = {pid: [] for pid in playlist_ids}
        for row in rows:
            audio_file = AudioFile(
                id=row["audio_file_id"],
                file_path=row["file_path"],
                title=row["title"],
                artist=row["artist"],
                duration_seconds=row["duration_seconds"]
            )
            audio_file.tags = tags_by_file.get(audio_file.id, [])
            track = PlaylistTrack(
                id=row["id"],
                playlist_id=row["playlist_id"],
                audio_file_id=row["audio_file_id"],
                position=row["position"],
                audio_file=audio_file
            )
            tracks_by_playlist[row["playlist_id"]].append(track)
        return tracks_by_playlist
```

Note: `_batch_load_tags` may receive duplicate `audio_file_ids` when the same
audio file appears in multiple playlists — read `_batch_load_tags`
(connection.py:346) and confirm it tolerates duplicates (it seeds the dict
with the ids and does IN-clause lookup, so duplicates are harmless; if you
prefer, pass `list(dict.fromkeys(audio_file_ids))`).

**Verify**: `venv/bin/pytest tests/test_database.py -q` → all pass.

### Step 2: Use it in `get_scene_playlist_entries`

Restructure the method to fetch rows first, batch-load once, then build:

```python
        rows = cursor.fetchall()
        playlist_ids = [row["playlist_id"] for row in rows]
        tracks_by_playlist = self._batch_load_playlist_tracks(playlist_ids)

        entries = []
        for row in rows:
            playlist = Playlist(...)          # unchanged
            playlist.tracks = tracks_by_playlist.get(row["playlist_id"], [])
            entry = ScenePlaylistEntry(...)   # unchanged
            entries.append(entry)
        return entries
```

The `ScenePlaylistEntry(...)` construction keeps all its existing keyword
arguments verbatim (id, scene_id, playlist_id, position, volume, is_shuffle,
is_repeat, play_mode, playlist).

**Verify**: `venv/bin/pytest tests/ -q` → all pass (the existing
scene-playlist-entry tests in `tests/test_database.py` and
`tests/test_scene_playlist_player.py` exercise this method).

### Step 3: Tests

Add to `tests/test_database.py`, using its existing `db` fixture and helper
patterns (search the file for existing `scene_playlist` tests and mirror their
setup — playlists are created via `db.add_playlist(Playlist(name=...))`,
tracks via `db.add_track_to_playlist(playlist_id, audio_file_id, position=i)`,
entries via the existing add-scene-playlist-entry method used by those tests):

- `test_scene_playlist_entries_load_tracks_for_multiple_playlists`: one scene
  with two playlist entries (playlist A: 2 tracks, playlist B: 3 tracks);
  assert each returned entry's `playlist.tracks` has the right count, the
  right titles, and position order preserved.
- `test_scene_playlist_entries_with_empty_playlist`: entry whose playlist has
  zero tracks → `playlist.tracks == []` (this guards the dict pre-seeding).
- `test_same_playlist_in_two_scenes_unaffected`: optional sanity — same
  playlist referenced from two different scenes loads identically for each.

**Verify**: `venv/bin/pytest tests/test_database.py -v` → all pass, including
the new tests.

## Test plan

Covered in Step 3. The strongest regression guard is the empty-playlist case
plus order preservation (`ORDER BY pt.playlist_id, pt.position` must not lose
the per-playlist position ordering the old per-playlist query had).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `venv/bin/pytest tests/ -q` exits 0 (84+ tests)
- [ ] `grep -n "get_playlist_tracks" app/database/connection.py` shows the method definition and NO call inside `get_scene_playlist_entries`
- [ ] `grep -c "_batch_load_playlist_tracks" app/database/connection.py` ≥ 2 (definition + call site)
- [ ] `git status --porcelain` shows changes only to the 2 in-scope files plus `plans/README.md`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `get_scene_playlist_entries` or `get_playlist_tracks` doesn't match the
  excerpts (drift since `d64c771`).
- Existing tests fail after Step 2 with differences in track ordering or tag
  contents — do not weaken assertions to pass; report the diff.
- `_batch_load_tags` turns out not to tolerate the input you give it
  (exception on duplicates/empties) — report rather than modifying
  `_batch_load_tags`, which is out of scope.

## Maintenance notes

- If playlist entries gain per-entry track filtering or ordering overrides
  later, this batch loader is the place that must learn about it.
- Plan 003 adds methods to the same file; whichever lands second rebases
  trivially (different methods, no overlapping hunks expected).
- Reviewer focus: the dict pre-seeding (`{pid: [] for pid in playlist_ids}`)
  — without it, an empty playlist yields a `KeyError`/`None` instead of `[]`.
