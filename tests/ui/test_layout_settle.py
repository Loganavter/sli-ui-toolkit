"""Guard tests for settle_layout (W0 of the qt-selfsizing epic).

A self-sizing host (own height derived from a child's size) must agree with
its contents in the same synchronous call: the size setter only posts the
host's Resize, so a layout left to the next turn paints one frame with stale
child geometry and QBoxLayout splits the delta into the wrong child
(growing exposes it, shrinking hides it). See QT_LAYOUT_PITFALLS.md.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.layout_settle import settle_layout


class _HintBox(QWidget):
    """Widget with a settable sizeHint.

    ``notify=False`` emulates a child whose hint-affecting state changed
    *without* ``updateGeometry()`` — the stale-cache condition behind the
    one-frame transient.
    """

    def __init__(self, w: int, h: int):
        super().__init__()
        self._hint = (w, h)
        self.notified = 0

    def set_hint(self, w: int, h: int, *, notify: bool = True) -> None:
        self._hint = (w, h)
        if notify:
            self.updateGeometry()

    def updateGeometry(self) -> None:  # noqa: N802 (Qt override)
        self.notified += 1
        super().updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        return QSize(*self._hint)


def _shelf(qapp):
    """Header (20) + content (40) host at the settled baseline (60)."""
    del qapp
    host = QWidget()
    box = QVBoxLayout(host)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(0)
    header = _HintBox(200, 20)
    content = _HintBox(200, 40)
    box.addWidget(header)
    box.addWidget(content)
    host.resize(200, 60)
    host.show()
    QApplication.processEvents()
    QApplication.processEvents()
    assert (header.height(), content.height(), host.height()) == (20, 40, 60)
    return host, box, header, content


def test_grow_settles_in_the_same_call(qapp):
    host, _box, header, content = _shelf(qapp)
    content.set_hint(200, 100, notify=False)  # stale cache, like the real bug
    host.setFixedHeight(120)
    settle_layout(host, header, content)  # no processEvents() here
    assert header.height() == 20
    assert content.height() == 100
    assert host.height() == 120


def test_shrink_settles_in_the_same_call(qapp):
    host, _box, header, content = _shelf(qapp)
    content.set_hint(200, 100, notify=False)
    host.setFixedHeight(120)
    settle_layout(host, header, content)
    content.set_hint(200, 40, notify=False)
    host.setFixedHeight(60)
    settle_layout(host, header, content)  # no processEvents() here
    assert header.height() == 20
    assert content.height() == 40
    assert host.height() == 60


def test_grow_without_hint_refresh_misattributes(qapp):
    """The defect, reproduced: a bare invalidate+activate (what Qt does next
    turn) with a stale child cache splits the growth into the wrong child,
    so merely re-running the layout is NOT a substitute for settle_layout."""
    host, box, header, content = _shelf(qapp)
    content.set_hint(200, 100, notify=False)
    host.setFixedHeight(120)
    box.invalidate()
    box.activate()
    assert header.height() != 20 or content.height() != 100


def test_none_children_skipped_and_hints_refreshed(qapp):
    host, _box, header, content = _shelf(qapp)
    before = (header.notified, content.notified)
    settle_layout(host, None, header, None, content)
    assert (header.notified, content.notified) == (before[0] + 1, before[1] + 1)


def test_widget_without_layout_is_noop(qapp):
    del qapp
    settle_layout(QWidget())
