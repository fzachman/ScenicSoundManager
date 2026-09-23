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

   **DONE 2026-09-22:** `paths.data_dir()` / `paths.log_dir()` take an
   optional `platform` argument, so `tests/test_paths.py` checks every
   platform on any host.

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

**Steps 3–5 DONE 2026-09-22.** Also found and fixed: the Keyboard Shortcuts
dialog hardcoded `⌘` glyphs (now `Ctrl+` off macOS). Platform flags are
module constants in `app/main_window.py` (`IS_MACOS`, `IS_WINDOWS`) so tests
cover both layouts on any host; Repair Library keys off
`repair.spotlight_available()` (a capability check, not a platform check).
Step 6 waits for the first Windows test.

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

**Steps 7–9 DONE 2026-09-22 (CI-only, by owner's choice — no dev tools on
the Windows machine).**
- `windows.spec` at the repo root; `resources/app_icon.ico` committed
  (16–256px, generated from the PNG with Pillow). `pyinstaller==6.22.3`
  win32-only in `requirements.txt`; `py2app` is now darwin-only.
- Workflow: two parallel jobs. `test` (VLC via choco, preflight, pytest)
  and `build` (PyInstaller → `scripts/smoke_test_build.py` → zip →
  `upload-artifact@v7` with `archive: false`, so the download is the exact
  zip a release attaches, named `ScenicSoundManager-<version>-windows.zip`).
  Triggers: push to `main`, `feature/**`, `fix/**`, plus `workflow_dispatch`.
  Pull requests are disabled on this repo (owner's choice: sole
  contributor), so `ci.yml` got the same push triggers. GOTCHA: the dispatch
  button only exists once the workflow is on `main`.
- Smoke test: launches the exe offscreen on the clean runner, waits for the
  new `app_started` log line (added to `main.py`), checks it is still alive,
  and checks the DB has seeded tags (proves both SQL data files were found).
  It refuses to run if a library already exists (never touches a real
  install).
- Found and fixed: structlog raises `SystemError` for colored console output
  on Windows without colorama — `CONSOLE_COLORS` in `app/shared/logging.py`
  turns colors off on win32 (the windowed exe has no console, but source runs
  and the tests do).
- Validated locally on macOS first: the same spec builds a runnable folder.
  To run it without touching the real app's macOS preferences (startup
  writes last scene/playlist/board), build a scratch copy of the spec with a
  runtime hook that points every default `QSettings()` at a temp INI dir,
  and set `HOME` to a temp dir for the data/log folders.

**First CI runs (2026-09-22):** build + smoke test green on the first try
(the exe logged `app_started platform=win32` and survived the VLC-missing
path). Windows tests: 1 of 840 failed — the floating-dock size round trip
resized below the dock's minimum width, which is wider on Windows fonts
(~540px); test fixed. Run 35801306497 at `ef67131`: all green, artifact
`ScenicSoundManager-0.9.4-windows.zip` (46 MB).

### Phase 4 — test (owner, on Windows)

10. Download the artifact, install 64-bit VLC, then check: SmartScreen at
    first launch, drag-drop import, scene + playlist playback, soundboard
    dock (docked and popped out), keyboard shortcuts (the event filter strips
    macOS's `KeypadModifier` — re-test arrows/Home/End), both themes,
    Restore Database (see risks), remote control, update check,
    single-instance refusal, window size/position memory.

**First owner test (2026-09-22, artifact from `ef67131`):** ~99% worked.
One glitch: scene start/stop fades stuttered. Cause (from VLC 3.0
`modules/audio_output/mmdevice.c`): the default Windows output (WASAPI,
"mmdevice") sets volume on the process-wide audio session
(`ISimpleAudioVolume`), which every player in the process shares — so
overlapping per-player ramps fight over one level, and per-track mix levels
collapse to the last one set. Fix: `vlc_instance_args()` in
`app/audio/engine.py` selects `--aout=directsound` (per-buffer volume,
`directsound.c`) plus `--no-volume-save` on win32. A Windows-only test
proves the installed VLC really provides DirectSound (an unknown `--aout`
silently falls back to WASAPI). Re-test: fades AND per-track volumes in a
multi-track scene.

**Re-test PASSED (2026-09-22, artifact from `85afe20`, run 35804081012):**
smooth fades, independent per-track volumes, and the owner's second report —
"inactive" tracks audible when starting a one-track scene — is gone too (it
was retiring players, still ramping down for 1.5s after a stop/switch,
sharing the fading-in track's session volume). **Phase 4 DONE.** Step 6
(Fusion style) not needed: the owner saw no stylesheet problems.

Release-step facts verified 2026-09-22: `gh api
repos/<repo>/actions/artifacts/<id>/zip` returns the exact uploaded zip for an
`archive: false` artifact (same byte size, `ScenicSound Manager/` at the top
level), so `just release` can attach the tested file without a rebuild.
v0.9.4 (released 2026-09-22, macOS zip only) predates the Windows work, so
the first Windows release needs a new version.

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
