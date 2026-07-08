# Plan 007: Stream Deck remote control (local WebSocket API)

> **Scope note**: Unlike plans 001–006 (advisor-generated, executed by
> dispatched subagents), this is a user-requested feature plan executed
> interactively. Phases are still ordered so each ends green and committed.
> Update this plan's status row in `plans/README.md` as phases land.

## Status

- **Feature**: Remote control of playback from an Elgato Stream Deck
- **Priority**: Feature (user-requested)
- **Effort**: M–L across two repos (app side ~2–3 focused sessions; plugin is a
  separate project, planned in Phase 4)
- **Risk**: LOW-MED — additive (new `app/remote/` module, one init hook in
  `MainWindow`); no changes to playback logic itself
- **Depends on**: none. Reuses the transport entry points added by the
  keyboard-shortcuts work (`toggle_playback` / `pause_active` / `play_current` /
  `next_track` on the tab widgets) and the `playback_state_changed` signal chain.
- **Planned at**: commit `6319f25`, 2026-07-07, branch `main`
- **Baseline**: `venv/bin/pytest tests/ -q` → **251 passed** (~1s)
- **Branch**: `feature/remote-control` off `main`
- **Status**: TODO

## Goal

Let a Stream Deck (via a custom plugin, separate project) do at minimum:

1. **Assign a scene to a button** — pressing it selects and plays that scene.
2. **Toggle global play/pause** — same semantics as the Space shortcut.
3. **Set master volume** — dial on Stream Deck+, up/down keys otherwise.

Buttons must be able to **reflect state** (which scene is playing, play/pause
icon, current volume), which is why the app exposes a push-capable channel
rather than a poll-only REST endpoint.

## Architecture decisions (settled)

- **Transport**: WebSocket server inside the app, bound to `127.0.0.1` only,
  using **`PyQt6.QtWebSockets.QWebSocketServer`** (verified importable in this
  venv). Rationale: it runs on the Qt event loop, so command handlers may call
  widget methods and connect to signals directly — no threads, no asyncio, no
  cross-thread marshaling. This is the decisive advantage over Flask/aiohttp/
  `websockets`.
- **Protocol**: JSON messages, documented in `docs/remote-protocol.md`
  (created Phase 2, kept authoritative). Draft v1 below.
- **State push model**: one coarse `state` event carrying the full snapshot
  (playing item + master volume), sent to every client on connect and on any
  change. Coarse-grained keeps the plugin trivial: any event → re-render all
  keys. Granular events are a later optimization if ever needed.
- **Scene identity**: buttons store the scene's **database id** (stable across
  renames), never the name. The plugin's property inspector fetches
  `get_scenes` to populate its dropdown.
- **Port**: default `8765`, persisted under QSettings group `remote`
  (key `port`), alongside the existing `audio`/`ui` groups. Tests bind port `0`
  (ephemeral) and read `serverPort()`.
- **Security**: localhost-only binding; no auth in v1 (single-user desktop
  app). A shared-token handshake is a noted follow-up, not v1 scope.
- **Failure isolation**: if the server can't bind (port in use), log a warning
  and continue — remote control must never prevent the app from starting.

## Protocol draft v1

Requests are `{"id": <int>, "cmd": <str>, "params": {...}}`; responses echo the
id: `{"id": 1, "ok": true, "result": {...}}` or
`{"id": 1, "ok": false, "error": {"code": "...", "message": "..."}}`.
Events (server→client, no id): `{"event": "state", "data": {...}}`.

| Command | Params | Result / effect |
|---------|--------|-----------------|
| `get_state` | — | `{playing: {type: "scene"\|"playlist", id, name} \| null, master_volume: 0–100}` |
| `get_scenes` | — | `[{id, name}, ...]` (from `db.get_all_scenes()`) |
| `get_playlists` | — | `[{id, name}, ...]` |
| `play_scene` | `scene_id` | Select + play that scene (validates id; error `not_found` otherwise) |
| `play_playlist` | `playlist_id` | Same for playlists (near-free; symmetric) |
| `toggle_play_pause` | — | Exactly the Space-key semantics (`_shortcut_toggle_play`) |
| `next_track` | — | Exactly the Right-key semantics (playing playlist only) |
| `set_master_volume` | `value` (0–100, clamped) | Sets engine + slider + persists |

Malformed JSON / unknown `cmd` / bad params get an `ok: false` response with
codes `bad_request` / `unknown_command` / `invalid_params`; the connection is
never dropped and the app never raises. (Remember the PyQt6 gotcha: an
unhandled exception in a slot invoked from C++ **aborts the process** — every
socket handler must be defensively wrapped.)

## Phases

### Phase 1 — `RemoteControlFacade` (no networking)

New `app/remote/facade.py`: a `QObject` constructed by `MainWindow` with
references to the pieces it needs (db, `scenes_widget`, `playlists_widget`,
`master_slider`, tab widget). It is the single seam between "remote command"
and the UI, and the only thing Phase 2's server talks to.

