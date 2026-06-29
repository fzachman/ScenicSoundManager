# Plan 006: De-duplicate the scene control cards (DEBT-01)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If
> anything in the "STOP conditions" section occurs, stop and report — do not
> improvise. Update this plan's status row in `plans/README.md` when done.
>
> This plan is optimized for the **best end result**, not for being
> interruptible — the operator will execute it in stable conditions. Phases are
> still ordered so each ends green and committed (good hygiene + easy review),
> but none are "optional" or "abandonable": the goal is the full refactor.
>
> **Drift check (run first)**:
> `git diff --stat e3f7de3..HEAD -- app/scenes/track_control.py app/scenes/playlist_entry_control.py app/scenes/scene_editor.py tests/test_track_control.py tests/test_playlist_entry_control.py app/shared/`
> If any in-scope file changed since this plan was written (`e3f7de3`), compare
> the "Current state" / line references below against the live code before
> proceeding; on a material mismatch, treat it as a STOP condition.

## Status

- **Finding**: DEBT-01
- **Priority**: P2
- **Effort**: M (~1.5 focused days; the characterization suite is ~40% of it)
- **Risk**: MED (live-audio-adjacent UI; two classes ~80% untested today)
- **Depends on**: none (PERF-02 already landed the `volume_committed` split this
  refactor absorbs; Plan 005's MainWindow exclusivity tests are an unrelated
  safety net and need not change)
- **Category**: tech-debt / maintainability
- **Planned at**: commit `e3f7de3`, 2026-06-25, branch `experimental-improvements`
- **Baseline**: `venv/bin/pytest tests/ -q` → **197 passed** (~1s)
- **Status**: ✅ DONE (2026-06-29, branch `advisor/006-dedupe-control-cards`)

## Execution outcome (2026-06-29)

All phases completed. Commits (in order): characterization tests →
`VolumeSlider` → `SceneControlCard` base → TrackControl migration →
PlaylistEntryControl migration → adversarial-review fixes → docs. Suite **197 →
243**; ruff + format clean; mypy held at the 202-error baseline (zero new on
touched files); `scene_editor.py` byte-unchanged; all public contracts
preserved.

Adversarially reviewed via the Codex skeptic/architect/minimalist lenses —
**verdict PASS** (no high-severity findings). Accepted findings folded in: a
shared `_build_play_button()`, an explicit construction-protocol docstring on the
base, removal of the speculative `VolumeSlider.value()/set_value()` and the
package-level export, and tighter remove/volume tests. One finding was recorded
as an out-of-scope follow-up (see below); the hook-layer minimalism finding was
rejected (the hooks encode genuine, characterization-tested divergences).

**Follow-up (pre-existing, NOT introduced here):** the live volume slots in
`scene_editor.py` (~lines 293/373/438/530) and `mixer.py` convert the 0-1 float
to a 0-100 int with `int(volume*100)`, truncating one step low for some values
(0.29 → 28). The new base uses `round()` for the control's own push (preserving
old behavior exactly), so this refactor neither caused nor worsened it.
Harmonizing all volume conversions to `round()` is a small standalone fix,
deliberately left out of this behavior-preserving refactor.

## Why this matters

`app/scenes/track_control.py` (`TrackControl`, 328 lines) and
`app/scenes/playlist_entry_control.py` (`PlaylistEntryControl`, 293 lines) are
two `QFrame` "scene control card" widgets that share a large common skeleton.
The structural diff (see `Current state`) found these are **identical or
near-identical** between the two:

- 5 signals: `volume_changed(int,float)`, `volume_committed(int,float)`,
  `repeat_changed(int,bool)`, `play_mode_changed(int,bool)`, `remove_requested(int)`.
- The entire volume row (Vol label + 0–100 slider + percent label) and the
  commit-on-release handlers PERF-02 added (`_on_volume_changed` /
  `_on_volume_released`, gated on `isSliderDown()`).
- The play toggle (`_toggle_play` / `set_play_mode`), the repeat toggle
  (`_toggle_repeat` / `_update_repeat_button` — `_update_repeat_button` is
  byte-identical), and the play-mode restyle skeleton.
- All four drag-drop / context-menu methods (`contextMenuEvent`,
  `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent`), differing only by a
  MIME-type literal and which id attribute they read.

Every bug fixed in one (e.g. the PERF-02 in-memory-staleness fix, or the
commit-on-release behavior) has to be hand-mirrored in the other — PERF-02
itself flagged that it copy-pasted the new two-signal volume API into both
controls. This refactor establishes a single source of truth for the shared
plumbing while leaving the genuinely-divergent parts per-class.

## Target end-state (architecture)

