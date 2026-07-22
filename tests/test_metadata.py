"""Tests for MetadataExtractor (app/library/metadata.py).

Covers the previously-untested extraction branches, especially the broad
``except Exception`` error path (TESTS-03): a mutagen failure must degrade to
using the filename as the title rather than propagating.
"""

import hashlib
from types import SimpleNamespace

from app.library.metadata import MetadataExtractor, compute_fingerprint


class FakeAudio:
    """Stand-in for a mutagen ``File`` (easy=True): dict-like ``get`` + ``info``."""

    def __init__(self, tags=None, length=None):
        self._tags = tags or {}
        self.info = SimpleNamespace(length=length) if length is not None else None

    def get(self, key):
        return self._tags.get(key)


def _patch_file(monkeypatch, behavior):
    """Patch the mutagen ``File`` symbol used inside metadata.py."""
    monkeypatch.setattr("app.library.metadata.File", behavior)


class TestExtractErrorPath:
    def test_exception_falls_back_to_filename(self, monkeypatch):
        # The TESTS-03 target: a mutagen failure must NOT propagate — extract
        # swallows it and uses the filename (sans extension) as the title.
        def boom(*args, **kwargs):
            raise RuntimeError("corrupt header")

        _patch_file(monkeypatch, boom)

        result = MetadataExtractor.extract("/music/Goblin Cave.mp3")

        assert result == {
            "title": "Goblin Cave",
            "artist": None,
            "duration_seconds": None,
        }

    def test_unrecognized_file_falls_back_to_filename(self, monkeypatch):
        # mutagen returns None when it doesn't recognize the file.
        _patch_file(monkeypatch, lambda *a, **k: None)

        result = MetadataExtractor.extract("/music/Mystery.xyz")

        assert result == {"title": "Mystery", "artist": None, "duration_seconds": None}


class TestExtractHappyPath:
    def test_reads_title_artist_and_duration(self, monkeypatch):
        audio = FakeAudio(
            tags={"title": ["Tavern Brawl"], "artist": ["The Bard"]}, length=185.5
        )
        _patch_file(monkeypatch, lambda *a, **k: audio)

        result = MetadataExtractor.extract("/music/track01.mp3")

        assert result["title"] == "Tavern Brawl"
        assert result["artist"] == "The Bard"
        assert result["duration_seconds"] == 185.5

    def test_missing_title_falls_back_to_filename(self, monkeypatch):
        # No title tag, but an artist tag and no info -> title from filename.
        audio = FakeAudio(tags={"artist": ["The Bard"]})
        _patch_file(monkeypatch, lambda *a, **k: audio)

        result = MetadataExtractor.extract("/music/Untitled Loop.flac")

        assert result["title"] == "Untitled Loop"
        assert result["artist"] == "The Bard"
        assert result["duration_seconds"] is None


class TestComputeFingerprint:
    def test_size_and_sha256_of_file_bytes(self, tmp_path):
        content = b"fake mp3 bytes" * 1000
        track = tmp_path / "track.mp3"
        track.write_bytes(content)

        size, digest = compute_fingerprint(str(track))

        assert size == len(content)
        assert digest == hashlib.sha256(content).hexdigest()

    def test_unreadable_file_returns_nones(self, tmp_path):
        size, digest = compute_fingerprint(str(tmp_path / "missing.mp3"))
        assert (size, digest) == (None, None)


class TestIsSupportedFormat:
    def test_supported_extensions(self):
        for path in ("/a/b.mp3", "/a/B.MP3", "/a/x.flac", "/a/y.opus", "/a/z.m4a"):
            assert MetadataExtractor.is_supported_format(path) is True

    def test_unsupported_extensions(self):
        for path in ("/a/notes.txt", "/a/clip.mov", "/a/noext"):
            assert MetadataExtractor.is_supported_format(path) is False
