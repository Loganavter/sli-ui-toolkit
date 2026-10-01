"""T2 (qt-selfsizing): dialog auto-size settle (dialogs/dialog_helpers.py).

``auto_size_dialog`` derives the dialog size from its content hint
(``resize`` from ``sizeHint``) while a ``QLayout`` places the children, but
ran with no synchronous settle — only a bare ``singleShot(0)``. The fix
extracts the synchronous core ``apply_auto_size`` (refresh hints, resize,
settle in the same call); the wrapper applies it synchronously when the
dialog is already visible and only defers while hidden (hints invalid).

Each test asserts child geometry/hint agreement IN THE SAME synchronous
call (no ``processEvents()`` between mutation and assertion), covering
grow AND shrink. (``apply_auto_size`` is imported inside the tests that
need it so the pre-fix tree fails this module on geometry — the missing
settle — rather than on a missing import.)
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.dialogs.dialog_helpers import auto_size_dialog


class _HintBox(QWidget):
    """Widget with a settable sizeHint.

    ``notify=False`` emulates a child whose hint-affecting state changed
    *without* ``updateGeometry()`` — the stale-cache condition behind the
    one-frame transient.
    """

    def __init__(self, w: int, h: int):
        super().__init__()
        self._hint = (w, h)

    def set_hint(self, w: int, h: int, *, notify: bool = True) -> None:
        self._hint = (w, h)
        if notify:
            self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        return QSize(*self._hint)


def _dialog(qapp, content_h: int = 40):
    """Shown header (20) + content host at the settled baseline."""
    del qapp
    dialog = QDialog()
    box = QVBoxLayout(dialog)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(0)
    header = _HintBox(200, 20)
    content = _HintBox(200, content_h)
    box.addWidget(header)
    box.addWidget(content)
    dialog.resize(200, 20 + content_h)
    dialog.show()
    QApplication.processEvents()
    QApplication.processEvents()
    assert (header.height(), content.height()) == (20, content_h)
    return dialog, header, content


def _assert_settled(dialog, header, content, width, height):
    """Same-call agreement + no drift on the next loop turns."""
    assert (dialog.width(), dialog.height()) == (width, height)
    assert header.height() + content.height() == height
    sync = (header.height(), content.height())
    QApplication.processEvents()
    QApplication.processEvents()
    assert (header.height(), content.height()) == sync  # no transient


def test_auto_size_settles_grow(qapp):
    dialog, header, content = _dialog(qapp)
    try:
        content.set_hint(200, 100, notify=False)  # stale cache
        auto_size_dialog(dialog)  # no processEvents() here
        _assert_settled(dialog, header, content, 250, 150)
        assert content.height() > 40  # grew with its hint
    finally:
        dialog.close()


def test_auto_size_settles_shrink(qapp):
    dialog, header, content = _dialog(qapp, content_h=100)
    try:
        content.set_hint(200, 100, notify=False)
        auto_size_dialog(dialog)
        QApplication.processEvents()
        QApplication.processEvents()
        grown = content.height()
        content.set_hint(200, 40, notify=False)  # stale cache
        auto_size_dialog(dialog)  # no processEvents() here
        _assert_settled(dialog, header, content, 250, 90)
        assert content.height() < grown  # shrank with its hint
    finally:
        dialog.close()


def test_auto_size_honors_minimums(qapp):
    dialog, header, content = _dialog(qapp)
    try:
        auto_size_dialog(dialog, min_width=400, min_height=300)
        _assert_settled(dialog, header, content, 400, 300)
    finally:
        dialog.close()


def test_auto_size_still_defers_while_hidden(qapp):
    """Hidden dialogs keep the old deferred behavior (hints invalid)."""
    del qapp
    dialog = QDialog()
    box = QVBoxLayout(dialog)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(0)
    content = _HintBox(200, 100)
    box.addWidget(content)
    try:
        auto_size_dialog(dialog)  # hidden: posted, not applied yet
        QApplication.processEvents()
        QApplication.processEvents()
        assert (dialog.width(), dialog.height()) == (250, 130)
    finally:
        dialog.close()


def test_apply_auto_size_core_settles_same_call(qapp):
    """The extracted core settles synchronously on its own."""
    from sli_ui_toolkit.ui.dialogs.dialog_helpers import apply_auto_size

    dialog, header, content = _dialog(qapp)
    try:
        content.set_hint(200, 100, notify=False)  # stale cache
        apply_auto_size(dialog)  # no processEvents() here
        _assert_settled(dialog, header, content, 250, 150)
    finally:
        dialog.close()