```
app/shared/volume_slider.py
    VolumeSlider(QWidget)                 # reusable: Vol label + 0-100 slider + % label
        signals: changed(float), committed(float)   # 0-1; commit-on-release owned here
        .slider (inner QSlider), .value_label, value(), set_value()

app/shared/base_control_card.py
    SceneControlCard(QFrame)              # mirrors app/shared/base_list_widget.py convention
        signals (hoisted): volume_changed, volume_committed, repeat_changed,
                           play_mode_changed, remove_requested
        class attr: MIME_TYPE: str = ""  (overridable)
        abstract hooks: _model (property), _entity_id (property),
                        _active_card_style(), _inactive_card_style()
        overridable hooks (default no-op): _on_volume_applied(value),
                        _on_repeat_applied(), _after_play_mode_update()
        owns: _init_card_state(); _build_volume_row() -> VolumeSlider;
              _on_volume_changed/_on_volume_released; _build_repeat_button();
              _toggle_repeat; _update_repeat_button; _toggle_play; set_play_mode;
              _update_play_mode_ui (template); contextMenuEvent;
              mousePressEvent/mouseMoveEvent/mouseReleaseEvent

app/scenes/track_control.py
    TrackControl(SceneControlCard)        # keeps: player cluster, position row,
        file-missing indicator, SUCCESS-accent styles, _on_volume_applied/_on_repeat_applied
        (player pushes), MIME_TYPE='application/x-soundmanager-track', _setup_ui assembly

app/scenes/playlist_entry_control.py
    PlaylistEntryControl(SceneControlCard) # keeps: shuffle cluster + shuffle_changed,
        'PL' badge, now-playing label + set_current_track, track-count info label,
        PRIMARY-accent styles, MIME_TYPE='application/x-soundmanager-scene-playlist',
        _setup_ui assembly
```

**Why a component *and* a base** (not one or the other): the volume row is the
one byte-identical, independently-reusable, best-tested strand — extracting it
as `VolumeSlider` makes it cleanly unit-testable and reusable beyond these two
cards (the master-volume slider in `app/main_window.py` is a future candidate —
see Maintenance notes). The base class then absorbs the *rest* of the common
surface (drag/context/toggles/signals) and composes `VolumeSlider` for its
volume row. Each abstraction does one job; neither is forced to carry the
other's concern.

## The complete public contract to preserve

The **only** production consumer of either control is `app/scenes/scene_editor.py`
(plus the two unit-test files). Nothing else in the repo imports them. The
refactor MUST keep every item below byte-stable; each is relied on by a named
call site.

**`TrackControl`** (`app/scenes/track_control.py`):
- Constructor: `TrackControl(track: SceneAudioFile, player: TrackPlayer | None = None, parent=None)`
  — `player` optional & positional. Called `TrackControl(track, player)` at
  `scene_editor.py:191`.
- Signals: `volume_changed(int,float)`, `volume_committed(int,float)`,
  `repeat_changed(int,bool)`, `play_mode_changed(int,bool)`, `remove_requested(int)`.
- Public methods: `set_player(player)` (called `scene_editor.py:534`);
  `set_play_mode(play_mode)` (parity API, no current caller — keep, must NOT emit).
- Public attrs: `.track` (read as `control.track.id` at `scene_editor.py:661`),
  `.player` (identity-compared at `scene_editor.py:533`).
- Drag MIME: `'application/x-soundmanager-track'` = `str(track.id)`. **This exact
  string is consumed by `TrackListContainer.dropEvent` (`scene_editor.py:664-699`)
  for track reordering — a typo silently breaks reorder.**
- Behavior: `volume_changed` fires every slider tick; `volume_committed` only on
  release / discrete change. `_on_volume_changed` also pushes
  `player.target_volume = value` on every tick when a player is set.

**`PlaylistEntryControl`** (`app/scenes/playlist_entry_control.py`):
- Constructor: `PlaylistEntryControl(entry: ScenePlaylistEntry, parent=None)` —
  **no player arg**. Called `PlaylistEntryControl(entry)` at `scene_editor.py:225`.
- Class const: `MIME_TYPE = 'application/x-soundmanager-scene-playlist'`
  (currently emitted-but-unconsumed — no drop handler exists; keep stable).
- Signals: the 5 above **plus** `shuffle_changed(int,bool)` (unique).
- Public methods: `set_current_track(title)` (called `scene_editor.py:399,401,407,416`);
  `set_play_mode(play_mode)` (parity, no caller — keep, must NOT emit).
- Public attr: `.entry` (id used as dict key; fields `volume/is_shuffle/is_repeat/
  play_mode` mutated live by scene_editor slots).
- Behavior: same volume split; **no** player branch.

`scene_editor.py` connects to the controls' **class signals**, not to inner
widgets — so if signals + methods + attrs are preserved, **`scene_editor.py`
needs zero changes**. The signal→slot map (for reviewer reference): track
`volume_changed→_on_track_volume_changed` (live mixer only),
`volume_committed→_on_track_volume_committed` (`db.update_scene_track_setting`),
`repeat_changed`, `play_mode_changed`, `remove_requested`; entry analogues plus
`shuffle_changed`.

## Current state (key files)

- `app/scenes/track_control.py` — `TrackControl(QFrame)`. Volume widgets+handlers
  at 130-155 / 189-213; toggles at 182-187, 275-288; `_update_play_mode_ui`
  256-273; player cluster 167-180, 215-248; drag/context 290-327; imports `os`
  for the file-missing check (76-83).
