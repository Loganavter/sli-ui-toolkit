"""ToolkitDragDropService lifecycle + de-host-coupling."""
from __future__ import annotations
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget
from sli_ui_toolkit.ui.services.dragdrop_service import ToolkitDragDropService
def _mouse_event(pos: QPointF = QPointF(5, 5)) -> QMouseEvent:
    return QMouseEvent(QMouseEvent.Type.MouseButtonPress, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
def _global_event(pos: QPointF = QPointF(5, 5)) -> QMouseEvent:
    return QMouseEvent(QMouseEvent.Type.MouseButtonRelease, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
def test_register_and_unregister_target(qapp):
    svc = ToolkitDragDropService()
    tgt = QWidget()
    tgt.show()
    svc.register_drop_target(tgt)
    assert tgt in svc._drop_targets
    svc.register_drop_target(tgt)
    assert svc._drop_targets.count(tgt) == 1
    svc.unregister_drop_target(tgt)
    assert tgt not in svc._drop_targets
    svc.unregister_drop_target(tgt)
    tgt.deleteLater()
    qapp.processEvents()
def test_cancel_drag_cleans_state(qapp):
    svc = ToolkitDragDropService()
    class Src(QWidget):
        list_num = 1
        index = 0
    src = Src()
    svc.start_drag(src, _mouse_event())
    assert svc.is_dragging() is True
    svc.cancel_drag()
    assert svc.is_dragging() is False
    assert svc.get_source_data() is None
    svc.cancel_drag()
def test_finish_drag_without_target_cleans(qapp, qtbot):
    svc = ToolkitDragDropService()
    class Src(QWidget):
        list_num = 1
        index = 2
    src = Src()
    svc.start_drag(src, _mouse_event())
    assert svc.is_dragging()
    svc.finish_drag(_global_event(QPointF(9999, 9999)))
    assert not svc.is_dragging()
@pytest.mark.parametrize("payload_source", ["getter", "attr", "extractor"])
def test_generic_payload_de_host_coupling(qapp, payload_source):
    if payload_source == "extractor":
        svc = ToolkitDragDropService(payload_extractor=lambda w: {"id": 42, "index": 3, "custom": True})
        src = QWidget()
        src.index = 3  # noqa: attr-defined
    elif payload_source == "getter":
        svc = ToolkitDragDropService()
        class Src(QWidget):
            def get_drag_payload(self):
                return {"id": 42, "index": 3, "custom": True}
        src = Src()
    else:
        class Src(QWidget):
            drag_payload = {"id": 42, "index": 3, "custom": True}
        src = Src()
        svc = ToolkitDragDropService()
    svc.start_drag(src, _mouse_event())
    assert svc.is_dragging()
    data = svc.get_source_data()
    assert data is not None
    assert data["id"] == 42
    assert data["index"] == 3
    svc.cancel_drag()
def test_legacy_list_num_still_works(qapp):
    svc = ToolkitDragDropService()
    class Src(QWidget):
        list_num = 2
        index = 5
    src = Src()
    svc.start_drag(src, _mouse_event())
    assert svc.is_dragging()
    assert svc.get_source_data()["list_num"] == 2
    svc.cancel_drag()
    class BadSrc(QWidget):
        list_num = 99
        index = 0
    bad = BadSrc()
    svc.start_drag(bad, _mouse_event())
    assert not svc.is_dragging()
def test_set_payload_extractor_injects(qapp):
    svc = ToolkitDragDropService()
    svc.set_payload_extractor(lambda w: {"from": "extractor", "index": 0})
    src = QWidget()
    svc.start_drag(src, _mouse_event())
    assert svc.get_source_data()["from"] == "extractor"
    svc.cancel_drag()
    svc.set_payload_extractor(None)
    svc.start_drag(QWidget(), _mouse_event())
    assert not svc.is_dragging()
def test_event_filter_lifecycle(qapp):
    svc = ToolkitDragDropService()
    class Src(QWidget):
        list_num = 1
        index = 0
    src = Src()
    assert svc._event_filter_installed is False
    svc.start_drag(src, _mouse_event())
    assert svc._event_filter_installed is True
    svc.cancel_drag()
    assert svc._event_filter_installed is False
def test_drop_target_handle_drop_called(qapp, qtbot):
    svc = ToolkitDragDropService()
    received = []
    class Target(QWidget):
        def can_accept_drop(self, payload):
            return payload.get("index") == 1
        def handle_drop(self, payload, pos):
            received.append(payload)
        def clear_drop_indicator(self):
            pass
        def update_drop_indicator(self, pos):
            pass
    class Src(QWidget):
        list_num = 1
        index = 1
    host = QWidget()
    host.show()
    qtbot.addWidget(host)
    tgt = Target(parent=host)
    tgt.resize(100, 100)
    tgt.show()
    qtbot.addWidget(tgt)
    qapp.processEvents()
    svc.register_drop_target(tgt)
    src = Src()
    svc.start_drag(src, _mouse_event(QPointF(10, 10)))
    global_pos = tgt.mapToGlobal(tgt.rect().center())
    svc._update_drag_position(QPointF(global_pos))
    assert svc._current_target is tgt
    svc.finish_drag(_global_event(QPointF(global_pos)))
    assert received and received[0]["index"] == 1
    assert not svc.is_dragging()
    tgt.deleteLater()
