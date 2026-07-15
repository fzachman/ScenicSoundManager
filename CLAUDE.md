# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app (development)
./run.sh
# or: source venv/bin/activate && python main.py

# Run all tests
venv/bin/pytest tests/ -v

# Run a single test file
venv/bin/pytest tests/test_database.py -v

# Run a single test
venv/bin/pytest tests/test_database.py::TestDatabaseConnection::test_add_audio_file -v

# Build macOS app (requires VLC.app installed)
python setup.py py2app        # production standalone
python setup.py py2app -A     # development alias mode
```

## Architecture

**D&D Audio Soundscape Manager** — PyQt6 desktop app with VLC audio backend and SQLite persistence.

### Playback model

- **Scenes** layer multiple sounds simultaneously (ambient soundscapes). `SceneMixer` manages N `TrackPlayer` instances playing in parallel, each with independent volume/repeat/play-mode. Scenes can also contain playlist entries via `ScenePlaylistPlayer`.
- **Playlists** play tracks sequentially through a single `TrackPlayer` with `SmartShuffle` support.
- Only one scene OR one playlist plays at a time — `MainWindow` coordinates mutual exclusivity via `playback_state_changed` signals.
- **Soundboards** play one-shot SFX *over* the active scene/playlist via `SoundboardPlayer` (single slot: new press cuts over, same press stops). Deliberately outside the mutual-exclusivity chain.

### Module layout

Each tab follows a **splitter pattern**: `*Widget` (container) = `*ListWidget` (left sidebar with list + CRUD) + `*Editor` (right panel with detail editing/playback).

- `app/audio/` — `AudioEngine` (singleton VLC factory), `TrackPlayer`, `SceneMixer`, `ScenePlaylistPlayer`, `SmartShuffle`, `SoundboardPlayer`
- `app/database/` — `DatabaseConnection` (SQLite CRUD), dataclass models in `models.py`, schema in `schema.sql`
- `app/library/` — Audio file import, metadata extraction (mutagen), tagging, search
- `app/scenes/` — Scene management, multi-track mixing, playlist-in-scene support
- `app/playlists/` — Playlist management, track ordering, playback
- `app/remote/` — Remote control: `RemoteControlFacade` (validated commands over MainWindow/widgets + coarse `state_changed` snapshots) and `RemoteControlServer` (localhost `QWebSocketServer`, protocol in `docs/remote-protocol.md`, QSettings `remote/enabled` + `remote/port`)
- `app/soundboard/` — Soundboard panel: `SoundboardDock` (collapsible/pop-out bottom `QDockWidget`), `SoundboardContent` (board combo + `FlowLayout` button grid), `SoundboardEditDialog`
- `app/shared/` — Reusable UI components, dark theme styles, structlog config, icon library

### Key conventions

- **Signals**: Use `pyqtSignal(object)` for dataclass payloads since PyQt6 doesn't support dataclass types directly.
- **Database**: All CRUD goes through `DatabaseConnection` methods. Models are dataclasses in `models.py`.
- **Logging**: Use `structlog` via `app.shared.logging.get_logger(__name__)`. Info+ goes to `~/Library/Logs/SoundManager/soundmanager.log` (rotated); the console only shows warning+.
- **Drag-drop**: Custom MIME type + container widget pattern (see `TrackListContainer`, `PlaylistTrackListContainer`).
- **Reusable dialogs**: `AudioFileSearchDialog` for track picking (supports `disabled_track_ids` for exclusion), `TextInputDialog` for name input.
