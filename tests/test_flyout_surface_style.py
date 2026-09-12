"""BaseFlyout background/border/shadow overrides (set_background_brush et al).

Same shape as Button's style_api.py: a plain instance override, ``None``
falls back to the theme token, setter repaints. See FLYOUT_SYSTEM.md
"Custom surface style (background / border / shadow)".
"""

from __future__ import annotations

from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPixmap
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout


def test_defaults_have_no_overrides(qapp):
    host = QWidget()
    flyout = BaseFlyout(host)
    try:
        assert flyout.background_brush() is None
        assert flyout.border_color() is None
        assert flyout.shadow_color() is None
    finally:
        flyout.deleteLater()
        host.deleteLater()


def test_set_background_brush_accepts_color_gradient_and_brush(qapp):
    host = QWidget()
    flyout = BaseFlyout(host)
    try:
        flyout.set_background_brush(QColor("#ff0000"))
        assert isinstance(flyout.background_brush(), QBrush)
        assert flyout.background_brush().color() == QColor("#ff0000")

        gradient = QLinearGradient(0, 0, 0, 1)
        flyout.set_background_brush(gradient)
        assert isinstance(flyout.background_brush(), QBrush)

        pixmap = QPixmap(4, 4)
        pixmap.fill(QColor("blue"))
        texture_brush = QBrush(pixmap)
        flyout.set_background_brush(texture_brush)
        assert flyout.background_brush() is texture_brush

        flyout.set_background_brush(None)
        assert flyout.background_brush() is None
    finally:
        flyout.deleteLater()
        host.deleteLater()


def test_set_border_color_overrides_and_resets(qapp):
    host = QWidget()
    flyout = BaseFlyout(host)
    try:
        flyout.set_border_color(QColor("#00ff00"))
        assert flyout.border_color() == QColor("#00ff00")

        flyout.set_border_color(None)
        assert flyout.border_color() is None
    finally:
        flyout.deleteLater()
        host.deleteLater()


def test_set_shadow_color_overrides_and_resets(qapp):
    host = QWidget()
    flyout = BaseFlyout(host)
    try:
        flyout.set_shadow_color(QColor("#3355ff"))
        assert flyout.shadow_color() == QColor("#3355ff")

        flyout.set_shadow_color(None)
        assert flyout.shadow_color() is None
    finally:
        flyout.deleteLater()
        host.deleteLater()


def test_paint_event_runs_with_custom_brush_border_and_shadow(qapp):
    """Smoke test: paintEvent must not choke on any override combination."""
    host = QWidget()
    host.resize(200, 200)
    host.show()
    flyout = BaseFlyout(host)
    try:
        flyout.set_background_brush(QColor("#202030"))
        flyout.set_border_color(QColor("#8888ff"))
        flyout.set_shadow_color(QColor("#4444ff"))
        flyout.setGeometry(10, 10, 100, 60)
        flyout.show()
        flyout.repaint()
        assert flyout.isVisible()
    finally:
        flyout.deleteLater()
        host.deleteLater()


def test_draw_rounded_shadow_uses_custom_color(qapp):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    from sli_ui_toolkit.ui.widgets.helpers.shadow_painter import draw_rounded_shadow

    image = QImage(40, 40, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    draw_rounded_shadow(
        painter,
        QRectF(10, 10, 20, 20),
        steps=6,
        radius=4,
        color=QColor("#ff00ff"),
    )
    painter.end()

    # Center is covered by every ring, so its color is blended purely from
    # the (magenta) shadow layers, with no black/gray contribution -- a
    # black shadow (the pre-fix default) would read as gray here instead.
    pixel = image.pixelColor(20, 20)
    assert pixel.alpha() > 0
    assert pixel.red() > pixel.green() + 20
    assert pixel.blue() > pixel.green() + 20
