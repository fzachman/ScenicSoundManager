# 009 — Repair Library (relink moved/missing audio files)

**Status:** TODO (idea captured 2026-07-22, user-requested; not yet planned)

## Problem

The library stores absolute paths to audio files it does not own. When files
are moved/renamed on disk, their library entries (and every scene, playlist,
and soundboard button referencing them) silently break. There is currently no
way to find or fix these except deleting and re-importing, which loses tags
and references.

## Sketch (from the user)

- Scan the library for "unlinked" entries (path no longer exists).
- Search the computer for candidate replacements:
  - by filename first (cheap);
  - ideally by content hash — which means we'd have to START STORING A HASH
    per audio file at import time (schema change; backfill existing rows by
    hashing on first repair run or lazily).
- Repair UI: list each unlinked file with its candidate match(es), let the
  user preview the candidate track (reuse the preview pattern from
  AudioFileSearchWidget), and accept each fix individually before relinking.

## Notes for planning later

- Relinking = updating `audio_files.file_path` only; all scene/playlist/
  soundboard references join on the audio file id, so they heal for free.
- Hash choice: partial hash (e.g. first N MB + size) is usually enough for
  audio and much faster than full-file SHA over a large library.
- Full-disk search needs scoping (start dirs, exclusions) or it will be slow;
  consider letting the user point at a folder to scan.
- Related, cheaper follow-up: a "show unlinked files" filter in the Library
  tab, so breakage is at least visible before a repair feature exists.
