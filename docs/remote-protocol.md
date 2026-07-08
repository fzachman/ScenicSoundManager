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
{"event": "state", "data": {"playing": {"type": "scene", "id": 3, "name": "Tavern"}, "master_volume": 80}}
```

## The `state` event

One coarse snapshot, pushed:

- immediately on connect (so clients can render without polling), and
- on any playback or master-volume change, regardless of source (remote
  command, in-app click, keyboard shortcut).

Schema of `data` (identical to the `get_state` result):

| Field | Type | Meaning |
|-------|------|---------|
| `playing` | object \| null | `null` when idle |
| `playing.type` | `"scene"` \| `"playlist"` | what kind of item is playing |
| `playing.id` | int | database id of the playing item |
| `playing.name` | string \| null | display name (`null` if unresolvable) |
| `master_volume` | int 0–100 | current master volume |

Clients should treat every `state` event as a full re-render; no diffing is
required or expected. Events and responses may interleave: a mutating command
typically produces a `state` broadcast *before* its own response arrives.

## Commands

| `cmd` | `params` | `result` on success |
|-------|----------|---------------------|
| `get_state` | — | state snapshot (see above) |
| `get_scenes` | — | `[{"id": int, "name": str}, ...]` |
| `get_playlists` | — | `[{"id": int, "name": str}, ...]` |
| `play_scene` | `{"scene_id": int}` | `null` — selects the scene in the UI (tab + sidebar, like clicking it) and plays it |
| `play_playlist` | `{"playlist_id": int}` | `null` — same for playlists |
| `toggle_play_pause` | — | `null` — pauses whatever is playing; if idle, starts the item open in the current Scenes/Playlists tab (Space-key semantics) |
| `next_track` | — | `null` — advances the playing playlist; no-op when a scene is playing or idle (Right-key semantics) |
| `set_master_volume` | `{"value": int}` | `{"master_volume": int}` — the applied value; out-of-range input is clamped to 0–100 |

Notes:

- Ids are **database ids** and stable across renames — controllers should
  store ids, never names, and use `get_scenes`/`get_playlists` to (re)resolve
  display names.
- Only one scene *or* one playlist plays at a time; `play_*` on one kind
  stops the other (the app's mutual-exclusivity rule).
- `play_scene`/`play_playlist` intentionally change the visible UI selection,
  exactly as if the item was clicked.

## Error codes

| Code | Meaning |
|------|---------|
| `bad_request` | Frame isn't valid JSON, isn't an object, or `params` isn't an object |
| `unknown_command` | `cmd` missing or not in the table above |
| `invalid_params` | A parameter has the wrong type (e.g. non-integer id/value) |
| `not_found` | No scene/playlist with the given id |
| `internal_error` | Unexpected server-side failure (logged app-side) |

Errors never close the connection; clients may keep the socket and continue.

## Versioning

v1 is intentionally minimal. Additive changes (new commands, new fields in
`state`) will not be signaled; clients must ignore unknown fields. Breaking
changes would introduce an explicit version handshake first.
