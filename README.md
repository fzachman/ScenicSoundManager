# SoundManager

A desktop **audio soundscape manager for tabletop RPGs** (D&D and friends). Build
layered ambient scenes, run music playlists, and switch between them live during a
session — all from one window.

Built with **PyQt6**, a **VLC** (libVLC) audio backend, and **SQLite** for
persistence.

> Note: this README is the user/contributor entry point. For architecture notes
> and conventions, see [`CLAUDE.md`](CLAUDE.md) and [`docs/`](docs/).

## Features

- **Library** — import individual files or whole folders (including drag-and-drop),
  with automatic metadata extraction (title/artist/duration via mutagen),
  user-defined **tags**, and search.
- **Scenes** — layer multiple sounds *simultaneously* for ambient soundscapes
  (e.g. rain + tavern murmur + crackling fire). Each track has independent volume,
  repeat, and play/stop state. A scene can also embed **playlist entries** that
  play sequentially (or shuffled) within the scene.
- **Playlists** — ordered tracks played one at a time through a single player,
  with **smart shuffle** (avoids immediate repeats).
- **Live control** — only one scene *or* one playlist plays at a time; switching
  is coordinated automatically. A master volume applies across everything.

Your library and scenes are stored in a local SQLite database at
`~/Library/Application Support/SoundManager/soundmanager.db` (macOS).

## Requirements

- **Python 3.10+** (developed and tested on 3.13).
- **VLC / libVLC** available on the system — `python-vlc` binds to the installed
  libVLC. The simplest way to get it is to install
  [VLC media player](https://www.videolan.org/vlc/). On Linux, install the
  distro's `libvlc`/`vlc` packages.
- Python dependencies (PyQt6, python-vlc, mutagen, structlog) — see
  [`requirements.txt`](requirements.txt).

Primarily developed on macOS; CI runs the test suite on Linux, so the app and
tests are cross-platform. The packaged `.app` build (below) is macOS-only.

## Setup

```bash
# from the repo root
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
./run.sh
# or, with the venv active:
python main.py
```

## Building the macOS app

Requires [VLC.app](https://www.videolan.org/vlc/) installed (its libraries are
bundled into the build):

```bash
python setup.py py2app        # production standalone build
python setup.py py2app -A      # development alias mode (faster; needs the source tree)
```

If VLC.app isn't found, the build still proceeds but the resulting app will
require VLC to be installed separately.

## Development

```bash
# run the test suite
venv/bin/pytest tests/ -v

# lint, format check, and (advisory) type check
venv/bin/ruff check app/ tests/
venv/bin/ruff format --check app/ tests/
venv/bin/mypy app
```

`ruff` (lint + format) and `pytest` are gating in CI (GitHub Actions); `mypy` runs
as advisory. Dependency bumps come through Dependabot PRs, which CI validates.

## Project layout

```
app/
  audio/      AudioEngine (VLC), TrackPlayer, SceneMixer, ScenePlaylistPlayer, SmartShuffle
  database/   SQLite CRUD (connection.py), dataclass models, schema.sql
  library/    audio import, metadata extraction, tagging, search
  scenes/     scene management, multi-track mixing, playlist-in-scene support
  playlists/  playlist management, ordering, sequential playback
  shared/     reusable widgets (base list/control cards, VolumeSlider), dark theme, logging, icons
main.py       application entry point
setup.py      py2app packaging
```

Each feature tab follows a **splitter pattern**: a `*ListWidget` sidebar (list +
CRUD) beside a `*Editor` detail/playback panel, inside a container `*Widget`.
