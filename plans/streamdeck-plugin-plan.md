# Plan: SoundManager Stream Deck Plugin

> **This document is self-contained and designed to be copied into a new
> repository as its starting plan.** It was exported from the SoundManager
> app project (plan 007, 2026-07-07) after the app-side WebSocket API was
> implemented, tested (297-test suite), and verified end-to-end against the
> running app. The full wire protocol is inlined below — no access to the app
> repo is required, though its `scripts/remote_client.py` is a working
> reference client if questions come up.

## Goal

An Elgato Stream Deck plugin that controls the SoundManager desktop app
(D&D audio soundscape manager) over its local WebSocket API:

1. **Play Scene** keys — each key is bound to one scene via a dropdown in the
   property inspector; pressing it plays that scene. The key visibly
   highlights while its scene is the one playing.
2. **Play/Pause** key — toggles playback; icon reflects current state.
3. **Master Volume** — a dial action for Stream Deck+ (rotate = adjust,
   optionally press = mute-style set-to-0/restore), plus volume-up /
   volume-down key actions as the fallback for button-only decks.

## Architecture

```
Stream Deck app ⇄ (Elgato WebSocket protocol, handled by SDK) ⇄ plugin process (Node)
                                                                  │
                                                    SoundManagerClient (this plan)
                                                                  │
                                              ws://127.0.0.1:8765 ⇄ SoundManager app
```

The plugin is a thin bridge: the Elgato SDK handles everything deck-side;
`SoundManagerClient` handles everything app-side; actions subscribe to state
snapshots and render.

## Scaffold

- Node 20+, TypeScript.
- Official SDK: `@elgato/streamdeck`. Scaffold with the official CLI
  (`npm i -g @elgato/cli`, then `streamdeck create`) — treat the generated
  template as the source of truth for manifest shape, build tooling, and dev
  workflow (`streamdeck link`, `streamdeck restart`), since these evolve.
- One plugin, four actions in the manifest: `play-scene`, `play-pause`,
  `master-volume-dial` (Encoder controller), `volume-step` (key, with a
  +/− direction setting).
- Global settings: `port` (default **8765**). Per-action settings: scene id
  for `play-scene`; step size and direction for `volume-step`.

## Milestone 1 — `SoundManagerClient`

A single shared connection for the whole plugin process:

- **Connect** to `ws://127.0.0.1:<port>`; JSON text frames.
- **Reconnect forever** with capped exponential backoff (e.g. 1s → 2s → 5s,
  cap 5s; the app simply may not be running yet). Never crash on refusal.
- **Request/response correlation**: every request carries a client-chosen
  `id` (monotonic counter); resolve the matching pending promise when a frame
  with that `id` arrives. Time out pending requests (~5s) with a rejection.
- **State fan-out**: frames with `{"event": "state"}` go to subscribers
  (`onState(cb)`). The server pushes a snapshot immediately on connect and on
  every change, so subscribers can render with zero polling.
- **Connection status fan-out**: `onStatus(cb)` with connected/disconnected,
  so actions can render a "disconnected" look (e.g. `showAlert()` on press,
  dimmed icon otherwise).
- Cache the latest state snapshot so newly-appearing actions render
  immediately.

Test this milestone against the real app before writing any action.

## Milestone 2 — Play/Pause action

- On key press: `toggle_play_pause`. Semantics (implemented app-side): pauses
  whatever is playing; if idle, starts the item currently open in the app's
  Scenes/Playlists tab.
- Render from state: playing → "pause" glyph + item name as title (truncate;
  `state.playing.name` may be `null`); idle → "play" glyph; disconnected →
  dimmed/alert.

## Milestone 3 — Play Scene action + property inspector

- Property inspector: a dropdown populated by calling `get_scenes` through
  the client (datasource pattern from the SDK template). Store the scene's
  **id** in action settings — ids are database ids, stable across renames.
  Never store the name; re-resolve display names via `get_scenes`.
