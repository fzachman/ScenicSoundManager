# SoundManager Remote-Control Protocol (v1)

SoundManager exposes a local WebSocket API so external controllers (e.g. a
Stream Deck plugin) can drive playback. This document is the authoritative
protocol spec; the implementation lives in `app/remote/`.

## Transport

- **URL**: `ws://127.0.0.1:8765` — localhost only; the server never binds a
  routable interface.
- **Port**: default `8765`, overridable via the app's QSettings
  (group `remote`, key `port`).
- **Frames**: JSON text messages, UTF-8. One request or event per frame.
- **Auth**: none in v1 (single-user desktop app; any local process may connect).

If the port can't be bound at startup, the app logs a warning and runs
without remote control — clients should retry with backoff.

## Message envelopes

**Request** (client → server):

```json
{"id": 1, "cmd": "play_scene", "params": {"scene_id": 3}}
```

- `id`: any JSON value chosen by the client; echoed verbatim in the response
  so requests can be correlated. Optional (echoed as `null` if omitted).
- `params`: object; may be omitted for commands that take none.

**Response** (server → client, exactly one per request):

```json
{"id": 1, "ok": true, "result": null}
{"id": 1, "ok": false, "error": {"code": "not_found", "message": "no scene with id 3"}}
```

If a request can't be parsed at all (invalid JSON), the response carries
`"id": null`.

**Event** (server → client, unsolicited, no `id`):

```json
{"event": "state", "data": {"playing": {"type": "scene", "id": 3, "name": "Tavern", "preset": {"slot": 2, "name": "Combat"}}, "paused": null, "sound": null, "master_volume": 80}}
```

## The `state` event

One coarse snapshot, pushed:

- immediately on connect (so clients can render without polling), and
- on any playback, preset, soundboard-sound, or master-volume change,
  regardless of source (remote command, in-app click, keyboard shortcut).

Schema of `data` (identical to the `get_state` result):

| Field | Type | Meaning |
|-------|------|---------|
| `playing` | object \| null | `null` when nothing is audibly playing |
| `playing.type` | `"scene"` \| `"playlist"` | what kind of item is playing |
| `playing.id` | int | database id of the playing item |
| `playing.name` | string \| null | display name (`null` if unresolvable) |
| `playing.preset` | object \| null | the scene's active preset, `{"slot": int, "name": str|null}`; always `null` for playlists (or if unresolvable). `name` is `null` for slots never renamed — render as "Preset {slot}" |
| `paused` | object \| null | the previously-playing item now paused (resumable); same shape as `playing`; `null` when something is playing or the app is fully idle |
| `sound` | object \| null | the soundboard one-shot currently playing: `{"button_id": int, "soundboard_id": int, "name": str\|null}`; `null` when the soundboard is silent |
| `master_volume` | int 0–100 | current master volume |

`sound` is independent of `playing`/`paused`: soundboard one-shots play
*over* the active scene/playlist, outside the mutual-exclusivity rule, and at
most one plays at a time (a new trigger cuts the previous sound off). It
clears on stop, cut-over, natural end, and when the board is switched in-app.

`playing` and `paused` are mutually exclusive — at most one is non-null. At
most one item is active app-wide: starting any scene or playlist stops
whatever else was active, **including a paused item**, so a `state` event
showing a new `playing` item also means any previously paused item is gone
(not resumable). Pausing is independent of UI selection: the paused item stays
paused (and reported) while the user browses other scenes/playlists in the app.

Clients should treat every `state` event as a full re-render; no diffing is
required or expected. Events and responses may interleave: a mutating command
typically produces a `state` broadcast *before* its own response arrives.

## Commands

| `cmd` | `params` | `result` on success |
|-------|----------|---------------------|
| `get_state` | — | state snapshot (see above) |
| `get_scenes` | — | `[{"id": int, "name": str, "active_preset": int, "presets": [{"slot": int, "name": str|null}, ...]}, ...]` — every scene lists all three preset slots; `name` is `null` for slots never renamed |
| `get_playlists` | — | `[{"id": int, "name": str}, ...]` |
| `get_soundboards` | — | `[{"id": int, "name": str, "buttons": [{"id": int, "name": str\|null}, ...]}, ...]` — boards alphabetical, buttons in grid order; button ids are what `trigger_sound` takes |
| `play_scene` | `{"scene_id": int, "preset": int?}` | `null` — selects the scene in the UI (tab + sidebar, like clicking it) and plays it. Optional `preset` (1–3) activates that slot first: a scene not yet playing starts directly in it; a scene already playing just live-crossfades the preset (no restart) — so one button per (scene, preset) pair always does the right thing |
| `play_playlist` | `{"playlist_id": int}` | `null` — same for playlists |
| `set_preset` | `{"preset": int}` | `null` — switches the active (playing **or paused**) scene to preset 1–3: live crossfade while playing; a paused scene resumes with the new preset's settings. Errors with `no_active_scene` when no scene is active (idle, or a playlist is playing). Selects that scene in the UI like `play_scene` does |
| `toggle_play_pause` | — | `null` — pauses whatever is playing; if idle, starts the item open in the current Scenes/Playlists tab (Space-key semantics) |
| `next_track` | — | `null` — advances the playing playlist; no-op when a scene is playing or idle (Right-key semantics) |
| `set_master_volume` | `{"value": int}` | `{"master_volume": int}` — the applied value; out-of-range input is clamped to 0–100 |
| `trigger_sound` | `{"button_id": int}` | `null` — presses a soundboard button, with exact in-app semantics: plays the sound over whatever is active; the same button while its sound plays stops it (toggle); a different button cuts the current sound off and plays instead. Errors with `file_missing` when the button's audio file is gone from disk (except on a toggle-off press, which still stops) |
| `stop_sound` | — | `null` — stops the playing soundboard sound; no-op when the soundboard is silent (the panel's Stop button) |

Notes:

- Ids are **database ids** and stable across renames — controllers should
  store ids, never names, and use `get_scenes`/`get_playlists` to (re)resolve
  display names.
- Only one scene *or* one playlist is active at a time; `play_*` stops
  whatever else was playing **or paused** (the app's mutual-exclusivity rule).
- `play_scene`/`play_playlist`/`set_preset` intentionally change the visible
  UI selection, exactly as if the item was clicked. `trigger_sound` does
  **not**: one-shots are momentary, so it never switches the visible board.
- Presets are per-scene slots 1–3 (there are no preset ids); slots always
  exist, custom names are optional. Playlists have no presets.
- Soundboard button ids are stable for a (board, track) pairing, but removing
  a track from a board and re-adding it mints a new id — controllers should
  `showAlert`-style surface `not_found` so the user re-picks in settings.

## Error codes

| Code | Meaning |
|------|---------|
| `bad_request` | Frame isn't valid JSON, isn't an object, or `params` isn't an object |
| `unknown_command` | `cmd` missing or not in the table above |
| `invalid_params` | A parameter has the wrong type or value (e.g. non-integer id, preset outside 1–3) |
| `not_found` | No scene/playlist/soundboard button with the given id |
| `no_active_scene` | `set_preset` when no scene is playing or paused |
| `file_missing` | `trigger_sound` when the button's audio file no longer exists on disk |
| `internal_error` | Unexpected server-side failure (logged app-side) |

Errors never close the connection; clients may keep the socket and continue.

## Versioning

v1 is intentionally minimal. Additive changes (new commands, new fields in
`state`) will not be signaled; clients must ignore unknown fields. Breaking
changes would introduce an explicit version handshake first.
