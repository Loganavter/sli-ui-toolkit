"""BaseFlyout show/hide lifecycle — manager notification + focus restore.

Every flyout close funnels through :meth:`hide` (explicit
``start_closing_animation``, FlyoutManager passive dismiss / close_all, host
calls), and every open through :meth:`show` / :meth:`raise_` — the manager
registration stays in sync because these overrides notify it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

import logging
import traceback
from typing import Any, Callable

from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)


class _FlyoutLifecycleApi:
    """Mixin: hide / show / raise_ overrides + the real-hide completion.

    Not a QWidget itself — mixed into BaseFlyout (QWidget stays earlier in
    the MRO so ``super()`` here resolves to QWidget's own methods); relies
    on instance state assigned in ``BaseFlyout.__init__``
    (``flyout_manager``, ``_fade``, ``_show_animation``,
    ``_window_active_on_show``).
    """

    # Declared here only so mypy can resolve them across the mixin split —
    # the real definitions live in BaseFlyout.__init__ (widget.py). Plain
    # annotations only (no `= value`).
    _fade: Any
    _show_animation: Any
    flyout_manager: Any
    restore_focus_on_hide: Callable[[], bool]
    parentWidget: Any
    parent: Any

    def hide(self):
        self._unregister_nav_section()
        # Debug aid: every flyout close funnels through here (explicit
        # start_closing_animation, FlyoutManager passive dismiss / close_all,
        # host calls), so logging the caller stack shows WHO closed it.
        # DISABLED — remove the "# " comment prefix to re-enable.
        # if not any(
        #     "attach_in_window_widget" in f.filename or "overlay_layer.py" in f.filename
        #     for f in traceback.extract_stack()[:-1]
        # ):
        #     logger.debug(
        #         "BaseFlyout.hide() called by:\n%s",
        #         "".join(traceback.format_stack()[:-1]),
        #     )
        fm = getattr(self, "flyout_manager", None)
        if fm is not None:
            fm.request_hide(self)

        if self._fade.hide_fade_in_progress:
            # Already fading out; _on_hide_fade_finished does the real hide.
            return
        if self._fade.should_fade_out(self):
            self._fade.start_hide_fade(
                self,
                on_finished=self._on_hide_fade_finished,
                show_animation=self._show_animation,
            )
            return

        self._finish_hide()

    def _finish_hide(self) -> None:
        QWidget.hide(self)  # type: ignore[arg-type]

        # hide() already called request_hide once (before the fade); re-run it
        # after the widget is actually hidden so FlyoutManager re-checks
        # _any_visible() and drops its app-wide event filter when nothing else
        # is open. Idempotent: active flyout and anchor snapshots are already
        # cleared, and linked children are already hidden.
        fm = getattr(self, "flyout_manager", None)
        if fm is not None:
            try:
                fm.request_hide(self)
            except Exception:
                pass

        if not self.restore_focus_on_hide():
            return
        parent = self.parentWidget()
        window = parent.window() if parent is not None else None
        if window is None or window.isActiveWindow():
            # Already the active window (the common case for a
            # hover-driven flyout closing while the user's cursor is still
            # inside the host app) -- activateWindow()/setFocus() would be
            # a no-op WM round-trip in that case, and doing it on every
            # close of a flyout that hides at hover frequency is enough
            # synchronous WM traffic to visibly stall the main thread
            # (observed as an "app not responding" busy-cursor flash).
            return
        active = QApplication.activeWindow()
        if active is not None and active is not window:
            # Another window of this app became active while the flyout was
            # open (e.g. a dialog opened from a flyout row). Do not yank
            # focus back: on Wayland the activateWindow() request carries a
            # token whose surface was the focus window *when the token was
            # requested* (before the dialog focused), so the compositor
            # rejects it and marks the host window as demanding attention —
            # surfacing as a "«App» is ready" notification.
            return
        if not getattr(self, "_window_active_on_show", False):
            # The host window was already inactive (app in the background,
            # OS focus elsewhere) at the moment this flyout opened -- e.g. a
            # purely hover-driven flyout (slider hint, settings panel) that
            # opened just because the cursor passed over its trigger while
            # the user was working in another app. There is no prior focus
            # state to "restore" here, so calling activateWindow() would
            # only steal/ request OS focus for a window the user never
            # activated -- surfacing as an unsolicited taskbar flash / "app
            # wants attention" hint. Only windows that were genuinely active
            # when the flyout opened (and lost activation during its
            # lifetime, e.g. to a nested dialog) get focus handed back.
            return
        window.activateWindow()
        window.setFocus()

    # Declared here only so mypy can resolve them across the mixin split —
    # the real implementation lives in QWidget itself (later in the MRO) or
    # the sibling _FlyoutManagerApi mixin.

    def _on_hide_fade_finished(self) -> None:
        self._fade.on_hide_fade_finished(self, on_finished=self._finish_hide)

    def show(self):
        fm = getattr(self, "flyout_manager", None)
        if fm is not None:
            fm.request_show(self)
        window = self.parent().window() if self.parent() else None
        self._window_active_on_show = bool(window is not None and window.isActiveWindow())
        QWidget.show(self)  # type: ignore[arg-type]
        # Register as a NavigationSection so arrow keys are routed here
        # instead of to the underlying section.
        self._register_nav_section()
        # Grab keyboard focus.  Walk the parent chain and temporarily
        # weaken any StrongFocus ancestor so Qt's focus chain doesn't
        # redirect focus away from the flyout.
        self._grab_focus()

    def _grab_focus(self) -> None:
        """Grant keyboard focus to this flyout, working around Qt's
        parent-chain focus redirection."""
        weakened: list[tuple[QWidget, Qt.FocusPolicy]] = []
        w = self.parentWidget()
        while w is not None:
            if w.focusPolicy() == Qt.FocusPolicy.StrongFocus:
                weakened.append((w, w.focusPolicy()))
                w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            w = w.parentWidget()
        try:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        finally:
            for widget, policy in weakened:
                widget.setFocusPolicy(policy)

    def _register_nav_section(self) -> None:
        from sli_ui_toolkit.managers import NavigationManager

        manager = NavigationManager.get_instance()
        if not hasattr(self, "_nav_section_registered"):
            self._nav_section_registered = False
        if not self._nav_section_registered:
            section = _FlyoutNavigationSection(self)
            manager.register(self, section)
            self._nav_section_registered = True
            # Use setFocusProxy so that when the parent window gets focus
            # (e.g. via NavigationManager), it routes to the flyout.
            window = self.window()
            if window is not None:
                window.setFocusProxy(self)

    def _unregister_nav_section(self) -> None:
        if getattr(self, "_nav_section_registered", False):
            from sli_ui_toolkit.managers import NavigationManager

            # Clear the focus proxy before unregistering.
            window = self.window()
            if window is not None and window.focusProxy() is self:
                window.setFocusProxy(None)
            NavigationManager.get_instance().unregister(self)
            self._nav_section_registered = False

    def raise_(self) -> None:  # noqa: N802 — Qt API
        QWidget.raise_(self)  # type: ignore[arg-type]
        fm = getattr(self, "flyout_manager", None)
        if fm is not None and hasattr(fm, "ensure_overlay_stacking"):
            # Skip re-entry when we are the context menu being raised by stacking.
            if getattr(type(self), "flyout_group", None) == "context_menu":
                return
            try:
                fm.ensure_overlay_stacking(raised=self)
            except Exception:
                pass


class _FlyoutNavigationSection:
    """Minimal NavigationSection for flyouts.

    Consumes all arrow keys so the NavigationManager routes them here
    instead of to the underlying section.  Actual key handling is done
    by the flyout's own ``keyPressEvent``.
    """

    def __init__(self, flyout: QWidget) -> None:
        self._flyout = flyout

    def owns(self, widget: QWidget) -> bool:
        return widget is self._flyout or self._flyout.isAncestorOf(widget)

    def navigate(self, key: int, widget: QWidget) -> bool:
        return True

    def focus_first(self) -> bool:
        return False

    def focus_last(self) -> bool:
        return False
