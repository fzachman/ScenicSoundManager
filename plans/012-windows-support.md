# Plan 012: Windows support

**Status:** TODO — deliberately deferred. macOS-only is fine for the beta;
execute phase 1 whenever convenient (it's cheap and also helps Linux),
phase 2 only when a real Windows user asks (it buys a permanent second
QA platform, so demand should justify it).

## Why this is tractable

The architecture is already cross-platform where it counts: PyQt6, VLC
(python-vlc), SQLite, QWebSocketServer. CI runs the full suite on Linux
today, proving the core logic has no macOS dependency. The work is
concentrated in paths, packaging, and QA.

## Phase 1 — platform-neutral paths (small, do anytime)

- `app/paths.py` hardcodes `~/Library/Application Support/ScenicSound`;
  `app/shared/logging.py` hardcodes `~/Library/Logs/ScenicSound`.
- Replace with `QStandardPaths.AppDataLocation` (already have Qt; avoids
  a new dep) or `platformdirs`. Keep the macOS results byte-identical so
  existing installs aren't orphaned — pin with tests.
- While in there: audit for any other `Path.home() / "Library"` usage.

## Phase 2 — Windows build + release (the real work)

- **Packaging:** PyInstaller (the standard for PyQt apps) with its own
  spec; expect a gotcha-hunting session equivalent to py2app's
  app-in-packages lesson (data files: schema.sql, default_tags.sql,
  feather SVGs). Icon: generate `.ico` from resources/app_icon.png.
  Installer: zip first, Inno Setup/NSIS if wanted.
- **Release pipeline:** `just build`/`just release` are macOS-flavored
  (ditto, PlistBuddy, iconutil, .app). Fork per-platform recipes or move
  to a GitHub Actions matrix build-on-tag (plan 010 follow-up pairs well).
- **VLC on Windows:** python-vlc discovers VLC via the registry, but
  64-bit Python REQUIRES 64-bit VLC and videolan.org tends to offer the
  32-bit build — the missing-VLC dialog needs Windows wording and this
  will be a recurring support question.
- **Repair Library:** `spotlight_search` already returns [] without
  mdfind, so Windows degrades to folder-scan-only. Small UI tweak: skip
  the Spotlight phase entirely off-macOS instead of "searching" nothing.
- **SmartScreen:** unsigned exe → "Windows protected your PC"; document
  "More info → Run anyway" like the macOS Open Anyway notes. Windows
  code-signing certs are pricier/more annoying than Apple's — beta ships
  unsigned with instructions.
- **QA reality:** need a Windows machine/VM per release: drag-drop, dock
  widget, keyboard shortcuts (the event-filter design has a macOS
  KeypadModifier workaround to re-test), dark theme, firewall prompt on
  the localhost WebSocket. `windows-latest` CI can build + run tests but
  not replace hands-on passes.
- **Stream Deck plugin:** separate repo, needs its own Windows pass.

## Out of scope

- Linux packaging (but phase 1 unlocks most of it for free).
- Bundling VLC on any platform (plan 010 decision stands).
