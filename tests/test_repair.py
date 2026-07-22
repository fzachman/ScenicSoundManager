"""Tests for the repair-library logic (app/library/repair.py)."""

import hashlib
import subprocess

import pytest

from app.database import AudioFile, DatabaseConnection
from app.library import repair
from app.library.repair import Candidate, Confidence, UnlinkedEntry


@pytest.fixture
def db(tmp_path):
    conn = DatabaseConnection(str(tmp_path / "live.db"))
    conn.connect()
    yield conn
    conn.close()


def make_file(tmp_path, name: str, content: bytes):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def add_entry(db, file_path: str, content: bytes | None = None) -> AudioFile:
    """Register a library entry, fingerprinted as if `content` was imported."""
    audio_file = AudioFile(file_path=file_path, title=file_path)
    if content is not None:
        audio_file.file_size = len(content)
        audio_file.content_hash = hashlib.sha256(content).hexdigest()
    file_id = db.add_audio_file(audio_file)
    stored = db.get_audio_file(file_id)
    assert stored is not None
    return stored


class TestFindUnlinked:
    def test_returns_only_entries_with_missing_paths(self, db, tmp_path):
        existing = make_file(tmp_path, "here.mp3", b"x")
        add_entry(db, str(existing))
        missing = add_entry(db, str(tmp_path / "gone.mp3"))

        unlinked = repair.find_unlinked(db)

        assert [e.audio_file.id for e in unlinked] == [missing.id]


class TestClassifyCandidate:
    def test_matching_hash_is_certain(self, db, tmp_path):
        content = b"goblin ambience" * 100
        entry = add_entry(db, str(tmp_path / "gone.mp3"), content)
        candidate_path = make_file(tmp_path, "moved/gone.mp3", content)

        candidate = repair.classify_candidate(entry, str(candidate_path))

        assert candidate is not None
        assert candidate.confidence is Confidence.CERTAIN
        assert candidate.file_size == len(content)
        assert candidate.content_hash == hashlib.sha256(content).hexdigest()

    def test_differing_hash_is_probable(self, db, tmp_path):
        entry = add_entry(db, str(tmp_path / "gone.mp3"), b"original")
        candidate_path = make_file(tmp_path, "moved/gone.mp3", b"different bytes")

        candidate = repair.classify_candidate(entry, str(candidate_path))

        assert candidate is not None
        assert candidate.confidence is Confidence.PROBABLE

    def test_no_stored_hash_is_probable_at_best(self, db, tmp_path):
        entry = add_entry(db, str(tmp_path / "gone.mp3"), content=None)
        candidate_path = make_file(tmp_path, "moved/gone.mp3", b"anything")

        candidate = repair.classify_candidate(entry, str(candidate_path))

        assert candidate is not None
        assert candidate.confidence is Confidence.PROBABLE

    def test_unreadable_candidate_returns_none(self, db, tmp_path):
        entry = add_entry(db, str(tmp_path / "gone.mp3"), b"x")
        assert repair.classify_candidate(entry, str(tmp_path / "nope.mp3")) is None


