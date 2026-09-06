"""Color-origin analysis for the inspector's Colors section.

Qt exposes no computed styles, so "why is this widget this color" is
reconstructed from the pieces Qt does expose:

- candidate QSS rules (the inspector's ``QssIndex`` scan) that set
  background / color / border properties on the widget;
- the effective ``QPalette`` roles (Window/Base/Text/WindowText) plus the
  ``autoFillBackground`` flag — the combination that actually paints;
- the ThemeManager tokens whose resolved value equals an effective color
  (reverse lookup), with the app-provided source labels (themes.json
  file:line) shown on the Theme page;
- whether the widget paints itself (custom ``paintEvent``) or shows the
  parent's paint through (transparent containers).

Pure functions + small dataclasses; the page rendering lives in
``rendering.py`` (thin-owner pattern).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import FunctionType
from typing import Any, Iterable

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget

from .qss_scan import QssRule

_BG_NAMES = frozenset({"background", "background-color"})
_TEXT_NAMES = frozenset({"color"})
_BORDER_PREFIXES = (
    "border",
    "border-color",
    "border-width",
    "border-style",
    "border-top",
    "border-right",
    "border-bottom",
    "border-left",
    "border-radius",
)

_QSS_TOKEN_RE = re.compile(r"^@([\w.]+)$")

_ROLE_NAMES = {
    QPalette.ColorRole.Window: "Window",
    QPalette.ColorRole.WindowText: "WindowText",
    QPalette.ColorRole.Base: "Base",
    QPalette.ColorRole.AlternateBase: "AlternateBase",
    QPalette.ColorRole.Text: "Text",
    QPalette.ColorRole.Button: "Button",
    QPalette.ColorRole.ButtonText: "ButtonText",
    QPalette.ColorRole.Highlight: "Highlight",
    QPalette.ColorRole.HighlightedText: "HighlightedText",
    QPalette.ColorRole.ToolTipBase: "ToolTipBase",
    QPalette.ColorRole.ToolTipText: "ToolTipText",
}


@dataclass(frozen=True)
class ColorRow:
    """One "why is it this color" row: a property + its value + where the
    value came from (QSS rule / palette role / token) + a resolvable
    color for the swatch (``None`` for transparent/unresolvable)."""

    label: str
    value: str
    origin: str
    color: QColor | None = None
    selector: str = ""
    source_path: str = ""
    source_line: int = 0


def _iter_qss_rules(qss_rows) -> Iterable[tuple[Any, Any]]:
    """Yield ``(rule, dead_flag)`` from either the pane's ``_qss_rows``
    list or a bare iterable of ``QssRule`` (``QssIndex.candidates_for``)."""
    for entry in qss_rows or ():
        if isinstance(entry, QssRule):
            yield entry, None
        else:
            yield entry[0], entry[1]


def _declarations(body: str) -> list[tuple[str, str]]:
    """QSS rule body → ``(property, value)`` pairs (declaration split on
    ``;`` — one property may share a line with the previous one)."""
    out: list[tuple[str, str]] = []
    for decl in body.split(";"):
        name, sep, value = decl.partition(":")
        if not sep:
            continue
        out.append((name.strip(), value.strip()))
    return out


def qss_background_rows(qss_rows, theme_manager) -> list[ColorRow]:
    """QSS candidate rules setting ``background``/``background-color``."""
    return _qss_property_rows(qss_rows, theme_manager, _BG_NAMES, "background")


def qss_text_rows(qss_rows, theme_manager) -> list[ColorRow]:
    """QSS candidate rules setting ``color``."""
    return _qss_property_rows(qss_rows, theme_manager, _TEXT_NAMES, "color")


def qss_border_rows(qss_rows, theme_manager) -> list[ColorRow]:
    """QSS candidate rules setting any ``border*`` property."""
    rows: list[ColorRow] = []
    for rule, _dead in _iter_qss_rules(qss_rows):
        for prop, value in _declarations(rule.body or ""):
            if not prop.startswith("border"):
                continue
            if prop not in _BORDER_PREFIXES:
                continue
            rows.append(
                ColorRow(
                    label=prop,
                    value=value,
                    origin=f"QSS {rule.selector}  ({rule.source}:{rule.line})",
                    color=resolve_qss_value(value, theme_manager),
                    selector=rule.selector,
                    source_path=rule.source,
                    source_line=rule.line,
                )
            )
    return rows


def _qss_property_rows(qss_rows, theme_manager, prop_names, label: str) -> list[ColorRow]:
    rows: list[ColorRow] = []
    for rule, _dead in _iter_qss_rules(qss_rows):
        for prop, value in _declarations(rule.body or ""):
            if prop not in prop_names:
                continue
            rows.append(
                ColorRow(
                    label=label,
                    value=value,
                    origin=f"QSS {rule.selector}  ({rule.source}:{rule.line})",
                    color=resolve_qss_value(value, theme_manager),
                    selector=rule.selector,
                    source_path=rule.source,
                    source_line=rule.line,
                )
            )
    return rows


def resolve_qss_value(value: str, theme_manager) -> QColor | None:
    """Resolve a QSS property value to a QColor where possible:
    ``@token`` (via ThemeManager), hex, ``rgba(...)`` or a named color.
    ``transparent``/``none``/unresolvable values yield ``None``."""
    value = value.strip()
    token = _QSS_TOKEN_RE.match(value)
    if token is not None:
        try:
            return QColor(theme_manager.get_color(token.group(1)))
        except Exception:
            return None
    if value in ("transparent", "none"):
        return None
    color = QColor(value)
    return color if color.isValid() else None


def palette_background(widget: QWidget) -> tuple[str, QColor, bool]:
    """(role name, effective color, autoFill) — what the palette would
    paint for the widget's background, and whether it actually does."""
    role = widget.backgroundRole()
    role_name = _ROLE_NAMES.get(role, str(role))
    color = QColor(widget.palette().color(role))
    return role_name, color, widget.autoFillBackground()


