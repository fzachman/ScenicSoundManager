"""Tests for database operations"""

import os
import tempfile
import pytest

from app.database import DatabaseConnection, AudioFile, Tag, Scene, SceneAudioFile


@pytest.fixture
def db():
    """Create a temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = DatabaseConnection(db_path)
    conn.connect()

    yield conn

    conn.close()
    os.unlink(db_path)


class TestAudioFiles:
    def test_add_audio_file(self, db):
        audio_file = AudioFile(
            file_path="/path/to/test.mp3",
            title="Test Song",
            artist="Test Artist",
            duration_seconds=180.5
        )
        file_id = db.add_audio_file(audio_file)

        assert file_id is not None
        assert file_id > 0

    def test_get_audio_file(self, db):
        audio_file = AudioFile(
            file_path="/path/to/test.mp3",
            title="Test Song",
            artist="Test Artist",
            duration_seconds=180.5
        )
        file_id = db.add_audio_file(audio_file)

        retrieved = db.get_audio_file(file_id)

        assert retrieved is not None
        assert retrieved.id == file_id
        assert retrieved.file_path == "/path/to/test.mp3"
        assert retrieved.title == "Test Song"
        assert retrieved.artist == "Test Artist"
        assert retrieved.duration_seconds == 180.5

    def test_get_audio_file_by_path(self, db):
        audio_file = AudioFile(
            file_path="/path/to/unique.mp3",
            title="Unique Song"
        )
        db.add_audio_file(audio_file)

        retrieved = db.get_audio_file_by_path("/path/to/unique.mp3")

        assert retrieved is not None
        assert retrieved.title == "Unique Song"

    def test_search_audio_files(self, db):
        db.add_audio_file(AudioFile(file_path="/a.mp3", title="Battle Theme"))
        db.add_audio_file(AudioFile(file_path="/b.mp3", title="Tavern Music"))
        db.add_audio_file(AudioFile(file_path="/c.mp3", title="Battle Drums"))

        results = db.search_audio_files("battle")

        assert len(results) == 2
        titles = [r.title for r in results]
        assert "Battle Theme" in titles
        assert "Battle Drums" in titles

    def test_delete_audio_file(self, db):
        audio_file = AudioFile(file_path="/delete.mp3", title="Delete Me")
        file_id = db.add_audio_file(audio_file)

        db.delete_audio_file(file_id)

        assert db.get_audio_file(file_id) is None


class TestTags:
    def test_add_tag(self, db):
        tag = Tag(name="Combat", color="#FF0000")
        tag_id = db.add_tag(tag)

        assert tag_id is not None
        assert tag_id > 0

    def test_get_all_tags(self, db):
        db.add_tag(Tag(name="Combat"))
        db.add_tag(Tag(name="Ambient"))
        db.add_tag(Tag(name="Music"))

        tags = db.get_all_tags()

        assert len(tags) == 3
        names = [t.name for t in tags]
        assert "Combat" in names
        assert "Ambient" in names
        assert "Music" in names

    def test_tag_audio_file_association(self, db):
        # Create audio file and tag
        file_id = db.add_audio_file(AudioFile(file_path="/test.mp3", title="Test"))
        tag_id = db.add_tag(Tag(name="TestTag"))

        # Associate
        db.add_tag_to_audio_file(file_id, tag_id)

        # Verify
        tags = db.get_tags_for_audio_file(file_id)
        assert len(tags) == 1
        assert tags[0].name == "TestTag"

        files = db.get_audio_files_by_tag(tag_id)
        assert len(files) == 1
        assert files[0].title == "Test"


class TestScenes:
    def test_add_scene(self, db):
        scene = Scene(title="Test Scene")
        scene_id = db.add_scene(scene)

        assert scene_id is not None
        assert scene_id > 0

    def test_get_scene(self, db):
        scene = Scene(title="My Scene")
        scene_id = db.add_scene(scene)

        retrieved = db.get_scene(scene_id)

        assert retrieved is not None
        assert retrieved.id == scene_id
        assert retrieved.title == "My Scene"

    def test_add_track_to_scene(self, db):
        # Create scene and audio file
        scene_id = db.add_scene(Scene(title="Test Scene"))
        file_id = db.add_audio_file(AudioFile(file_path="/track.mp3", title="Track"))

        # Add track
        track_id = db.add_track_to_scene(scene_id, file_id, position=0)

        # Verify
        scene = db.get_scene(scene_id)
        assert len(scene.tracks) == 1
        assert scene.tracks[0].audio_file_id == file_id
        assert scene.tracks[0].position == 0
        assert scene.tracks[0].play_mode is True

    def test_update_track_settings(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        file_id = db.add_audio_file(AudioFile(file_path="/track.mp3", title="Track"))
        db.add_track_to_scene(scene_id, file_id)

        # Get track and update
        scene = db.get_scene(scene_id)
        track = scene.tracks[0]
        track.volume = 0.5
        track.is_repeat = True
        track.play_mode = False
        db.update_track_settings(track)

        # Verify
        scene = db.get_scene(scene_id)
        assert scene.tracks[0].volume == 0.5
        assert scene.tracks[0].is_repeat is True
        assert scene.tracks[0].play_mode is False

    def test_delete_scene_cascades(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        file_id = db.add_audio_file(AudioFile(file_path="/track.mp3", title="Track"))
        db.add_track_to_scene(scene_id, file_id)

        # Delete scene
        db.delete_scene(scene_id)

        # Scene should be gone
        assert db.get_scene(scene_id) is None
