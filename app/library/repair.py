"""Repair-library logic: find unlinked entries and candidate replacements.

Qt-free on purpose so it can be unit-tested directly; the dialog in
repair_dialog.py drives it with progress callbacks. Design in plan 009:
the stored content hash CONFIRMS candidates found cheaply (by filename
via Spotlight, or by exact size in a folder walk) — we never hash the
disk looking for matches.
"""

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from app.database import AudioFile, DatabaseConnection
from app.shared.logging import get_logger

from .metadata import MetadataExtractor, compute_fingerprint

_log = get_logger(__name__)

MDFIND_TIMEOUT_SECONDS = 10


class Confidence(Enum):
    """How sure we are that a candidate file is the unlinked entry."""

    CERTAIN = "certain"  # content hash matches the stored fingerprint
    PROBABLE = "probable"  # filename matches, but hash differs or is unknown

    @property
    def label(self) -> str:
        return {
            Confidence.CERTAIN: "Exact match",
            Confidence.PROBABLE: "Possible match — preview to confirm",
        }[self]


@dataclass
class Candidate:
    """A file on disk that may be the new home of an unlinked entry."""

    path: str
    confidence: Confidence
    file_size: int | None = None
    content_hash: str | None = None


@dataclass
class UnlinkedEntry:
    """A library row whose file_path no longer exists, plus candidates."""

    audio_file: AudioFile
    candidates: list[Candidate] = field(default_factory=list)

    def add_candidates(self, new: list[Candidate]) -> None:
        """Merge candidates, dropping duplicate paths and keeping CERTAIN first."""
        known = {c.path for c in self.candidates}
        self.candidates.extend(c for c in new if c.path not in known)
        self.candidates.sort(key=lambda c: c.confidence is not Confidence.CERTAIN)


def find_unlinked(db: DatabaseConnection) -> list[UnlinkedEntry]:
    """All library entries whose stored path no longer exists on disk."""
    return [
        UnlinkedEntry(audio_file=f)
        for f in db.get_all_audio_files()
        if not os.path.exists(f.file_path)
    ]


def classify_candidate(audio_file: AudioFile, path: str) -> Candidate | None:
    """Fingerprint a candidate path and grade it against the stored entry.

    Returns None when the candidate is unreadable. Without a stored hash
    (file was unreadable at import) the best we can say is PROBABLE.
    """
    size, digest = compute_fingerprint(path)
    if digest is None:
        return None
    if audio_file.content_hash is not None and digest == audio_file.content_hash:
        confidence = Confidence.CERTAIN
    else:
        confidence = Confidence.PROBABLE
    return Candidate(
        path=path, confidence=confidence, file_size=size, content_hash=digest
    )


def spotlight_search(filename: str) -> list[str]:
    """Find files named exactly `filename` via Spotlight (macOS mdfind).

    Returns [] when Spotlight is unavailable (non-macOS, unindexed
    volumes) — the folder-walk fallback covers those cases.
    """
    if shutil.which("mdfind") is None:
        return []
    # No shell involved (argv), so only the query language's own quoting
    # matters: double-quoted string with backslash escapes.
    escaped = filename.replace("\\", "\\\\").replace('"', '\\"')
    query = f'kMDItemFSName == "{escaped}"'
    try:
        result = subprocess.run(
            ["mdfind", query],
            capture_output=True,
            text=True,
            timeout=MDFIND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _log.warning("spotlight_search_failed", filename=filename, error=str(e))
        return []
    if result.returncode != 0:
        _log.warning("spotlight_search_failed", filename=filename, stderr=result.stderr)
        return []
    return [line for line in result.stdout.splitlines() if line]


def scan_spotlight(
    entries: list[UnlinkedEntry],
    library_paths: set[str],
    progress: Callable[[int, int], bool] | None = None,
    search: Callable[[str], list[str]] | None = None,
) -> None:
    """Attach Spotlight candidates to each entry, in place.

    `progress(done, total)` is called per entry; returning False cancels.
    Candidate paths already registered to another library entry are
    skipped: relinking to them would just create a duplicate row's path
    (file_path is UNIQUE).
    """
    if search is None:
        # Resolved at call time (not a default arg) so tests can patch
        # module-level spotlight_search.
        search = spotlight_search
    for index, entry in enumerate(entries):
        if progress is not None and not progress(index, len(entries)):
            return
        filename = os.path.basename(entry.audio_file.file_path)
        found = []
        for path in search(filename):
            if path in library_paths or not os.path.isfile(path):
                continue
            candidate = classify_candidate(entry.audio_file, path)
            if candidate is not None:
                found.append(candidate)
        entry.add_candidates(found)
    if progress is not None:
        progress(len(entries), len(entries))


def scan_folder(
    root: str,
    entries: list[UnlinkedEntry],
    library_paths: set[str],
    progress: Callable[[int, int], bool] | None = None,
    walk_tick: Callable[[int], bool] | None = None,
) -> None:
    """Attach candidates found under `root` to each entry, in place.

    One walk collects every supported audio file, indexed by size and by
    filename. A file is a candidate if its size matches the stored size
    (then the hash decides — this catches RENAMED files) or its filename
    matches (PROBABLE at best). Only the small candidate set is hashed.

    `walk_tick(files_seen)` fires once per directory so a UI can stay
    responsive during large walks; returning False cancels. `progress`
    behaves as in scan_spotlight.
    """
    by_size: dict[int, list[str]] = {}
    by_name: dict[str, list[str]] = {}
    seen = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        if walk_tick is not None and not walk_tick(seen):
            return
        seen += len(filenames)
        for name in filenames:
            path = os.path.join(dirpath, name)
            if not MetadataExtractor.is_supported_format(path) or (
                path in library_paths
            ):
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            by_size.setdefault(size, []).append(path)
            by_name.setdefault(name.lower(), []).append(path)

    for index, entry in enumerate(entries):
        if progress is not None and not progress(index, len(entries)):
            return
        audio_file = entry.audio_file
        paths: list[str] = []
        if audio_file.file_size is not None:
            paths.extend(by_size.get(audio_file.file_size, []))
        filename = os.path.basename(audio_file.file_path).lower()
        paths.extend(p for p in by_name.get(filename, []) if p not in paths)

        found = []
        for path in paths:
            candidate = classify_candidate(audio_file, path)
            if candidate is None:
                continue
            # A size-only hit whose hash doesn't match and whose name
            # differs is noise (thousands of tracks share sizes loosely);
            # keep it only when the hash or the filename backs it up.
            name_matches = os.path.basename(path).lower() == filename
            if candidate.confidence is Confidence.CERTAIN or name_matches:
                found.append(candidate)
        entry.add_candidates(found)
    if progress is not None:
        progress(len(entries), len(entries))


def relink(db: DatabaseConnection, audio_file: AudioFile, candidate: Candidate) -> None:
    """Point the library entry at the candidate's path.

    Also refreshes the stored fingerprint from the accepted file, which
    covers accepting a PROBABLE candidate whose bytes differ (plan 009).
    Scene/playlist/soundboard references join on the audio file id, so
    they heal for free.
    """
    assert audio_file.id is not None
    db.relink_audio_file(
        audio_file.id, candidate.path, candidate.file_size, candidate.content_hash
    )
    _log.info(
        "audio_file_relinked",
        audio_file_id=audio_file.id,
        old_path=audio_file.file_path,
        new_path=candidate.path,
        confidence=candidate.confidence.value,
    )