- On key press: `play_scene {scene_id}`. On a `not_found` error, `showAlert()`
  (the scene was deleted; the user should re-pick in the inspector).
- Render from state: when `state.playing` is `{type: "scene", id: <mine>}`,
  show the active look; otherwise inactive. Title = scene name from settings
  refresh or `get_scenes`.
- Note: playing a scene from the deck intentionally changes the app's visible
  UI selection (tab + sidebar), exactly as if clicked in-app.

## Milestone 3b — Scene presets (decided UX: tap = toggle, long-press = preset page)

The app exposes presets as fixed per-scene slots 1–3 (no ids); `get_scenes`
returns each scene's slot names + active slot.

**Scene key, tap** — toggle play/pause, never touches the preset:

- If `state.playing` is this scene → `toggle_play_pause` (pauses it; safe
  globally since only one item plays app-wide).
- Otherwise → `play_scene {scene_id}` with NO preset param. App-verified
  semantics: a paused scene RESUMES from position (same-scene start reuses
  the paused players), a different playing item crossfades over, and the
  active preset is untouched.
- Do NOT use `toggle_play_pause` to resume/start: its Space-key semantics
  act on whatever is open in the app's current tab, which drifts if the user
  browsed in-app. `play_scene {scene_id}` is deterministic.

**Scene key, long-press** — open the preset page:

- No native long-press event: measure `keyDown`→`keyUp` duration and act on
  `keyUp` only (a threshold-crossed hold must suppress the tap action).
- Plugins can't open native folders programmatically; use `switchToProfile`
  to a plugin-bundled "preset page" profile (3 preset keys + back). Store
  the long-pressed scene id in plugin state; the page's keys render that
  scene's labels from `get_scenes` (`presets[].name`, fallback
  "Preset {slot}") and highlight `state.playing.preset.slot`.
- Each preset key = `play_scene {scene_id, preset}` — starts the scene in
  that preset if not playing (crossfading out whatever was), or
  live-crossfades just the preset if it is (no restart). One command covers
  both, so the keys need no conditional logic.

Optional extra action, **Set Preset** (scene-agnostic key outside the page):
`set_preset {preset}` acts on whatever scene is playing/paused;
`showAlert()` on `no_active_scene`.

## Milestone 4 — Master volume

- **Dial (Stream Deck+)**: on rotate, adjust by `ticks * step` from the last
  known `state.master_volume` and send `set_master_volume` (server clamps to
  0–100 and echoes the applied value). Render the value/bar on the touchscreen
  via the SDK's feedback layout. Debounce lightly if rotation floods (the app
  persists volume on every change).
- **Volume-step keys**: same math on press; settings choose +/− and step
  (default 5).
- Always re-render from pushed `state` events, not from local echo — in-app
  slider changes must move the deck's display too.

## Milestone 5 — Polish & packaging

- Global settings UI for the port (rarely changed; default 8765).
- Icons for all states (Stream Deck expects @1x/@2x PNGs; template shows sizes).
- `streamdeck pack` for a distributable `.streamDeckPlugin`.
- Manual test matrix: app not running (reconnect + disconnected render), app
  restarted mid-session, scene deleted while bound, two decks/pages with the
  same scene bound twice, volume dial while a playlist plays.

## Milestone 6 — Soundboard hit action (app side shipped 2026-07-20)

One action = one soundboard hit, manually mapped (boards can hold many
sounds; no auto-layout).

- Property inspector: two chained dropdowns — Soundboard, then Track —
  populated from `get_soundboards` (boards alphabetical, buttons in grid
  order). Store the **button id** from the chosen track; re-resolve display
  names via `get_soundboards` on render, same rule as scenes.
