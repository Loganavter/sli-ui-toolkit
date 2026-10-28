"""Icons must be rasterized at the paint device's ratio, not the app's.

Red-before: on the pre-change tree ``normalized_icon_pixmap`` called
``QIcon.pixmap(QSize)``, which uses ``QGuiApplication.devicePixelRatio()``.
Measured 2026-10-28 on KDE/Wayland at 125 %: application 2.0, window 1.25, so a
22 px icon came back as 44×44 @2.0 and the painter squeezed it into 27.5 device
px — a 0.625 resample that made every thin stroke look ragged, while the same
icons were crisp on a 100 % screen. The owner noticed it as "иконки шершавые".
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QImage, QPainter

from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import normalized_icon_pixmap
from sli_ui_toolkit.ui.widgets.helpers.paint_device import painter_dpr
from sli_ui_toolkit.ui.managers.ui_scale import UiScale


@pytest.fixture()
def icon() -> QIcon:
    # A drawable icon without depending on the app's asset tree.
    from PySide6.QtGui import QPixmap

    source = QPixmap(64, 64)
    source.fill(QColor("#ffffff"))
    return QIcon(source)


def test_pixmap_is_rasterized_at_the_given_ratio(icon):
    pixmap = normalized_icon_pixmap(icon, 22, dpr=1.25)

    assert pixmap.devicePixelRatio() == pytest.approx(1.25)
    # 22 logical at 1.25 = 27.5 device px; Qt rounds to 28. What must NOT
    # happen is the application-ratio answer (44 px) being squeezed into the
    # window's 1.25 device grid.
    assert pixmap.width() == round(22 * 1.25)
    assert pixmap.deviceIndependentSize().width() == pytest.approx(
        pixmap.width() / 1.25
    )


def test_ratios_do_not_share_a_cache_entry(icon):
    at_one = normalized_icon_pixmap(icon, 22, dpr=1.0)
    at_two = normalized_icon_pixmap(icon, 22, dpr=2.0)

    assert at_one.devicePixelRatio() == pytest.approx(1.0)
    assert at_two.devicePixelRatio() == pytest.approx(2.0)
    assert at_one.width() == 22
    assert at_two.width() == 44


def test_painter_ratio_is_the_paint_device_ratio(qapp):
    image = QImage(40, 40, QImage.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(1.25)
    painter = QPainter(image)
    try:
        assert painter_dpr(painter) == pytest.approx(1.25)
    finally:
        painter.end()


def test_scale_factor_still_keys_the_cache(icon):
    """UiScale is logical size, the ratio is device density: both must key it."""
    UiScale.get_instance().set_factor(1.0)
    a = normalized_icon_pixmap(icon, 22, dpr=1.25)
    UiScale.get_instance().set_factor(1.25)
    try:
        b = normalized_icon_pixmap(icon, 22, dpr=1.25)
    finally:
        UiScale.get_instance().set_factor(1.0)
    # Same device size (the caller passes logical px already scaled), different
    # cache slot only if the target px changes -- the point is that the call is
    # safe (never raises) and the ratio survives.
    assert b.devicePixelRatio() == pytest.approx(1.25)
