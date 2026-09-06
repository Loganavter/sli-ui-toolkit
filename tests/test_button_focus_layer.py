from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QFocusEvent, QImage, QPainter, QPixmap

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.buttons.context import DrawContext
from sli_ui_toolkit.ui.widgets.buttons.layers.focus import FocusLayer
from sli_ui_toolkit.ui.widgets.buttons.variants import get_variant
from sli_ui_toolkit.widgets import Button


def _ctx(button, painter):
    return DrawContext(
        widget=button,
        painter=painter,
        rect=button.rect(),
        states=frozenset(),
        variant=get_variant("default"),
        corner_radius=6,
    )


def _pixmap_painter(button):
    pixmap = QPixmap(button.size())
    return pixmap, QPainter(pixmap)


def test_focus_layer_skips_mouse_focus(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")

    button = Button(text="")
    button._keyboard_focus = False
    _pixmap, painter = _pixmap_painter(button)
    try:
        ctx = _ctx(button, painter)
        assert not FocusLayer().applies(ctx)
    finally:
        painter.end()
        button.deleteLater()


def test_focus_layer_applies_for_keyboard_focus(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")

    button = Button(text="")
    button.show()
    button.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    button._keyboard_focus = True

    _pixmap, painter = _pixmap_painter(button)
    try:
        ctx = _ctx(button, painter)
        assert FocusLayer().applies(ctx)
    finally:
        painter.end()
        button.deleteLater()


def test_focus_layer_draws_accent_ring(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")

    button = Button(text="")
    button.resize(80, 40)
    button.show()
    button.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    button._keyboard_focus = True

    image = QImage(80, 40, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    try:
        FocusLayer().draw(_ctx(button, painter), tm)
    finally:
        painter.end()
        button.deleteLater()

    accent = QColor(tm.get_color("accent"))
    # Ring pixels should be near-accent along the left edge (inset ~1-2px).
    matches = 0
    for y in range(4, 36):
        for x in range(0, 3):
            c = image.pixelColor(x, y)
            if abs(c.red() - accent.red()) < 40 and c.alpha() > 40:
                matches += 1
    assert matches > 5


def test_focus_in_event_records_keyboard_reason(qapp):
    # Ring modality follows the input device (NavigationManager 4.2.4),
    # reason is only a hint: drive the manager's input flag explicitly.
    from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

    mgr = NavigationManager.get_instance()
    button = Button(text="")
    button.show()
    try:
        mgr._last_input_keyboard = False
        event = QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.MouseFocusReason)
        button.focusInEvent(event)
        assert button._keyboard_focus is False

        # Qt-generated Tab on a mouse history draws no ring (the fix).
        event = QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)
        button.focusInEvent(event)
        assert button._keyboard_focus is False

        mgr._last_input_keyboard = True
        event = QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)
        button.focusInEvent(event)
        assert button._keyboard_focus is True

        # Programmatic Mouse-steal during keyboard navigation preserves ring.
        event = QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.MouseFocusReason)
        button.focusInEvent(event)
        assert button._keyboard_focus is True

        # ActiveWindow on a mouse history draws no ring.
        mgr._last_input_keyboard = False
        event = QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.ActiveWindowFocusReason)
        button.focusInEvent(event)
        assert button._keyboard_focus is False
    finally:
        mgr._last_input_keyboard = False

    out = QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.ActiveWindowFocusReason)
    button.focusOutEvent(out)
    assert button._keyboard_focus is False
    button.deleteLater()
