"""Field formatting + small visual helpers for the inspector view.

Pure value→text conversion (``_field_text``) and Python-ish literal
rendering for the Code section's synthetic constructor call
(``_config_literal`` / ``_config_snippet``), plus the tiny color swatch
widget used by COLOR-kind rows.
"""

from __future__ import annotations

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
    if not isinstance(value, (str, int, float, bool)) and not isinstance(value, Enum):
        # opaque object (QIcon, QBrush, ...): a Call placeholder — keeps the
        # snippet parseable and the preview's kwarg extractor skips it
        return f"{type(value).__name__}(...)"
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
    return repr(value)


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