- Commands map onto existing methods:
  - `play_scene(id)` → validate via `db.get_scene`, switch to the Scenes tab,
    `scenes_widget.select_scene(id)` + `play_current()` (mutual exclusivity
    comes free via the existing signal chain). Same pattern for playlists.
  - `toggle_play_pause()` → extract the body of
    `MainWindow._shortcut_toggle_play` so the key handler and facade share it
    (they must never drift). Same for `next_track()`.
  - `set_master_volume(v)` → clamp, then `master_slider.setValue(v)` — the
    existing `_on_master_volume_changed` slot already updates engine, label,
    and QSettings.
  - `get_state()` → read `MainWindow._current_playing_type` /
    `_current_scene_id` / `_current_playlist_playing_id` + engine volume
    (expose via a small accessor rather than reaching into privates).
- One signal: `state_changed(object)` (dict payload, per the pyqtSignal
  convention), emitted by connecting to both widgets'
  `playback_state_changed` and to `master_slider.valueChanged`.
- **Tests** (`tests/test_remote_facade.py`): drive a real `MainWindow` with the
  offscreen `qapp` fixture (precedent: Plan 005's exclusivity tests) — assert
  command→widget-method dispatch, unknown-id errors, volume clamping, and
  `state_changed` emissions on playback/volume changes.
- **Commit point**: facade + tests green, no user-visible change.

### Phase 2 — WebSocket server

New `app/remote/server.py`: `RemoteControlServer(QObject)` wrapping
`QWebSocketServer` (NonSecureMode, `127.0.0.1`, port from settings).

- Decode/dispatch requests to the facade; serialize responses; broadcast
  `state` events on `facade.state_changed`; send a snapshot on connect.
  Track connected clients; clean up on `disconnected`.
- Defensive envelope around every handler (see abort gotcha above), with
  structlog logging via `app.shared.logging.get_logger`.
- Write `docs/remote-protocol.md` — the authoritative protocol spec.
- **Tests** (`tests/test_remote_server.py`): in-process end-to-end with a
  `QtWebSockets.QWebSocket` client against a server on port 0 (no new deps).
  Cover: connect→snapshot, each command round-trip, malformed JSON, unknown
  command, two clients both receiving broadcasts, client disconnect.
- **Commit point**: server + tests + protocol doc, still not wired into the app.

### Phase 3 — Wire-up + manual verification

- Instantiate the server in `MainWindow.__init__` (after `_setup_ui`), stop it
  in `closeEvent`. Bind failure → warning log, app continues.
- `scripts/remote_client.py`: a tiny CLI test client built on PyQt6's
  `QWebSocket` (zero new dependencies) — `remote_client.py play-scene 3`,
  `toggle`, `volume 40`, `watch` (prints state events). This is the manual
  test rig *and* the reference implementation for the plugin author.
- Manual verification against the real running app (`./run.sh`): play a scene
  by id, toggle pause, spin volume, watch events while clicking the UI.
- Update `README.md` (user-facing) and `CLAUDE.md` (module layout) briefly.
- **Commit point**: feature complete in-app; suite green.

### Phase 4 — Export the plugin-project plan (final step, by design)

Written last so it describes the protocol **as actually implemented**, not as
drafted. Deliverable: `plans/streamdeck-plugin-plan.md` — fully self-contained
(inline the final protocol; don't reference this repo's paths), ready to copy
into the new plugin repo as its starting plan. Contents:

- Scaffold: Elgato Stream Deck SDK (`@elgato/streamdeck`, Node 20,
  `streamdeck create` CLI template), TypeScript.
- A shared `SoundManagerClient` (WebSocket wrapper): auto-reconnect with
  backoff, request/response correlation by id, state-event fan-out,
  "disconnected" rendering when the app isn't running.
- Three actions: **Play Scene** (property-inspector dropdown populated from
  `get_scenes`, stores scene id, highlights when its scene is playing),
  **Play/Pause** (icon reflects state), **Master Volume** (dial action for
  Stream Deck+, up/down key fallback).
- Port/config UI (defaults to 8765), packaging/install notes.

## Risks & gotchas

- **PyQt slot exceptions abort the process** — all socket/dispatch code wrapped;
  tests include malformed input for exactly this reason.
- **`set_master_volume` writes QSettings per tick** (existing slot behavior).
  A Stream Deck+ dial can emit many ticks/second. Likely fine (same as
  wheel-scrolling the slider today); if profiling says otherwise, debounce the
  persist — do not bypass the slider, the single-path wiring is the point.
- **`play_scene` changes UI selection** (tab + sidebar) by design — remote
  press behaves exactly like clicking the scene. Noting it as intentional.
- **py2app**: the standalone build must bundle `PyQt6.QtWebSockets`; check
  `setup.py` includes when packaging (dev alias mode unaffected).
- **Port collisions**: 8765 is a common dev port; the settings override plus
  warn-and-continue behavior covers it.

## Deferred (recorded, not v1)

- Shared-token auth handshake for the localhost socket.
- Granular events / per-track position streaming (e.g. scrubber on the deck).
- Previous-track and scene-internal controls (per-track volumes) over remote.
- Settings-UI panel for enabling/disabling the server (v1: always on,
  QSettings-editable port).
