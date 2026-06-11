"""SQLite database connection management"""

import os
import sqlite3
from pathlib import Path
from typing import Optional

from .models import AudioFile, Tag, Scene, SceneAudioFile, ScenePlaylistEntry, Playlist, PlaylistTrack


class DatabaseConnection:
    """Manages SQLite database connection and operations"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to user's application support directory
            app_support = Path.home() / "Library" / "Application Support" / "SoundManager"
            app_support.mkdir(parents=True, exist_ok=True)
            db_path = str(app_support / "soundmanager.db")

        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Establish database connection and initialize schema"""
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Create database tables if they don't exist"""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, "r") as f:
            schema = f.read()
        self.connection.executescript(schema)
        self._ensure_scene_positions()
        self._ensure_scene_track_play_mode()
        self._ensure_scene_playlist_entry_play_mode()
        self._ensure_scene_playlist_entry_volume()
        self.connection.commit()

    def _ensure_scene_positions(self) -> None:
        """Ensure scenes have a position column and values"""
        cursor = self.connection.execute("PRAGMA table_info(scenes)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "position" not in columns:
            self.connection.execute(
                "ALTER TABLE scenes ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
            )

        # Initialize positions for existing rows if needed
        rows = self.connection.execute(
            "SELECT id, position FROM scenes ORDER BY title COLLATE NOCASE"
        ).fetchall()
        has_nonzero = any(row["position"] != 0 for row in rows)
        if rows and not has_nonzero:
            for index, row in enumerate(rows):
                self.connection.execute(
                    "UPDATE scenes SET position = ? WHERE id = ?",
                    (index, row["id"])
                )

    def _ensure_scene_track_play_mode(self) -> None:
        """Ensure scene tracks have a play_mode column"""
        cursor = self.connection.execute("PRAGMA table_info(scene_audio_files)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "play_mode" not in columns:
            self.connection.execute(
                "ALTER TABLE scene_audio_files ADD COLUMN play_mode INTEGER NOT NULL DEFAULT 1"
            )
        self.connection.execute(
            "UPDATE scene_audio_files SET play_mode = 1 WHERE play_mode IS NULL"
        )

    def _ensure_scene_playlist_entry_play_mode(self) -> None:
        """Ensure scene playlist entries have a play_mode column"""
        cursor = self.connection.execute("PRAGMA table_info(scene_playlist_entries)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "play_mode" not in columns:
            self.connection.execute(
                "ALTER TABLE scene_playlist_entries ADD COLUMN play_mode INTEGER NOT NULL DEFAULT 1"
            )
        self.connection.execute(
            "UPDATE scene_playlist_entries SET play_mode = 1 WHERE play_mode IS NULL"
        )

    def _ensure_scene_playlist_entry_volume(self) -> None:
        """Ensure scene playlist entries have a volume column"""
        cursor = self.connection.execute("PRAGMA table_info(scene_playlist_entries)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "volume" not in columns:
            self.connection.execute(
                "ALTER TABLE scene_playlist_entries ADD COLUMN volume REAL NOT NULL DEFAULT 1.0"
            )

    def close(self) -> None:
        """Close database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None

    # Audio File operations
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

    def get_audio_file(self, file_id: int) -> Optional[AudioFile]:
        """Get an audio file by ID"""
        cursor = self.connection.execute(
            "SELECT * FROM audio_files WHERE id = ?", (file_id,)
        )
        row = cursor.fetchone()
        if row:
            audio_file = self._row_to_audio_file(row)
            audio_file.tags = self.get_tags_for_audio_file(file_id)
            return audio_file
        return None

    def get_audio_file_by_path(self, file_path: str) -> Optional[AudioFile]:
        """Get an audio file by path"""
        cursor = self.connection.execute(
            "SELECT * FROM audio_files WHERE file_path = ?", (file_path,)
        )
        row = cursor.fetchone()
        if row:
            audio_file = self._row_to_audio_file(row)
            audio_file.tags = self.get_tags_for_audio_file(audio_file.id)
            return audio_file
        return None

    def get_all_audio_file_paths(self) -> set[str]:
        """Get the set of all file paths currently in the library"""
        cursor = self.connection.execute("SELECT file_path FROM audio_files")
        return {row["file_path"] for row in cursor.fetchall()}

    def get_all_audio_files(self) -> list[AudioFile]:
        """Get all audio files in the library"""
        cursor = self.connection.execute(
            "SELECT * FROM audio_files ORDER BY title COLLATE NOCASE"
        )
        files = [self._row_to_audio_file(row) for row in cursor.fetchall()]
        tags_by_file = self._batch_load_tags([f.id for f in files])
        for audio_file in files:
            audio_file.tags = tags_by_file.get(audio_file.id, [])
        return files

    def search_audio_files(self, query: str, tag_ids: Optional[list[int]] = None) -> list[AudioFile]:
        """Search audio files by title, artist, or tags"""
        query_pattern = f"%{query}%"

        if tag_ids:
            include_no_tag = -1 in tag_ids
            real_tag_ids = [tag_id for tag_id in tag_ids if tag_id != -1]

            # Filter by tags and rank by number of matched tags (descending).
            if real_tag_ids:
                placeholders = ",".join("?" * len(real_tag_ids))
                join_type = "LEFT JOIN" if include_no_tag else "JOIN"
                sql = f"""
                    SELECT af.*, COUNT(DISTINCT aft.tag_id) AS match_count
                    FROM audio_files af
                    {join_type} audio_file_tags aft ON af.id = aft.audio_file_id
                    WHERE (
                        aft.tag_id IN ({placeholders})
                        {"OR aft.tag_id IS NULL" if include_no_tag else ""}
                    )
                    AND (af.title LIKE ? OR af.artist LIKE ?)
                    GROUP BY af.id
                    ORDER BY match_count DESC, af.title COLLATE NOCASE
                """
                params = real_tag_ids + [query_pattern, query_pattern]
            else:
                sql = """
                    SELECT af.* FROM audio_files af
                    LEFT JOIN audio_file_tags aft ON af.id = aft.audio_file_id
                    WHERE aft.tag_id IS NULL
                    AND (af.title LIKE ? OR af.artist LIKE ?)
                    ORDER BY af.title COLLATE NOCASE
                """
                params = [query_pattern, query_pattern]
        else:
            sql = """
                SELECT * FROM audio_files
                WHERE title LIKE ? OR artist LIKE ?
                ORDER BY title COLLATE NOCASE
            """
            params = [query_pattern, query_pattern]

        cursor = self.connection.execute(sql, params)
        files = [self._row_to_audio_file(row) for row in cursor.fetchall()]
        tags_by_file = self._batch_load_tags([f.id for f in files])
        for audio_file in files:
            audio_file.tags = tags_by_file.get(audio_file.id, [])
        return files

    def update_audio_file(self, audio_file: AudioFile) -> None:
        """Update an audio file's metadata"""
        self.connection.execute(
            """
            UPDATE audio_files
            SET title = ?, artist = ?, duration_seconds = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (audio_file.title, audio_file.artist, audio_file.duration_seconds, audio_file.id)
        )
        self.connection.commit()

    def delete_audio_file(self, file_id: int) -> None:
        """Delete an audio file from the library"""
        self.connection.execute("DELETE FROM audio_files WHERE id = ?", (file_id,))
        self.connection.commit()

    def _row_to_audio_file(self, row: sqlite3.Row) -> AudioFile:
        """Convert a database row to an AudioFile object"""
        return AudioFile(
            id=row["id"],
            file_path=row["file_path"],
            title=row["title"],
            artist=row["artist"],
            duration_seconds=row["duration_seconds"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    # Tag operations
    def add_tag(self, tag: Tag) -> int:
        """Add a new tag, return its ID"""
        cursor = self.connection.execute(
            "INSERT INTO tags (name, color) VALUES (?, ?)",
            (tag.name, tag.color)
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_all_tags(self) -> list[Tag]:
        """Get all tags"""
        cursor = self.connection.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE")
        return [self._row_to_tag(row) for row in cursor.fetchall()]

    def get_tag_by_name(self, name: str) -> Optional[Tag]:
        """Get a tag by name (case-insensitive)"""
        cursor = self.connection.execute(
            "SELECT * FROM tags WHERE name = ? COLLATE NOCASE", (name,)
        )
        row = cursor.fetchone()
        return self._row_to_tag(row) if row else None

    def update_tag(self, tag: Tag) -> None:
        """Update a tag"""
        self.connection.execute(
            "UPDATE tags SET name = ?, color = ? WHERE id = ?",
            (tag.name, tag.color, tag.id)
        )
        self.connection.commit()

    def delete_tag(self, tag_id: int) -> None:
        """Delete a tag"""
        self.connection.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        self.connection.commit()

    def _row_to_tag(self, row: sqlite3.Row) -> Tag:
        """Convert a database row to a Tag object"""
        return Tag(
            id=row["id"],
            name=row["name"],
            color=row["color"],
            created_at=row["created_at"]
        )

    # Audio file <-> Tag associations
    def add_tag_to_audio_file(self, audio_file_id: int, tag_id: int) -> None:
        """Associate a tag with an audio file"""
        self.connection.execute(
            "INSERT OR IGNORE INTO audio_file_tags (audio_file_id, tag_id) VALUES (?, ?)",
            (audio_file_id, tag_id)
        )
        self.connection.commit()

    def bulk_add_tags_to_audio_files(self, audio_file_ids: list[int], tag_ids: list[int]) -> None:
        """Add multiple tags to multiple audio files in a single transaction"""
        for file_id in audio_file_ids:
            for tag_id in tag_ids:
                self.connection.execute(
                    "INSERT OR IGNORE INTO audio_file_tags (audio_file_id, tag_id) VALUES (?, ?)",
                    (file_id, tag_id)
                )
        self.connection.commit()

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

    def bulk_remove_tags_from_audio_files(self, audio_file_ids: list[int], tag_ids: list[int]) -> None:
        """Remove specified tags from multiple audio files in a single transaction"""
        if not audio_file_ids or not tag_ids:
            return
        file_placeholders = ",".join("?" * len(audio_file_ids))
        tag_placeholders = ",".join("?" * len(tag_ids))
        self.connection.execute(
            f"""
            DELETE FROM audio_file_tags
            WHERE audio_file_id IN ({file_placeholders})
            AND tag_id IN ({tag_placeholders})
            """,
            audio_file_ids + tag_ids
        )
        self.connection.commit()

    def remove_tag_from_audio_file(self, audio_file_id: int, tag_id: int) -> None:
        """Remove a tag association from an audio file"""
        self.connection.execute(
            "DELETE FROM audio_file_tags WHERE audio_file_id = ? AND tag_id = ?",
            (audio_file_id, tag_id)
        )
        self.connection.commit()

    def get_tags_for_audio_file(self, audio_file_id: int) -> list[Tag]:
        """Get all tags for an audio file"""
        cursor = self.connection.execute(
            """
            SELECT t.* FROM tags t
            JOIN audio_file_tags aft ON t.id = aft.tag_id
            WHERE aft.audio_file_id = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (audio_file_id,)
        )
        return [self._row_to_tag(row) for row in cursor.fetchall()]

    def _batch_load_tags(self, audio_file_ids: list[int]) -> dict[int, list[Tag]]:
        """Load tags for multiple audio files in a single query.

        Returns a dict mapping audio_file_id -> list of Tags.
        """
        if not audio_file_ids:
            return {}

        placeholders = ",".join("?" * len(audio_file_ids))
        cursor = self.connection.execute(
            f"""
            SELECT aft.audio_file_id, t.* FROM tags t
            JOIN audio_file_tags aft ON t.id = aft.tag_id
            WHERE aft.audio_file_id IN ({placeholders})
            ORDER BY t.name COLLATE NOCASE
            """,
            audio_file_ids,
        )

        tags_by_file: dict[int, list[Tag]] = {fid: [] for fid in audio_file_ids}
        for row in cursor.fetchall():
            tags_by_file[row["audio_file_id"]].append(self._row_to_tag(row))
        return tags_by_file

    def get_audio_files_by_tag(self, tag_id: int) -> list[AudioFile]:
        """Get all audio files with a specific tag"""
        cursor = self.connection.execute(
            """
            SELECT af.* FROM audio_files af
            JOIN audio_file_tags aft ON af.id = aft.audio_file_id
            WHERE aft.tag_id = ?
            ORDER BY af.title COLLATE NOCASE
            """,
            (tag_id,)
        )
        files = [self._row_to_audio_file(row) for row in cursor.fetchall()]
        tags_by_file = self._batch_load_tags([f.id for f in files])
        for audio_file in files:
            audio_file.tags = tags_by_file.get(audio_file.id, [])
        return files

    # Scene operations
    def add_scene(self, scene: Scene) -> int:
        """Add a new scene, return its ID"""
        self.connection.execute("UPDATE scenes SET position = position + 1")
        next_position = 0
        cursor = self.connection.execute(
            "INSERT INTO scenes (title, position) VALUES (?, ?)",
            (scene.title, next_position)
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_scene(self, scene_id: int) -> Optional[Scene]:
        """Get a scene by ID with all its tracks and playlist entries"""
        cursor = self.connection.execute(
            "SELECT * FROM scenes WHERE id = ?", (scene_id,)
        )
        row = cursor.fetchone()
        if row:
            scene = self._row_to_scene(row)
            scene.tracks = self.get_scene_tracks(scene_id)
            scene.playlist_entries = self.get_scene_playlist_entries(scene_id)
            return scene
        return None

    def get_all_scenes(self) -> list[Scene]:
        """Get all scenes"""
        cursor = self.connection.execute(
            "SELECT * FROM scenes ORDER BY position, title COLLATE NOCASE"
        )
        return [self._row_to_scene(row) for row in cursor.fetchall()]

    def search_scenes(self, query: str) -> list[Scene]:
        """Search scenes by title"""
        cursor = self.connection.execute(
            "SELECT * FROM scenes WHERE title LIKE ? ORDER BY position, title COLLATE NOCASE",
            (f"%{query}%",)
        )
        return [self._row_to_scene(row) for row in cursor.fetchall()]

    def update_scene(self, scene: Scene) -> None:
        """Update a scene's title"""
        self.connection.execute(
            "UPDATE scenes SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (scene.title, scene.id)
        )
        self.connection.commit()

    def delete_scene(self, scene_id: int) -> None:
        """Delete a scene"""
        self.connection.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))
        self.connection.commit()

    def _row_to_scene(self, row: sqlite3.Row) -> Scene:
        """Convert a database row to a Scene object"""
        return Scene(
            id=row["id"],
            title=row["title"],
            position=row["position"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    def reorder_scenes(self, scene_ids: list[int]) -> None:
        """Reorder scenes by updating their positions"""
        for position, scene_id in enumerate(scene_ids):
            self.connection.execute(
                "UPDATE scenes SET position = ? WHERE id = ?",
                (position, scene_id)
            )
        self.connection.commit()

    # Scene track operations
    def add_track_to_scene(
        self,
        scene_id: int,
        audio_file_id: int,
        position: int = 0,
        play_mode: bool = True,
    ) -> int:
        """Add an audio file to a scene, return the scene_audio_file ID"""
        cursor = self.connection.execute(
            """
            INSERT INTO scene_audio_files (scene_id, audio_file_id, position, play_mode)
            VALUES (?, ?, ?, ?)
            """,
            (scene_id, audio_file_id, position, int(play_mode))
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_scene_tracks(self, scene_id: int) -> list[SceneAudioFile]:
        """Get all tracks in a scene with their audio file data"""
        cursor = self.connection.execute(
            """
            SELECT saf.*, af.file_path, af.title, af.artist, af.duration_seconds
            FROM scene_audio_files saf
            JOIN audio_files af ON saf.audio_file_id = af.id
            WHERE saf.scene_id = ?
            ORDER BY saf.position
            """,
            (scene_id,)
        )
        tracks = []
        for row in cursor.fetchall():
            audio_file = AudioFile(
                id=row["audio_file_id"],
                file_path=row["file_path"],
                title=row["title"],
                artist=row["artist"],
                duration_seconds=row["duration_seconds"]
            )
            track = SceneAudioFile(
                id=row["id"],
                scene_id=row["scene_id"],
                audio_file_id=row["audio_file_id"],
                position=row["position"],
                volume=row["volume"],
                is_repeat=bool(row["is_repeat"]),
                play_mode=bool(row["play_mode"]),
                audio_file=audio_file
            )
            tracks.append(track)
        return tracks

    def update_track_settings(self, track: SceneAudioFile) -> None:
        """Update a track's volume, repeat, position, and play mode settings"""
        self.connection.execute(
            """
            UPDATE scene_audio_files
            SET volume = ?, is_repeat = ?, position = ?, play_mode = ?
            WHERE id = ?
            """,
            (track.volume, int(track.is_repeat), track.position, int(track.play_mode), track.id)
        )
        self.connection.commit()

    def remove_track_from_scene(self, track_id: int) -> None:
        """Remove a track from a scene"""
        self.connection.execute("DELETE FROM scene_audio_files WHERE id = ?", (track_id,))
        self.connection.commit()

    def reorder_tracks(self, scene_id: int, track_ids: list[int]) -> None:
        """Reorder tracks in a scene by updating their positions"""
        for position, track_id in enumerate(track_ids):
            self.connection.execute(
                "UPDATE scene_audio_files SET position = ? WHERE id = ? AND scene_id = ?",
                (position, track_id, scene_id)
            )
        self.connection.commit()

    # Scene playlist entry operations
    def add_playlist_to_scene(
        self,
        scene_id: int,
        playlist_id: int,
        position: int = 0,
        volume: float = 1.0,
        is_shuffle: bool = False,
        is_repeat: bool = False,
        play_mode: bool = True,
    ) -> int:
        """Add a playlist entry to a scene, return the entry ID"""
        cursor = self.connection.execute(
            """
            INSERT INTO scene_playlist_entries (scene_id, playlist_id, position, volume, is_shuffle, is_repeat, play_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (scene_id, playlist_id, position, volume, int(is_shuffle), int(is_repeat), int(play_mode))
        )
        self.connection.commit()
        return cursor.lastrowid

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
            entry = ScenePlaylistEntry(
                id=row["id"],
                scene_id=row["scene_id"],
                playlist_id=row["playlist_id"],
                position=row["position"],
                volume=row["volume"],
                is_shuffle=bool(row["is_shuffle"]),
                is_repeat=bool(row["is_repeat"]),
                play_mode=bool(row["play_mode"]),
                playlist=playlist
            )
            entries.append(entry)
        return entries

    def update_scene_playlist_entry(self, entry: ScenePlaylistEntry) -> None:
        """Update a scene playlist entry's settings"""
        self.connection.execute(
            """
            UPDATE scene_playlist_entries
            SET volume = ?, is_shuffle = ?, is_repeat = ?, position = ?, play_mode = ?
            WHERE id = ?
            """,
            (entry.volume, int(entry.is_shuffle), int(entry.is_repeat), entry.position, int(entry.play_mode), entry.id)
        )
        self.connection.commit()

    def remove_playlist_from_scene(self, entry_id: int) -> None:
        """Remove a playlist entry from a scene"""
        self.connection.execute("DELETE FROM scene_playlist_entries WHERE id = ?", (entry_id,))
        self.connection.commit()

    def reorder_scene_playlist_entries(self, scene_id: int, entry_ids: list[int]) -> None:
        """Reorder playlist entries in a scene by updating their positions"""
        for position, entry_id in enumerate(entry_ids):
            self.connection.execute(
                "UPDATE scene_playlist_entries SET position = ? WHERE id = ? AND scene_id = ?",
                (position, entry_id, scene_id)
            )
        self.connection.commit()

    # Playlist operations
    def add_playlist(self, playlist: Playlist) -> int:
        """Add a new playlist, return its ID"""
        self.connection.execute("UPDATE playlists SET position = position + 1")
        cursor = self.connection.execute(
            "INSERT INTO playlists (name, position) VALUES (?, ?)",
            (playlist.name, 0)
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_playlist(self, playlist_id: int) -> Optional[Playlist]:
        """Get a playlist by ID with all its tracks"""
        cursor = self.connection.execute(
            "SELECT * FROM playlists WHERE id = ?", (playlist_id,)
        )
        row = cursor.fetchone()
        if row:
            playlist = self._row_to_playlist(row)
            playlist.tracks = self.get_playlist_tracks(playlist_id)
            return playlist
        return None

    def get_all_playlists(self) -> list[Playlist]:
        """Get all playlists"""
        cursor = self.connection.execute(
            "SELECT * FROM playlists ORDER BY position, name COLLATE NOCASE"
        )
        return [self._row_to_playlist(row) for row in cursor.fetchall()]

    def search_playlists(self, query: str) -> list[Playlist]:
        """Search playlists by name"""
        cursor = self.connection.execute(
            "SELECT * FROM playlists WHERE name LIKE ? ORDER BY position, name COLLATE NOCASE",
            (f"%{query}%",)
        )
        return [self._row_to_playlist(row) for row in cursor.fetchall()]

    def update_playlist(self, playlist: Playlist) -> None:
        """Update a playlist's name"""
        self.connection.execute(
            "UPDATE playlists SET name = ?, updated_at = datetime('now') WHERE id = ?",
            (playlist.name, playlist.id)
        )
        self.connection.commit()

    def delete_playlist(self, playlist_id: int) -> None:
        """Delete a playlist"""
        self.connection.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        self.connection.commit()

    def reorder_playlists(self, playlist_ids: list[int]) -> None:
        """Reorder playlists by updating their positions"""
        for position, playlist_id in enumerate(playlist_ids):
            self.connection.execute(
                "UPDATE playlists SET position = ? WHERE id = ?",
                (position, playlist_id)
            )
        self.connection.commit()

    def _row_to_playlist(self, row: sqlite3.Row) -> Playlist:
        """Convert a database row to a Playlist object"""
        return Playlist(
            id=row["id"],
            name=row["name"],
            position=row["position"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    # Playlist track operations
    def add_track_to_playlist(
        self,
        playlist_id: int,
        audio_file_id: int,
        position: Optional[int] = None,
    ) -> int:
        """Add an audio file to a playlist, return the playlist_track ID"""
        if position is None:
            cursor = self.connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM playlist_tracks WHERE playlist_id = ?",
                (playlist_id,)
            )
            position = cursor.fetchone()["next_pos"]
        cursor = self.connection.execute(
            "INSERT INTO playlist_tracks (playlist_id, audio_file_id, position) VALUES (?, ?, ?)",
            (playlist_id, audio_file_id, position)
        )
        self.connection.commit()
        return cursor.lastrowid

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

    def remove_track_from_playlist(self, track_id: int) -> None:
        """Remove a track from a playlist"""
        self.connection.execute("DELETE FROM playlist_tracks WHERE id = ?", (track_id,))
        self.connection.commit()

    def reorder_playlist_tracks(self, playlist_id: int, track_ids: list[int]) -> None:
        """Reorder tracks in a playlist by updating their positions"""
        for position, track_id in enumerate(track_ids):
            self.connection.execute(
                "UPDATE playlist_tracks SET position = ? WHERE id = ? AND playlist_id = ?",
                (position, track_id, playlist_id)
            )
        self.connection.commit()
