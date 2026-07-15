# Plan 008: Soundboard (one-shot sound effects panel)

> **Scope note**: User-requested feature plan, executed interactively (like
> Plan 007). Phases are ordered so each ends green and committed. Update this
> plan's status row in `plans/README.md` as phases land. This realizes the
> "One-shot soundboard effects" direction finding from the original audit.

## Status

- **Feature**: A collapsible/resizable/pop-out-able panel docked below the main
  content holding named boards of buttons that play short sound effects
  **concurrently** with whatever scene/playlist is playing
- **Priority**: Feature (user-requested)
- **Effort**: M–L (five phases; the dock shell and the grid drag-reorder are the
  only genuinely novel UI work — everything else is templated on playlists)
- **Risk**: LOW-MED — almost entirely additive (new `app/soundboard/` module,
  new tables, one dock hook + teardown hook in `MainWindow`); no changes to
  scene/playlist playback logic. The one open risk is macOS `QDockWidget`
  float behavior (spiked first, with a documented fallback).
- **Depends on**: none
- **Planned at**: commit `6d6a3cc`, 2026-07-15, branch `main`
- **Baseline**: `venv/bin/pytest tests/ -q` → **572 passed**
- **Branch**: `feature/soundboard` off `main`
- **Status**: ✅ DONE (all 5 phases, 2026-07-15, on `feature/soundboard`;
  awaiting user merge)

## Execution outcome (2026-07-15)

All five phases completed on `feature/soundboard` in one day, one commit
per phase plus fixes: plan (`aaa61c8` on main) → Phase 1 dock shell
(`38c382c`) + collapsed-width fix (`7725517`) + first-pop-out geometry
(`a626916`) → Phase 2 data layer (`88f4741`) → Phase 3 playback core
(`4915c43`) → Phase 4 refactors (`d461048`) + board UI (`f902586`) +
icon tint (`1c9e971`) → Phase 5 drag-reorder (final commit). Suite
**572 → 649** (77 new tests); ruff format/check + mypy green throughout.
(Note: the "655" quoted in the Phase 4 commit message was a miscount;
640 was the true post-Phase-4 count.)

Both spikes PASSED and are recorded inline (Phase 1: QDockWidget float on
macOS — no splitter fallback needed; Phase 3: 64 concurrent players clean —
no caps introduced). Each phase was also verified live against the real
app on macOS (scripted QTimer drives + screenshots), including real audio
trigger/cut-over/toggle-stop and a simulated drop persisting a reorder.

Notable deviations from / additions to the original plan:

- **First-ever pop-out gets a distinct default geometry** (70% of the main
  window width, centered): Qt floats a dock at its docked footprint, which
  was visually indistinguishable from staying docked (user-reported).
- **Collapse pins content to zero height instead of hiding it**: a hidden
  content widget caps QDockWidget's max width at the title bar's sizeHint,
  shrinking the collapsed dock out of its full-width span (user-reported).
- **Latent PyQt6 bug found in the relocated FlowLayout**:
  `expandingDirections` returned PyQt5-style `Qt.Orientations(...)`, which
  doesn't exist in PyQt6 and aborts the process when raised inside the
  C++-called override. Never triggered from inside scroll areas (tag
  badges); the soundboard grid is the first top-level use. Fixed.
- Icon visibility: bundled feather SVGs render `currentColor` as black via
  QIcon; the five new icons + `plus.svg` are tinted `#A1ADBE`.
- The duplicated dark QComboBox stylesheet was hoisted to
  `Styles.combobox_style()` (GetInfoDialog now shares it).

## Goal

1. **Always-available panel** below the main interface (peer of the top bar,
   not a tab): collapsible to a single title-bar line, resizable by dragging
   its top edge (main content above shrinks/grows), and pop-out-able into a
   separate window (removed from the main window while popped out; closing the
   pop-out re-docks it).
2. **Multiple named soundboards**, switched via a combo box; create via a "+"
   dialog (name + track picker with the standard search/tag filters), edit via
   the same dialog (already-added tracks indicated the same way the playlist
   add-tracks dialog does).