- `app/scenes/playlist_entry_control.py` — `PlaylistEntryControl(QFrame)`. Volume
  107-134 / 176-192; toggles 202-243 (incl. shuffle 231-236, 245-249);
  `_update_play_mode_ui` 215-229; drag/context 257-292; `MIME_TYPE` at 33.
- `app/shared/base_list_widget.py` — the existing base-widget precedent
  (`QWidget`, template-method with `NotImplementedError` hooks, subclassed by
  `SceneListWidget`/`PlaylistListWidget`). **Mirror its conventions**: one base
  per module, `base_<thing>.py`, in `app/shared/`, abstract hooks grouped under a
  `# --- Abstract methods ... ---` comment.
- `app/shared/styles.py` — all styling is `@staticmethod` on `Styles`, called as
  `Styles.X(...)`: `card_frame_style(selector, accent_color=, border_color=,
  background_color=)`, `play_button_style(size=)`, `play_button_inactive_style(size=)`,
  `icon_toggle_button_style(active, size=)`, `subtle_text_style(size=)`,
  `title_style(size=)`. Call signatures do NOT change; only the call sites move.
- `app/shared/__init__.py` — exports dialogs/logging/styles. `base_list_widget`
  is NOT exported (imported directly from its module). Follow that: import the
  new classes directly from their modules. (You MAY add `VolumeSlider` to
  `__all__` for discoverability since it's a reusable component — low risk, it
  depends only on `Styles`.)
- `tests/conftest.py` — sets `QT_QPA_PLATFORM=offscreen` at import; provides a
  session-scoped `qapp` fixture. Every widget test requests `qapp`.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Full suite | `venv/bin/pytest tests/ -q` | 197 pass at baseline; grows as tests are added; never regresses |
| One control's tests | `venv/bin/pytest tests/test_track_control.py -v` | all pass |
| New component tests | `venv/bin/pytest tests/test_volume_slider.py -v` | all pass |
| Lint | `venv/bin/ruff check app/ tests/` | clean |
| Format check | `venv/bin/ruff format --check app/ tests/` | clean |
| Types (advisory) | `venv/bin/mypy app` | no NEW errors on touched files |

Use the venv pytest, not a global one. DX-01 wired ruff/mypy/CI — keep new files
lint-clean and formatted (`ruff format` them before committing).

## Scope

**In scope** (files you will create or modify):
- `app/shared/volume_slider.py` (create)
- `app/shared/base_control_card.py` (create)
- `app/shared/__init__.py` (optional: export `VolumeSlider`)
- `app/scenes/track_control.py` (migrate onto base + VolumeSlider)
- `app/scenes/playlist_entry_control.py` (migrate onto base + VolumeSlider)
- `tests/test_track_control.py` (expand: characterization)
- `tests/test_playlist_entry_control.py` (expand: characterization)
- `tests/test_volume_slider.py` (create)
- `tests/conftest.py` (only if you place the fake player / fixtures here)
- `plans/README.md` (status row + finding annotation)

**Out of scope** (do NOT touch):
- `app/scenes/scene_editor.py` — must require **zero** changes. If you find
  yourself editing it, a contract was broken — STOP and reconsider.
- `app/main_window.py` master-volume slider — a future reuse candidate, not this
  plan.
- The `shuffle_changed` signal, the `MIME_TYPE` strings, and the
  emit-vs-no-emit asymmetry of `set_play_mode` vs `_toggle_play` — preserve
  exactly, do not "clean up".

## Git workflow

- Branch off the current branch: `advisor/006-dedupe-control-cards`.
- One commit per phase (messages suggested per phase below); imperative style
  matching repo history.
- Do NOT push or open a PR unless the operator asks.

---

## Phase 0 — Baseline (no code change)

Confirm a clean starting point so later phases have something to diff against.

- `venv/bin/pytest tests/ -q` → **197 passed**.
- `venv/bin/ruff check app/ tests/` → clean. `venv/bin/mypy app` → record the
  current advisory error count (baseline; must not grow on touched files).

**STOP** if the baseline suite is not green — a broken baseline is not yours to
fix here.

---

## Phase 1 — Characterization tests (pin ALL current behavior first)

**No production code changes.** Today only the volume-commit split (~20%) is
tested; this phase pins the rest so every later phase is provably
behavior-preserving. This is the largest phase and the safety net the whole
refactor leans on — do it thoroughly.

### Test mechanics (read before writing a single test)

1. **Request `qapp`** in every widget-constructing test (offscreen platform).
2. **Never call `contextMenuEvent` or `mouseMoveEvent` directly** — `menu.exec()`
   and `drag.exec()` block on a real event loop and will hang the suite. Drive
   the inner logic instead (call the handler, build the `QMimeData` yourself, or
   `action.trigger()` on a menu you construct without `exec`).
3. **Never instantiate the real `TrackPlayer`** (it touches the VLC
   `AudioEngine`). Use the `FakeTrackPlayer` below.
