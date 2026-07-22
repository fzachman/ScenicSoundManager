# 010 — First real build (py2app) and distribution story

**Status:** IN PROGRESS (2026-07-22). setup.py has existed since early on
but `python setup.py py2app` has never actually been run.

## Decisions (agreed 2026-07-22)

- **Don't bundle VLC for beta.** The app requires VLC.app installed;
  python-vlc auto-discovers /Applications/VLC.app with zero config. A
  startup dialog (below) instructs users who don't have it. Embedding
  libVLC stays a future option — it's legal (libvlc/libvlccore are
  LGPL 2.1+, dynamic linking is the blessed path; ship license text +
  attribution + source pointer) but means curating the plugin set
  (a few plugins are GPL; we only need audio ones) and wiring
  PYTHON_VLC_LIB_PATH/VLC_PLUGIN_PATH (hooks already exist in main.py
  and AudioEngine._configure_vlc_paths).
- **VLC-missing UX:** app already degrades gracefully (AudioEngine
  catches the import failure; players no-op) but silently. Add a
  one-time startup dialog: "install VLC from videolan.org and relaunch,"
  with an Open-Download-Page button. Must-have before any build goes to
  another person.
- **Builds never go in git.** build/ + dist/ in .gitignore. Distribution
  = GitHub Releases: tag `v<version>`, attach zipped .app (or .dmg).
- **Versioning:** single source of truth stays app/__init__.__version__;
  setup.py reads it into CFBundleVersion/CFBundleShortVersionString.
  Semver, numeric triplets (Apple's plist fields want X.Y.Z). Consider
  dropping to 0.9.x for beta, reserving 1.0.0 for release.
- **Data identity:** a build shares settings (com.scenicsound.SoundManager
  plist) and DB (~/Library/Application Support/ScenicSound/) with source
  runs — it IS the same app to the OS. Never run both at once (SQLite
  interleaving, remote port 8765 bind conflict). Back up the DB before
  first build-launch.

## Known setup.py gaps (found by reading, pre-build)

- `includes` predates the soundboard: app.soundboard (and
  app.settings_dialog) missing. Better fix: put `"app"` in `packages` —
  py2app copies packages as REAL directories (not into the site-packages
  zip), which also fixes the next item.
- Resource loading: DatabaseConnection reads schema.sql and IconLibrary
  reads app/assets/icons/feather/*.svg via `__file__`-relative paths.
  Inside the zip those paths don't exist; `"app"` in `packages` keeps
  them working unchanged.
- VLC "bundling" is half-implemented (adds 2 dylibs to frameworks, never
  copies plugins → libVLC that can't decode). Per the no-bundle decision:
  remove it; print a note that VLC.app is required at runtime.
- `iconfile` is None — .icns app icon still TODO (separate polish item).

## Verification approach for a build

Launch the built .app (no quarantine locally, Gatekeeper not an issue),
then: check the structlog file for a clean startup, and probe the running
app over the remote WebSocket API (get_scenes/get_soundboards + a brief
play_scene/stop) — proves DB, settings, Qt plugins, and VLC all work in
bundled form without needing screen-recording permissions.

## First build results (2026-07-22)

`venv/bin/python setup.py py2app` works after removing
install_requires/setup_requires (newer setuptools rejects them) — the
build is ~279 MB, named "Scenic Sound Manager.app" (py2app picks up
CFBundleName). Verified in the built bundle: schema.sql + all SVG icons
present (the `"app"`-in-packages fix), real DB + settings shared with
source runs, remote WebSocket server up (the Stream Deck plugin
connected to it on its own), single-track soundboard playback, scene
playback with crossfades and preset switches.

**Open watch item:** ONE unreproduced crash on the very first playback
attempt of the first-ever launch: SIGBUS, a VLC-spawned thread created
with entry pointer 0x1 while 5 mpg123 decoder threads were live
(DiagnosticReports/Scenic Sound Manager-2026-07-22-164210.ips). Not
reproduced in 12+ subsequent attempts (cold starts, scene-first
playback, crossfade/preset stress). Minimal python-vlc tests inside the
bundle (single + 8 concurrent players, ctypes callbacks) all pass. No
matching crash signature in the source app's history. If it recurs
during real use, start from the .ips files.

## Later / follow-ups

- .icns app icon; .app bundle display name ("Scenic Sound Manager.app").
- .dmg packaging; Developer ID signing + notarization when distributing
  beyond friends (unsigned = right-click-Open instruction).
- GitHub Actions build-on-tag workflow (runner needs
  `brew install --cask vlc` or the no-VLC build).
- Single-instance guard; optional --data-dir override for sandboxed
  test profiles.
- About box should display __version__ for bug reports.