3. **Button grid** that fills left-to-right and wraps to the next row based on
   panel width (dynamic column count). Each cell: the trigger button plus a
   grabber (≡) for drag-reorder, insert-style (drop shifts the target cell
   down-list), with a trailing empty cell as an always-available "move to end"
   drop target.
4. **One-shot playback, concurrent with scenes/playlists** — pressing a button
   never touches the scene/playlist mutual-exclusivity chain. Master volume
   applies. Per-button volume in v1. Within the soundboard itself, **at most
   one sound plays at a time**.

## Decided UX (from planning Q&A, 2026-07-15)

- **Panel shell = `QDockWidget`** in the bottom dock area (MainWindow is a
  `QMainWindow`; the dock separator gives drag-top-edge resize natively, and
  floating gives pop-out natively). Custom title bar via `setTitleBarWidget`.
  Fallback if the macOS float spike fails: hand-rolled vertical `QSplitter`
  panel + reparent-to-top-level pop-out (see Phase 1 STOP condition).
- **One soundboard sound at a time** (decided in follow-up discussion,
  superseding the earlier per-button-player answer): the soundboard owns a
  **single dedicated player slot**. Pressing a button while a *different*
  sound plays hard-stops it (instant, no fade) and plays the new one.
  Pressing the *same* button while its sound plays **stops it** (play/stop
  toggle — the common soundboard idiom). No polyphonic overlap in v1
  (recorded as deferred).
- **Per-button volume in v1**, stored on `soundboard_buttons.volume`, exposed
  via a right-click context menu `VolumeSlider` on the button cell (same
  commit-on-release contract as playlist tracks).
- **Pop-out is a normal window** (not always-on-top; a pin toggle is deferred).
  Closing the pop-out window re-docks the panel — it can never be closed away
  entirely (the "always visible" contract; the pop-out is the one caveat).
  The **first-ever pop-out defaults to ~70% of the main-window width,
  centered over it** (added during Phase 1: Qt floats a dock at its docked
  footprint, which is visually indistinguishable from staying docked); after
  that, the user's floating geometry is preserved.
- **Stop button** — stops the current soundboard sound (only one can play),
  without touching the scene/playlist. Lives in the controls row (below),
  not the title bar. Mostly redundant with same-button toggle-stop, but it's
  a fixed mouse target that works without finding the lit button. Proposed
  during planning and not objected to; flag at review if unwanted.
- **Playing feedback**: the playing button highlights (at most one lit at a
  time); highlight clears on `end_reached`/stop/cut-over.
- **Title bar is minimal and identical collapsed/uncollapsed** (clarified
  2026-07-15): `[“Soundboard” title] … [collapse/expand arrow] [pop-out ⧉]`
  — nothing else. All board controls live **inside the panel content**.
- **Controls row = sticky content header**: the first line inside the panel
  is `[board combo] [+ add] [✎ edit]` left-aligned, `[Stop]` right — laid
  out *outside* the grid's `QScrollArea` so it stays visible while the
  button grid scrolls (same pattern as the scene editor's fixed header above
  its scrolling track list).
- **Grid fill**: left-to-right reading order, wrapping (interpreted from
  "filling in from the right"; flag if right-aligned fill was actually meant).
- **Same track twice on one board**: disallowed (`UNIQUE(soundboard_id,
  audio_file_id)`), matching playlists and enabling the dialog's
  `disabled_track_ids` "Already added" treatment.

## Architecture decisions (settled)

- **Concurrency is deliberate non-integration**: the soundboard never calls
  `stop_all_playback` on scenes/playlists, never sets
  `MainWindow._current_playing_type`, and does not connect into the
  `playback_state_changed` exclusivity handlers (`main_window.py`
  `_on_scene_playback_changed` / `_on_playlist_playback_changed`). It is a
  third, independent player pool.
- **Master volume is free**: `TrackPlayer` registers with `AudioEngine`'s
  `WeakSet`, and the engine's `master_volume` setter fans out to every
  registered player. No engine changes needed.