4. **Pin observable behavior, NOT internal attributes the refactor relocates.**
   Specifically: assert via the **class signals**, the **model object** mutation,
   and `control.volume_slider` state. Do **not** assert on
   `control.volume_value_label` — that percent label moves into `VolumeSlider`
   in Phase 2 and would make the safety net fight the refactor. (`control.volume_slider`
   survives: Phase 4/5 keep it as an alias to the inner slider — see Phase 2.)
5. **Style assertions stay coarse**: assert `widget.styleSheet() == Styles.X(...)`
   (the exact call output), not parsed CSS — so cosmetic-neutral refactors
   survive but branch swaps are caught. `_update_play_mode_ui` styling stays
   per-class through this refactor, so these are safe to pin.
6. **Highest-value pins are exactly-once signal counts** — the likeliest
   regression is a dropped or doubled `emit`. Reuse the established `_capture`
   recorder pattern already in both test files.

### FakeTrackPlayer (test double)

Add to `tests/test_track_control.py` (or `tests/conftest.py` if you prefer a
shared fixture). Must be a `QObject` subclass:

```python
from PyQt6.QtCore import QObject, pyqtSignal

class FakeTrackPlayer(QObject):
    position_changed = pyqtSignal(int)
    end_reached = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.target_volume = 0
        self.repeat = False
        self._duration = 60000
        self.set_position_calls = []

    def get_duration(self):
        return self._duration

    def set_position(self, pos):
        self.set_position_calls.append(pos)
```

### Phase 1A — Volume-strand pins (guards Phases 2–5; required)

Add to **both** test files (the 3 existing volume tests stay):

- TrackControl **with a `FakeTrackPlayer`**: during a drag
  (`volume_slider.setSliderDown(True); volume_slider.setValue(80)`), assert the
  live tick sets `player.target_volume == 80` (covers the player branch the
  current tests dodge by passing no player). Without a player, the same drag
  must not raise.
- `volume_committed` fires **exactly once** per `sliderReleased.emit()`, with the
  final value, on both controls.
- In-memory freshness: `track.volume` / `entry.volume` track the slider on both
  discrete and mid-drag changes (entry mirrors the existing track test).

### Phase 1B — Broader behavior pins (required before Phase 3+; do it now)

**TrackControl** (`tests/test_track_control.py`):
- Constructor branches: `title_label` == `display_title` with `audio_file` else
  `"Unknown"`; tooltip == `file_path` iff `audio_file`; the "⚠️ File not found"
  label is present iff `audio_file` exists and the path is missing (the
  `/fake/track.mp3` fixture does NOT exist → label currently present — pin it);
  `duration_label` == `duration_formatted` else `"--:--"`; `volume_slider.value()
  == 50` and percent shows `"50%"` for `volume=0.5`.
- Play-mode initial style: construct with `play_mode=True` vs `False`; assert
  `play_btn.styleSheet()` == `Styles.play_button_style(size=28)` vs
  `Styles.play_button_inactive_style(size=28)` and the frame stylesheet matches
  the active (SUCCESS-accent) vs `_base_style` output.
- Toggles (no player): `_toggle_play()` flips `_play_mode`, sets
  `track.play_mode`, emits `play_mode_changed(7, newval)` **once**; `_toggle_repeat()`
  flips `_repeat_mode`, sets `track.is_repeat`, emits `repeat_changed(7, newval)`
  once.
- `set_play_mode(True/False)` updates `_play_mode` + `track.play_mode` and does
  **NOT** emit `play_mode_changed` (pin the asymmetry).
- Remove: connect a recorder to `remove_requested`; build the menu's action and
  `action.trigger()` (no `exec`) — assert it emits `(7,)`.
- Drag MIME: assert `QByteArray(str(track.id).encode())` decodes to `"7"` and
  the type string is `'application/x-soundmanager-track'` (construct the
  `QMimeData` the same way the widget does; do not invoke `mouseMoveEvent`).
- Player integration (`FakeTrackPlayer`): `set_player(p)` connects
  `position_changed`/`end_reached` and applies `p.target_volume ==
  int(track.volume*100) == 50` and `p.repeat == track.is_repeat`; with a player,
  `_toggle_repeat()` flips `p.repeat`; `_on_position_pressed()` sets
  `_updating_position=True` and `_update_position(...)` no-ops while set;
  `_on_position_released()` maps slider→ms via `get_duration()` and calls
  `set_position(...)`, then clears the flag; `_update_position(ms)` (flag clear)
  sets the slider to `ms*1000/duration` and label to `m:ss`; `_on_end_reached()`
  resets slider to 0 and label to `"0:00"`.

**PlaylistEntryControl** (`tests/test_playlist_entry_control.py`, no fake player):
- Add an `entry_with_playlist` fixture (a `Playlist` with a known name and N
  `PlaylistTrack`s).
- Constructor branches: `title_label` == `playlist.name` with playlist else
  `"Unknown Playlist"`; tooltip == `"Playlist: <name>"` iff playlist;
  `info_label` == `"<n> tracks"` / `"1 track"` (singular/plural) with playlist
  else `"Unknown"`; volume widgets reflect `entry.volume` (50 / `"50%"`);
  `now_playing_label` starts hidden with empty text.