class TestSpotlightSearch:
    def test_returns_empty_when_mdfind_unavailable(self, monkeypatch):
        monkeypatch.setattr(repair.shutil, "which", lambda name: None)
        assert repair.spotlight_search("a.mp3") == []

    def test_query_quotes_filename(self, monkeypatch):
        seen = {}

        def fake_run(argv, **kwargs):
            seen["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        monkeypatch.setattr(repair.shutil, "which", lambda name: "/usr/bin/mdfind")
        monkeypatch.setattr(repair.subprocess, "run", fake_run)

        repair.spotlight_search('Don\'t "Stop".mp3')

        assert seen["argv"][0] == "mdfind"
        assert seen["argv"][1] == 'kMDItemFSName == "Don\'t \\"Stop\\".mp3"'

    def test_parses_output_lines(self, monkeypatch):
        monkeypatch.setattr(repair.shutil, "which", lambda name: "/usr/bin/mdfind")
        monkeypatch.setattr(
            repair.subprocess,
            "run",
            lambda argv, **kw: subprocess.CompletedProcess(
                argv, 0, stdout="/a/x.mp3\n/b/x.mp3\n", stderr=""
            ),
        )
        assert repair.spotlight_search("x.mp3") == ["/a/x.mp3", "/b/x.mp3"]

    def test_nonzero_exit_returns_empty(self, monkeypatch):
        monkeypatch.setattr(repair.shutil, "which", lambda name: "/usr/bin/mdfind")
        monkeypatch.setattr(
            repair.subprocess,
            "run",
            lambda argv, **kw: subprocess.CompletedProcess(
                argv, 1, stdout="", stderr="boom"
            ),
        )
        assert repair.spotlight_search("x.mp3") == []


class TestScanSpotlight:
    def test_attaches_classified_candidates(self, db, tmp_path):
        content = b"cavern drips" * 50
        entry = UnlinkedEntry(add_entry(db, str(tmp_path / "gone.mp3"), content))
        exact = make_file(tmp_path, "new-home/gone.mp3", content)
        near = make_file(tmp_path, "other/gone.mp3", b"re-encoded")

        repair.scan_spotlight(
            [entry],
            library_paths=set(),
            search=lambda name: [str(exact), str(near), "/does/not/exist.mp3"],
        )

        assert [c.path for c in entry.candidates] == [str(exact), str(near)]
        assert entry.candidates[0].confidence is Confidence.CERTAIN
        assert entry.candidates[1].confidence is Confidence.PROBABLE

    def test_paths_already_in_library_are_skipped(self, db, tmp_path):
        content = b"z"
        entry = UnlinkedEntry(add_entry(db, str(tmp_path / "gone.mp3"), content))
        registered = make_file(tmp_path, "dup/gone.mp3", content)

        repair.scan_spotlight(
            [entry],
            library_paths={str(registered)},
            search=lambda name: [str(registered)],
        )

        assert entry.candidates == []

    def test_progress_false_cancels(self, db, tmp_path):
        content = b"z"
        entry = UnlinkedEntry(add_entry(db, str(tmp_path / "gone.mp3"), content))
        exact = make_file(tmp_path, "new/gone.mp3", content)

        repair.scan_spotlight(
            [entry],
            library_paths=set(),
            progress=lambda done, total: False,
            search=lambda name: [str(exact)],
        )

        assert entry.candidates == []


class TestScanFolder:
    def test_finds_renamed_file_by_size_and_hash(self, db, tmp_path):
        content = b"tavern brawl" * 200
        entry = UnlinkedEntry(add_entry(db, str(tmp_path / "Old Name.mp3"), content))
        renamed = make_file(tmp_path, "root/New Name.mp3", content)

        repair.scan_folder(str(tmp_path / "root"), [entry], library_paths=set())

        assert [c.path for c in entry.candidates] == [str(renamed)]
        assert entry.candidates[0].confidence is Confidence.CERTAIN

    def test_same_name_different_content_is_probable(self, db, tmp_path):
        entry = UnlinkedEntry(add_entry(db, str(tmp_path / "Theme.mp3"), b"v1"))
        candidate = make_file(tmp_path, "root/sub/Theme.mp3", b"v2 remaster")

        repair.scan_folder(str(tmp_path / "root"), [entry], library_paths=set())

        assert [c.path for c in entry.candidates] == [str(candidate)]
        assert entry.candidates[0].confidence is Confidence.PROBABLE

    def test_size_collision_with_different_name_is_noise(self, db, tmp_path):
        entry = UnlinkedEntry(add_entry(db, str(tmp_path / "Theme.mp3"), b"aaaa"))
        make_file(tmp_path, "root/Other.mp3", b"bbbb")  # same size, no match

        repair.scan_folder(str(tmp_path / "root"), [entry], library_paths=set())

        assert entry.candidates == []

    def test_unsupported_and_library_files_ignored(self, db, tmp_path):
        content = b"x" * 10
        entry = UnlinkedEntry(add_entry(db, str(tmp_path / "gone.mp3"), content))
        make_file(tmp_path, "root/gone.txt", content)
        registered = make_file(tmp_path, "root/gone.mp3", content)

        repair.scan_folder(
            str(tmp_path / "root"), [entry], library_paths={str(registered)}
        )

        assert entry.candidates == []

    def test_walk_tick_false_cancels(self, db, tmp_path):
        content = b"x"
        entry = UnlinkedEntry(add_entry(db, str(tmp_path / "gone.mp3"), content))
        make_file(tmp_path, "root/gone.mp3", content)

        repair.scan_folder(
            str(tmp_path / "root"),
            [entry],
            library_paths=set(),
            walk_tick=lambda seen: False,
        )

        assert entry.candidates == []


class TestAddCandidates:
    def test_dedups_by_path_and_sorts_certain_first(self):
        entry = UnlinkedEntry(AudioFile(file_path="/gone.mp3"))
        probable = Candidate("/a.mp3", Confidence.PROBABLE)
        entry.add_candidates([probable])
        entry.add_candidates(
            [
                Candidate("/a.mp3", Confidence.PROBABLE),  # duplicate path
                Candidate("/b.mp3", Confidence.CERTAIN),
            ]
        )
        assert [(c.path, c.confidence) for c in entry.candidates] == [
            ("/b.mp3", Confidence.CERTAIN),
            ("/a.mp3", Confidence.PROBABLE),
        ]


class TestRelink:
    def test_updates_path_and_fingerprint(self, db, tmp_path):
        entry = add_entry(db, str(tmp_path / "gone.mp3"), b"old bytes")
        new_content = b"new bytes here"
        candidate = Candidate(
            path=str(tmp_path / "found.mp3"),
            confidence=Confidence.PROBABLE,
            file_size=len(new_content),
            content_hash=hashlib.sha256(new_content).hexdigest(),
        )

        repair.relink(db, entry, candidate)

        stored = db.get_audio_file(entry.id)
        assert stored is not None
        assert stored.file_path == candidate.path
        assert stored.file_size == candidate.file_size
        assert stored.content_hash == candidate.content_hash
