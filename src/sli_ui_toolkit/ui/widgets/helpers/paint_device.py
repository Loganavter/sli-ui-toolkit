"""Paint-device ratio helpers for the toolkit's painter pipeline.

Two numbers can disagree under fractional display scaling, and picking the
wrong one silently resamples every raster:

* the **application** ratio (`QGuiApplication.devicePixelRatio()`) — what
  `QIcon.pixmap(QSize)` implicitly uses;
* the ratio of the **device actually being painted on** — the widget's or the
  painter's `devicePixelRatioF()`.

Measured 2026-10-28 (KDE/Wayland, 125 %): application 2.0, window 1.25. An icon
rasterized at 2.0 and painted into a 1.25 device is downscaled by 0.625 and its
thin strokes look ragged, while the same icon is crisp at 100 %.

Every raster that will be painted must be produced at :func:`painter_dpr` /
:func:`widget_dpr`, never at the application ratio.
"""

from __future__ import annotations

from typing import Any

__all__ = ["painter_dpr", "widget_dpr"]


def _ratio_of(device: Any) -> float:
    get_ratio = getattr(device, "devicePixelRatioF", None)
    if not callable(get_ratio):
        get_ratio = getattr(device, "devicePixelRatio", None)
    if not callable(get_ratio):
        return 1.0
    try:
        ratio = float(get_ratio())
    except (AttributeError, TypeError, RuntimeError):
        return 1.0
    return ratio if ratio > 0.0 else 1.0


def painter_dpr(painter: Any) -> float:
    """Device pixel ratio the painter will land on (1.0 when unknown)."""
    if painter is None:
        return 1.0
    try:
        device = painter.device()
    except (AttributeError, RuntimeError):
        return 1.0
    return _ratio_of(device)


def widget_dpr(widget: Any) -> float:
    """Device pixel ratio the widget paints on (1.0 when unknown)."""
    if widget is None:
        return 1.0
    return _ratio_of(widget)
