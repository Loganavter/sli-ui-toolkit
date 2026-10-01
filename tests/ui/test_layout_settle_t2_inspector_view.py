"""T2 (qt-selfsizing): inspector page-resize settle (inspector/view.py).

``QStackedWidget`` only lays out its current page, so hidden section pages
kept their creation-time internals (a 640x480 scroll area inside a resized
page) and the freshly shown tab flashed one stale frame. The pane resized
every page on stack resizes / row switches but never settled the pages'
own layouts. Both legs now end with ``settle_layout`` (settling the page —
a different widget than the watched stack — never inside anyone's own
``resizeEvent``).

Each test asserts page/scroll agreement IN THE SAME synchronous call (no
``processEvents()`` between mutation and assertion), covering grow AND
shrink.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.ui.inspector.view import InspectorWindow

from tests.inspector_helpers import _build_button_inspection


def _shown_window(qapp):
    del qapp
    win = InspectorWindow()
    win.set_inspection(_build_button_inspection())
    win.resize(560, 400)
    win.show()
    QApplication.processEvents()
    QApplication.processEvents()
    return win


def _code_page(win):
    pane = win.active_pane()
    assert pane is not None
    return pane, pane.pages["Code"], pane.shell.pages_stack


def _assert_page_settled(win, page, stack):
    """Page/scroll agreement, stable across the next loop turns."""
    assert page.size() == stack.size()
    assert page.scroll_area.size() == page.size()
    QApplication.processEvents()
    QApplication.processEvents()
    assert page.scroll_area.size() == page.size()  # no one-frame transient


def test_stack_resize_settles_hidden_pages_grow(qapp):
    win = _shown_window(qapp)
    try:
        _pane, code, stack = _code_page(win)  # Code starts hidden
        win.resize(560, 650)
        # SAME synchronous call: no processEvents() since the resize.
        _assert_page_settled(win, code, stack)
    finally:
        win.close()


def test_stack_resize_settles_hidden_pages_shrink(qapp):
    win = _shown_window(qapp)
    try:
        _pane, code, stack = _code_page(win)
        win.resize(560, 650)
        QApplication.processEvents()
        QApplication.processEvents()
        win.resize(560, 300)
        # SAME synchronous call: no processEvents() since the resize.
        _assert_page_settled(win, code, stack)
    finally:
        win.close()


def test_row_switch_settles_freshly_shown_page(qapp):
    """Row switches agree same-call even when the page missed a resize.

    (Hardening leg: Qt's show processing already heals this offscreen, so
    this passes without the fix here — live styled/polish paths may defer
    it, hence the explicit settle. The RED-carrying legs are the two
    stack-resize tests above.)
    """
    win = _shown_window(qapp)
    try:
        pane, code, stack = _code_page(win)
        pane.show_section("Code")
        QApplication.processEvents()
        QApplication.processEvents()
        pane.show_section("Object")  # Code hidden again
        # Simulate a page that missed stack tracking (e.g. added after the
        # last stack resize): desynced size AND stale internals.
        code.resize(100, 100)
        code.scroll_area.resize(640, 480)
        pane.show_section("Code")  # no processEvents() after this switch
        _assert_page_settled(win, code, stack)
    finally:
        win.close()
