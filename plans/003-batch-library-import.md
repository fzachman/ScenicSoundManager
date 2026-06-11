# Plan 003: Make bulk library import use one duplicate-check query and one transaction

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat d64c771..HEAD -- app/database/connection.py app/library/library_widget.py tests/test_database.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `d64c771`, 2026-06-11

## Why this matters

Directory import (a recently added feature — the user can drop a whole folder
of audio into the library) processes files in a Python loop where **each file
costs one SELECT (duplicate check) plus one INSERT plus one `commit()`**.
SQLite commits flush to disk, so importing a 500-file folder issues 500
SELECTs and 500 fsync-ing transactions, all on the UI thread. Batching the
duplicate check into one query and the inserts into one transaction removes
almost all of that overhead with no behavior change. (Metadata extraction
also runs synchronously in this loop; moving it off the UI thread is
explicitly out of scope here — see Maintenance notes.)

## Current state

- `app/database/connection.py` — all SQLite CRUD lives here on a single
  `DatabaseConnection` class.
- `app/library/library_widget.py` — the import loop.

The per-file insert+commit, `app/database/connection.py:104-114`:

```python
    def add_audio_file(self, audio_file: AudioFile) -> int:
        """Add an audio file to the library, return its ID"""
        cursor = self.connection.execute(
            """
            INSERT INTO audio_files (file_path, title, artist, duration_seconds)
            VALUES (?, ?, ?, ?)
            """,
            (audio_file.file_path, audio_file.title, audio_file.artist, audio_file.duration_seconds)
        )
        self.connection.commit()
        return cursor.lastrowid
```

The import loop, `app/library/library_widget.py:195-232`:

```python
    def _import_files(self, file_paths: list[str]):
        """Import files into the library"""
        added_count = 0
        skipped_count = 0
        duplicate_paths: list[str] = []
        seen_duplicates: set[str] = set()

        for file_path in file_paths:
            if not MetadataExtractor.is_supported_format(file_path):
                skipped_count += 1
                continue

            # Check if file already exists in library
            existing = self.db.get_audio_file_by_path(file_path)
            if existing:
                skipped_count += 1
                if file_path not in seen_duplicates:
                    duplicate_paths.append(file_path)
                    seen_duplicates.add(file_path)
                continue

            # Extract metadata
            metadata = MetadataExtractor.extract(file_path)

            # Create audio file record
            audio_file = AudioFile(
                file_path=file_path,
                title=metadata["title"],
                artist=metadata["artist"],
                duration_seconds=metadata["duration_seconds"]
            )

            self.db.add_audio_file(audio_file)
            added_count += 1

        # Refresh display
        self._load_files()
        self.library_updated.emit()

        if duplicate_paths:
            dialog = DuplicateFilesDialog(self, duplicates=duplicate_paths)
            dialog.exec()
```

Repo convention for bulk DB methods — single statement / single commit, empty
input short-circuits (exemplar `app/database/connection.py:293-306`):

```python
    def bulk_update_artist(self, audio_file_ids: list[int], artist: str | None) -> None:
        """Update artist for multiple audio files in a single transaction"""
        if not audio_file_ids:
            return
        placeholders = ",".join("?" * len(audio_file_ids))
        self.connection.execute(
            f"""
            UPDATE audio_files
            SET artist = ?, updated_at = datetime('now')
            WHERE id IN ({placeholders})
            """,
            [artist] + audio_file_ids
        )
        self.connection.commit()
```

DB test conventions: `tests/test_database.py` uses a `db` fixture creating a
`DatabaseConnection` against a `tempfile.NamedTemporaryFile(suffix=".db")`.
Models are dataclasses in `app/database/models.py` (`AudioFile` has
`file_path`, `title`, `artist`, `duration_seconds`).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| All tests | `venv/bin/pytest tests/ -q` | all pass (82 before this plan) |
| DB tests only | `venv/bin/pytest tests/test_database.py -v` | all pass |
| Run the app (manual check) | `./run.sh` | window opens |

## Scope

**In scope** (the only files you should modify):
- `app/database/connection.py` (add two methods; do not change `add_audio_file`)
- `app/library/library_widget.py` (`_import_files` only)
- `tests/test_database.py` (extend)

**Out of scope** (do NOT touch, even though they look related):
- `app/library/metadata.py` — extraction stays synchronous in this plan.
- `add_audio_file` itself — other callers (single-file flows, tests, fixtures)
  rely on its commit-per-call semantics; leave it alone.
- Any UI changes (progress bar, threading) — deferred.

## Git workflow

- Branch: `advisor/003-batch-library-import`.
- Single commit; message style: short imperative sentence, e.g.
  `Batch duplicate checks and inserts during library import.`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add `get_all_audio_file_paths` to DatabaseConnection

In `app/database/connection.py`, next to `get_all_audio_files` (line 140), add:

```python
    def get_all_audio_file_paths(self) -> set[str]:
        """Get the set of all file paths currently in the library"""
        cursor = self.connection.execute("SELECT file_path FROM audio_files")
        return {row["file_path"] for row in cursor.fetchall()}
```

