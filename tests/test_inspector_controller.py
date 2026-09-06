"""InspectorController: Shift+click selection, overlays, capture flow."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.inspector.controller import InspectorController
from sli_ui_toolkit.ui.inspector.view import InspectorWindow
from sli_ui_toolkit.widgets import Button, ButtonRegion, Switch


def _theme(app):
    tm = ThemeManager.get_instance()
    tm.register_palettes(
        {"accent": "#0078d4", "dialog.text": "#111111"},
        {"accent": "#0096ff", "dialog.text": "#dddddd"},
    )
    tm.set_theme("light", app)
    return tm


def _click(widget, *, shift: bool = False) -> QMouseEvent:
    center = widget.mapToGlobal(widget.rect().center())
    modifiers = (
        Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    )
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        center,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        modifiers,
    )


def test_plain_click_does_not_commit(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(text="x")
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        assert ctrl._handle_mouse_press(_click(button, shift=False)) is False
        assert ctrl._committed_widget is None
    finally:
        ctrl.shutdown()


def test_shift_click_commits_and_shows_window(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(regions=[ButtonRegion(id="main")], variant="surface")
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        assert ctrl._handle_mouse_press(_click(button, shift=True)) is True
        assert ctrl._committed_widget is button
        assert win.isVisible()
        # overlay exists on the widget's top-level window
        assert host.window() in ctrl._overlays
        assert ctrl._active_overlay is not None
        # Button-family → region rects mapped into the overlay
        assert len(ctrl._active_overlay._regions) == 1
    finally:
        ctrl.shutdown()


def test_escape_clears_selection(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(text="x")
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        ctrl._handle_mouse_press(_click(button, shift=True))
        assert ctrl._committed_widget is button
        from PySide6.QtGui import QKeyEvent

        esc = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        assert ctrl._handle_key_press(esc) is True
        assert ctrl._committed_widget is None
    finally:
        ctrl.shutdown()


def test_capture_tokens_populates_live_tokens(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(text="x")
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        ctrl._select_widget(button, global_pos=QPoint(0, 0))
        assert not win._current.live_tokens
        ctrl._capture_tokens()
        assert win._current.live_tokens
        keys = {f.name for f in win._current.live_tokens}
        assert "surface.list" in keys
    finally:
        ctrl.shutdown()


def test_widget_activated_selects_child(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    switch = Switch()
    button = Button(text="x")
    layout.addWidget(switch)
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        ctrl._select_widget(button, global_pos=QPoint(0, 0))
        ctrl._on_widget_activated(switch)
        assert ctrl._committed_widget is switch
        assert win.active_pane()._current.family == "Switch"
    finally:
        ctrl.shutdown()


def test_tree_activation_opens_new_tab(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    switch = Switch()
    button = Button(text="x")
    layout.addWidget(switch)
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        ctrl._select_widget(button, global_pos=QPoint(0, 0))
        assert win.tabs.count() == 1
        assert win.active_pane().widget is button
        ctrl._on_widget_activated(switch)
        assert win.tabs.count() == 2
        assert ctrl._committed_widget is switch
        assert win.active_pane().widget is switch
        # re-activating the same widget switches to its tab, no duplicate
        ctrl._on_widget_activated(switch)
        assert win.tabs.count() == 2
        assert win.active_pane().widget is switch
    finally:
        ctrl.shutdown()


def test_tree_hover_highlights_widget_and_clears_back_to_committed(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    switch = Switch()
    button = Button(text="x")
    layout.addWidget(switch)
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        ctrl._select_widget(button, global_pos=QPoint(0, 0))
        assert ctrl._hover_widget is None
        ctrl._on_tree_hover(switch)
        assert ctrl._hover_widget is switch
        assert ctrl._active_overlay is not None
        ctrl._on_tree_hover_cleared()
        assert ctrl._hover_widget is None
        # overlay falls back to the committed widget
        assert ctrl._active_overlay._target_rect is not None
        ctrl._on_tree_hover(button)
        assert ctrl._hover_widget is button
        ctrl._on_tree_hover_cleared()
        assert ctrl._hover_widget is None
    finally:
        ctrl.shutdown()


def _key(key) -> "QKeyEvent":
    from PySide6.QtGui import QKeyEvent

    return QKeyEvent(
        QKeyEvent.Type.KeyPress,
        key,
        Qt.KeyboardModifier.NoModifier,
    )


def test_selecting_inside_modal_dialog_reparents_inspector_under_modal(qapp):
    """Find Action-style ApplicationModal dialog must not block the
    inspector window: committing a widget inside it reparents the inspector
    as a *child window* of the modal (Qt's modal filter exempts descendants
    of the modal window) — without hiding/showing the modal, which would
    visually close and reopen it. Escape restores the top-level parenting."""
    from PySide6.QtWidgets import QDialog

    dialog = QDialog()
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    layout = QVBoxLayout(dialog)
    button = Button(text="x")
    layout.addWidget(button)
    dialog.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        assert dialog.windowModality() == Qt.WindowModality.ApplicationModal
        original_flags = win.windowFlags()
        ctrl._handle_mouse_press(_click(button, shift=True))
        assert ctrl._committed_widget is button
        # The inspector becomes a child window of the modal.
        assert win.parentWidget() is dialog
        assert win.isVisible()
        # setParent(parent, flags) replaces window flags — the CSD/frameless
        # setup of the decorated QDialog must survive the round trip.
        assert win.windowFlags() == original_flags
        # The modal itself is untouched — no hide/show flicker.
        assert dialog.windowModality() == Qt.WindowModality.ApplicationModal
        assert dialog.isVisible()
        # Escape drops the selection and restores the top-level parenting.
        ctrl._handle_key_press(_key(Qt.Key.Key_Escape))
        assert ctrl._committed_widget is None
        assert win.parentWidget() is None
        assert win.isVisible()
        assert win.windowFlags() == original_flags
    finally:
        ctrl.shutdown()


def test_hiding_modal_detaches_inspector_child_window(qapp):
    """The modal's reject/accept path hides it without a Close event — the
    inspector child window must be detached then, or it hides along with it."""
    from PySide6.QtWidgets import QDialog

    dialog = QDialog()
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    layout = QVBoxLayout(dialog)
    button = Button(text="x")
    layout.addWidget(button)
    dialog.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        ctrl._handle_mouse_press(_click(button, shift=True))
        assert win.parentWidget() is dialog
        dialog.hide()
        qapp.processEvents()
        assert win.parentWidget() is None
        assert win.isVisible()
    finally:
        ctrl.shutdown()


def test_closing_inspected_window_clears_stale_selection(qapp):
    """Closing the window that holds the committed widget must not leave the
    inspector holding a dangling reference — later interactions keep working
    (the old behavior crashed on the deleted widgets and hung the tool)."""
    from PySide6.QtWidgets import QDialog

    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    button = Button(text="x")
    layout.addWidget(button)
    dialog.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        ctrl._handle_mouse_press(_click(button, shift=True))
        assert ctrl._committed_widget is button
        dialog.close()
        qapp.processEvents()
        # Committed is dropped once its window is gone.
        assert ctrl._committed_widget is None
        # The stale overlay must not survive either.
        assert ctrl._active_overlay is None
        # A plain click (clear path) and hover polling stay crash-free.
        assert ctrl._handle_mouse_press(_click(button, shift=False)) is False
        ctrl._poll_hover()
        ctrl._refresh_overlay()
    finally:
        ctrl.shutdown()


def test_selecting_a_deleted_widget_clears_instead_of_crashing(qapp):
    from PySide6.QtWidgets import QDialog

    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    button = Button(text="x")
    layout.addWidget(button)
    dialog.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        ctrl._select_widget(button, global_pos=QPoint(0, 0))
        assert ctrl._committed_widget is button
        from shiboken6 import delete

        delete(dialog)
        # Re-activating the stale tree node must reset, not raise.
        ctrl._on_widget_activated(button)
        assert ctrl._committed_widget is None
    finally:
        ctrl.shutdown()


def test_plain_click_suspends_highlight_and_inspector_click_resumes(qapp):
    """A plain click in the inspected window hides the highlight but keeps
    the committed widget; clicking back on the inspector restores it."""
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(text="x")
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        ctrl._handle_mouse_press(_click(button, shift=True))
        assert ctrl._committed_widget is button
        assert ctrl._active_overlay is not None
        # Plain click on the inspected window: highlight hides, selection stays.
        ctrl._handle_mouse_press(_click(button, shift=False))
        assert ctrl._committed_widget is button
        assert ctrl._overlay_suspended is True
        assert ctrl._active_overlay is None
        # Click back on the inspector window: highlight restored.
        ctrl._handle_mouse_press(_click(win, shift=False))
        assert ctrl._overlay_suspended is False
        assert ctrl._active_overlay is not None
    finally:
        ctrl.shutdown()


def test_closing_inspector_window_clears_highlight(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(text="x")
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        ctrl._handle_mouse_press(_click(button, shift=True))
        assert ctrl._committed_widget is button
        win.close()
        qapp.processEvents()
        assert ctrl._committed_widget is None
        assert ctrl._active_overlay is None
    finally:
        ctrl.shutdown()


def test_tree_hover_does_not_revive_suspended_highlight(qapp):
    """Hovering the inspector's tree rows or clicking region rows must not
    silently re-light a suspended highlight (it made the highlight look
    permanently stuck while the user worked in the inspected window)."""
    host = QWidget()
    layout = QVBoxLayout(host)
    button = Button(text="x")
    layout.addWidget(button)
    host.show()
    qapp.processEvents()

    win = InspectorWindow()
    ctrl = InspectorController(qapp, win, _theme(qapp))
    try:
        ctrl._handle_mouse_press(_click(button, shift=True))
        ctrl._handle_mouse_press(_click(button, shift=False))
        assert ctrl._overlay_suspended is True
        assert ctrl._active_overlay is None
        # Tree hover / region click paths must stay dark while suspended.
        ctrl._on_tree_hover(button)
        assert ctrl._overlay_suspended is True
        assert ctrl._active_overlay is None
        ctrl._on_region_selected("main")
        assert ctrl._active_overlay is None
        # Clicking the inspector resumes and re-lights the highlight.
        ctrl._handle_mouse_press(_click(win, shift=False))
        assert ctrl._overlay_suspended is False
        assert ctrl._active_overlay is not None
    finally:
        ctrl.shutdown()
