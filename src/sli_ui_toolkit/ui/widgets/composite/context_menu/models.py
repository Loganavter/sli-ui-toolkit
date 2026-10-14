"""Declarative context-menu entry models and pure helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtGui import QColor, QKeySequence

from sli_ui_toolkit.ui.managers.ui_font import measure_text_width

# Destructive-action red — deliberately NOT a theme token (documented
# hardcode, reviewed 2026-09-21). Rationale: the danger cue must read as
# the same red in both themes (both shipped palettes would define the
# identical value, so a token buys indirection without flexibility), and
# hosts that need a different destructive color own their row paint layers
# already. If a third consumer ever needs this red, promote it to the
# Optional tier in palettes.py + DESIGN_LANGUAGE.md instead of copying it.
_DANGER_COLOR = QColor("#e5484d")
_ROW_H_PADDING = 12

# Back-compat alias for callers that imported the helper from here before it
# moved to the toolkit text home (ui_font.measure_text_width).
_measure_text_width = measure_text_width


@dataclass(slots=True)
class ContextMenuAction:
    action_id: str
    text: str
    icon: object | None = None
    enabled: bool = True
    visible: bool = True
    checked: bool = False
    checkable: bool = False
    danger: bool = False
    shortcut: str | QKeySequence | None = None
    tooltip: str = ""
    data: object = None
    children: tuple["ContextMenuEntry", ...] = ()
    # Row click closes the menu (hiding/destroying the row) and invokes
    # on_triggered synchronously -- fine for lightweight actions, but a
    # handler that opens a modal (``.exec()``) dialog blocks the event loop
    # before the row's own click ripple has any chance to play at all (the
    # row is gone the instant the menu hides). Set True to delay the
    # hide+emit+on_triggered by the ripple duration instead, same rationale
    # as ``Button(defer_click=DEFER_CLICK_AWAIT_RIPPLE)``.
    defer_trigger: bool = False
    # Declarative translation keys. When set and a translator is bound to the
    # owning ``ContextMenu`` (``set_translator``/``bind_translator``), the row's
    # text/tooltip re-resolve on every language change; the key wins over the
    # literal and a miss shows the key itself.
    text_key: str | None = None
    tooltip_key: str | None = None


@dataclass(slots=True)
class ContextMenuSection:
    entries: tuple["ContextMenuEntry", ...] = field(default_factory=tuple)
    title: str = ""


@dataclass(slots=True)
class ContextMenuSeparator:
    visible: bool = True


ContextMenuEntry = ContextMenuAction | ContextMenuSection | ContextMenuSeparator


@dataclass(slots=True)
class _SectionTitle:
    text: str


def _entry_visible(entry: ContextMenuEntry) -> bool:
    if isinstance(entry, ContextMenuAction):
        return entry.visible
    if isinstance(entry, ContextMenuSeparator):
        return entry.visible
    if isinstance(entry, ContextMenuSection):
        return any(_entry_visible(child) for child in entry.entries)
    return False


def _trim_flat_separators(flat: list) -> list:
    while flat and isinstance(flat[0], ContextMenuSeparator):
        flat.pop(0)
    while flat and isinstance(flat[-1], ContextMenuSeparator):
        flat.pop()
    result = []
    previous_separator = False
    for item in flat:
        if isinstance(item, ContextMenuSeparator):
            if previous_separator:
                continue
            previous_separator = True
        else:
            previous_separator = False
        result.append(item)
    return result


def _shortcut_display_text(shortcut: str | QKeySequence | None) -> str:
    if not shortcut:
        return ""
    sequence = shortcut if isinstance(shortcut, QKeySequence) else QKeySequence(shortcut)
    return sequence.toString(QKeySequence.SequenceFormat.NativeText)
