# 013 — Redesign the tag create/edit interface

**Status:** TODO (stowed 2026-07-31, from beta feedback + user's own gripes)
**Priority:** P3 / polish — the current dialog works, it's just clumsy
**Touches:** `TagEditDialog` in `app/shared/dialogs.py`, `Styles.TAG_COLORS` in
`app/shared/styles.py`, possibly `default_tags.sql` colors

## Problems (as reported)

1. **Default palette is weak.** Colors aren't great in general, and several
   are close enough to be hard to tell apart at tag-pill size (e.g. the
   blue/indigo/light-blue cluster, the green/light-green/lime cluster).
2. **No real color picking.** The custom-color interface has no eyedropper /
   system picker and no way to copy an existing tag's color, so making a new
   tag match or coordinate with an existing one is guesswork.

## Direction (sketch, refine at execution time)

- Rebuild the default palette as fewer, maximally-distinct hues, each checked
  for white-text contrast at 11px pill size (or pair with auto text color,
  below). Existing user tags keep their stored colors — palette only affects
  the picker's presets.
- Replace/augment the custom-color swatch grid with the native color dialog
  (`QColorDialog` — the macOS picker includes an eyedropper) plus a hex field.
- "Copy color from existing tag": a dropdown/swatch row of current tags in the
  dialog, click to adopt its color.
- Consider luminance-based text color on pills (white text on dark colors,
  dark text on light ones) — today white text is hard-coded and is illegible
  on light colors like Lime. `TagBadge`/`Styles.tag_badge_style` change;
  independent of the dialog work and could ship first.

## Context from the 2026-07-31 highlighting fix

Selected-tag indication is now a "✓" glyph on the pill (commit `2153cad`),
chosen because ANY color-based selected-state indicator can collide with
user-chosen tag colors — same reasoning applies to this redesign: don't rely
on color alone anywhere tags are rendered. Mockup methodology that settled it:
offscreen-render candidate treatments side by side in the real theme
(scratchpad scripts `mock_selection.py` / `mock_halo.py` pattern).

## STOP conditions

- Don't migrate or rewrite existing tags' stored colors without asking.
- Dialog is shared by create and edit paths (and reachable from the file
  table's tag flow) — check all entry points before changing its API.
