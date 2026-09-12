"""Field formatting + small visual helpers for the inspector view.

Pure value→text conversion (``_field_text``) and Python-ish literal
rendering for the Code section's synthetic constructor call
(``_config_literal`` / ``_config_snippet``), plus the tiny color swatch
widget used by COLOR-kind rows.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from .contract import FieldKind, InspectField

#: Enum classes seen in LIVE config values, keyed by short class name.
#: The Code snippet renders enum members as ``Type.MEMBER``; the preview's
#: kwarg extractor resolves them against this registry so members whose
#: class is NOT importable from the widget's own module (e.g. the app's
#: ``AppIcon``, which widgets receive as constructor args without importing
#: the module) still make it into the preview instead of being skipped.
_PREVIEW_ENUM_CLASSES: dict[str, type] = {}


def preview_enum_classes() -> dict[str, type]:
    """Registered enum classes for preview-literal resolution."""
    return dict(_PREVIEW_ENUM_CLASSES)


class _Swatch(QWidget):
    """Small solid color square (painted, no QSS)."""

    def __init__(self, color: QColor, size: int = 14, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(size, size)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._color)
        painter.end()


def _field_text(field: InspectField) -> str:
    value = field.value
    if field.kind is FieldKind.RECT:
        if isinstance(value, (QRect, QRectF)):
            return f"{value.x()},{value.y()} {value.width()}x{value.height()}"
        return str(value)
    if field.kind is FieldKind.ENUM:
        return getattr(value, "name", str(value))
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "—"
    return str(value)


def _config_literal(value: Any, depth: int = 0) -> str:
    """Python-ish literal for a live config value in the Code section.

    Inferred from runtime state, not the original call: enums become
    ``Type.MEMBER``, colors hex strings, child widgets degrade to a
    ``Type(...)`` placeholder, nested ``InspectField`` blocks become dicts.
    """
    pad = "    " * depth
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, QColor):
        return repr(value.name())
    if isinstance(value, (QRect, QRectF)):
        return (
            f"{type(value).__name__}("
            f"{value.x()}, {value.y()}, {value.width()}, {value.height()})"
        )
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, QWidget):
        return f"{type(value).__name__}(...)  # child widget"
    if isinstance(value, tuple) and value and all(
        isinstance(item, InspectField) for item in value
    ):
        rows = ",\n".join(
            f"{pad}    {item.name}={_config_literal(item.value, depth + 1)}"
            for item in value
        )
        return "{\n" + rows + "\n" + pad + "}"
    if isinstance(value, dict):
        if not value:
            return "{}"
        rows = ",\n".join(
            f"{pad}    {_config_literal(k, depth + 1)}: "
            f"{_config_literal(v, depth + 1)}"
            for k, v in value.items()
        )
        return "{\n" + rows + "\n" + pad + "}"
    if isinstance(value, (tuple, list)):
        inner = ", ".join(_config_literal(item, depth + 1) for item in value)
        if isinstance(value, tuple) and len(value) == 1:
            inner += ","
        return f"[{inner}]" if isinstance(value, list) else f"({inner})"
    if dataclasses.is_dataclass(value):
        try:
            fields = dataclasses.fields(value)
        except Exception:
            return f"{type(value).__name__}(...)"
        if not fields:
            return f"{type(value).__name__}()"
        inner = ", ".join(
            f"{f.name}={_config_literal(getattr(value, f.name), depth + 1)}"
            for f in fields
            # hide noisy defaults for compact output
            if _should_show_dataclass_field(value, f)
        )
        # if all fields were hidden, still show at least the visible ones
        if not inner:
            inner = ", ".join(
                f"{f.name}={_config_literal(getattr(value, f.name), depth + 1)}"
                for f in fields
            )
        return f"{type(value).__name__}({inner})"
    if isinstance(value, (int, float)):
        return repr(value)
    # fallback: opaque object (QIcon, QBrush, custom types)
    return f"{type(value).__name__}(...)"


def _should_show_dataclass_field(obj: Any, field) -> bool:
    """Hide noisy dataclass defaults for ButtonRow/ButtonRegion etc."""
    try:
        val = getattr(obj, field.name)
        # hide None — not informative
        if val is None:
            return False
        default = field.default
        if default is not dataclasses.MISSING and val == default:
            # keep text-like fields even when default is '' to avoid
            # hiding the actual display text, but skip empty containers
            if field.name in {"text", "rows"} and val in ("", [], (), {}):
                return False
            # skip default weight/ratio etc. when they are the factory default
            if field.name in {"weight", "ratio", "marquee", "strikethrough", "italic"}:
                return False
            if field.name in {"size"} and val == 12:
                # ButtonRow default size
                return False
            if field.name == "h_align":
                return False
        # for ButtonRow, always show text when non-empty
        if field.name == "text" and isinstance(val, str) and val:
            return True
        return True
    except Exception:
        return True


def _config_snippet(class_name: str, config) -> str:
    """Synthetic constructor call for the Code section: the class plus its
    live config as kwargs (``WidgetInspection.config``)."""
    for field in config:
        if isinstance(field.value, Enum):
            _PREVIEW_ENUM_CLASSES[type(field.value).__name__] = type(field.value)
    lines = [f"{class_name}("]
    lines.extend(
        f"    {field.name}={_config_literal(field.value)}," for field in config
    )
    lines.append(")")
    return "\n".join(lines)