- Play-mode initial style: `play_mode=True` → `_base_style` (PRIMARY) + active
  play btn; `False` → BORDER/BACKGROUND_LIGHT card style + inactive btn.
- Toggles: `_toggle_play` → emits `play_mode_changed(9, v)` once;
  **`_toggle_shuffle`** flips `_shuffle_mode` + `entry.is_shuffle`, emits
  `shuffle_changed(9, v)` once (UNIQUE to this control, entirely untested today);
  `_toggle_repeat` → emits `repeat_changed(9, v)` once.
- `set_play_mode` updates state without emitting.
- `set_current_track("Foo")` → `now_playing_label` visible, text `"Now playing:
  Foo"`; `set_current_track("")` → hidden.
- Remove: action `trigger()` emits `remove_requested(9)`.
- Drag MIME: `PlaylistEntryControl.MIME_TYPE == 'application/x-soundmanager-scene-playlist'`
  and payload decodes to `str(entry.id)`.

**Verify**: `venv/bin/pytest tests/test_track_control.py
tests/test_playlist_entry_control.py -v` → all green against **unchanged**
production code. Full suite still 197+new green. `ruff`/`mypy` clean on the test
files.

**Commit**: `DEBT-01: characterization tests for scene control widgets`.

---

## Phase 2 — Add the reusable `VolumeSlider` component

Create `app/shared/volume_slider.py`. It owns the entire current volume row and
the commit-on-release contract; it emits **float-only** signals (the entity id
stays in the parent control, which re-emits its `(int, float)` class signals).

```python
"""Reusable volume slider with commit-on-release semantics."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from .styles import Styles


class VolumeSlider(QWidget):
    """A 'Vol:' label + 0-100 slider + percent label.

    Emits `changed` every tick (live) and `committed` only when the value
    settles — on slider release, or immediately for a discrete keyboard/wheel/
    programmatic change (when the handle is not held down). This is the
    commit-on-release contract PERF-02 introduced; persisting listeners connect
    to `committed`, live listeners (audio) connect to `changed`.
    """

    changed = pyqtSignal(float)    # 0-1, every tick
    committed = pyqtSignal(float)  # 0-1, on settle

    def __init__(self, initial_volume: float, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("Vol:")
        label.setStyleSheet(Styles.subtle_text_style(size=12))
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setValue(int(initial_volume * 100))
        self.slider.setFixedWidth(120)
        self.slider.valueChanged.connect(self._on_changed)
        self.slider.sliderReleased.connect(self._on_released)
        layout.addWidget(self.slider)

        self.value_label = QLabel(f"{int(initial_volume * 100)}%")
        self.value_label.setFixedWidth(40)
        self.value_label.setStyleSheet(Styles.subtle_text_style(size=12))
        self.value_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        layout.addWidget(self.value_label)

    def value(self) -> float:
        return self.slider.value() / 100.0

    def set_value(self, volume: float) -> None:
        self.slider.setValue(int(volume * 100))

    def _on_changed(self, value: int) -> None:
        self.value_label.setText(f"{value}%")
        volume = value / 100.0
        self.changed.emit(volume)
        if not self.slider.isSliderDown():
            self.committed.emit(volume)

    def _on_released(self) -> None:
        self.committed.emit(self.slider.value() / 100.0)
```

Notes:
- `WA_TransparentForMouseEvents` on the two labels preserves the card's
  drag-through behavior (only the slider should capture the mouse). Keep it.
- No `addStretch()` inside — the parent layout owns spacing, exactly as today.
- Optionally add `VolumeSlider` to `app/shared/__init__.py` `__all__`.

Create `tests/test_volume_slider.py` pinning the widget **in isolation** (request
`qapp`): constructor sets `slider.value()` and `value_label` text from
`initial_volume`; `changed` fires every `setValue`; `committed` fires on a
discrete `setValue` but NOT while `setSliderDown(True)`; `committed` fires
exactly once on `sliderReleased.emit()` with the final value; `value_label` text
format is `"<n>%"`; `value()`/`set_value()` round-trip.

**Verify**: `venv/bin/pytest tests/test_volume_slider.py -v` green; full suite
unchanged-green (nothing consumes it yet); `ruff`/`mypy` clean.

**Commit**: `DEBT-01: add reusable VolumeSlider widget (commit-on-release)`.

---

## Phase 3 — Add the `SceneControlCard` base class (no subclassing yet)

Create `app/shared/base_control_card.py` mirroring `base_list_widget.py`. It
hoists the common surface and composes `VolumeSlider`. At the end of this phase
it is dead code (no subclasses) — a safe, reviewable checkpoint.

Key elements:

- Declare the 5 common signals on the base (`volume_changed`/`volume_committed`
  `pyqtSignal(int,float)`; `repeat_changed`/`play_mode_changed` `pyqtSignal(int,
  bool)`; `remove_requested` `pyqtSignal(int)`). **PyQt6 subclasses inherit
  signals declared on a `QObject` base** — Phase 4 verifies this empirically; if
  any subtlety bites, the fallback is to re-declare the 5 on each subclass (5
  lines, no behavior change).
