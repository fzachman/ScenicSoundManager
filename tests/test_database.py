"""Tests for database operations"""

import os
import tempfile
import pytest

from app.database import DatabaseConnection, AudioFile, Tag, Scene, SceneAudioFile, ScenePlaylistEntry, Playlist, PlaylistTrack


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


class TestPlaylists:
    def test_add_playlist(self, db):
        playlist = Playlist(name="My Playlist")
        playlist_id = db.add_playlist(playlist)

        assert playlist_id is not None
        assert playlist_id > 0

    def test_get_playlist(self, db):
        playlist = Playlist(name="Test Playlist")
        playlist_id = db.add_playlist(playlist)

        retrieved = db.get_playlist(playlist_id)

        assert retrieved is not None
        assert retrieved.id == playlist_id
        assert retrieved.name == "Test Playlist"

    def test_get_all_playlists(self, db):
        db.add_playlist(Playlist(name="Playlist A"))
        db.add_playlist(Playlist(name="Playlist B"))
        db.add_playlist(Playlist(name="Playlist C"))

        playlists = db.get_all_playlists()

        assert len(playlists) == 3

    def test_search_playlists(self, db):
        db.add_playlist(Playlist(name="Battle Music"))
        db.add_playlist(Playlist(name="Tavern Ambience"))
        db.add_playlist(Playlist(name="Battle Drums"))

        results = db.search_playlists("battle")

        assert len(results) == 2
        names = [p.name for p in results]
        assert "Battle Music" in names
        assert "Battle Drums" in names

    def test_update_playlist(self, db):
        playlist_id = db.add_playlist(Playlist(name="Old Name"))

        playlist = db.get_playlist(playlist_id)
        playlist.name = "New Name"
        db.update_playlist(playlist)

        retrieved = db.get_playlist(playlist_id)
        assert retrieved.name == "New Name"

    def test_delete_playlist(self, db):
        playlist_id = db.add_playlist(Playlist(name="Delete Me"))

        db.delete_playlist(playlist_id)

        assert db.get_playlist(playlist_id) is None

    def test_reorder_playlists(self, db):
        id_a = db.add_playlist(Playlist(name="A"))
        id_b = db.add_playlist(Playlist(name="B"))
        id_c = db.add_playlist(Playlist(name="C"))

        db.reorder_playlists([id_c, id_a, id_b])

        playlists = db.get_all_playlists()
        assert playlists[0].id == id_c
        assert playlists[1].id == id_a
        assert playlists[2].id == id_b

    def test_add_track_to_playlist(self, db):
        playlist_id = db.add_playlist(Playlist(name="Test Playlist"))
        file_id = db.add_audio_file(AudioFile(file_path="/track.mp3", title="Track"))

        track_id = db.add_track_to_playlist(playlist_id, file_id)

        assert track_id is not None
        playlist = db.get_playlist(playlist_id)
        assert len(playlist.tracks) == 1
        assert playlist.tracks[0].audio_file_id == file_id
        assert playlist.tracks[0].audio_file.title == "Track"

    def test_add_track_auto_position(self, db):
        playlist_id = db.add_playlist(Playlist(name="Test Playlist"))
        f1 = db.add_audio_file(AudioFile(file_path="/a.mp3", title="A"))
        f2 = db.add_audio_file(AudioFile(file_path="/b.mp3", title="B"))

        db.add_track_to_playlist(playlist_id, f1)
        db.add_track_to_playlist(playlist_id, f2)

        playlist = db.get_playlist(playlist_id)
        assert playlist.tracks[0].position == 0
        assert playlist.tracks[1].position == 1

    def test_track_uniqueness_in_playlist(self, db):
        playlist_id = db.add_playlist(Playlist(name="Test Playlist"))
        file_id = db.add_audio_file(AudioFile(file_path="/track.mp3", title="Track"))

        db.add_track_to_playlist(playlist_id, file_id)

        with pytest.raises(Exception):
            db.add_track_to_playlist(playlist_id, file_id)

    def test_remove_track_from_playlist(self, db):
        playlist_id = db.add_playlist(Playlist(name="Test Playlist"))
        file_id = db.add_audio_file(AudioFile(file_path="/track.mp3", title="Track"))
        track_id = db.add_track_to_playlist(playlist_id, file_id)

        db.remove_track_from_playlist(track_id)

        playlist = db.get_playlist(playlist_id)
        assert len(playlist.tracks) == 0

    def test_reorder_playlist_tracks(self, db):
        playlist_id = db.add_playlist(Playlist(name="Test Playlist"))
        f1 = db.add_audio_file(AudioFile(file_path="/a.mp3", title="A"))
        f2 = db.add_audio_file(AudioFile(file_path="/b.mp3", title="B"))
        f3 = db.add_audio_file(AudioFile(file_path="/c.mp3", title="C"))

        t1 = db.add_track_to_playlist(playlist_id, f1)
        t2 = db.add_track_to_playlist(playlist_id, f2)
        t3 = db.add_track_to_playlist(playlist_id, f3)

        db.reorder_playlist_tracks(playlist_id, [t3, t1, t2])

        playlist = db.get_playlist(playlist_id)
        assert playlist.tracks[0].id == t3
        assert playlist.tracks[1].id == t1
        assert playlist.tracks[2].id == t2

    def test_delete_playlist_cascades_tracks(self, db):
        playlist_id = db.add_playlist(Playlist(name="Test Playlist"))
        file_id = db.add_audio_file(AudioFile(file_path="/track.mp3", title="Track"))
        db.add_track_to_playlist(playlist_id, file_id)

        db.delete_playlist(playlist_id)

        assert db.get_playlist(playlist_id) is None

    def test_playlist_tracks_include_tags(self, db):
        playlist_id = db.add_playlist(Playlist(name="Tagged Playlist"))
        file_id = db.add_audio_file(AudioFile(file_path="/tagged.mp3", title="Tagged Track"))
        tag_id = db.add_tag(Tag(name="Combat", color="#FF0000"))
        db.add_tag_to_audio_file(file_id, tag_id)
        db.add_track_to_playlist(playlist_id, file_id)

        playlist = db.get_playlist(playlist_id)

        assert len(playlist.tracks) == 1
        assert playlist.tracks[0].audio_file is not None
        assert len(playlist.tracks[0].audio_file.tags) == 1
        assert playlist.tracks[0].audio_file.tags[0].name == "Combat"
        assert playlist.tracks[0].audio_file.tags[0].color == "#FF0000"