- **Playback core = `SoundboardPlayer(QObject)`** in
  `app/audio/soundboard_player.py`: a **single-slot** player, not a pool. It
  tracks `_current_button_id` and one live `TrackPlayer`.
  `trigger(button_id, file_path, volume)`: same button playing → stop
  (toggle); otherwise hard-stop the current sound and play the new one.
  Also `stop()`, `set_current_volume()`, `clear()`. Signals:
  `button_started(int)`, `button_stopped(int)` (drive the highlight).
  Implementation note: `TrackPlayer` binds its media at construction, so the
  slot **recreates a `TrackPlayer` per press** and releases the old one
  (Plan 001's detach-before-release path makes this safe; only one is ever
  live). If per-press churn proves audible/costly, the alternative is adding
  a `load(file_path)` media-swap to `TrackPlayer` — deferred unless needed.
  The soundboard's capacity cost is therefore structurally **exactly one
  player slot**, idle or playing.
- **No player cap; empirical capacity spike instead.** libVLC has no
  documented hard limit on concurrent `MediaPlayer` instances (the ceiling is
  practical: CPU/memory/CoreAudio), and the codebase enforces no cap today
  (`SceneMixer` is unbounded). Phase 3 includes a cheap spike measuring
  8/16/32/64 concurrent `TrackPlayer`s on the target machine; a scene-track
  cap of (ceiling − 1) is added at the UI/validation layer **only if** the
  spike reveals a real problem — otherwise deliberately not introduced.
- **DB schema copies the playlists pattern** (additive `CREATE TABLE IF NOT
  EXISTS` in `schema.sql`; per the alpha convention, no migration code needed
  for new tables):
  - `soundboards`: `id`, `name`, `created_at`, `updated_at` — **no
    `position`** (decided 2026-07-15): the combo has no reorder UI, so
    boards list alphabetically (`ORDER BY name COLLATE NOCASE`). If manual
    ordering is ever wanted, an added column is a trivial additive
    migration.
  - `soundboard_buttons`: `id`, `soundboard_id` (FK cascade),
    `audio_file_id` (FK cascade), `position`, `volume REAL DEFAULT 1.0`,
    `UNIQUE(soundboard_id, audio_file_id)`, index on
    `(soundboard_id, position)`
  - Dataclasses `Soundboard` / `SoundboardButton` in `models.py`, mirroring
    `Playlist` / `PlaylistTrack` (button carries its `AudioFile`).
- **CRUD mirrors the playlist methods** in `DatabaseConnection`:
  `add_soundboard` (plain insert — no position bump),
  `get_soundboard`, `get_all_soundboards` (alphabetical),
  `update_soundboard` (rename), `delete_soundboard`,
  `add_button_to_soundboard` (append via `MAX(position)+1`),
  `remove_soundboard_button`, `reorder_soundboard_buttons`,
  `update_soundboard_button_volume`, `get_soundboard_buttons` (JOIN
  `audio_files`, batch-load tags like `get_playlist_tracks`).
- **UI module `app/soundboard/`**: `SoundboardPanel` (dock content: selector
  row + grid), `SoundboardTitleBar` (custom dock title bar),
  `SoundboardGrid` + `SoundboardButtonCell` (grid container + cell),
  `SoundboardEditDialog` (create/edit: name field + track picker).
- **Track-picker reuse via extraction**: `AudioFileSearchDialog` owns the
  search box + tag filter + selectable file list + preview player. Extract
  that body into an `AudioFileSearchWidget` (mechanical refactor;
  `AudioFileSearchDialog` becomes a thin shell around it — behavior and
  public API byte-identical, existing tests must stay green). The soundboard
  dialog composes: name `QLineEdit` on top + the widget below, honoring
  `disabled_track_ids` for edit mode.