- `MIME_TYPE: str = ""` class attribute (overridable).
- Abstract hooks (raise `NotImplementedError`, grouped under a
  `# --- Abstract methods (subclasses must override) ---` comment, per
  `base_list_widget.py`): `_model` (property → the bound dataclass),
  `_entity_id` (property → `_model.id`), `_active_card_style()` and
  `_inactive_card_style()` (return the `Styles.card_frame_style(...)` string for
  each play-mode state).
- Overridable **no-op** hooks: `_on_volume_applied(self, value: int)`,
  `_on_repeat_applied(self)`, `_after_play_mode_update(self)`.
- `_init_card_state(self)`: sets `self._icons = IconLibrary()`,
  `self._drag_start_pos = None`, `self._play_mode = bool(self._model.play_mode)`,
  `self._repeat_mode = bool(self._model.is_repeat)`, and
  `self.setFrameStyle(QFrame.Shape.StyledPanel)`. (Subclasses call this after
  setting their model.)
- `_build_volume_row(self) -> VolumeSlider`: creates `self.volume =
  VolumeSlider(self._model.volume)`; sets `self.volume_slider = self.volume.slider`
  (the documented public handle the existing/characterization tests poke);
  wires `self.volume.changed.connect(self._on_volume_changed)` and
  `self.volume.committed.connect(self._on_volume_committed)`; returns
  `self.volume` for the subclass to place in its row.
- `_on_volume_changed(self, volume: float)`: `self._model.volume = volume`;
  `self._on_volume_applied(int(volume * 100))`; `self.volume_changed.emit(
  self._entity_id, volume)`.
- `_on_volume_committed(self, volume: float)`: `self._model.volume = volume`;
  `self.volume_committed.emit(self._entity_id, volume)`.
- `_build_repeat_button(self) -> QPushButton`: builds the 28×28 repeat button
  (icon `"repeat"`, iconSize 14×14, `clicked→_toggle_repeat`); returns it.
- `_toggle_repeat(self)`: flips `_repeat_mode`, sets `self._model.is_repeat`,
  `self._on_repeat_applied()`, `self._update_repeat_button()`, emits
  `repeat_changed(self._entity_id, self._repeat_mode)`.
- `_update_repeat_button(self)`: `self.repeat_btn.setStyleSheet(
  Styles.icon_toggle_button_style(self._repeat_mode, size=28))` (byte-identical
  to both controls today). Requires subclasses to assign `self.repeat_btn`.
- `_toggle_play(self)`: flips `_play_mode`, sets `self._model.play_mode`,
  `_update_play_mode_ui()`, emits `play_mode_changed(self._entity_id,
  self._play_mode)`. `set_play_mode(self, play_mode)`: same writes, calls
  `_update_play_mode_ui()`, but **does NOT emit** (preserve the asymmetry).
- `_update_play_mode_ui(self)` (template):
  ```python
  self.play_btn.setIcon(self._icons.icon("play-solid"))
  if self._play_mode:
      self.play_btn.setStyleSheet(Styles.play_button_style(size=28))
      self.setStyleSheet(self._active_card_style())
  else:
      self.play_btn.setStyleSheet(Styles.play_button_inactive_style(size=28))
      self.setStyleSheet(self._inactive_card_style())
  self._after_play_mode_update()
  ```
- `contextMenuEvent(self, event)`: build the `QMenu`, add "Remove from scene",
  connect `triggered → lambda: self.remove_requested.emit(self._entity_id)`,
  `menu.exec(event.globalPos())`.
- `mousePressEvent`/`mouseReleaseEvent`: byte-identical to today (set/clear
  `_drag_start_pos`). `mouseMoveEvent`: the drag-threshold guard + `QDrag` with
  `mime.setData(self.MIME_TYPE, QByteArray(str(self._entity_id).encode()))`.

**Verify**: full suite green (the file is imported by nothing yet, so behavior is
unchanged); `ruff`/`mypy` clean on the new file (type the abstract hooks).

**Commit**: `DEBT-01: add SceneControlCard base (drag/context/toggles/volume)`.

---

## Phase 4 — Migrate `TrackControl` onto the base (higher-risk control first)

In `app/scenes/track_control.py`:
- `class TrackControl(SceneControlCard)` (import from `..shared.base_control_card`).
- Add `MIME_TYPE = "application/x-soundmanager-track"` as a class attr (replaces
  the inline literal — behavior-neutral, but the string MUST be identical).
- **Delete** the 5 now-inherited signal declarations.
- Keep `__init__(self, track, player=None, parent=None)`: `super().__init__(parent)`,
  set `self.track`, `self.player`, `self._updating_position = False`, call
  `self._init_card_state()`, set `self._base_style = Styles.card_frame_style(
  "TrackControl")` + `self.setStyleSheet(self._base_style)`, set the tooltip,
  then `self._setup_ui()`, `self._connect_player_signals()`,
  `self._update_play_mode_ui()`.