class TestScenePlaylistEntries:
    def test_add_playlist_to_scene(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        playlist_id = db.add_playlist(Playlist(name="Battle Music"))

        entry_id = db.add_playlist_to_scene(scene_id, playlist_id, position=0)

        assert entry_id is not None
        assert entry_id > 0

    def test_get_scene_playlist_entries(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        playlist_id = db.add_playlist(Playlist(name="Battle Music"))

        db.add_playlist_to_scene(scene_id, playlist_id, position=0)

        entries = db.get_scene_playlist_entries(scene_id)

        assert len(entries) == 1
        assert entries[0].scene_id == scene_id
        assert entries[0].playlist_id == playlist_id
        assert entries[0].playlist is not None
        assert entries[0].playlist.name == "Battle Music"
        assert entries[0].is_shuffle is False
        assert entries[0].is_repeat is False

    def test_scene_includes_playlist_entries(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        playlist_id = db.add_playlist(Playlist(name="Battle Music"))

        db.add_playlist_to_scene(scene_id, playlist_id)

        scene = db.get_scene(scene_id)

        assert len(scene.playlist_entries) == 1
        assert scene.playlist_entries[0].playlist.name == "Battle Music"

    def test_add_playlist_with_shuffle_and_repeat(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        playlist_id = db.add_playlist(Playlist(name="Battle Music"))

        db.add_playlist_to_scene(scene_id, playlist_id, is_shuffle=True, is_repeat=True)

        entries = db.get_scene_playlist_entries(scene_id)

        assert entries[0].is_shuffle is True
        assert entries[0].is_repeat is True

    def test_update_scene_playlist_entry(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        playlist_id = db.add_playlist(Playlist(name="Battle Music"))
        entry_id = db.add_playlist_to_scene(scene_id, playlist_id)

        entries = db.get_scene_playlist_entries(scene_id)
        entry = entries[0]
        entry.is_shuffle = True
        entry.is_repeat = True
        db.update_scene_playlist_entry(entry)

        updated = db.get_scene_playlist_entries(scene_id)
        assert updated[0].is_shuffle is True
        assert updated[0].is_repeat is True

    def test_remove_playlist_from_scene(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        playlist_id = db.add_playlist(Playlist(name="Battle Music"))
        entry_id = db.add_playlist_to_scene(scene_id, playlist_id)

        db.remove_playlist_from_scene(entry_id)

        entries = db.get_scene_playlist_entries(scene_id)
        assert len(entries) == 0

    def test_playlist_uniqueness_in_scene(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        playlist_id = db.add_playlist(Playlist(name="Battle Music"))

        db.add_playlist_to_scene(scene_id, playlist_id)

        with pytest.raises(Exception):
            db.add_playlist_to_scene(scene_id, playlist_id)

    def test_reorder_scene_playlist_entries(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        pl_a = db.add_playlist(Playlist(name="A"))
        pl_b = db.add_playlist(Playlist(name="B"))
        pl_c = db.add_playlist(Playlist(name="C"))

        e_a = db.add_playlist_to_scene(scene_id, pl_a, position=0)
        e_b = db.add_playlist_to_scene(scene_id, pl_b, position=1)
        e_c = db.add_playlist_to_scene(scene_id, pl_c, position=2)

        db.reorder_scene_playlist_entries(scene_id, [e_c, e_a, e_b])

        entries = db.get_scene_playlist_entries(scene_id)
        assert entries[0].id == e_c
        assert entries[1].id == e_a
        assert entries[2].id == e_b

    def test_delete_scene_cascades_playlist_entries(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        playlist_id = db.add_playlist(Playlist(name="Battle Music"))
        db.add_playlist_to_scene(scene_id, playlist_id)

        db.delete_scene(scene_id)

        assert db.get_scene(scene_id) is None

    def test_delete_playlist_cascades_scene_entries(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        playlist_id = db.add_playlist(Playlist(name="Battle Music"))
        db.add_playlist_to_scene(scene_id, playlist_id)

        db.delete_playlist(playlist_id)

        entries = db.get_scene_playlist_entries(scene_id)
        assert len(entries) == 0

    def test_scene_playlist_entries_load_tracks_for_multiple_playlists(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        pl_a_id = db.add_playlist(Playlist(name="Playlist A"))
        pl_b_id = db.add_playlist(Playlist(name="Playlist B"))

        f1 = db.add_audio_file(AudioFile(file_path="/a1.mp3", title="A Track 1"))
        f2 = db.add_audio_file(AudioFile(file_path="/a2.mp3", title="A Track 2"))
        f3 = db.add_audio_file(AudioFile(file_path="/b1.mp3", title="B Track 1"))
        f4 = db.add_audio_file(AudioFile(file_path="/b2.mp3", title="B Track 2"))
        f5 = db.add_audio_file(AudioFile(file_path="/b3.mp3", title="B Track 3"))

        db.add_track_to_playlist(pl_a_id, f1)
        db.add_track_to_playlist(pl_a_id, f2)
        db.add_track_to_playlist(pl_b_id, f3)
        db.add_track_to_playlist(pl_b_id, f4)
        db.add_track_to_playlist(pl_b_id, f5)

        db.add_playlist_to_scene(scene_id, pl_a_id, position=0)
        db.add_playlist_to_scene(scene_id, pl_b_id, position=1)

        entries = db.get_scene_playlist_entries(scene_id)

        assert len(entries) == 2
        entry_a = next(e for e in entries if e.playlist_id == pl_a_id)
        entry_b = next(e for e in entries if e.playlist_id == pl_b_id)

        assert len(entry_a.playlist.tracks) == 2
        titles_a = [t.audio_file.title for t in entry_a.playlist.tracks]
        assert titles_a == ["A Track 1", "A Track 2"]

        assert len(entry_b.playlist.tracks) == 3
        titles_b = [t.audio_file.title for t in entry_b.playlist.tracks]
        assert titles_b == ["B Track 1", "B Track 2", "B Track 3"]

    def test_scene_playlist_entries_with_empty_playlist(self, db):
        scene_id = db.add_scene(Scene(title="Test Scene"))
        pl_id = db.add_playlist(Playlist(name="Empty Playlist"))

        db.add_playlist_to_scene(scene_id, pl_id, position=0)

        entries = db.get_scene_playlist_entries(scene_id)

        assert len(entries) == 1
        assert entries[0].playlist.tracks == []

    def test_same_playlist_in_two_scenes_unaffected(self, db):
        scene_a_id = db.add_scene(Scene(title="Scene A"))
        scene_b_id = db.add_scene(Scene(title="Scene B"))
        pl_id = db.add_playlist(Playlist(name="Shared Playlist"))

        f1 = db.add_audio_file(AudioFile(file_path="/s1.mp3", title="Shared Track 1"))
        f2 = db.add_audio_file(AudioFile(file_path="/s2.mp3", title="Shared Track 2"))
        db.add_track_to_playlist(pl_id, f1)
        db.add_track_to_playlist(pl_id, f2)

        db.add_playlist_to_scene(scene_a_id, pl_id, position=0)
        db.add_playlist_to_scene(scene_b_id, pl_id, position=0)

        entries_a = db.get_scene_playlist_entries(scene_a_id)
        entries_b = db.get_scene_playlist_entries(scene_b_id)

        assert len(entries_a) == 1
        assert len(entries_a[0].playlist.tracks) == 2
        assert len(entries_b) == 1
        assert len(entries_b[0].playlist.tracks) == 2
        assert entries_a[0].playlist.tracks[0].audio_file.title == "Shared Track 1"
        assert entries_b[0].playlist.tracks[0].audio_file.title == "Shared Track 1"


class TestBulkAudioFileMethods:
    def test_bulk_add_audio_files_returns_ids_and_persists(self, db):
        files = [
            AudioFile(file_path="/bulk/a.mp3", title="Alpha", artist="Artist A", duration_seconds=60.0),
            AudioFile(file_path="/bulk/b.mp3", title="Beta", artist="Artist B", duration_seconds=90.0),
            AudioFile(file_path="/bulk/c.mp3", title="Gamma", artist="Artist C", duration_seconds=120.0),
        ]
        ids = db.bulk_add_audio_files(files)

        assert len(ids) == 3
        assert len(set(ids)) == 3  # all distinct

        for file_id, original in zip(ids, files):
            retrieved = db.get_audio_file(file_id)
            assert retrieved is not None
            assert retrieved.file_path == original.file_path
            assert retrieved.title == original.title

    def test_bulk_add_audio_files_empty_list(self, db):
        result = db.bulk_add_audio_files([])
        assert result == []

    def test_get_all_audio_file_paths(self, db):
        # Empty DB returns empty set
        assert db.get_all_audio_file_paths() == set()

        # Add one file via add_audio_file and one via bulk_add_audio_files
        db.add_audio_file(AudioFile(file_path="/paths/single.mp3", title="Single"))
        db.bulk_add_audio_files([AudioFile(file_path="/paths/bulk.mp3", title="Bulk")])

        paths = db.get_all_audio_file_paths()
        assert paths == {"/paths/single.mp3", "/paths/bulk.mp3"}