- **`FlowLayout` moves to `app/shared/layouts.py`** (it currently lives in
  `app/library/tag_manager.py`; the move is mechanical — `tag_manager` and
  `tag_selection_dialog` import from the new home). It already implements
  width-based wrapping (`heightForWidth`, hidden-widget skipping) and is the
  grid layout for the button cells.
- **Persistence**: QSettings group `soundboard` — `last_board_id`,
  `collapsed`, `expanded_height` (restored on un-collapse). Dock geometry /
  floating state via `QMainWindow.saveState()`/`restoreState()` stored under
  `ui/window_state` (requires `setObjectName` on the dock — a documented
  saveState prerequisite). MainWindow doesn't call save/restoreState today;
  adding it is safe (no toolbars/other docks exist).
- **Dock constraints**: `setAllowedAreas(BottomDockWidgetArea)` only; no
  built-in close/float buttons (custom title bar replaces them); the floating
  window's close event re-docks (`setFloating(False)`) instead of hiding.
- **Empty-state**: with zero soundboards, the panel shows a hint + the "+"
  button (same spirit as the playlist editor empty label).
- **Teardown**: `MainWindow.closeEvent` additionally calls
  `soundboard_player.clear()` before `audio_engine.release()`.
- **Remote control**: out of scope for v1, but the design keeps it purely
  additive later — facade methods (`get_soundboards`, `trigger_sound
  (button_id)`, `stop_sound`) + `server.py` `_commands` entries +
  protocol doc rows, exactly the extension seam Plan 007 built.

## Phases

### Phase 1 — Dock shell (placeholder content)

The novel-risk phase, so it goes first and starts with a spike.

- **Spike (first task)**: minimal `QDockWidget` in the bottom area with a
  custom title bar on macOS — verify: separator drag-resize works with a
  custom title bar; `setFloating(True)` produces a sane normal window;
  closing the float re-docks; `saveState` round-trips geometry.
  **STOP condition**: if floating is broken/ugly on macOS (known quirk area),
  stop and switch this phase to the fallback design (vertical `QSplitter` +
  reparent pop-out); record the decision here before continuing.
  **Spike result (2026-07-15): PASS** — verified live on macOS (real Cocoa
  windowing, scripted QTimer drive + screenshots): separator drag-resize
  works with the custom title bar, `setFloating(True)` yields a clean
  Qt-drawn floating window, `close()` re-docks, collapse pins to the title
  line. QDockWidget design confirmed; splitter fallback not needed. One
  fix out of the spike: bundled feather SVGs use `stroke="currentColor"`,
  which QIcon renders black — the four new icons are tinted `#A1ADBE`
  (TEXT_MUTED) directly in the SVG.
- Build `SoundboardTitleBar`: "Soundboard" label, collapse/expand arrow
  toggle, pop-out button — that's its final form; all board controls belong
  to the content (Phase 4). Dark-theme styling in `styles.py`.
- Collapse = hide the content widget and pin the dock to title-bar height;
  expand restores `expanded_height`. Collapsed state + height persisted
  (QSettings `soundboard` group); dock geometry via
  `saveState`/`restoreState` in MainWindow.
- Content is a placeholder widget this phase.
- **Tests** (`tests/test_soundboard_panel.py`, offscreen `qapp` fixture):
  collapse/expand toggles content visibility and persists state; pop-out sets
  floating and close-refloat re-docks; settings round-trip. (Precedent:
  Plan 005 drives a real MainWindow offscreen.)
- **Commit point**: dock shell green; app shows a collapsible, floatable
  placeholder panel.

### Phase 2 — Data layer

Independent of Phase 1 (can be built in parallel if convenient).

- `schema.sql`: `soundboards` + `soundboard_buttons` tables as decided above.
- `models.py`: `Soundboard`, `SoundboardButton` dataclasses.
- `DatabaseConnection`: the CRUD set listed in decisions, copying the
  playlist implementations (boards: plain insert, alphabetical listing;
  buttons: `MAX(position)+1` append).
