# Plan 012: Windows support

**Status:** IN PROGRESS (2026-09-22, branch `feature/windows-support`).
Re-planned 2026-09-22 against the current app. The original 2026-07-29
draft predated the theme system, single-instance lock, update checker,
restore flow, and the public beta; wherever it disagreed with the code, the
code won (see "Corrections" below).

## Decisions (agreed 2026-09-22)

- **Build in CI, test by hand, release from the Mac.** PyInstaller builds
  only for the OS it runs on, so a macOS build of the Windows app is not
  possible (Wine: rejected as fragile). A manually triggered
  (`workflow_dispatch`) job on `windows-latest` runs the tests + PyInstaller
  and uploads the zip as a workflow **artifact** — no tag, no release. The
  owner downloads it on their Windows machine and tests it. `just release`
  then attaches **that** artifact (the successful run for `HEAD`) to the
  same GitHub release as the macOS zip: the shipped Windows binary is the
  tested one, not a rebuild.
- **QA on the owner's real Windows machine.** No VM needed.
- **Optional local build for the first packaging session.** Iterating on
  the PyInstaller spec is faster locally (seconds vs a CI round trip); it
  needs Python + a clone on the Windows machine. The release path stays CI.
  (`just` recipes are macOS-only in their bodies — `sed`, `PlistBuddy`,
  `ditto`, py2app — so local Windows builds use plain commands.)
- **Packaging:** PyInstaller one-folder build, zipped (faster start, fewer
  antivirus false positives than one-file). An installer (Inno Setup) can
  come later.
- **VLC stays unbundled** (plan 010 decision). Windows users install 64-bit
  VLC; 64-bit Python cannot load 32-bit libVLC.
- **Unsigned for beta.** Document SmartScreen's "More info → Run anyway",
  like the macOS "Open Anyway" notes.
- **One release carries both platforms.** The update checker links to the
  release page (`app/update_check.py`), so both zips go on the same release.

## Corrections to the 2026-07-29 draft (current app wins)

- **Paths via `QStandardPaths` — wrong.** `app/paths.py` is stdlib-only by
  design, `configure_logging()` runs before the `QApplication` exists
  (`main.py`), and `AppDataLocation` on macOS appends a `SoundManager`
  subfolder — adopting it would orphan beta users' databases. Use a plain
  `sys.platform` branch instead.
- **Windows data goes in `%LOCALAPPDATA%`, not Roaming.** The library
  stores absolute paths to audio files on this machine, so the database is
  meaningless on another one; roaming profiles would also sync a growing DB
  and its backups.
- **Firewall prompt:** the remote server binds loopback only
  (`app/remote/server.py`), so a prompt is unlikely. Test item, not a task.
- **"Dark theme" QA** is now the live dark/light theme system. The app never
  calls `setStyle()`, so Windows 11 gets Qt's native `windows11` style, which
  can clash with stylesheets.
- **The justfile `arch -arm64` shell pin does not block Windows** —
  `set windows-shell` would override it; the recipe bodies are the blocker.
- `iconutil` is a manual step (see the `setup.py` comment), not part of
  `just build`.

## Steps

### Phase 0 — plan

1. Rewrite this plan and its `plans/README.md` row. **DONE 2026-09-22.**

### Phase 1 — platform-neutral paths

2. `sys.platform` branch in `app/paths.py` for `DATA_DIR` and `LOG_DIR`;
   `app/shared/logging.py` takes `LOG_DIR` from there.
   - macOS: unchanged, pinned literally by tests (real beta users).
   - Windows: `%LOCALAPPDATA%\ScenicSound` (logs in `...\ScenicSound\Logs`).
   - Other (Linux): XDG data/state dirs.
   - No migration: Windows has no installs, macOS paths do not move.

### Phase 2 — Windows code fixes

3. **Menus.** `_setup_menus` (`app/main_window.py`) puts About / Settings /
   Quit at the top of File and relies on macOS `MenuRole` relocation. Off
   macOS: About goes to Help, Quit becomes "Exit" and goes last in File.
4. **Missing-VLC dialog** (`MainWindow`, "install VLC from videolan.org"):
   Windows wording that says 64-bit VLC is required.
5. **Repair Library:** `spotlight_search` already returns `[]` without
   `mdfind`; skip the Spotlight phase in the UI off macOS instead of
   "searching" nothing.
6. **Style (conditional):** only if the first Windows test shows stylesheet
   problems, `app.setStyle("Fusion")` on `win32` only.

Optional cleanup: the py2app-only frozen-bundle VLC code (`main.py`
`setup_environment`, `AudioEngine._configure_vlc_paths`) looks for
`libvlc.dylib` under `../Resources`. Dead on Windows, harmless.

### Phase 3 — packaging and CI

7. **PyInstaller spec** (windowed, one-folder). Data files — the complete
   list, verified 2026-09-22: `app/database/schema.sql`,
   `app/database/default_tags.sql`, `app/assets/icons/**` (feather SVGs).
   Loading is `__file__`-relative (`app/database/connection.py`,
   `app/shared/icons.py`) — expect the same class of gotcha as py2app's
   "app must be in packages". Icon: `.ico` generated from
   `resources/app_icon.png`.
8. **`requirements.txt` platform markers:** `py2app` darwin-only,
   `pyinstaller` win32-only.
9. **`.github/workflows/windows-build.yml`:** `workflow_dispatch` (optionally
   also push to `main`), `windows-latest`, Python 3.13, install VLC so the
   VLC-guarded tests run rather than skip, pytest, PyInstaller, zip,
   `actions/upload-artifact`. `permissions: contents: read`.

### Phase 4 — test (owner, on Windows)

10. Download the artifact, install 64-bit VLC, then check: SmartScreen at
    first launch, drag-drop import, scene + playlist playback, soundboard
    dock (docked and popped out), keyboard shortcuts (the event filter strips
    macOS's `KeypadModifier` — re-test arrows/Home/End), both themes,
    Restore Database (see risks), remote control, update check,
    single-instance refusal, window size/position memory.

### Phase 5 — release

11. **`just release`:** preflight requires a successful `windows-build` run
    for `HEAD` (`gh run list --workflow windows-build.yml --commit <sha>
    --status success`), downloads its artifact, and attaches it beside the
    macOS zip in `gh release create`.
12. **Docs:** Windows install steps in `docs/release-notes-base.md` (unzip,
    SmartScreen, 64-bit VLC); README install/build sections and the
    database location; a `docs/release-notes-unreleased.md` bullet when the
    first Windows build ships.

## Already cross-platform (verified 2026-09-22, no change needed)

- Single-instance guard (`QLockFile`), `QSettings` (registry on Windows),
  window geometry (`saveGeometry`).
- Restore-then-relaunch via `QProcess.startDetached(sys.executable, ...)` —
  under PyInstaller `sys.executable` is the app exe (only the comment says
  py2app).
- `python-vlc`'s `media_new` treats `C:\...` as a local path, not a URL.

## Risks to watch in testing

- **Restore Database renames the live DB file** (`swap_database` in
  `app/database/backup.py`). Windows refuses to rename a file with an open
  handle. Every connection is closed by the time `closeEvent` swaps, but if
  the rename fails the app quits without restoring or relaunching — only a
  log line says so.
- `windows11` style vs the app's stylesheets (step 6).
- 64-bit vs 32-bit VLC: expect recurring support questions.
- The Stream Deck plugin (separate repo) needs its own Windows pass.

## Out of scope

- Linux packaging (phase 1 gives Linux sensible XDG paths for free).
- Bundling VLC on any platform (plan 010 decision stands).
- Code signing.
