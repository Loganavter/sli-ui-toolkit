"""ButtonFamily: shared policies + combined geometry across buttons."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.widgets import Button, ButtonFamily


def _show(widget, qtbot):
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def _pair(qtbot, pos1=(10, 10), pos2=(100, 10), size=(60, 28), **kwargs):
    """Two shown sibling buttons on a shown host."""
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 200)
    b1 = Button(parent=host, size=size, **kwargs)
    b1.move(*pos1)
    b2 = Button(parent=host, size=size, **kwargs)
    b2.move(*pos2)
    host.show()
    qtbot.waitExposed(host)
    qtbot.waitExposed(b1)
    qtbot.waitExposed(b2)
    return host, b1, b2


def _hovered(button):
    return ButtonState.HOVERED in button._controller.states("_main")


def test_membership_add_remove(qtbot):
    fam = ButtonFamily()
    b1, b2 = Button(), Button()
    assert fam.buttons() == []
    fam.addButton(b1)
    fam.addButton(b1)  # duplicate: no-op
    fam.addButton(b2)
    assert fam.buttons() == [b1, b2]
    fam.removeButton(b1)
    assert fam.buttons() == [b2]
    fam.removeButton(b1)  # unknown: no-op, no raise
    assert fam.buttons() == [b2]


def test_shared_hover_off_by_default(qtbot):
    host, b1, b2 = _pair(qtbot)
    fam = ButtonFamily()
    fam.addButton(b1)
    fam.addButton(b2)
    qtbot.mouseMove(b1, QPoint(30, 14))
    assert _hovered(b1)
    assert not _hovered(b2)


def test_shared_hover_lights_whole_family(qtbot):
    host, b1, b2 = _pair(qtbot)
    fam = ButtonFamily()
    fam.setSharedHover(True)
    fam.addButton(b1)
    fam.addButton(b2)
    qtbot.mouseMove(b1, QPoint(30, 14))
    assert _hovered(b1)
    assert _hovered(b2)
    # Leaving all members clears the mirrored glow (via the poll backstop —
    # Leave synthesis is not guaranteed, so allow one poll interval).
    qtbot.mouseMove(host, QPoint(290, 90))
    qtbot.wait(200)
    assert not _hovered(b1)
    assert not _hovered(b2)


def test_disabling_shared_hover_clears_glow(qtbot):
    host, b1, b2 = _pair(qtbot)
    fam = ButtonFamily()
    fam.setSharedHover(True)
    fam.addButton(b1)
    fam.addButton(b2)
    qtbot.mouseMove(b1, QPoint(30, 14))
    assert _hovered(b2)
    fam.setSharedHover(False)
    assert not _hovered(b2)


def test_exclusive_unchecks_siblings(qtbot):
    b1 = _show(Button(toggle=True), qtbot)
    b2 = _show(Button(toggle=True), qtbot)
    fam = ButtonFamily()
    fam.setExclusive(True)
    fam.addButton(b1)
    fam.addButton(b2)
    assert fam.isExclusive()
    b1.setChecked(True)
    assert b1.isChecked()
    b2.setChecked(True)
    assert b2.isChecked()
    assert not b1.isChecked()


def test_exclusive_off_leaves_siblings_checked(qtbot):
    b1 = _show(Button(toggle=True), qtbot)
    b2 = _show(Button(toggle=True), qtbot)
    fam = ButtonFamily()
    fam.addButton(b1)
    fam.addButton(b2)
    b1.setChecked(True)
    b2.setChecked(True)
    assert b1.isChecked() and b2.isChecked()


def test_removed_member_leaves_group_logic(qtbot):
    b1 = _show(Button(toggle=True), qtbot)
    b2 = _show(Button(toggle=True), qtbot)
    fam = ButtonFamily()
    fam.setExclusive(True)
    fam.addButton(b1)
    fam.addButton(b2)
    fam.removeButton(b2)
    b1.setChecked(True)
    b2.setChecked(True)  # must not touch b1 anymore
    assert b1.isChecked() and b2.isChecked()


def test_union_rect_and_center(qtbot):
    host, b1, b2 = _pair(qtbot, pos2=(100, 50))
    fam = ButtonFamily()
    fam.addButton(b1)
    fam.addButton(b2)
    union = fam.unionRect()
    assert union.size().width() == 150
    assert union.size().height() == 68
    # Contains both members exactly.
    for b in (b1, b2):
        r = QRect(b.mapToGlobal(b.rect().topLeft()), b.rect().size())
        assert union.contains(r)
    assert fam.center() == union.center()
    # Mapped back into the host: the layout-local footprint.
    local = fam.unionRectMappedTo(host)
    assert local == QRect(10, 10, 150, 68)


def test_union_rect_empty_family(qtbot):
    fam = ButtonFamily()
    assert fam.unionRect().isNull()
    assert fam.center().isNull()
    host = _show(QWidget(), qtbot)
    assert fam.unionRectMappedTo(host).isNull()


def test_member_rects_mapped_to(qtbot):
    host, b1, b2 = _pair(qtbot, pos2=(100, 50))
    fam = ButtonFamily()
    fam.addButton(b1)
    fam.addButton(b2)
    rects = fam.memberRectsMappedTo(host)
    assert rects == {b1: QRect(10, 10, 60, 28), b2: QRect(100, 50, 60, 28)}
    assert fam.memberRectMappedTo(b1, host) == QRect(10, 10, 60, 28)
    # Non-member → null.
    assert fam.memberRectMappedTo(Button(), host).isNull()
    # Hidden members drop out of both forms.
    b1.hide()
    assert b1 not in fam.memberRectsMappedTo(host)
    assert fam.memberRectMappedTo(b1, host).isNull()


def test_geometry_changed_on_member_move(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 200)
    b1 = Button(parent=host, size=(60, 28))
    b1.move(10, 10)
    host.show()
    qtbot.waitExposed(b1)
    fam = ButtonFamily()
    fam.addButton(b1)
    fired: list = []
    fam.geometryChanged.connect(lambda: fired.append(1))
    b1.move(40, 40)
    assert fired
    before = fam.unionRect()
    b1.move(10, 10)
    assert fam.unionRect() != before