- **Tests** (`tests/test_soundboard_db.py`): CRUD round-trips, cascade
  deletes (board delete removes buttons; audio-file delete removes its
  buttons), button reorder persistence, alphabetical board ordering
  (case-insensitive), volume update, unique constraint, tag batch-loading
  on `get_soundboard_buttons`.
- **Commit point**: data layer green; no UI change.

### Phase 3 — One-shot playback core + capacity spike

- **Capacity spike (first task, cheap)**: a throwaway script spinning up
  8/16/32/64 concurrent `TrackPlayer`s with real audio, watching for
  glitches, CPU, and VLC errors on the target machine. Record the observed
  practical ceiling **in this plan**. Decision rule: no problem at realistic
  counts → no caps anywhere (status quo); problem found → cap scene track
  count at (ceiling − 1) at the UI/validation layer as a follow-up item.
  **Spike result (2026-07-15): no practical ceiling found.** Near-silent
  WAVs, 6s measured window per fleet on the target Mac: 8 → 9% CPU,
  16 → 13%, 32 → 25%, 64 → 45% (of one core); at every size all players
  reported Playing with positions advancing and zero VLC Error states.
  Decision: **no caps anywhere** — scenes stay unbounded, and the
  soundboard's one-slot design costs a single player regardless.
- `app/audio/soundboard_player.py`: single-slot `SoundboardPlayer` per the
  settled design (cut-over hard stop, same-button toggle-stop, per-button
  volume applied on trigger, `stop()`, started/stopped signals, `clear()`).
- `end_reached` → emit `button_stopped` and release the player (natural end
  empties the slot).
- **Tests** (`tests/test_soundboard_player.py`, patterned on
  `test_mixer.py` — mock the `TrackPlayer` boundary; `qapp` fixture):
  trigger plays with button volume, different-button press stops old + plays
  new, same-button press stops (toggle), natural end empties the slot and
  emits `button_stopped`, `stop()`/`clear()` release the player, signal
  ordering on cut-over (old stopped before new started).
- **Commit point**: playback core green; still not user-visible.

### Phase 4 — Board UI (selector, dialog, grid, playback wiring)

- Extract `AudioFileSearchWidget` from `AudioFileSearchDialog` (mechanical;
  dialog behavior unchanged, existing tests stay green).