- Implement hooks: `_model` → `self.track`; `_entity_id` → `self.track.id`;
  `_active_card_style()` → `Styles.card_frame_style("TrackControl",
  accent_color=Styles.SUCCESS, border_color=Styles.SUCCESS,
  background_color=Styles.BACKGROUND_LIGHT)`; `_inactive_card_style()` →
  `self._base_style`; `_after_play_mode_update()` → `self._update_repeat_button()`
  (TrackControl refreshes repeat after play-mode restyle — preserve);
  `_on_volume_applied(value)` → `if self.player: self.player.target_volume = value`;
  `_on_repeat_applied()` → `if self.player: self.player.repeat = self._repeat_mode`.
- **Delete** the now-inherited bodies: `_on_volume_changed`, `_on_volume_released`,
  `_toggle_play`, `set_play_mode`, `_toggle_repeat`, `_update_repeat_button`,
  `contextMenuEvent`, `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent`,
  and the 5 signal lines.
- `_setup_ui`: keep per-class. For the volume area, call
  `vol = self._build_volume_row()` and add `vol` where the slider used to go
  (the `bottom_row` shared with repeat); for repeat, `self.repeat_btn =
  self._build_repeat_button()` and add it. Keep the position row, the
  file-missing indicator (keep `import os`), and the title/play-button top row.
- Keep the entire player cluster (`_connect_player_signals`, `set_player`,
  `_update_position`, `_on_position_pressed`, `_on_position_released`,
  `_on_end_reached`).

**Verify**: `venv/bin/pytest tests/test_track_control.py -v` → all Phase-1 tests
green. Then full suite (catches any `scene_editor` integration regression via
`control.track.id`, `control.player`, `set_player`). Sanity-check that a
constructed `TrackControl` actually has the inherited signals
(`hasattr(tc, "volume_changed")`). `ruff`/`mypy` clean.

**Commit**: `DEBT-01: TrackControl extends SceneControlCard`.

---

## Phase 5 — Migrate `PlaylistEntryControl` onto the base

In `app/scenes/playlist_entry_control.py`:
- `class PlaylistEntryControl(SceneControlCard)`.
- **Delete** the 5 inherited signal declarations but **keep** the unique
  `shuffle_changed = pyqtSignal(int, bool)`.
- **Keep** the existing `MIME_TYPE = "application/x-soundmanager-scene-playlist"`
  (overrides the base default).
- Keep `__init__(self, entry, parent=None)` (no player): `super().__init__(parent)`,
  set `self.entry`, `self._shuffle_mode = bool(entry.is_shuffle)`, call
  `self._init_card_state()`, set the PRIMARY-accent `self._base_style`
  (`Styles.card_frame_style("PlaylistEntryControl", accent_color=Styles.PRIMARY,
  border_color=Styles.PRIMARY)`), set the `"Playlist: <name>"` tooltip — **do
  NOT** call `setStyleSheet` in `__init__` (this control relies on
  `_update_play_mode_ui`, preserve that) — then `_setup_ui()`,
  `_update_play_mode_ui()`.
- Implement hooks: `_model` → `self.entry`; `_entity_id` → `self.entry.id`;
  `_active_card_style()` → `self._base_style`; `_inactive_card_style()` →
  `Styles.card_frame_style("PlaylistEntryControl", border_color=Styles.BORDER,
  background_color=Styles.BACKGROUND_LIGHT)`. Do **NOT** override
  `_after_play_mode_update` (default no-op — this control does NOT refresh repeat
  there). Do **NOT** override `_on_volume_applied`/`_on_repeat_applied` (no
  player — base no-ops are correct).
- **Delete** the now-inherited bodies (`_on_volume_changed`, `_on_volume_released`,
  `_toggle_play`, `set_play_mode`, `_toggle_repeat`, `_update_repeat_button`,
  `contextMenuEvent`, `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent`).
- `_setup_ui`: keep per-class — the `"PL"` badge, the now-playing label, the
  track-count `info_label`, and the shuffle button + `_update_shuffle_button()`.
  Use `self._build_volume_row()` for the volume row and `self.repeat_btn =
  self._build_repeat_button()` for repeat.
- Keep the shuffle cluster (`_toggle_shuffle`, `_update_shuffle_button`,
  `shuffle_changed`) and `set_current_track` entirely in the subclass.

**Verify**: `venv/bin/pytest tests/test_playlist_entry_control.py -v` → all green,
**especially the `_toggle_shuffle` test** (shuffle has no base equivalent and
must remain 100% subclass). Full suite green. `ruff`/`mypy` clean.

**Commit**: `DEBT-01: PlaylistEntryControl extends SceneControlCard`.

---

## Phase 6 — Cleanup, lint, docs

- Confirm `app/scenes/__init__.py` still exports `TrackControl` +
  `PlaylistEntryControl` unchanged (no `__all__` churn).
- Confirm `scene_editor.py` is **untouched** (`git diff --stat` shows no entry
  for it).
- Remove any now-dead names/imports in the two controls (e.g. the old
  `volume_value_label` attribute is gone — it lives in `VolumeSlider` now; verify
  nothing references it).
