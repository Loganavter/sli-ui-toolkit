# Light / Dark Theme Audit

Static audit of every widget with a custom `paintEvent` under
`src/sli_ui_toolkit/ui/widgets/`. The goal is to confirm each painter
resolves its colors through `ThemeManager` (and therefore reacts to a
runtime theme switch) instead of hard-coding light-mode-only values.

The contrast targets that underpin this audit are documented in
`DESIGN_LANGUAGE.md` and enforced for default palette pairs by
`tests/test_contrast.py`.

## Methodology

For each module containing `def paintEvent`:

1. Grep the file for one of `ThemeManager`, `theme_manager`,
   `get_color`, `try_get_color`, `palette`, `self._theme`, `self.theme`.
2. If none of those appear, the painter is presumed theme-blind and the
   file is read directly to confirm and remediate.
3. Read the actual `paintEvent` to verify the colors that *are* pulled
   from the theme cover every fill / pen / text role inside it (i.e. no
   stray hard-coded `QColor(0, 0, 0)` for visible text).

## Findings

29 modules contain a `paintEvent`. 25 were already theme-aware. The four
exceptions were:

| Module | Status before | Outcome |
|--------|---------------|---------|
| `composite/drag_ghost_widget.py` | Hard-coded `QPainterPath` clip + host-supplied `QPixmap`; no painted color of its own. | **OK as-is** — the widget renders only the supplied pixmap; nothing to themify. |
| `composite/unified_flyout/style.py` | Uses `draw_rounded_shadow` helper. | **OK as-is** — the helper paints translucent black shadow steps that look right on both palettes. (The `shadow.color` token is reserved for hosts that want a non-black shadow; promoting it into the helper is a future polish, not a correctness gap.) |
| `overlays/drag_drop_overlay.py` | Hard-coded `QColor(0, 100, 200, 153)` blue fill and `QColor(255, 255, 255, 179)` white border; text always white. | **Fixed (0.2.7)** — now resolves accent / `HighlightedText` via `ThemeManager`. |
| `overlays/paste_direction_overlay.py` | Hard-coded white surface (`#ffffff`), dark-gray text, light-gray borders, gray cancel circle. Light-mode only. | **Fixed (0.2.7)** — surface uses `flyout.background`, text uses `WindowText`, idle border uses `flyout.border`, hover border uses `accent`, cancel circle uses `separator.color`. |

## Audited modules (theme-aware before this pass)

`atomic/checkbox.py`, `atomic/custom_group_widget.py`,
`atomic/custom_line_edit.py`, `atomic/drop_zone_label.py`,
`atomic/instances_counter_button.py`, `atomic/loading_spinner.py`,
`atomic/minimalist_scrollbar.py`, `atomic/radio.py`, `atomic/slider.py`,
`atomic/switch.py`, `atomic/time_line_edit.py`, `atomic/tooltips.py`,
`buttons/_dropdown_menu.py`, `buttons/button.py`,
`buttons/button_group.py`, `comboboxes/_overlay.py`,
`comboboxes/combo_box.py`, `comboboxes/scrollable_combobox.py`,
`composite/base_flyout.py`, `composite/calendar_widget/day_button.py`,
`composite/simple_options_flyout.py`, `composite/toast.py`,
`composite/timeline_widget/widget.py`,
`composite/unified_flyout/panel.py`,
`list_items/rating_item.py`.

## How to re-run this audit

```bash
for f in $(grep -rln "def paintEvent" src/sli_ui_toolkit/ui/widgets/ \
            --include="*.py" | grep -v __pycache__); do
  if ! grep -q "ThemeManager\|theme_manager\|theme\.get_color\|palette\|get_color\|tm\.\|self\._theme\|self\.theme" "$f"; then
    echo "NO-THEME: $f"
  fi
done
```

Any file the script prints should either be remediated to read from
`ThemeManager`, or its `paintEvent` should be inspected and exempted
here with a short justification.
