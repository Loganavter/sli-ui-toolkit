"""PreviewPanel — painted ``TextView`` migration contract.

The panel's text surface is the painted :class:`TextView` (no stock Qt text
widget, no QSS): read-only display, edit mode through the same canvas, and
the wheel consumed at the scroll edges so it never bubbles to the host.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.widgets.composite.preview_panel import PreviewPanel
from sli_ui_toolkit.ui.widgets.composite.text_view import TextView


def _wheel(angle_y: int) -> QWheelEvent:
    return QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, angle_y),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


class _WheelSpy(QWidget):
    """Host widget that counts any wheel event bubbling up to it."""

    def __init__(self) -> None:
        super().__init__()
        self.wheels = 0

    def wheelEvent(self, event) -> None:  # noqa: N802
        self.wheels += 1
        event.accept()


def test_text_roundtrip_and_painted_view(qtbot):
    panel = PreviewPanel("Preview")
    qtbot.addWidget(panel)

    assert isinstance(panel.text_view, TextView)
    assert panel.text_view.objectName() == "previewTextView"

    panel.set_text("hello\nworld")
    assert panel.text() == "hello\nworld"
    assert panel.text_view.text() == "hello\nworld"


def test_edit_mode_toggles_painted_canvas(qtbot):
    panel = PreviewPanel("Preview")
    qtbot.addWidget(panel)
    panel.set_text("abc")
    assert panel.text_view.is_editing() is False

    panel.set_edit_mode(True)
    assert panel.text_view.is_editing() is True
    assert panel.edit_button.isEnabled() is False
    assert panel.save_button.isEnabled() is True
    assert panel.revert_button.isEnabled() is True
    # The painted canvas IS the editor: inserting text mutates the buffer.
    panel.text_view.canvas().insert_text("X")
    assert panel.text() == "Xabc"

    panel.set_edit_mode(False)
    assert panel.text_view.is_editing() is False
    assert panel.edit_button.isEnabled() is True
    assert panel.save_button.isEnabled() is False
    assert panel.revert_button.isEnabled() is False


def test_wheel_at_edges_is_consumed_not_propagated(qtbot):
    spy = _WheelSpy()
    qtbot.addWidget(spy)
    spy.resize(240, 120)

    panel = PreviewPanel("Preview")
    panel.setParent(spy)
    panel.resize(240, 120)
    panel.set_text("\n".join(f"line {i}" for i in range(60)))

    spy.show()
    QApplication.processEvents()

    bar = panel.text_view.verticalScrollBar()
    # Content overflows, so there is somewhere to scroll.
    assert bar.maximum() > bar.minimum()

    # At the top, scrolling up is consumed and never bubbles to the host.
    bar.setValue(bar.minimum())
    up = _wheel(120)
    QApplication.sendEvent(panel.text_view.viewport(), up)
    assert up.isAccepted()
    assert spy.wheels == 0

    # At the bottom, scrolling down is consumed and never bubbles.
    bar.setValue(bar.maximum())
    down = _wheel(-120)
    QApplication.sendEvent(panel.text_view.viewport(), down)
    assert down.isAccepted()
    assert spy.wheels == 0

    # Away from an edge the wheel scrolls this view (still not the host).
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    before = bar.value()
    mid = _wheel(-120)
    QApplication.sendEvent(panel.text_view.viewport(), mid)
    assert mid.isAccepted()
    qtbot.wait(50)
    assert bar.value() > before
    assert spy.wheels == 0
