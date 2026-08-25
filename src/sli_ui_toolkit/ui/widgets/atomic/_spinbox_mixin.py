"""Shared spinbox handlers — consolidates SpinBox ↔ DoubleSpinBox duplication.

Both variants share the same routing contract for wheel/key/editing events
(toolbar navigation reserves Up/Down, PageUp/PageDown steps the value,
wheel respects ``shouldHandleWheelEvent``). Only value parsing/formatting
and step size differ.
"""
from __future__ import annotations

from PySide6.QtCore import Qt


def spinbox_wheel_step(event, *, single_step: float) -> float | None:
    """Return signed step for a wheel event, or ``None`` if ignored."""
    # Caller should have checked shouldHandleWheelEvent already
    delta = event.angleDelta().y()
    if delta == 0:
        return None
    factor = 10.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
    step = single_step * factor
    return step if delta > 0 else -step


def spinbox_key_step(key: int, *, single_step: float) -> tuple[str, float | None]:
    """Map key to action: returns (\"ignore\", None), (\"step\", delta), or (\"pass\", None)."""
    if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
        return "ignore", None
    if key == Qt.Key.Key_PageUp:
        return "step", single_step
    if key == Qt.Key.Key_PageDown:
        return "step", -single_step
    return "pass", None