def tokens_for_color(theme_manager, color: QColor) -> list[str]:
    """Theme tokens whose resolved value equals ``color`` (direct reverse
    lookup: ``Window``, ``dialog.background``, …)."""
    if theme_manager is None or not color.isValid():
        return []
    try:
        dark = bool(theme_manager.is_dark())
    except Exception:
        dark = False
    palette = None
    try:
        palette = (
            getattr(theme_manager, "_dark_palette", None)
            if dark
            else getattr(theme_manager, "_light_palette", None)
        )
    except Exception:
        palette = None
    keys: set[str] = set()
    if isinstance(palette, dict):
        keys.update(palette.keys())
    keys.update(("surface.background", "Window", "WindowText", "Base", "Text"))
    out: list[str] = []
    for key in sorted(keys):
        try:
            resolved = theme_manager.try_get_color(key)
        except Exception:
            continue
        if resolved is not None and resolved.isValid() and resolved.rgba() == color.rgba():
            out.append(key)
    return out


def first_painting_ancestor(widget: QWidget) -> QWidget | None:
    """The nearest ancestor that actually paints its background
    (``autoFillBackground`` on, a stylesheet, or custom paint) — what a
    transparent widget shows through to."""
    node = widget.parentWidget()
    while node is not None:
        try:
            if node.autoFillBackground() or bool(node.styleSheet()):
                return node
            if has_custom_paint(node):
                return node
        except RuntimeError:
            return None
        node = node.parentWidget()
    return None


def has_custom_paint(widget: QWidget) -> bool:
    """Whether the widget's class defines its own ``paintEvent`` in
    Python (toolkit primitives paint their own chrome — palette/QSS rules
    only feed the well behind them). C++/shiboken methods are method
    descriptors, not Python functions, so stock Qt widgets read as
    non-custom-painted."""
    try:
        return isinstance(getattr(type(widget), "paintEvent", None), FunctionType)
    except Exception:
        return False


def widget_flags(widget: QWidget) -> list[tuple[str, str]]:
    """Paint-relevant Qt attributes as ``(name, value)`` rows."""
    from PySide6.QtCore import Qt

    attrs = (
        ("autoFillBackground", widget.autoFillBackground()),
        ("WA_StyledBackground", widget.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)),
        ("WA_TranslucentBackground", widget.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)),
        ("WA_NoSystemBackground", widget.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)),
        ("WA_OpaquePaintEvent", widget.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)),
    )
    return [(name, "on" if value else "off") for name, value in attrs]


__all__ = [
    "ColorRow",
    "first_painting_ancestor",
    "has_custom_paint",
    "palette_background",
    "qss_background_rows",
    "qss_border_rows",
    "qss_text_rows",
    "resolve_qss_value",
    "tokens_for_color",
    "widget_flags",
]