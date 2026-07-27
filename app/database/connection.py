"""SQLite database connection management"""

import sqlite3
from pathlib import Path

from .. import paths
from ..shared.logging import get_logger
from .models import (
    AudioFile,
    Playlist,
    PlaylistTrack,
    Scene,
    SceneAudioFile,
    ScenePlaylistEntry,
    Soundboard,
    SoundboardButton,
    Tag,
)

_log = get_logger(__name__)

# Every scene has exactly these preset slots; each holds a full copy of the
# per-track/per-entry settings.
PRESET_SLOTS = (1, 2, 3)


class DatabaseConnection:
    """Manages SQLite database connection and operations"""

    def __init__(self, db_path: str | None = None, seed_default_tags: bool = False):
        if db_path is None:
            # Default to user's application support directory
            paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
            db_path = str(paths.DATA_DIR / paths.DB_FILENAME)

        self.db_path = db_path
        self.seed_default_tags = seed_default_tags
        self.connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Establish database connection and initialize schema"""
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Create database tables if they don't exist"""
        # Freshness must be checked before the schema script creates the
        # tables: seeding only ever applies to a brand-new database, never
        # to an existing one whose user may have deleted the defaults.
        is_fresh = not self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tags'"
        ).fetchone()
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path) as f:
            schema = f.read()
        self._conn.executescript(schema)
        if is_fresh and self.seed_default_tags:
            self._seed_default_tags()
        self._ensure_scene_positions()
        self._ensure_playlist_shuffle()
        self._ensure_playlist_track_volume()
        self._ensure_scene_active_preset_slot()
        self._migrate_scene_settings_to_presets()
        self._conn.commit()

    def _seed_default_tags(self) -> None:
        """Populate a brand-new database with the starter tag set"""
        seed_path = Path(__file__).parent / "default_tags.sql"
        with open(seed_path) as f:
            self._conn.executescript(f.read())
        _log.info("seeded_default_tags")

    def _ensure_scene_positions(self) -> None:
        """Ensure scenes have a position column and values"""
        cursor = self._conn.execute("PRAGMA table_info(scenes)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "position" not in columns:
            self._conn.execute(
                "ALTER TABLE scenes ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
            )

        # Initialize positions for existing rows if needed
        rows = self._conn.execute(
            "SELECT id, position FROM scenes ORDER BY title COLLATE NOCASE"
        ).fetchall()
        has_nonzero = any(row["position"] != 0 for row in rows)
        if rows and not has_nonzero:
            for index, row in enumerate(rows):
                self._conn.execute(
                    "UPDATE scenes SET position = ? WHERE id = ?", (index, row["id"])
                )

    def _ensure_scene_active_preset_slot(self) -> None:
        """Ensure scenes track which preset slot is active"""
        cursor = self._conn.execute("PRAGMA table_info(scenes)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "active_preset_slot" not in columns:
            self._conn.execute(
                "ALTER TABLE scenes ADD COLUMN active_preset_slot INTEGER NOT NULL DEFAULT 1"
            )

    def _migrate_scene_settings_to_presets(self) -> None:
        """Move per-item scene settings into the preset tables (one-time).

        Pre-preset databases stored volume/repeat/shuffle/play_mode directly
        on scene_audio_files / scene_playlist_entries. Copy those values into
        all three preset slots, then drop the old columns. Gated on the old
        columns still existing, so fresh and already-migrated databases skip
        it entirely.
        """
        track_columns = {
            row["name"]
            for row in self._conn.execute(
                "PRAGMA table_info(scene_audio_files)"
            ).fetchall()
        }
        if "volume" in track_columns:
            _log.info("migrating_scene_track_settings_to_presets")
            for slot in PRESET_SLOTS:
                self._conn.execute(
                    """
                    INSERT INTO scene_track_presets
                        (scene_audio_file_id, slot, volume, is_repeat, play_mode)
                    SELECT id, ?, volume, is_repeat, play_mode
                    FROM scene_audio_files
                    """,
                    (slot,),
                )
            for column in ("volume", "is_repeat", "play_mode"):
                self._conn.execute(
                    f"ALTER TABLE scene_audio_files DROP COLUMN {column}"
                )

        entry_columns = {
            row["name"]
            for row in self._conn.execute(
                "PRAGMA table_info(scene_playlist_entries)"
            ).fetchall()
        }
        if "volume" in entry_columns:
            _log.info("migrating_scene_playlist_entry_settings_to_presets")
            for slot in PRESET_SLOTS:
                self._conn.execute(
                    """
                    INSERT INTO scene_playlist_entry_presets
                        (scene_playlist_entry_id, slot, volume, is_shuffle,
                         is_repeat, play_mode)
                    SELECT id, ?, volume, is_shuffle, is_repeat, play_mode
                    FROM scene_playlist_entries
                    """,
                    (slot,),
                )
            for column in ("volume", "is_shuffle", "is_repeat", "play_mode"):
                self._conn.execute(
                    f"ALTER TABLE scene_playlist_entries DROP COLUMN {column}"
                )

    def _ensure_playlist_shuffle(self) -> None:
        """Ensure playlists have an is_shuffle column"""
        cursor = self._conn.execute("PRAGMA table_info(playlists)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "is_shuffle" not in columns:
            self._conn.execute(
                "ALTER TABLE playlists ADD COLUMN is_shuffle INTEGER NOT NULL DEFAULT 0"
            )

    def _ensure_playlist_track_volume(self) -> None:
        """Ensure playlist tracks have a per-track volume column"""
        cursor = self._conn.execute("PRAGMA table_info(playlist_tracks)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "volume" not in columns:
            self._conn.execute(
                "ALTER TABLE playlist_tracks ADD COLUMN volume REAL NOT NULL DEFAULT 1.0"
            )

    def close(self) -> None:
        """Close database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None

    def backup_to(self, dest_path: str) -> None:
        """Write a consistent snapshot of the database to ``dest_path``.

        Uses SQLite's online-backup API, so it is safe while this connection
        is live (unlike copying the file). An existing destination file is
        fully replaced.
        """
        dest = sqlite3.connect(dest_path)
        try:
            with dest:
                self._conn.backup(dest)
        finally:
            dest.close()

    @property
    def _conn(self) -> sqlite3.Connection:
        """The live connection; connect() must have been called."""
        assert self.connection is not None, "Database is not connected"
        return self.connection

    @staticmethod
    def _insert_id(cursor: sqlite3.Cursor) -> int:
        """The rowid generated by a just-executed INSERT."""
        row_id = cursor.lastrowid
        assert row_id is not None, "INSERT did not produce a rowid"
        return row_id

    # Audio File operations
    def add_audio_file(self, audio_file: AudioFile) -> int:
        """Add an audio file to the library, return its ID"""
        cursor = self._conn.execute(
            """
            INSERT INTO audio_files
                (file_path, title, artist, duration_seconds, file_size, content_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                audio_file.file_path,
                audio_file.title,
                audio_file.artist,
                audio_file.duration_seconds,
                audio_file.file_size,
                audio_file.content_hash,
            ),
        )
        self._conn.commit()
        return self._insert_id(cursor)

    def bulk_add_audio_files(self, audio_files: list[AudioFile]) -> list[int]:
        """Add multiple audio files in a single transaction, return their IDs"""
        if not audio_files:
            return []
        ids = []
        for audio_file in audio_files:
            cursor = self._conn.execute(
                """
                INSERT INTO audio_files
                    (file_path, title, artist, duration_seconds, file_size, content_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    audio_file.file_path,
                    audio_file.title,
                    audio_file.artist,
                    audio_file.duration_seconds,
                    audio_file.file_size,
                    audio_file.content_hash,
                ),
            )
            ids.append(self._insert_id(cursor))
        self._conn.commit()
        return ids

    def get_audio_file(self, file_id: int) -> AudioFile | None:
        """Get an audio file by ID"""
        cursor = self._conn.execute(
            "SELECT * FROM audio_files WHERE id = ?", (file_id,)
        )
        row = cursor.fetchone()
        if row:
            audio_file = self._row_to_audio_file(row)
            audio_file.tags = self.get_tags_for_audio_file(file_id)
            return audio_file
        return None

    def get_audio_file_by_path(self, file_path: str) -> AudioFile | None:
        """Get an audio file by path"""
        cursor = self._conn.execute(
            "SELECT * FROM audio_files WHERE file_path = ?", (file_path,)
        )
        row = cursor.fetchone()
        if row:
            audio_file = self._row_to_audio_file(row)
            audio_file.tags = self.get_tags_for_audio_file(row["id"])
            return audio_file
        return None

    def get_all_audio_file_paths(self) -> set[str]:
        """Get the set of all file paths currently in the library"""
        cursor = self._conn.execute("SELECT file_path FROM audio_files")
        return {row["file_path"] for row in cursor.fetchall()}

    def get_all_audio_files(self) -> list[AudioFile]:
        """Get all audio files in the library"""
        cursor = self._conn.execute(
            "SELECT * FROM audio_files ORDER BY title COLLATE NOCASE"
        )
        files = [self._row_to_audio_file(row) for row in cursor.fetchall()]
        self._attach_tags(files)
        return files

    def search_audio_files(
        self,
        query: str,
        tag_ids: list[int] | None = None,
        excluded_tag_ids: list[int] | None = None,
    ) -> list[AudioFile]:
        """Search audio files by title/artist, filtered by tags.

        Included tags are ANDed: a file must carry every one of them.
        Excluded tags drop any file carrying one of them. Tag id -1 is the
        "No Tag" pseudo-tag: included = only untagged files, excluded = only
        files with at least one tag.
        """
        query_pattern = f"%{query}%"
        conditions = ["(af.title LIKE ? OR af.artist LIKE ?)"]
        params: list[object] = [query_pattern, query_pattern]

        include_ids = [t for t in (tag_ids or []) if t != -1]
        include_no_tag = -1 in (tag_ids or [])
        exclude_ids = [t for t in (excluded_tag_ids or []) if t != -1]
        exclude_no_tag = -1 in (excluded_tag_ids or [])

        if include_ids:
            placeholders = ",".join("?" * len(include_ids))
            conditions.append(f"""af.id IN (
                SELECT audio_file_id FROM audio_file_tags
                WHERE tag_id IN ({placeholders})
                GROUP BY audio_file_id
                HAVING COUNT(DISTINCT tag_id) = ?
            )""")
            params.extend(include_ids)
            params.append(len(include_ids))
        if include_no_tag:
            conditions.append(
                "af.id NOT IN (SELECT audio_file_id FROM audio_file_tags)"
            )
        if exclude_ids:
            placeholders = ",".join("?" * len(exclude_ids))
            conditions.append(
                "af.id NOT IN (SELECT audio_file_id FROM audio_file_tags"
                f" WHERE tag_id IN ({placeholders}))"
            )
            params.extend(exclude_ids)
        if exclude_no_tag:
            conditions.append("af.id IN (SELECT audio_file_id FROM audio_file_tags)")

        sql = f"""
            SELECT af.* FROM audio_files af
            WHERE {" AND ".join(conditions)}
            ORDER BY af.title COLLATE NOCASE
        """
        cursor = self._conn.execute(sql, params)
        files = [self._row_to_audio_file(row) for row in cursor.fetchall()]
        self._attach_tags(files)
        return files

    def update_audio_file(self, audio_file: AudioFile) -> None:
        """Update an audio file's metadata"""
        self._conn.execute(
            """
            UPDATE audio_files
            SET title = ?, artist = ?, duration_seconds = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                audio_file.title,
                audio_file.artist,
                audio_file.duration_seconds,
                audio_file.id,
            ),
        )
        self._conn.commit()

    def relink_audio_file(
        self,
        file_id: int,
        new_path: str,
        file_size: int | None,
        content_hash: str | None,
    ) -> None:
        """Point an entry at a new path, refreshing its fingerprint.

        Used by the repair-library flow. References (scenes, playlists,
        soundboards) join on the id, so relinking heals them all.
        """
        self._conn.execute(
            """
            UPDATE audio_files
            SET file_path = ?, file_size = ?, content_hash = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (new_path, file_size, content_hash, file_id),
        )
        self._conn.commit()

    def delete_audio_file(self, file_id: int) -> None:
        """Delete an audio file from the library"""
        self._conn.execute("DELETE FROM audio_files WHERE id = ?", (file_id,))
        self._conn.commit()

    def _row_to_audio_file(self, row: sqlite3.Row) -> AudioFile:
        """Convert a database row to an AudioFile object"""
        return AudioFile(
            id=row["id"],
            file_path=row["file_path"],
            title=row["title"],
            artist=row["artist"],
            duration_seconds=row["duration_seconds"],
            file_size=row["file_size"],
            content_hash=row["content_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # Tag operations
    def add_tag(self, tag: Tag) -> int:
        """Add a new tag, return its ID"""
        cursor = self._conn.execute(
            "INSERT INTO tags (name, color) VALUES (?, ?)", (tag.name, tag.color)
        )
        self._conn.commit()
        return self._insert_id(cursor)

    def get_all_tags(self) -> list[Tag]:
        """Get all tags"""
        cursor = self._conn.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE")
        return [self._row_to_tag(row) for row in cursor.fetchall()]

    def get_tag_by_name(self, name: str) -> Tag | None:
        """Get a tag by name (case-insensitive)"""
        cursor = self._conn.execute(
            "SELECT * FROM tags WHERE name = ? COLLATE NOCASE", (name,)
        )
        row = cursor.fetchone()
        return self._row_to_tag(row) if row else None

    def update_tag(self, tag: Tag) -> None:
        """Update a tag"""
        self._conn.execute(
            "UPDATE tags SET name = ?, color = ? WHERE id = ?",
            (tag.name, tag.color, tag.id),
        )
        self._conn.commit()

    def delete_tag(self, tag_id: int) -> None:
        """Delete a tag"""
        self._conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        self._conn.commit()

    def _row_to_tag(self, row: sqlite3.Row) -> Tag:
        """Convert a database row to a Tag object"""
        return Tag(
            id=row["id"],
            name=row["name"],
            color=row["color"],
            created_at=row["created_at"],
        )

    # Audio file <-> Tag associations
    def add_tag_to_audio_file(self, audio_file_id: int, tag_id: int) -> None:
        """Associate a tag with an audio file"""
        self._conn.execute(
            "INSERT OR IGNORE INTO audio_file_tags (audio_file_id, tag_id) VALUES (?, ?)",
            (audio_file_id, tag_id),
        )
        self._conn.commit()

    def bulk_add_tags_to_audio_files(
        self, audio_file_ids: list[int], tag_ids: list[int]
    ) -> None:
        """Add multiple tags to multiple audio files in a single transaction"""
        for file_id in audio_file_ids:
            for tag_id in tag_ids:
                self._conn.execute(
                    "INSERT OR IGNORE INTO audio_file_tags (audio_file_id, tag_id) VALUES (?, ?)",
                    (file_id, tag_id),
                )
        self._conn.commit()

    def bulk_update_artist(self, audio_file_ids: list[int], artist: str | None) -> None:
        """Update artist for multiple audio files in a single transaction"""
        if not audio_file_ids:
            return
        placeholders = ",".join("?" * len(audio_file_ids))
        self._conn.execute(
            f"""
            UPDATE audio_files
            SET artist = ?, updated_at = datetime('now')
            WHERE id IN ({placeholders})
            """,
            [artist, *audio_file_ids],
        )
        self._conn.commit()

    def bulk_remove_tags_from_audio_files(
        self, audio_file_ids: list[int], tag_ids: list[int]
    ) -> None:
        """Remove specified tags from multiple audio files in a single transaction"""
        if not audio_file_ids or not tag_ids:
            return
        file_placeholders = ",".join("?" * len(audio_file_ids))
        tag_placeholders = ",".join("?" * len(tag_ids))
        self._conn.execute(
            f"""
            DELETE FROM audio_file_tags
            WHERE audio_file_id IN ({file_placeholders})
            AND tag_id IN ({tag_placeholders})
            """,
            audio_file_ids + tag_ids,
        )
        self._conn.commit()

    def remove_tag_from_audio_file(self, audio_file_id: int, tag_id: int) -> None:
        """Remove a tag association from an audio file"""
        self._conn.execute(
            "DELETE FROM audio_file_tags WHERE audio_file_id = ? AND tag_id = ?",
            (audio_file_id, tag_id),
        )
        self._conn.commit()

    def get_tags_for_audio_file(self, audio_file_id: int) -> list[Tag]:
        """Get all tags for an audio file"""
        cursor = self._conn.execute(
            """
            SELECT t.* FROM tags t
            JOIN audio_file_tags aft ON t.id = aft.tag_id
            WHERE aft.audio_file_id = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (audio_file_id,),
        )
        return [self._row_to_tag(row) for row in cursor.fetchall()]

    def _attach_tags(self, files: list[AudioFile]) -> None:
        """Populate .tags for a batch of library files with one query."""
        tags_by_file = self._batch_load_tags([f.id for f in files if f.id is not None])
        for audio_file in files:
            if audio_file.id is not None:
                audio_file.tags = tags_by_file.get(audio_file.id, [])

    def _batch_load_tags(self, audio_file_ids: list[int]) -> dict[int, list[Tag]]:
        """Load tags for multiple audio files in a single query.

        Returns a dict mapping audio_file_id -> list of Tags.
        """
        if not audio_file_ids:
            return {}

        placeholders = ",".join("?" * len(audio_file_ids))
        cursor = self._conn.execute(
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
        cursor = self._conn.execute(
            """
            SELECT af.* FROM audio_files af
            JOIN audio_file_tags aft ON af.id = aft.audio_file_id
            WHERE aft.tag_id = ?
            ORDER BY af.title COLLATE NOCASE
            """,
            (tag_id,),
        )
        files = [self._row_to_audio_file(row) for row in cursor.fetchall()]
        self._attach_tags(files)
        return files

    # Scene operations
    def add_scene(self, scene: Scene) -> int:
        """Add a new scene, return its ID"""
        self._conn.execute("UPDATE scenes SET position = position + 1")
        next_position = 0
        cursor = self._conn.execute(
            "INSERT INTO scenes (title, position) VALUES (?, ?)",
            (scene.title, next_position),
        )
        self._conn.commit()
        return self._insert_id(cursor)

    def get_scene(self, scene_id: int) -> Scene | None:
        """Get a scene by ID with all its tracks and playlist entries"""
        cursor = self._conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,))
        row = cursor.fetchone()
        if row:
            scene = self._row_to_scene(row)
            scene.tracks = self.get_scene_tracks(scene_id)
            scene.playlist_entries = self.get_scene_playlist_entries(scene_id)
            scene.preset_names = self.get_scene_preset_names(scene_id)
            return scene
        return None

    def get_all_scenes(self) -> list[Scene]:
        """Get all scenes"""
        cursor = self._conn.execute(
            "SELECT * FROM scenes ORDER BY position, title COLLATE NOCASE"
        )
        return [self._row_to_scene(row) for row in cursor.fetchall()]

    def search_scenes(self, query: str) -> list[Scene]:
        """Search scenes by title"""
        cursor = self._conn.execute(
            "SELECT * FROM scenes WHERE title LIKE ? ORDER BY position, title COLLATE NOCASE",
            (f"%{query}%",),
        )
        return [self._row_to_scene(row) for row in cursor.fetchall()]

    def update_scene(self, scene: Scene) -> None:
        """Update a scene's title"""
        self._conn.execute(
            "UPDATE scenes SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (scene.title, scene.id),
        )
        self._conn.commit()

    def delete_scene(self, scene_id: int) -> None:
        """Delete a scene"""
        self._conn.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))
        self._conn.commit()

    def _row_to_scene(self, row: sqlite3.Row) -> Scene:
        """Convert a database row to a Scene object"""
        return Scene(
            id=row["id"],
            title=row["title"],
            position=row["position"],
            active_preset_slot=row["active_preset_slot"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def reorder_scenes(self, scene_ids: list[int]) -> None:
        """Reorder scenes by updating their positions"""
        for position, scene_id in enumerate(scene_ids):
            self._conn.execute(
                "UPDATE scenes SET position = ? WHERE id = ?", (position, scene_id)
            )
        self._conn.commit()

    def duplicate_scene(self, scene_id: int, new_title: str) -> Scene | None:
        """Deep-copy a scene: tracks, playlist entries, every preset slot's
        settings, custom preset names, and the active slot."""
        source = self._conn.execute(
            "SELECT * FROM scenes WHERE id = ?", (scene_id,)
        ).fetchone()
        if source is None:
            return None

        self._conn.execute("UPDATE scenes SET position = position + 1")
        cursor = self._conn.execute(
            "INSERT INTO scenes (title, position, active_preset_slot) VALUES (?, 0, ?)",
            (new_title, source["active_preset_slot"]),
        )
        new_scene_id = self._insert_id(cursor)

        self._conn.execute(
            """
            INSERT INTO scene_presets (scene_id, slot, name)
            SELECT ?, slot, name FROM scene_presets WHERE scene_id = ?
            """,
            (new_scene_id, scene_id),
        )

        tracks = self._conn.execute(
            "SELECT id, audio_file_id, position FROM scene_audio_files WHERE scene_id = ?",
            (scene_id,),
        ).fetchall()
        for row in tracks:
            cursor = self._conn.execute(
                "INSERT INTO scene_audio_files (scene_id, audio_file_id, position) VALUES (?, ?, ?)",
                (new_scene_id, row["audio_file_id"], row["position"]),
            )
            new_track_id = self._insert_id(cursor)
            self._conn.execute(
                """
                INSERT INTO scene_track_presets
                    (scene_audio_file_id, slot, volume, is_repeat, play_mode)
                SELECT ?, slot, volume, is_repeat, play_mode
                FROM scene_track_presets WHERE scene_audio_file_id = ?
                """,
                (new_track_id, row["id"]),
            )

        entries = self._conn.execute(
            "SELECT id, playlist_id, position FROM scene_playlist_entries WHERE scene_id = ?",
            (scene_id,),
        ).fetchall()
        for row in entries:
            cursor = self._conn.execute(
                "INSERT INTO scene_playlist_entries (scene_id, playlist_id, position) VALUES (?, ?, ?)",
                (new_scene_id, row["playlist_id"], row["position"]),
            )
            new_entry_id = self._insert_id(cursor)
            self._conn.execute(
                """
                INSERT INTO scene_playlist_entry_presets
                    (scene_playlist_entry_id, slot, volume, is_shuffle,
                     is_repeat, play_mode)
                SELECT ?, slot, volume, is_shuffle, is_repeat, play_mode
                FROM scene_playlist_entry_presets WHERE scene_playlist_entry_id = ?
                """,
                (new_entry_id, row["id"]),
            )

        self._conn.commit()
        _log.info(
            "scene_duplicated", source_scene_id=scene_id, new_scene_id=new_scene_id
        )
        return self.get_scene(new_scene_id)

    # Scene preset operations
    def _get_active_preset_slot(self, scene_id: int) -> int:
        """The scene's active preset slot (1 if the scene is unknown)"""
        row = self._conn.execute(
            "SELECT active_preset_slot FROM scenes WHERE id = ?", (scene_id,)
        ).fetchone()
        return row["active_preset_slot"] if row else 1

    def _get_track_active_slot(self, track_id: int) -> int:
        """The active preset slot of the scene owning a scene track"""
        row = self._conn.execute(
            """
            SELECT s.active_preset_slot AS slot
            FROM scenes s
            JOIN scene_audio_files saf ON saf.scene_id = s.id
            WHERE saf.id = ?
            """,
            (track_id,),
        ).fetchone()
        return row["slot"] if row else 1

    def _get_entry_active_slot(self, entry_id: int) -> int:
        """The active preset slot of the scene owning a scene playlist entry"""
        row = self._conn.execute(
            """
            SELECT s.active_preset_slot AS slot
            FROM scenes s
            JOIN scene_playlist_entries spe ON spe.scene_id = s.id
            WHERE spe.id = ?
            """,
            (entry_id,),
        ).fetchone()
        return row["slot"] if row else 1

    def set_active_preset_slot(self, scene_id: int, slot: int) -> None:
        """Persist which preset slot is active for a scene"""
        self._conn.execute(
            "UPDATE scenes SET active_preset_slot = ?, updated_at = datetime('now') WHERE id = ?",
            (slot, scene_id),
        )
        self._conn.commit()

    def get_scene_preset_names(self, scene_id: int) -> dict[int, str]:
        """Custom preset names by slot (slots never renamed are absent)"""
        cursor = self._conn.execute(
            "SELECT slot, name FROM scene_presets WHERE scene_id = ?", (scene_id,)
        )
        return {row["slot"]: row["name"] for row in cursor.fetchall()}

    def rename_scene_preset(self, scene_id: int, slot: int, name: str) -> None:
        """Set a custom name for one of a scene's preset slots"""
        self._conn.execute(
            """
            INSERT INTO scene_presets (scene_id, slot, name)
            VALUES (?, ?, ?)
            ON CONFLICT (scene_id, slot) DO UPDATE SET name = excluded.name
            """,
            (scene_id, slot, name),
        )
        self._conn.commit()

    # Scene track operations
    def add_track_to_scene(
        self,
        scene_id: int,
        audio_file_id: int,
        position: int = 0,
        play_mode: bool = True,
    ) -> int:
        """Add an audio file to a scene, return the scene_audio_file ID.

        Seeds identical settings rows for every preset slot so switching a
        never-customized preset doesn't change the new track.
        """
        cursor = self._conn.execute(
            """
            INSERT INTO scene_audio_files (scene_id, audio_file_id, position)
            VALUES (?, ?, ?)
            """,
            (scene_id, audio_file_id, position),
        )
        track_id = self._insert_id(cursor)
        for slot in PRESET_SLOTS:
            self._conn.execute(
                """
                INSERT INTO scene_track_presets (scene_audio_file_id, slot, play_mode)
                VALUES (?, ?, ?)
                """,
                (track_id, slot, int(play_mode)),
            )
        self._conn.commit()
        return track_id

    def get_scene_tracks(
        self, scene_id: int, slot: int | None = None
    ) -> list[SceneAudioFile]:
        """Get all tracks in a scene with their audio file data.

        Settings come from the given preset slot (default: the scene's
        active one).
        """
        if slot is None:
            slot = self._get_active_preset_slot(scene_id)
        cursor = self._conn.execute(
            """
            SELECT saf.id, saf.scene_id, saf.audio_file_id, saf.position,
                   stp.volume, stp.is_repeat, stp.play_mode,
                   af.file_path, af.title, af.artist, af.duration_seconds
            FROM scene_audio_files saf
            JOIN audio_files af ON saf.audio_file_id = af.id
            JOIN scene_track_presets stp
                 ON stp.scene_audio_file_id = saf.id AND stp.slot = ?
            WHERE saf.scene_id = ?
            ORDER BY saf.position
            """,
            (slot, scene_id),
        )
        tracks = []
        for row in cursor.fetchall():
            audio_file = AudioFile(
                id=row["audio_file_id"],
                file_path=row["file_path"],
                title=row["title"],
                artist=row["artist"],
                duration_seconds=row["duration_seconds"],
            )
            track = SceneAudioFile(
                id=row["id"],
                scene_id=row["scene_id"],
                audio_file_id=row["audio_file_id"],
                position=row["position"],
                volume=row["volume"],
                is_repeat=bool(row["is_repeat"]),
                play_mode=bool(row["play_mode"]),
                audio_file=audio_file,
            )
            tracks.append(track)
        return tracks

    def update_track_settings(self, track: SceneAudioFile) -> None:
        """Update a track's position plus its settings in the active preset"""
        self._conn.execute(
            "UPDATE scene_audio_files SET position = ? WHERE id = ?",
            (track.position, track.id),
        )
        assert track.id is not None
        self._conn.execute(
            """
            UPDATE scene_track_presets
            SET volume = ?, is_repeat = ?, play_mode = ?
            WHERE scene_audio_file_id = ? AND slot = ?
            """,
            (
                track.volume,
                int(track.is_repeat),
                int(track.play_mode),
                track.id,
                self._get_track_active_slot(track.id),
            ),
        )
        self._conn.commit()

    def update_scene_track_setting(
        self,
        track_id: int,
        *,
        volume: float | None = None,
        is_repeat: bool | None = None,
        play_mode: bool | None = None,
        slot: int | None = None,
    ) -> None:
        """Update individual settings for one scene track, by id.

        Targeted single-row UPDATE that only writes the fields passed (a value
        of ``None`` means "leave unchanged") to the given preset slot
        (default: the owning scene's active one). Column names are hard-coded
        literals; all values are parameterized.
        """
        assignments = []
        params: list[object] = []
        if volume is not None:
            assignments.append("volume = ?")
            params.append(volume)
        if is_repeat is not None:
            assignments.append("is_repeat = ?")
            params.append(int(is_repeat))
        if play_mode is not None:
            assignments.append("play_mode = ?")
            params.append(int(play_mode))
        if not assignments:
            return  # nothing to update

        if slot is None:
            slot = self._get_track_active_slot(track_id)
        params.extend([track_id, slot])
        self._conn.execute(
            f"UPDATE scene_track_presets SET {', '.join(assignments)} "
            "WHERE scene_audio_file_id = ? AND slot = ?",
            params,
        )
        self._conn.commit()

    def remove_track_from_scene(self, track_id: int) -> None:
        """Remove a track from a scene"""
        self._conn.execute("DELETE FROM scene_audio_files WHERE id = ?", (track_id,))
        self._conn.commit()

    def reorder_tracks(self, scene_id: int, track_ids: list[int]) -> None:
        """Reorder tracks in a scene by updating their positions"""
        for position, track_id in enumerate(track_ids):
            self._conn.execute(
                "UPDATE scene_audio_files SET position = ? WHERE id = ? AND scene_id = ?",
                (position, track_id, scene_id),
            )
        self._conn.commit()

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
        """Add a playlist entry to a scene, return the entry ID.

        Seeds identical settings rows for every preset slot so switching a
        never-customized preset doesn't change the new entry.
        """
        cursor = self._conn.execute(
            """
            INSERT INTO scene_playlist_entries (scene_id, playlist_id, position)
            VALUES (?, ?, ?)
            """,
            (scene_id, playlist_id, position),
        )
        entry_id = self._insert_id(cursor)
        for slot in PRESET_SLOTS:
            self._conn.execute(
                """
                INSERT INTO scene_playlist_entry_presets
                    (scene_playlist_entry_id, slot, volume, is_shuffle,
                     is_repeat, play_mode)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    slot,
                    volume,
                    int(is_shuffle),
                    int(is_repeat),
                    int(play_mode),
                ),
            )
        self._conn.commit()
        return entry_id

    def get_scene_playlist_entries(
        self, scene_id: int, slot: int | None = None
    ) -> list[ScenePlaylistEntry]:
        """Get all playlist entries in a scene with their playlist data.

        Settings come from the given preset slot (default: the scene's
        active one).
        """
        if slot is None:
            slot = self._get_active_preset_slot(scene_id)
        cursor = self._conn.execute(
            """
            SELECT spe.id, spe.scene_id, spe.playlist_id, spe.position,
                   spep.volume, spep.is_shuffle, spep.is_repeat, spep.play_mode,
                   p.name, p.position AS playlist_position,
                   p.created_at AS playlist_created_at, p.updated_at AS playlist_updated_at
            FROM scene_playlist_entries spe
            JOIN playlists p ON spe.playlist_id = p.id
            JOIN scene_playlist_entry_presets spep
                 ON spep.scene_playlist_entry_id = spe.id AND spep.slot = ?
            WHERE spe.scene_id = ?
            ORDER BY spe.position
            """,
            (slot, scene_id),
        )
        rows = cursor.fetchall()
        playlist_ids = [row["playlist_id"] for row in rows]
        tracks_by_playlist = self._batch_load_playlist_tracks(playlist_ids)

        entries = []
        for row in rows:
            playlist = Playlist(
                id=row["playlist_id"],
                name=row["name"],
                position=row["playlist_position"],
                created_at=row["playlist_created_at"],
                updated_at=row["playlist_updated_at"],
            )
            playlist.tracks = tracks_by_playlist.get(row["playlist_id"], [])
            entry = ScenePlaylistEntry(
                id=row["id"],
                scene_id=row["scene_id"],
                playlist_id=row["playlist_id"],
                position=row["position"],
                volume=row["volume"],
                is_shuffle=bool(row["is_shuffle"]),
                is_repeat=bool(row["is_repeat"]),
                play_mode=bool(row["play_mode"]),
                playlist=playlist,
            )
            entries.append(entry)
        return entries

    def update_scene_playlist_entry(self, entry: ScenePlaylistEntry) -> None:
        """Update an entry's position plus its settings in the active preset"""
        self._conn.execute(
            "UPDATE scene_playlist_entries SET position = ? WHERE id = ?",
            (entry.position, entry.id),
        )
        assert entry.id is not None
        self._conn.execute(
            """
            UPDATE scene_playlist_entry_presets
            SET volume = ?, is_shuffle = ?, is_repeat = ?, play_mode = ?
            WHERE scene_playlist_entry_id = ? AND slot = ?
            """,
            (
                entry.volume,
                int(entry.is_shuffle),
                int(entry.is_repeat),
                int(entry.play_mode),
                entry.id,
                self._get_entry_active_slot(entry.id),
            ),
        )
        self._conn.commit()

    def update_scene_playlist_entry_setting(
        self,
        entry_id: int,
        *,
        volume: float | None = None,
        is_shuffle: bool | None = None,
        is_repeat: bool | None = None,
        play_mode: bool | None = None,
        slot: int | None = None,
    ) -> None:
        """Update individual settings for one scene playlist entry, by id.

        Targeted single-row UPDATE that only writes the fields passed (a value
        of ``None`` means "leave unchanged") to the given preset slot
        (default: the owning scene's active one). Column names are hard-coded
        literals; all values are parameterized.
        """
        assignments = []
        params: list[object] = []
        if volume is not None:
            assignments.append("volume = ?")
            params.append(volume)
        if is_shuffle is not None:
            assignments.append("is_shuffle = ?")
            params.append(int(is_shuffle))
        if is_repeat is not None:
            assignments.append("is_repeat = ?")
            params.append(int(is_repeat))
        if play_mode is not None:
            assignments.append("play_mode = ?")
            params.append(int(play_mode))
        if not assignments:
            return  # nothing to update

        if slot is None:
            slot = self._get_entry_active_slot(entry_id)
        params.extend([entry_id, slot])
        self._conn.execute(
            f"UPDATE scene_playlist_entry_presets SET {', '.join(assignments)} "
            "WHERE scene_playlist_entry_id = ? AND slot = ?",
            params,
        )
        self._conn.commit()

    def remove_playlist_from_scene(self, entry_id: int) -> None:
        """Remove a playlist entry from a scene"""
        self._conn.execute(
            "DELETE FROM scene_playlist_entries WHERE id = ?", (entry_id,)
        )
        self._conn.commit()

    def reorder_scene_playlist_entries(
        self, scene_id: int, entry_ids: list[int]
    ) -> None:
        """Reorder playlist entries in a scene by updating their positions"""
        for position, entry_id in enumerate(entry_ids):
            self._conn.execute(
                "UPDATE scene_playlist_entries SET position = ? WHERE id = ? AND scene_id = ?",
                (position, entry_id, scene_id),
            )
        self._conn.commit()

    # Playlist operations
    def add_playlist(self, playlist: Playlist) -> int:
        """Add a new playlist, return its ID"""
        self._conn.execute("UPDATE playlists SET position = position + 1")
        cursor = self._conn.execute(
            "INSERT INTO playlists (name, position) VALUES (?, ?)", (playlist.name, 0)
        )
        self._conn.commit()
        return self._insert_id(cursor)

    def get_playlist(self, playlist_id: int) -> Playlist | None:
        """Get a playlist by ID with all its tracks"""
        cursor = self._conn.execute(
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
        cursor = self._conn.execute(
            "SELECT * FROM playlists ORDER BY position, name COLLATE NOCASE"
        )
        return [self._row_to_playlist(row) for row in cursor.fetchall()]

    def search_playlists(self, query: str) -> list[Playlist]:
        """Search playlists by name"""
        cursor = self._conn.execute(
            "SELECT * FROM playlists WHERE name LIKE ? ORDER BY position, name COLLATE NOCASE",
            (f"%{query}%",),
        )
        return [self._row_to_playlist(row) for row in cursor.fetchall()]

    def update_playlist(self, playlist: Playlist) -> None:
        """Update a playlist's name"""
        self._conn.execute(
            "UPDATE playlists SET name = ?, updated_at = datetime('now') WHERE id = ?",
            (playlist.name, playlist.id),
        )
        self._conn.commit()

    def update_playlist_shuffle(self, playlist_id: int, is_shuffle: bool) -> None:
        """Update a playlist's persisted shuffle mode"""
        self._conn.execute(
            "UPDATE playlists SET is_shuffle = ?, updated_at = datetime('now') WHERE id = ?",
            (int(is_shuffle), playlist_id),
        )
        self._conn.commit()

    def delete_playlist(self, playlist_id: int) -> None:
        """Delete a playlist"""
        self._conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        self._conn.commit()

    def reorder_playlists(self, playlist_ids: list[int]) -> None:
        """Reorder playlists by updating their positions"""
        for position, playlist_id in enumerate(playlist_ids):
            self._conn.execute(
                "UPDATE playlists SET position = ? WHERE id = ?",
                (position, playlist_id),
            )
        self._conn.commit()

    def _row_to_playlist(self, row: sqlite3.Row) -> Playlist:
        """Convert a database row to a Playlist object"""
        return Playlist(
            id=row["id"],
            name=row["name"],
            position=row["position"],
            is_shuffle=bool(row["is_shuffle"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # Playlist track operations
    def add_track_to_playlist(
        self,
        playlist_id: int,
        audio_file_id: int,
        position: int | None = None,
        volume: float = 1.0,
    ) -> int:
        """Add an audio file to a playlist, return the playlist_track ID"""
        if position is None:
            cursor = self._conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM playlist_tracks WHERE playlist_id = ?",
                (playlist_id,),
            )
            position = cursor.fetchone()["next_pos"]
        cursor = self._conn.execute(
            "INSERT INTO playlist_tracks (playlist_id, audio_file_id, position, volume)"
            " VALUES (?, ?, ?, ?)",
            (playlist_id, audio_file_id, position, volume),
        )
        self._conn.commit()
        return self._insert_id(cursor)

    def update_playlist_track_volume(self, track_id: int, volume: float) -> None:
        """Update a playlist track's stored volume (0.0-1.0)"""
        self._conn.execute(
            "UPDATE playlist_tracks SET volume = ? WHERE id = ?",
            (volume, track_id),
        )
        self._conn.commit()

    def get_playlist_tracks(self, playlist_id: int) -> list[PlaylistTrack]:
        """Get all tracks in a playlist with their audio file data and tags"""
        cursor = self._conn.execute(
            """
            SELECT pt.*, af.file_path, af.title, af.artist, af.duration_seconds
            FROM playlist_tracks pt
            JOIN audio_files af ON pt.audio_file_id = af.id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
            """,
            (playlist_id,),
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
                duration_seconds=row["duration_seconds"],
            )
            audio_file.tags = tags_by_file.get(row["audio_file_id"], [])
            track = PlaylistTrack(
                id=row["id"],
                playlist_id=row["playlist_id"],
                audio_file_id=row["audio_file_id"],
                position=row["position"],
                volume=row["volume"],
                audio_file=audio_file,
            )
            tracks.append(track)
        return tracks

    def _batch_load_playlist_tracks(
        self, playlist_ids: list[int]
    ) -> dict[int, list[PlaylistTrack]]:
        """Load tracks for multiple playlists in a single query.

        Returns a dict mapping playlist_id -> list of PlaylistTracks
        (ordered by position).
        """
        if not playlist_ids:
            return {}

        placeholders = ",".join("?" * len(playlist_ids))
        cursor = self._conn.execute(
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
        audio_file_ids = list(dict.fromkeys(row["audio_file_id"] for row in rows))
        tags_by_file = self._batch_load_tags(audio_file_ids)

        tracks_by_playlist: dict[int, list[PlaylistTrack]] = {
            pid: [] for pid in playlist_ids
        }
        for row in rows:
            audio_file = AudioFile(
                id=row["audio_file_id"],
                file_path=row["file_path"],
                title=row["title"],
                artist=row["artist"],
                duration_seconds=row["duration_seconds"],
            )
            audio_file.tags = tags_by_file.get(row["audio_file_id"], [])
            track = PlaylistTrack(
                id=row["id"],
                playlist_id=row["playlist_id"],
                audio_file_id=row["audio_file_id"],
                position=row["position"],
                volume=row["volume"],
                audio_file=audio_file,
            )
            tracks_by_playlist[row["playlist_id"]].append(track)
        return tracks_by_playlist

    def remove_track_from_playlist(self, track_id: int) -> None:
        """Remove a track from a playlist"""
        self._conn.execute("DELETE FROM playlist_tracks WHERE id = ?", (track_id,))
        self._conn.commit()

    def reorder_playlist_tracks(self, playlist_id: int, track_ids: list[int]) -> None:
        """Reorder tracks in a playlist by updating their positions"""
        for position, track_id in enumerate(track_ids):
            self._conn.execute(
                "UPDATE playlist_tracks SET position = ? WHERE id = ? AND playlist_id = ?",
                (position, track_id, playlist_id),
            )
        self._conn.commit()

    # Soundboard operations
    def add_soundboard(self, soundboard: Soundboard) -> int:
        """Add a new soundboard, return its ID"""
        cursor = self._conn.execute(
            "INSERT INTO soundboards (name) VALUES (?)", (soundboard.name,)
        )
        self._conn.commit()
        return self._insert_id(cursor)

    def get_soundboard(self, soundboard_id: int) -> Soundboard | None:
        """Get a soundboard by ID with all its buttons"""
        cursor = self._conn.execute(
            "SELECT * FROM soundboards WHERE id = ?", (soundboard_id,)
        )
        row = cursor.fetchone()
        if row:
            soundboard = self._row_to_soundboard(row)
            soundboard.buttons = self.get_soundboard_buttons(soundboard_id)
            return soundboard
        return None

    def get_all_soundboards(self) -> list[Soundboard]:
        """Get all soundboards, alphabetically (no manual board ordering)"""
        cursor = self._conn.execute(
            "SELECT * FROM soundboards ORDER BY name COLLATE NOCASE"
        )
        return [self._row_to_soundboard(row) for row in cursor.fetchall()]

    def update_soundboard(self, soundboard: Soundboard) -> None:
        """Update a soundboard's name"""
        self._conn.execute(
            "UPDATE soundboards SET name = ?, updated_at = datetime('now') WHERE id = ?",
            (soundboard.name, soundboard.id),
        )
        self._conn.commit()

    def delete_soundboard(self, soundboard_id: int) -> None:
        """Delete a soundboard"""
        self._conn.execute("DELETE FROM soundboards WHERE id = ?", (soundboard_id,))
        self._conn.commit()

    def _row_to_soundboard(self, row: sqlite3.Row) -> Soundboard:
        """Convert a database row to a Soundboard object"""
        return Soundboard(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # Soundboard button operations
    def add_button_to_soundboard(
        self,
        soundboard_id: int,
        audio_file_id: int,
        position: int | None = None,
        volume: float = 1.0,
    ) -> int:
        """Add an audio file button to a soundboard, return the button ID"""
        if position is None:
            cursor = self._conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM soundboard_buttons WHERE soundboard_id = ?",
                (soundboard_id,),
            )
            position = cursor.fetchone()["next_pos"]
        cursor = self._conn.execute(
            "INSERT INTO soundboard_buttons (soundboard_id, audio_file_id, position, volume)"
            " VALUES (?, ?, ?, ?)",
            (soundboard_id, audio_file_id, position, volume),
        )
        self._conn.commit()
        return self._insert_id(cursor)

    def update_soundboard_button_volume(self, button_id: int, volume: float) -> None:
        """Update a soundboard button's stored volume (0.0-1.0)"""
        self._conn.execute(
            "UPDATE soundboard_buttons SET volume = ? WHERE id = ?",
            (volume, button_id),
        )
        self._conn.commit()

    def get_soundboard_buttons(self, soundboard_id: int) -> list[SoundboardButton]:
        """Get all buttons on a soundboard with their audio file data and tags"""
        cursor = self._conn.execute(
            """
            SELECT sb.*, af.file_path, af.title, af.artist, af.duration_seconds
            FROM soundboard_buttons sb
            JOIN audio_files af ON sb.audio_file_id = af.id
            WHERE sb.soundboard_id = ?
            ORDER BY sb.position
            """,
            (soundboard_id,),
        )
        rows = cursor.fetchall()
        audio_file_ids = [row["audio_file_id"] for row in rows]
        tags_by_file = self._batch_load_tags(audio_file_ids)

        buttons = []
        for row in rows:
            audio_file = AudioFile(
                id=row["audio_file_id"],
                file_path=row["file_path"],
                title=row["title"],
                artist=row["artist"],
                duration_seconds=row["duration_seconds"],
            )
            audio_file.tags = tags_by_file.get(row["audio_file_id"], [])
            button = SoundboardButton(
                id=row["id"],
                soundboard_id=row["soundboard_id"],
                audio_file_id=row["audio_file_id"],
                position=row["position"],
                volume=row["volume"],
                audio_file=audio_file,
            )
            buttons.append(button)
        return buttons

    def get_soundboard_button(self, button_id: int) -> SoundboardButton | None:
        """Get a single soundboard button with its audio file data and tags"""
        cursor = self._conn.execute(
            """
            SELECT sb.*, af.file_path, af.title, af.artist, af.duration_seconds
            FROM soundboard_buttons sb
            JOIN audio_files af ON sb.audio_file_id = af.id
            WHERE sb.id = ?
            """,
            (button_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        audio_file = AudioFile(
            id=row["audio_file_id"],
            file_path=row["file_path"],
            title=row["title"],
            artist=row["artist"],
            duration_seconds=row["duration_seconds"],
        )
        audio_file.tags = self._batch_load_tags([row["audio_file_id"]]).get(
            row["audio_file_id"], []
        )
        return SoundboardButton(
            id=row["id"],
            soundboard_id=row["soundboard_id"],
            audio_file_id=row["audio_file_id"],
            position=row["position"],
            volume=row["volume"],
            audio_file=audio_file,
        )

    def remove_soundboard_button(self, button_id: int) -> None:
        """Remove a button from a soundboard"""
        self._conn.execute("DELETE FROM soundboard_buttons WHERE id = ?", (button_id,))
        self._conn.commit()

    def reorder_soundboard_buttons(
        self, soundboard_id: int, button_ids: list[int]
    ) -> None:
        """Reorder buttons on a soundboard by updating their positions"""
        for position, button_id in enumerate(button_ids):
            self._conn.execute(
                "UPDATE soundboard_buttons SET position = ? WHERE id = ? AND soundboard_id = ?",
                (position, button_id, soundboard_id),
            )
        self._conn.commit()