**Verify**: `venv/bin/pytest tests/test_database.py -q` → all pass (nothing
uses it yet; this confirms no syntax/import damage).

### Step 2: Add `bulk_add_audio_files` to DatabaseConnection

Below `add_audio_file`, add (matching the bulk-method convention shown above):

```python
    def bulk_add_audio_files(self, audio_files: list[AudioFile]) -> list[int]:
        """Add multiple audio files in a single transaction, return their IDs"""
        if not audio_files:
            return []
        ids = []
        for audio_file in audio_files:
            cursor = self.connection.execute(
                """
                INSERT INTO audio_files (file_path, title, artist, duration_seconds)
                VALUES (?, ?, ?, ?)
                """,
                (audio_file.file_path, audio_file.title, audio_file.artist, audio_file.duration_seconds)
            )
            ids.append(cursor.lastrowid)
        self.connection.commit()
        return ids
```

(One `commit()` total. `executemany` is not used because the per-row
`lastrowid` values are returned.)

**Verify**: `venv/bin/pytest tests/test_database.py -q` → all pass.

### Step 3: Rewrite the import loop to use the batch methods

In `app/library/library_widget.py`, modify `_import_files` so that:

- Before the loop: `existing_paths = self.db.get_all_audio_file_paths()` and
  `new_files: list[AudioFile] = []`.
- Inside the loop, the duplicate check becomes
  `if file_path in existing_paths:` (same skip/duplicate-dialog bookkeeping as
  today). After passing the check, add the path to `existing_paths` —
  this also deduplicates repeated paths *within* the incoming `file_paths`
  list, which the old code caught via its per-file DB query.
- Instead of `self.db.add_audio_file(audio_file)`, append the `AudioFile` to
  `new_files`.
- After the loop, before `self._load_files()`:
  `self.db.bulk_add_audio_files(new_files)` and set
  `added_count = len(new_files)` (or keep incrementing in the loop — either
  way the count must equal the number inserted).

Everything else (`skipped_count`, `duplicate_paths`, `DuplicateFilesDialog`,
`self._load_files()`, `library_updated.emit()`) stays exactly as-is.

**Verify**: `venv/bin/pytest tests/ -q` → all pass.
**Verify (manual)**: `./run.sh`, drop a folder of audio files onto the Library
tab → files appear; drop the same folder again → duplicate dialog lists them
and nothing is double-imported. Close the app.

### Step 4: Tests

Add to `tests/test_database.py` (use its existing `db` fixture and the
`AudioFile` import already present there):

- `test_bulk_add_audio_files_returns_ids_and_persists`: bulk-add 3 files,
  assert 3 distinct ids returned, and `db.get_audio_file(id)` returns each
  with matching `file_path`/`title`.
- `test_bulk_add_audio_files_empty_list`: `db.bulk_add_audio_files([]) == []`.
- `test_get_all_audio_file_paths`: empty DB → `set()`; after adding 2 files
  (one via `add_audio_file`, one via `bulk_add_audio_files`) → set of both paths.

**Verify**: `venv/bin/pytest tests/test_database.py -v` → all pass, including
3 new tests.

## Test plan

Covered in Step 4. Pattern source: existing tests in `tests/test_database.py`
(temp-file DB fixture, dataclass construction). The import-widget loop itself
has no existing test harness; it is covered by the manual verification in
Step 3 — do not build a new UI test rig for this plan.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `venv/bin/pytest tests/ -q` exits 0 (85+ tests)
- [ ] `grep -n "get_audio_file_by_path" app/library/library_widget.py` returns no matches
- [ ] `grep -n "bulk_add_audio_files" app/library/library_widget.py` returns at least one match
- [ ] `grep -n "add_audio_file(" app/database/connection.py` still shows the original method unchanged (single-file API preserved)
- [ ] `git status --porcelain` shows changes only to the 3 in-scope files plus `plans/README.md`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The `_import_files` body doesn't match the excerpt (drift since `d64c771`).
- You find other callers of `_import_files` that depend on files being
  visible in the DB *mid-loop* (search `grep -rn "_import_files" app/`) —
  the batch delays inserts to the end of the loop.
- `audio_files.file_path` turns out to have a UNIQUE constraint that the old
  per-file flow relied on for dedup in a way the new flow misses (check
  `app/database/schema.sql` for the `audio_files` table definition before
  Step 3; if INSERTs start failing on constraint violations, stop).

## Maintenance notes

- Deferred on purpose: metadata extraction (`MetadataExtractor.extract`) still
  runs synchronously per file on the UI thread. If imports of huge folders
  feel slow *after* this lands, the next step is a worker-thread import
  (QThreadPool) with progress reporting — a separate, riskier plan.
- If a "watch folder" or re-scan feature is added later,
  `get_all_audio_file_paths` is the cheap primitive to build it on.
- Reviewer focus: the in-loop `existing_paths.add(file_path)` line — without
  it, a file list containing the same path twice inserts duplicates.
