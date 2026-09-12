"""Regression guard: click-outside-clears-focus must stay on one shared
app-wide filter, not one QApplication.installEventFilter per CustomLineEdit
instance (see item #9 in the API consistency audit, kept private in the
improve-imgsli-internal-docs repo, sli-ui-toolkit/docs/dev/API_CONSISTENCY_AUDIT.md)."""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.widgets.helpers.editable_text import _OUTSIDE_CLICK
from sli_ui_toolkit.widgets import CustomLineEdit


def _show(widget, qtbot):
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)


def test_many_line_edits_register_into_one_shared_coordinator(qapp):
    """Every CustomLineEdit must join the same coordinator singleton, not
    carry its own private outside-click filter object."""
    edits = [CustomLineEdit() for _ in range(5)]
    try:
        for edit in edits:
            assert edit in _OUTSIDE_CLICK._widgets
    finally:
        for edit in edits:
            edit.deleteLater()


def test_creating_line_edits_does_not_install_a_new_app_filter_each_time(qapp):
    """The one regression this guards against directly: a future change that
    goes back to ``app.installEventFilter(...)`` inside ``apply_editable_text_
    behavior`` (once per widget) instead of routing through the shared
    coordinator. Forces a fresh install so the count is exact, then restores
    the coordinator's real installation afterward.
    """
    was_installed = _OUTSIDE_CLICK._installed_app is qapp
    if was_installed:
        qapp.removeEventFilter(_OUTSIDE_CLICK)
        _OUTSIDE_CLICK._installed_app = None

    original_install = QApplication.installEventFilter
    install_calls_for_coordinator = []

    def spy_install(self, filt):
        if filt is _OUTSIDE_CLICK:
            install_calls_for_coordinator.append(filt)
        return original_install(self, filt)

    edits = []
    try:
        with patch.object(QApplication, "installEventFilter", spy_install):
            edits = [CustomLineEdit() for _ in range(5)]
        assert len(install_calls_for_coordinator) == 1, (
            "5 CustomLineEdit instances should install the shared outside-click "
            "coordinator on QApplication exactly once, not once per widget"
        )
    finally:
        for edit in edits:
            edit.deleteLater()
        if not was_installed:
            qapp.removeEventFilter(_OUTSIDE_CLICK)
            _OUTSIDE_CLICK._installed_app = None


def test_click_outside_clears_focus_click_inside_keeps_it(qtbot, qapp):
    """End-to-end behavior through the consolidated coordinator: unrelated
    outside clicks still clear focus, clicks on/inside the field don't."""
    host = QWidget()
    host.resize(300, 200)
    edit = CustomLineEdit(host)
    edit.move(10, 10)
    other = QWidget(host)
    other.resize(50, 50)
    other.move(10, 100)
    _show(host, qtbot)

    qtbot.mouseClick(edit, Qt.MouseButton.LeftButton)
    qtbot.wait(10)
    assert edit.hasFocus(), "clicking the field must focus it"

    qtbot.mouseClick(other, Qt.MouseButton.LeftButton)
    qtbot.wait(10)
    assert not edit.hasFocus(), "clicking an unrelated widget must clear the field's focus"

    host.deleteLater()
