"""CheckBox: ``stateChanged`` on every change, and a row shape a host can use.

Two gaps a host had to shim (REAL-Video-Enhancer's ``advanced_settings``):

* ``stateChanged`` fired only from ``setCheckState`` — a click, ``Space`` or
  ``setChecked`` emitted ``toggled`` alone. Every case below is compared with a
  stock ``QCheckBox`` on the same Qt: same order, same count, same int payload.
* the control kept Button's 36x36 square (Fixed policy, a 32 px floor), so a
  host that wanted a checkbox at the start of a settings row had to release
  the minimums, the maximums and the size policy itself. ``row=True`` is that
  path.

Measured on QCheckBox 6.12 (the oracle, not memory): a *bool* write emits
``stateChanged`` **before** ``toggled`` (Qt emits it from ``checkStateSet``),
while ``setCheckState`` and the tri-state cycle emit ``toggled`` first.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.widgets import CheckBox

QWIDGETSIZE_MAX = 16777215


def _theme() -> None:
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")


class _Pairs:
    """The toolkit checkbox and a stock ``QCheckBox`` under the same actions."""

    def __init__(self, qtbot, *, tristate: bool = False) -> None:
        _theme()
        self.mine = CheckBox("Option", tristate=tristate)
        self.ref = QCheckBox("Option")
        self.ref.setTristate(tristate)
        for widget in (self.mine, self.ref):
            qtbot.addWidget(widget)
            widget.show()
            qtbot.waitExposed(widget)
        self.log_mine: list[tuple[str, object]] = []
        self.log_ref: list[tuple[str, object]] = []
        for widget, log in ((self.mine, self.log_mine), (self.ref, self.log_ref)):
            widget.toggled.connect(lambda c, log=log: log.append(("toggled", bool(c))))
            widget.stateChanged.connect(
                lambda s, log=log: log.append(("stateChanged", int(s)))
            )

    def apply(self, qtbot, action) -> None:
        for widget in (self.mine, self.ref):
            action(widget)
        assert self.log_mine == self.log_ref, (self.log_mine, self.log_ref)
        assert self.mine.checkState() == self.ref.checkState()

    def clear(self) -> None:
        self.log_mine.clear()
        self.log_ref.clear()


def _click(qtbot):
    def action(widget) -> None:
        qtbot.mouseClick(widget, Qt.MouseButton.LeftButton, pos=widget.rect().center())

    return action


def _space(qtbot):
    def action(widget) -> None:
        widget.setFocus()
        qtbot.keyClick(widget, Qt.Key.Key_Space)

    return action


def test_click_emits_state_changed_like_qt(qtbot) -> None:
    pairs = _Pairs(qtbot)

    pairs.apply(qtbot, _click(qtbot))
    assert pairs.log_mine == [("toggled", True), ("stateChanged", 2)]

    pairs.clear()
    pairs.apply(qtbot, _click(qtbot))
    assert pairs.log_mine == [("toggled", False), ("stateChanged", 0)]


def test_space_emits_state_changed_like_qt(qtbot) -> None:
    pairs = _Pairs(qtbot)

    pairs.apply(qtbot, _space(qtbot))
    assert pairs.log_mine == [("toggled", True), ("stateChanged", 2)]

    pairs.clear()
    pairs.apply(qtbot, _space(qtbot))
    assert pairs.log_mine == [("toggled", False), ("stateChanged", 0)]


def test_set_checked_emits_state_changed_like_qt(qtbot) -> None:
    pairs = _Pairs(qtbot)

    pairs.apply(qtbot, lambda widget: widget.setChecked(True))
    assert pairs.log_mine == [("stateChanged", 2), ("toggled", True)]

    # A repeat write is silent in Qt.
    pairs.clear()
    pairs.apply(qtbot, lambda widget: widget.setChecked(True))
    assert pairs.log_mine == []

    pairs.clear()
    pairs.apply(qtbot, lambda widget: widget.setChecked(False))
    assert pairs.log_mine == [("stateChanged", 0), ("toggled", False)]


def test_no_op_set_checked_emits_nothing(qtbot) -> None:
    checkbox = CheckBox("Option")
    qtbot.addWidget(checkbox)
    log: list[tuple[str, object]] = []
    checkbox.toggled.connect(lambda c: log.append(("toggled", bool(c))))
    checkbox.stateChanged.connect(lambda s: log.append(("stateChanged", int(s))))

    checkbox.setChecked(False)

    assert log == []


def test_set_check_state_emits_state_changed_like_qt(qtbot) -> None:
    pairs = _Pairs(qtbot, tristate=True)
    state = Qt.CheckState

    pairs.apply(qtbot, lambda widget: widget.setCheckState(state.PartiallyChecked))
    assert pairs.log_mine == [("toggled", True), ("stateChanged", 1)]

    # Partial -> checked keeps isChecked() true: stateChanged alone.
    pairs.clear()
    pairs.apply(qtbot, lambda widget: widget.setCheckState(state.Checked))
    assert pairs.log_mine == [("stateChanged", 2)]

    pairs.clear()
    pairs.apply(qtbot, lambda widget: widget.setCheckState(state.Checked))
    assert pairs.log_mine == []

    pairs.clear()
    pairs.apply(qtbot, lambda widget: widget.setCheckState(state.Unchecked))
    assert pairs.log_mine == [("toggled", False), ("stateChanged", 0)]


def test_tristate_click_cycle_emits_state_changed_like_qt(qtbot) -> None:
    pairs = _Pairs(qtbot, tristate=True)

    pairs.apply(qtbot, _click(qtbot))
    assert pairs.log_mine == [("toggled", True), ("stateChanged", 1)]

    pairs.clear()
    pairs.apply(qtbot, _click(qtbot))
    assert pairs.log_mine == [("stateChanged", 2)]

    pairs.clear()
    pairs.apply(qtbot, _click(qtbot))
    assert pairs.log_mine == [("toggled", False), ("stateChanged", 0)]


def test_set_checked_collapses_partial_and_emits_like_qt(qtbot) -> None:
    pairs = _Pairs(qtbot, tristate=True)
    pairs.mine.setCheckState(Qt.CheckState.PartiallyChecked)
    pairs.ref.setCheckState(Qt.CheckState.PartiallyChecked)
    pairs.clear()

    pairs.apply(qtbot, lambda widget: widget.setChecked(True))

    assert pairs.log_mine == [("stateChanged", 2)]


def test_row_shape_releases_the_control_square(qtbot) -> None:
    _theme()
    host = QWidget()
    qtbot.addWidget(host)
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    checkbox = CheckBox("Option", row=True)
    # The layout parents it to the host: registering both would make pytest-qt
    # close a child the host already deleted.
    layout.addWidget(checkbox, 1)
    host.resize(400, 80)
    host.show()
    qtbot.waitExposed(host)

    policy = checkbox.sizePolicy()
    assert policy.horizontalPolicy() == QSizePolicy.Policy.Minimum
    assert policy.verticalPolicy() == QSizePolicy.Policy.Fixed
    assert checkbox.minimumWidth() == 0
    assert checkbox.maximumWidth() == QWIDGETSIZE_MAX

    # The layout is allowed to widen the row and keeps the one-line height.
    assert checkbox.width() > checkbox.sizeHint().width()
    assert checkbox.height() == checkbox.sizeHint().height()


def test_default_checkbox_keeps_the_control_square(qtbot) -> None:
    _theme()
    checkbox = CheckBox("Option")
    qtbot.addWidget(checkbox)
    checkbox.show()
    qtbot.waitExposed(checkbox)

    assert checkbox.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed
    assert checkbox.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
    assert checkbox.width() == checkbox.sizeHint().width()
