"""Color helpers — shared interpolation for painter code.

Consolidates ``_lerp_color`` duplicates from
``switch.py`` and ``buttons/layers/ripple.py``.
"""
from __future__ import annotations

from PySide6.QtGui import QColor


def lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    """Linear interpolation between two ``QColor`` (including alpha)."""
    t = max(0.0, min(1.0, float(t)))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )
