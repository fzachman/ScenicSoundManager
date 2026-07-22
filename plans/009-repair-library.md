# 009 — Repair Library (relink moved/missing audio files)

**Status:** SHIPPED 2026-07-22 (feature/repair-library). File → Repair
Library… implements the design below (app/library/repair.py +
repair_dialog.py). Remaining follow-up idea: "show unlinked files"
filter in the Library tab (see Notes).

## Problem

The library stores absolute paths to audio files it does not own. When files
are moved/renamed on disk, their library entries (and every scene, playlist,
and soundboard button referencing them) silently break. There is currently no
way to find or fix these except deleting and re-importing, which loses tags
and references.

## Agreed design (discussed 2026-07-22)

### Fingerprint: `file_size` + `content_hash` (full-file SHA-256)

- Stored on `audio_files`, computed at import time (the import already reads
  every file for mutagen metadata, so the extra read is nearly free).
- Full-file hash, NOT a partial hash: ID3 tags sit at the *start* of MP3s,
  so "first N MB" would mostly hash tag data. Full SHA-256 over a music
  library is fast enough on modern disks.
- Known caveat (accepted): a byte hash fingerprints the FILE, not the audio.
  Editing tags in an external app changes the bytes and stales the hash.
  Fine for the moved/reorganized-files scenario this feature targets. If it
  ever matters, the upgrade path is hashing only the audio stream (mutagen
  knows where tags end; FLAC headers even carry a decoded-audio MD5).

### Hash CONFIRMS, it never SEARCHES

Never hash the disk looking for matches — find cheap candidates first, then
hash only the candidates. Per unlinked entry:

1. Candidates by **filename** (and exact **byte size** — a strong
   discriminator on its own).
2. Hash each candidate (a handful of files, milliseconds).
3. Confidence tiers:
   - filename + hash match → certain; safe for one-click / bulk accept
   - filename match, hash mismatch or no stored hash → "probably" —
     require preview + explicit accept
   - nothing found → unresolved

### Finding candidates: Spotlight fast path + folder-walk fallback

- **Spotlight** (macOS): `mdfind "kMDItemFSName == '<name>'"` via
  QProcess/subprocess — instant, whole-disk, no walking. Fire queries for
  ALL unlinked entries automatically when the repair dialog opens.
  Caveat: skips unindexed volumes (some external drives), so it cannot be
  the only mechanism.
- **Folder walk** fallback: user picks a root (`getExistingDirectory`),
  `Path.rglob` in a worker QThread with progress. Pre-filter by exact size,
  hash only size matches — this also catches RENAMED files, which filename
  search never can.

### Repair UI

Dialog: scan library for dead paths → auto-run Spotlight queries → list of
unlinked entries with candidate(s) + confidence badge, preview player
(reuse AudioFileSearchWidget pattern), accept per-fix; "Search a folder…"
button for leftovers.

## Notes for planning later

- Relinking = updating `audio_files.file_path` only; all scene/playlist/
  soundboard references join on the audio file id, so they heal for free.
  On accept, also refresh `file_size`/`content_hash` from the accepted file
  (covers the accepted-despite-hash-mismatch case).
- Full-disk search needs scoping (start dirs, exclusions) or it will be slow;
  the Spotlight + user-chosen-folder combination above is the answer.
- Related, cheaper follow-up: a "show unlinked files" filter in the Library
  tab, so breakage is at least visible before the repair feature exists.

## Scaffolding shipped ahead (2026-07-22)

- `audio_files.file_size` (INTEGER) + `audio_files.content_hash` (TEXT,
  hex SHA-256) in schema.sql; populated at import for all new files.
- Existing library backfilled via one-shot script (run directly against the
  live DB, not committed — per alpha migration convention).