- On key press: `trigger_sound {button_id}`. That's the whole behavior —
  the app implements exact grid-button semantics: plays over the active
  scene/playlist; pressing while *this* button's sound plays stops it
  (toggle); pressing while another sound plays cuts it off. No preset/UI
  side effects (the app's visible board is never switched).
- Render from state: active look while `state.sound.button_id == <mine>`;
  `state.sound` is `null` when the soundboard is silent. It clears on stop,
  cut-over, natural end, and in-app board switch — re-render on every event
  as usual.
- Errors: `not_found` → the button was removed from the board (or the track
  re-added, which mints a new id) — `showAlert()`, user re-picks in the
  inspector. `file_missing` → file gone from disk — `showAlert()`.
- Optional companion key: **Stop Sound** = `stop_sound` (no params, no-op
  when silent).

---

## Wire protocol (v1) — as implemented and verified

Transport: `ws://127.0.0.1:8765` (localhost only; port configurable app-side
via its settings). JSON text frames, UTF-8, one message per frame. No auth.
Errors never close the connection.

**Request** (plugin → app): `{"id": <any>, "cmd": <str>, "params": {...}}` —
`id` is echoed verbatim in the response; `params` may be omitted.

**Response** (one per request):
`{"id": 1, "ok": true, "result": ...}` or
`{"id": 1, "ok": false, "error": {"code": "...", "message": "..."}}`.
Unparseable requests get `"id": null`.

**Event** (unsolicited, no `id`):
`{"event": "state", "data": {...}}` — pushed on connect and on any playback,
preset, or master-volume change from any source. `data` schema (same as
`get_state`):

```json
{
  "playing": {"type": "scene", "id": 3, "name": "Tavern", "preset": {"slot": 2, "name": "Combat"}},
  "paused": null,
  "sound": {"button_id": 5, "soundboard_id": 1, "name": "Sword Clash"},
  "master_volume": 80
}
```

`playing` is `null` when nothing is audibly playing; `type` is `"scene"` or
`"playlist"`; `name` can be `null` if unresolvable. `preset` is the scene's
active preset slot (`name` null for never-renamed slots — render as
"Preset {slot}"); always `null` for playlists. `paused` has the same shape as
`playing` and holds the resumable paused item; the two are mutually exclusive
(at most one non-null). `sound` is the soundboard one-shot playing *over* the
active item (`null` when silent) — independent of both fields, at most one at
a time. Treat every event as a full re-render — a mutating command's `state`
broadcast typically arrives *before* its response.

| `cmd` | `params` | `result` |
|-------|----------|----------|
| `get_state` | — | state snapshot (above) |
| `get_scenes` | — | `[{"id": int, "name": str, "active_preset": int, "presets": [{"slot": int, "name": str\|null} ×3]}, ...]` |
| `get_playlists` | — | `[{"id": int, "name": str}, ...]` |
| `play_scene` | `{"scene_id": int, "preset": int?}` | `null` — optional `preset` 1–3: not-yet-playing scene starts in that preset; already-playing scene live-crossfades to it (no restart) |
| `play_playlist` | `{"playlist_id": int}` | `null` |
| `set_preset` | `{"preset": int}` | `null` — switch the active (playing/paused) scene's preset; `no_active_scene` error when idle or a playlist is active |
| `toggle_play_pause` | — | `null` |
| `next_track` | — | `null` (playing playlist only; no-op otherwise) |
| `set_master_volume` | `{"value": int}` | `{"master_volume": int}` (clamped 0–100) |
| `get_soundboards` | — | `[{"id": int, "name": str, "buttons": [{"id": int, "name": str\|null}, ...]}, ...]` |
| `trigger_sound` | `{"button_id": int}` | `null` — in-app button semantics: same-button toggle-stop, different-button cut-over, plays over the active item; never touches the app's UI |
| `stop_sound` | — | `null` (no-op when silent) |

Error codes: `bad_request` (bad JSON / non-object frame or params),
`unknown_command`, `invalid_params` (wrong type or preset outside 1–3; ids and
volume must be JSON integers — booleans are rejected), `not_found`,
`no_active_scene`, `file_missing` (`trigger_sound` with the audio file gone
from disk), `internal_error`.

Only one scene *or* one playlist plays at a time (app-enforced mutual
exclusivity). v1 is additive-versioned: ignore unknown fields in `state` and
responses.
