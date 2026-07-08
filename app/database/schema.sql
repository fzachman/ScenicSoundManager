PRAGMA foreign_keys = ON;

-- Audio files in the library (referenced by path, not moved)
CREATE TABLE IF NOT EXISTS audio_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    title TEXT,
    artist TEXT,
    duration_seconds REAL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audio_files_title ON audio_files(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_audio_files_artist ON audio_files(artist COLLATE NOCASE);

-- User-defined tags
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    color TEXT,  -- Hex color for UI display
    created_at TEXT DEFAULT (datetime('now'))
);

-- Many-to-many: audio files <-> tags
CREATE TABLE IF NOT EXISTS audio_file_tags (
    audio_file_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (audio_file_id, tag_id),
    FOREIGN KEY (audio_file_id) REFERENCES audio_files(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_audio_file_tags_tag_id ON audio_file_tags(tag_id);

-- Scene definitions
CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Audio files in scenes with per-scene settings
CREATE TABLE IF NOT EXISTS scene_audio_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL,
    audio_file_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    volume REAL NOT NULL DEFAULT 1.0,
    is_repeat INTEGER NOT NULL DEFAULT 0,
    play_mode INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
    FOREIGN KEY (audio_file_id) REFERENCES audio_files(id) ON DELETE CASCADE,
    UNIQUE (scene_id, audio_file_id)
);

CREATE INDEX IF NOT EXISTS idx_scene_audio_files_scene_id ON scene_audio_files(scene_id, position);

-- Playlist entries within scenes (playlist as a track type in a scene)
CREATE TABLE IF NOT EXISTS scene_playlist_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL,
    playlist_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    volume REAL NOT NULL DEFAULT 1.0,
    is_shuffle INTEGER NOT NULL DEFAULT 0,
    is_repeat INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    UNIQUE (scene_id, playlist_id)
);

CREATE INDEX IF NOT EXISTS idx_scene_playlist_entries_scene_id ON scene_playlist_entries(scene_id, position);

-- Playlist definitions
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    is_shuffle INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Audio files in playlists (ordered, unique per playlist)
CREATE TABLE IF NOT EXISTS playlist_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER NOT NULL,
    audio_file_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (audio_file_id) REFERENCES audio_files(id) ON DELETE CASCADE,
    UNIQUE (playlist_id, audio_file_id)
);

CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist_id ON playlist_tracks(playlist_id, position);