- Move `FlowLayout` to `app/shared/layouts.py` (mechanical).
- `SoundboardEditDialog`: name field + search widget; create mode (empty
  name, no disabled ids) and edit mode (prefilled name,
  `disabled_track_ids` = current buttons' audio-file ids). Additions append;
  removal is **not** in this dialog — it's a context-menu action on the cell.
- `SoundboardPanel` real content: a fixed controls row — board combo (loads
  `get_all_soundboards`, restores `last_board_id`), "+" and "✎" buttons
  driving the dialog, Stop button — above a `QScrollArea` holding the
  `SoundboardGrid` of `SoundboardButtonCell`s (`FlowLayout`), so the
  controls stay visible while the grid scrolls; empty-state hint. Combo
  selection is always tracked/restored **by board id, never by index**
  (alphabetical ordering means a rename can move a board in the list; the
  renamed board must remain the selected one after refresh).
- `SoundboardButtonCell`: trigger button (track `display_title`) + grabber
  (≡, inert until Phase 5); pressed → `SoundboardPlayer.trigger` (which
  handles cut-over/toggle); highlight bound to
  `button_started`/`button_stopped`; context menu with `VolumeSlider`
  (commit-on-release → `update_soundboard_button_volume`, live →
  `set_current_volume` if that button is playing) and "Remove from board".
- Board switch / board delete calls `clear()`.
- MainWindow: instantiate `SoundboardPlayer`, wire teardown in `closeEvent`.
  Explicitly no wiring into the exclusivity handlers.
- Update `CLAUDE.md` module layout + `README.md` feature list briefly.
- **Tests** (`tests/test_soundboard_widget.py`): dialog create/edit flows
  (mocked exec), combo populates/persists selection, rename keeps the
  renamed board selected despite its alphabetical position changing,
  trigger dispatches to player with button volume, highlight follows
  signals (and moves on cut-over), Stop button stops, remove/volume context
  actions hit the DB, empty state.
- **Commit point**: soundboard fully usable end-to-end (manual check with
  `./run.sh`: SFX over a playing scene, cut-over between buttons,
  same-button stop, master volume affects both, Stop leaves the scene
  playing).

### Phase 5 — Drag-reorder in the grid

- Grabber starts a `QDrag` with custom MIME
  `application/x-soundmanager-soundboard-button` carrying the button id
  (pattern: `PlaylistTrackItem`, `playlist_editor.py`).
- `SoundboardGrid` accepts drops; `_index_for_pos(x, y)` maps a drop point to
  an insert index in the wrapped flow (row by y-bands, column by midpoint —
  the 2D analog of `_index_for_y`); always keep one trailing empty cell as
  the "append" target; insert semantics shift subsequent cells down-list.
- Persist via `reorder_soundboard_buttons`, then refresh.
- **Tests**: extend `tests/test_soundboard_widget.py` — `_index_for_pos`
  math across wrap boundaries and the trailing cell; `order_changed` →
  DB reorder call.
- **Commit point**: feature complete.

## Risks & gotchas

- **macOS `QDockWidget` float quirks** — the reason Phase 1 leads with a
  spike and a written STOP condition. Do not sink time into styling before
  the spike passes.
- **QDockWidget sizing on collapse** is finicky: constrain via the content
  widget (hide + `setFixedHeight` on the dock), and always restore max-height
  bounds on expand, or the dock can get stuck un-resizable.
- **`saveState` silently no-ops without `setObjectName`** on the dock —
  set it and assert it in tests.
- **PyQt slot exceptions abort the process** (Plan 007 lesson): button
  trigger and drag handlers must not raise (missing file → log via
  `structlog` + skip, matching Plan 002's missing-file behavior).
- **VLC player lifecycle**: the single slot recreates a `TrackPlayer` per
  press; every release must go through `TrackPlayer`'s
  detach-before-release path (Plan 001). Rapid button-mashing is the stress
  case — the spike/manual check should include it. If per-press
  create/release is ever audible or costly, fall back to a `load()`
  media-swap on one persistent player (recorded in decisions).
- **Space-bar collision**: a focused soundboard `QPushButton` swallows
  Space, which the app-level event filter uses for global play/pause. Set
  `NoFocus` on trigger buttons (precedent: `master_slider`).
- **`AudioFileSearchWidget` extraction** touches the library import dialog
  path — keep it byte-compatible; the existing dialog tests are the guard.
- **FlowLayout drag hit-testing** near wrap boundaries is the fiddliest part
  of Phase 5 — cover it with pure-math unit tests, not just integration.
- **py2app**: `setup.py` `includes` needs `app.soundboard` (Plan 007 hit the
  same omission with `app.playlists`).
- **CI gates**: `ruff format --check`, `ruff check`, and `mypy app/` (0
  errors) are all blocking — run all three per phase, not just pytest.

## Deferred (recorded, not v1)

- **Stream Deck / remote API integration** (facade `trigger_sound` /
  `stop_sound` / `get_soundboards`, server commands, protocol rows,
  plugin actions) — explicitly deferred by the user; the seam is ready.
- **Polyphonic / multiple simultaneous soundboard sounds** (per-button or
  per-board overlap toggle) — v1 is strictly one-at-a-time.
- **Fade or crossfade on cut-over / stop** — v1 is hard stop by design.
- **Scene track-count cap** — only if the Phase 3 capacity spike shows a
  real ceiling; deliberately not introduced otherwise.
- **Keyboard shortcuts / hotkeys** for buttons.
- **Always-on-top pin** on the pop-out window.
- **Button customization** (color, custom label, icon).
- **Per-button loop toggle** (long ambience belongs in scenes, but a looping
  soundboard button has come up in other tools).
- **Manual soundboard ordering in the combo** — v1 is alphabetical; a
  `position` column is a trivial additive migration if ever wanted.
