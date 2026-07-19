"""UnifiedFlyout multi-select / batch reorder smoke."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.widgets import UnifiedFlyout


def _mouse_event(event_type, widget, pos, buttons):
    return QMouseEvent(
        event_type,
        QPointF(pos),
        widget.mapToGlobal(pos),
        Qt.MouseButton.LeftButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def test_create_double_list_ctrl_toggle_selection(qapp, qtbot):
    host = QWidget()
    host.resize(640, 480)
    qtbot.addWidget(host)
    host.show()

    left = QWidget(host)
    right = QWidget(host)
    left.setGeometry(20, 20, 40, 24)
    right.setGeometry(80, 20, 40, 24)
    left.show()
    right.show()

    flyout = UnifiedFlyout.create_double_list(
        parent_window=host,
        anchor_left=left,
        anchor_right=right,
        left_items=["a", "b", "c", "d"],
        right_items=["x", "y"],
        current_left=0,
        current_right=0,
    )
    # populate happens in showAsSingle, not bare show()
    flyout.showAsSingle(1, left)
    qapp.processEvents()

    panel = flyout.panel_left
    widgets = panel._item_widgets()
    assert len(widgets) >= 3

    widgets[1].itemSelectionToggled.emit(1)
    widgets[2].itemSelectionToggled.emit(2)
    assert panel.selected_indices() == {1, 2}
    assert widgets[1].is_selected is True
    assert widgets[2].is_selected is True

    # Drag indices from a selected row include the whole set.
    assert widgets[1].drag_indices() == [1, 2]
    # Unselected row stays single.
    assert widgets[0].drag_indices() == [0]

    flyout.hide()
    flyout.deleteLater()


def test_rating_button_click_clears_marquee_selection(qapp, qtbot):
    host = QWidget()
    host.resize(640, 480)
    qtbot.addWidget(host)
    host.show()

    left = QWidget(host)
    right = QWidget(host)
    left.setGeometry(20, 20, 40, 24)
    right.setGeometry(80, 20, 40, 24)
    left.show()
    right.show()

    flyout = UnifiedFlyout.create_double_list(
        parent_window=host,
        anchor_left=left,
        anchor_right=right,
        left_items=["a", "b", "c", "d"],
        right_items=["x", "y"],
        current_left=0,
        current_right=0,
    )
    flyout.showAsSingle(1, left)
    qapp.processEvents()

    panel = flyout.panel_left
    widgets = panel._item_widgets()
    panel.set_selected_indices({1, 2})
    assert panel.selected_indices() == {1, 2}

    widgets[0]._on_plus_clicked()

    assert panel.selected_indices() == set()
    assert widgets[1].is_selected is False
    assert widgets[2].is_selected is False

    flyout.hide()
    flyout.deleteLater()


def test_drag_outside_selection_clears_selection_but_selected_drag_keeps_it(
    qapp, qtbot, monkeypatch
):
    host = QWidget()
    host.resize(640, 480)
    qtbot.addWidget(host)
    host.show()

    left = QWidget(host)
    right = QWidget(host)
    left.setGeometry(20, 20, 40, 24)
    right.setGeometry(80, 20, 40, 24)
    left.show()
    right.show()

    flyout = UnifiedFlyout.create_double_list(
        parent_window=host,
        anchor_left=left,
        anchor_right=right,
        left_items=["a", "b", "c", "d"],
        right_items=["x", "y"],
        current_left=0,
        current_right=0,
    )
    flyout.showAsSingle(1, left)
    qapp.processEvents()

    class DragServiceStub:
        def is_dragging(self):
            return True

    import sli_ui_toolkit.ui.widgets.list_items.rating_item as rating_item

    monkeypatch.setattr(rating_item, "get_dragdrop_service", lambda: DragServiceStub())

    panel = flyout.panel_left
    widgets = panel._item_widgets()
    panel.set_selected_indices({1, 2})

    outside_row = widgets[0]
    center = outside_row.rect().center()
    drag_distance = QApplication.startDragDistance() + 1
    move_pos = center + QPoint(drag_distance, 0)
    outside_row.mousePressEvent(
        _mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            outside_row,
            center,
            Qt.MouseButton.LeftButton,
        )
    )
    outside_row.mouseMoveEvent(
        _mouse_event(
            QMouseEvent.Type.MouseMove,
            outside_row,
            move_pos,
            Qt.MouseButton.LeftButton,
        )
    )
    assert panel.selected_indices() == set()

    panel.set_selected_indices({1, 2})
    selected_row = widgets[1]
    center = selected_row.rect().center()
    move_pos = center + QPoint(drag_distance, 0)
    selected_row.mousePressEvent(
        _mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            selected_row,
            center,
            Qt.MouseButton.LeftButton,
        )
    )
    selected_row.mouseMoveEvent(
        _mouse_event(
            QMouseEvent.Type.MouseMove,
            selected_row,
            move_pos,
            Qt.MouseButton.LeftButton,
        )
    )
    assert panel.selected_indices() == {1, 2}

    flyout.hide()
    flyout.deleteLater()


def test_simple_adapter_batch_reorder(qapp):
    flyout = UnifiedFlyout.create_double_list(
        parent_window=QWidget(),
        anchor_left=QWidget(),
        anchor_right=QWidget(),
        left_items=["a", "b", "c", "d"],
        right_items=[],
    )
    controller = flyout.main_controller
    controller.reorder_items_in_list(list_num=1, indices=[1, 3], dest_index=0)
    names = [i.display_name for i in flyout.store.document.list1]
    assert names == ["b", "d", "a", "c"]