- `venv/bin/ruff check app/ tests/`, `venv/bin/ruff format --check app/ tests/`,
  `venv/bin/mypy app` — clean / no new errors on touched files.
- Update `plans/README.md`: set Plan 006 status to DONE; mark the DEBT-01 finding
  ✅ with a one-line note (VolumeSlider + SceneControlCard shipped; PERF-02
  follow-up (c) absorbed). Note any deliberately-retained per-class divergence
  (`_setup_ui`, `_update_play_mode_ui` hooks, the TrackControl player cluster,
  the PlaylistEntryControl shuffle/badge clusters) as intentional, not debt.
- Final `venv/bin/pytest tests/ -q` → all green.

**Commit**: `DEBT-01: dedupe scene control cards — cleanup + plan update`.

---

## Test plan (summary)

Characterization-first and behavior-preserving. Phase 1 pins the **full** current
observable contract of both widgets against unchanged source; Phases 4–5 must
keep that exact suite green (proof of preservation), plus the full suite for
`scene_editor` integration. Phase 2 gives `VolumeSlider` independent isolation
coverage. New behavior is never added — a green suite after each migration is the
proof. Highest-value pins: exactly-once signal counts, the `set_play_mode`
no-emit asymmetry, the unique shuffle toggle, the TrackControl player branches
(via `FakeTrackPlayer`), and the MIME type+payload (reorder depends on the track
string).

## Done criteria (machine-checkable)

- [ ] `venv/bin/pytest tests/ -q` exits 0, test count ≥ 197 + the new
      characterization + `test_volume_slider.py` tests, zero failures.
- [ ] `app/shared/volume_slider.py` and `app/shared/base_control_card.py` exist;
      `grep -n "class VolumeSlider" app/shared/volume_slider.py` and
      `grep -n "class SceneControlCard" app/shared/base_control_card.py` match.
- [ ] `grep -n "class TrackControl(SceneControlCard)" app/scenes/track_control.py`
      and `grep -n "class PlaylistEntryControl(SceneControlCard)"
      app/scenes/playlist_entry_control.py` match.
- [ ] Neither control still declares the 5 common signals or the 10 hoisted
      methods (`grep -n "def contextMenuEvent\|def mouseMoveEvent\|def _toggle_play\|def _update_repeat_button" app/scenes/track_control.py app/scenes/playlist_entry_control.py`
      returns nothing).
- [ ] `git diff --stat e3f7de3..HEAD -- app/scenes/scene_editor.py` shows **no
      changes** to `scene_editor.py`.
- [ ] `grep -n "application/x-soundmanager-track" app/scenes/track_control.py` and
      `grep -n "application/x-soundmanager-scene-playlist" app/scenes/playlist_entry_control.py`
      each match (MIME strings preserved).
- [ ] `PlaylistEntryControl` still declares `shuffle_changed`.
- [ ] `venv/bin/ruff check app/ tests/` and `venv/bin/ruff format --check app/ tests/`
      clean; `venv/bin/mypy app` no new errors on touched files.
- [ ] `plans/README.md` Plan 006 row + DEBT-01 finding updated.

## STOP conditions

Stop and report (do not improvise) if:

- The baseline suite is not green before Phase 1 (broken baseline isn't yours to
  fix).
- A characterization test in Phase 1 reveals current behavior that contradicts
  this plan's stated contract (e.g. a signal fires a different number of times
  than assumed) — the plan's model of "current behavior" is wrong; report it.
- Inherited signals do NOT work after Phase 4 (a constructed subclass lacks
  `volume_changed` etc.) — report; the fallback is re-declaring the 5 on each
  subclass.
- You find yourself needing to edit `scene_editor.py` — a public contract was
  broken; STOP and find which one.
- `app/scenes/track_control.py` / `playlist_entry_control.py` have drifted from
  the line references above since `e3f7de3` in a way that invalidates the
  migration steps.
- The offscreen suite **hangs** — almost certainly a test called
  `contextMenuEvent`/`mouseMoveEvent` directly (blocking `exec`); fix the test.

## Maintenance notes

- **Future reuse**: `app/main_window.py` has its own master-volume slider
  (`_on_master_volume_changed`). It is a candidate to adopt `VolumeSlider` later
  — but master volume may not want commit-on-release deferral, so validate the
  semantics before reusing. Out of scope here.
- **Future feature**: `PlaylistEntryControl`'s `MIME_TYPE` is emitted by its drag
  but has **no drop handler** anywhere — playlist entries are draggable but not
  reorderable today. If entry reordering is ever added, a `TrackListContainer`-style
  drop handler keyed on that MIME type is the place.
- **If a new common control behavior is added**, add it to `SceneControlCard`
  once (with a hook if it diverges), not to both subclasses — that single source
  of truth is the whole point of this refactor.
- The base is intentionally a **partial** template: `_setup_ui` (row composition)
  and the `_active_/_inactive_card_style` hooks stay per-subclass because the
  card layouts and accent colors genuinely differ. This is by design, documented
  in the base class docstring — not an incomplete refactor.
