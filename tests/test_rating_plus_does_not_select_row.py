"""Nested rating +/- must not select the row (that closes UnifiedFlyout)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget
from sli_ui_toolkit.ui.widgets.list_items.rating_item import RatingListItem


def test_rating_plus_does_not_emit_item_selected(qapp):
    parent = QWidget()
    selected = []

    item = RatingListItem(
        index=0,
        text="shot.png",
        rating=1,
        full_path="/tmp/shot.png",
        image_number=1,
        get_rating=lambda *_: 1,
        increment_rating=lambda *_: None,
        decrement_rating=lambda *_: None,
        create_rating_gesture=lambda *_args, **_kwargs: None,
        on_update_drop_indicator=lambda *_: None,
        on_clear_drop_indicator=lambda: None,
        parent=parent,
        is_current=True,
    )
    item.itemSelected.connect(selected.append)
    item.show()
    parent.show()
    qapp.processEvents()

    plus = item.btn_plus
    center = plus.rect().center()
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(center),
        plus.mapToGlobal(center),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(center),
        plus.mapToGlobal(center),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(plus, press)
    QApplication.sendEvent(plus, release)
    qapp.processEvents()

    assert selected == []
    assert press.isAccepted()

    parent.deleteLater()
