"""A flyout's arrow navigation must follow VISUAL ROWS, not x order.

Regression (owner report 2026-10-19, label-text flyout live walk): the flyout's
``_navigate_focusable`` collected every ``StrongFocus`` descendant and sorted it
**by centre x only** — so a right-aligned control (a ``Switch``) sorted with the
right-hand column and Down jumped backwards, while a side-by-side pair in one
row (``По краям`` / ``На линии``) was chained as consecutive vertical steps, so
Up from the right button walked left. Measured live at the time: Down went
``Opacity → Draw background(right-aligned switch) → Text color(up the panel) →
Background → Edges → Split line``.

The traversal now groups controls into visual rows (centre-y bands, x inside a
row): Up/Down step rows (nearest column), Left/Right step inside the row.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from sli_ui_toolkit.widgets import BaseFlyout, Button, Switch


class _Focusable(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.label = label
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(40, 24)


def _build(qtbot):
    """A panel shaped like the label-text flyout: full-width rows, one row with a
    right-aligned Switch, and a last row with two side-by-side controls.

    Every widget created here is returned so the test keeps a Python reference —
    a parentless widget whose wrapper is collected is deleted by shiboken.
    """
    host = QWidget()
    host.setMinimumSize(300, 300)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)

    flyout = BaseFlyout(host)
    keep: list[QWidget] = [host, flyout]
    for name in ("Row A", "Row B"):
        widget = _Focusable(name)
        flyout.add_row(name, widget)
        keep.append(widget)
    switch_holder = QWidget()
    holder_layout = QHBoxLayout(switch_holder)
    switch_label = _Focusable("Switch row label")
    switch = Switch()
    holder_layout.addWidget(switch_label)
    holder_layout.addWidget(switch)
    flyout.add_row("Draw background", switch_holder)
    keep += [switch_holder, switch_label, switch]

    pair_holder = QWidget()
    pair_layout = QHBoxLayout(pair_holder)
    left = _Focusable("Left radio")
    right = _Focusable("Right radio")
    pair_layout.addWidget(left)
    pair_layout.addWidget(right)
    flyout.add_row("Position", pair_holder)
    keep += [pair_holder, left, right]

    flyout.show()
    qapp = QApplication.instance()
    if qapp is not None:
        qapp.processEvents()
    return {"flyout": flyout, "switch": switch, "left": left, "right": right, "keep": keep}


def _focus_label() -> str:
    focused = QApplication.focusWidget()
    return getattr(focused, "label", type(focused).__name__ if focused else "<none>")


def _step(flyout: BaseFlyout, key) -> None:
    flyout._navigate_focusable(key)


def test_down_walks_visual_rows(qapp, qtbot):
    built = _build(qtbot)
    flyout, switch = built["flyout"], built["switch"]

    # y order: the second full-width row comes after the first, not a
    # right-hand control of an earlier row (the old x-sort's backward jump).
    row_a = next(w for w in built["keep"] if getattr(w, "label", "") == "Row A")
    row_a.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    _step(flyout, Qt.Key.Key_Down)
    qapp.processEvents()
    assert _focus_label() == "Row B", _focus_label()

    # A row step keeps the COLUMN: from the right-aligned Switch, Down lands on
    # the right half of the pair row.
    switch.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    _step(flyout, Qt.Key.Key_Down)
    qapp.processEvents()
    assert _focus_label() == "Right radio", _focus_label()

    # At the bottom edge Down must NOT step sideways inside the row (that was
    # the reported "the two bottom controls think they are stacked").
    built["left"].setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    _step(flyout, Qt.Key.Key_Down)
    qapp.processEvents()
    assert _focus_label() != "Right radio", "Down stepped sideways inside the row"


def test_right_then_up_steps_inside_then_row_wise(qapp, qtbot):
    built = _build(qtbot)
    flyout, left, right = built["flyout"], built["left"], built["right"]
    left.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()

    _step(flyout, Qt.Key.Key_Right)
    qapp.processEvents()
    assert _focus_label() == "Right radio", _focus_label()

    # Up from the right half goes to the row ABOVE (never sideways).
    _step(flyout, Qt.Key.Key_Up)
    qapp.processEvents()
    assert _focus_label() != "Left radio", "Up moved sideways inside the row"
    assert built["keep"]
