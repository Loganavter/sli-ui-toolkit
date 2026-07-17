"""Declarative context-menu entry models and pure helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtGui import QColor, QFontMetrics, QKeySequence

_DANGER_COLOR = QColor("#e5484d")
_ROW_H_PADDING = 12
_TEXT_WIDTH_FUDGE = 8


def _measure_text_width(fm: QFontMetrics, text: str) -> int:
    if not text:
        return 0
    return max(fm.horizontalAdvance(text), fm.boundingRect(text).width()) + _TEXT_WIDTH_FUDGE


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
