"""BaseFlyout show/hide lifecycle — manager notification + focus restore.

Every flyout close funnels through :meth:`hide` (explicit
``start_closing_animation``, FlyoutManager passive dismiss / close_all, host
calls), and every open through :meth:`show` / :meth:`raise_` — the manager
registration stays in sync because these overrides notify it.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

import logging
import traceback
from typing import Any, Callable

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
        logger.debug(
            "[flyout-nav] hide() called on %s id=%s fade_in_progress=%s should_fade=%s",
            type(self).__name__, id(self),
            self._fade.hide_fade_in_progress,
            self._fade.should_fade_out(self),
        )
        self._unregister_nav_section()
        # Restore focus immediately — before fade animation starts.
        # The fade defers _finish_hide() for ~100ms, during which Qt's
        # focus chain moves focus to CsdMenuTrigger.  Restoring here
        # avoids that intermediate jump.
        self._restore_focus_policies()
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
        logger.debug(
            "[flyout-nav] _finish_hide %s id=%s", type(self).__name__, id(self)
        )
        # Restore focus BEFORE hiding — setFocus() during hide causes a
        # synchronous focus jump that Qt processes via the event loop,
        # resulting in an intermediate CsdMenuTrigger flash. Restoring
        # before hide avoids this.
        self._restore_focus_policies()
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
        logger.debug(
            "[flyout-nav] _on_hide_fade_finished %s id=%s", type(self).__name__, id(self)
        )
        self._fade.on_hide_fade_finished(self, on_finished=self._finish_hide)

    def show(self):
        logger.debug(
            "[flyout-nav] show() called on %s id=%s", type(self).__name__, id(self)
        )
        fm = getattr(self, "flyout_manager", None)
        if fm is not None:
            fm.request_show(self)
        # Capture focus BEFORE register/setFocusProxy — they redirect focus
        # to the flyout, losing the original trigger widget.
        self._previous_focus_widget = QApplication.focusWidget()
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
        # WA_ShowWithoutActivating suppresses window activation which
        # blocks keyboard events.  Activate the window so the flyout
        # receives keyboard input.
        w = self.window()
        if w is not None and not w.isActiveWindow():
            w.activateWindow()

    def _grab_focus(self) -> None:
        """Grant keyboard focus to this flyout, working around Qt's
        parent-chain focus redirection.

        Weakens every StrongFocus ancestor to NoFocus and stores them on
        ``self._weakened_focus_ancestors`` so they can be restored in
        :meth:`_finish_hide` — no timers, no deferred hacks.

        Saves the previously focused widget so :meth:`_finish_hide` can
        restore focus to it.

        Focuses the first focusable child (StrongFocus descendant)
        directly instead of the flyout container itself, skipping the
        extra navigation step.  Falls back to ``self.setFocus()`` when
        no focusable child is found.
        """
        self._weakened_focus_ancestors: list[tuple[QWidget, Qt.FocusPolicy]] = []
        w = self.parentWidget()
        while w is not None:
            if w.focusPolicy() == Qt.FocusPolicy.StrongFocus:
                self._weakened_focus_ancestors.append((w, w.focusPolicy()))
                w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            w = w.parentWidget()
        target = self._first_focusable(self)
        if target is not None:
            target.setFocus(Qt.FocusReason.MouseFocusReason)
        else:
            self.setFocus(Qt.FocusReason.MouseFocusReason)

        logger.debug(
            "[flyout-nav] _grab_focus weakened=%d target=%s",
            len(self._weakened_focus_ancestors),
            type(target).__name__ if target else "self",
        )

    @staticmethod
    def _first_focusable(widget: QWidget) -> QWidget | None:
        """Return the first leaf StrongFocus descendant in layout order,
        or ``None``.

        A "leaf" is a StrongFocus widget that has no StrongFocus children —
        this skips containers like QScrollArea and finds the actual
        interactive buttons/rows.
        """
        for child in widget.findChildren(QWidget):
            if child.focusPolicy() == Qt.FocusPolicy.StrongFocus:
                has_strong_child = any(
                    c.focusPolicy() == Qt.FocusPolicy.StrongFocus
                    for c in child.findChildren(QWidget)
                )
                if not has_strong_child:
                    return child
        return None

    def _restore_focus_policies(self) -> None:
        """Restore focus policies of ancestors weakened by :meth:`_grab_focus`.

        Called from :meth:`_finish_hide` so the window regains StrongFocus
        only after the flyout is actually gone — not on a timer.
        Restores focus to the widget that had it before the flyout opened.
        """
        weakened = getattr(self, "_weakened_focus_ancestors", None)
        if weakened is None:
            logger.debug("[flyout-nav] _restore_focus_policies: no weakened list")
            return
        for w, policy in weakened:
            w.setFocusPolicy(policy)
        weakened.clear()
        prev = getattr(self, "_previous_focus_widget", None)
        actual_before = QApplication.focusWidget()
        logger.debug(
            "[flyout-nav] _restore_focus_policies: prev=%s actual_before=%s prev_visible=%s prev_enabled=%s",
            type(prev).__name__ if prev else None,
            type(actual_before).__name__ if actual_before else None,
            prev.isVisible() if prev else None,
            prev.isEnabled() if prev else None,
        )
        if prev is not None and prev.isVisible() and prev.isEnabled():
            prev.setFocus(Qt.FocusReason.OtherFocusReason)
            QApplication.processEvents()
            actual_after = QApplication.focusWidget()
            logger.debug(
                "[flyout-nav] _restore_focus_policies: setFocus → actual_after=%s",
                type(actual_after).__name__ if actual_after else None,
            )

    def _register_nav_section(self) -> None:
        from sli_ui_toolkit.managers import NavigationManager

        manager = NavigationManager.get_instance()
        if not hasattr(self, "_nav_section_registered"):
            self._nav_section_registered = False
        if not self._nav_section_registered:
            section = _FlyoutNavigationSection(self)
            manager.register(self, section)
            self._nav_section_registered = True
            window = self.window()
            if window is not None:
                window.setFocusProxy(self)
            logger.debug(
                "[flyout-nav] registered %s", type(self).__name__,
            )

    def _unregister_nav_section(self) -> None:
        if getattr(self, "_nav_section_registered", False):
            from sli_ui_toolkit.managers import NavigationManager

            window = self.window()
            if window is not None and window.focusProxy() is self:
                window.setFocusProxy(None)
            NavigationManager.get_instance().unregister(self)
            self._nav_section_registered = False
            logger.debug(
                "[flyout-nav] unregistered %s", type(self).__name__,
            )

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

    Consumes all navigation-relevant keys and delivers them directly to the
    flyout's ``keyPressEvent``.  This bypasses ``WA_ShowWithoutActivating``
    which prevents Qt from routing keyboard events to the widget normally.
    """

    _NAV_KEYS: frozenset[int] = frozenset({
        0x01000012,  # Key_Left
        0x01000014,  # Key_Right
        0x01000013,  # Key_Up
        0x01000015,  # Key_Down
    })

    _EXTRA_KEYS: frozenset[int] = frozenset({
        0x01000005,  # Key_Return
        0x01000004,  # Key_Enter
        0x01000000,  # Key_Escape
    })

    def __init__(self, flyout: QWidget) -> None:
        self._flyout = flyout

    def owns(self, widget: QWidget) -> bool:
        result = widget is self._flyout or self._flyout.isAncestorOf(widget)
        if result:
            logger.debug(
                "[flyout-nav] owns(%s) → True (flyout=%s)",
                type(widget).__name__, type(self._flyout).__name__,
            )
        return result

    def navigate(self, key: int, widget: QWidget) -> bool:
        if key not in self._NAV_KEYS and key not in self._EXTRA_KEYS:
            return False
        event = QKeyEvent(
            QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier,
        )
        self._flyout.keyPressEvent(event)
        logger.debug(
            "[flyout-nav] navigate key=%s → delivered to %s (accepted=%s)",
            hex(key), type(self._flyout).__name__, event.isAccepted(),
        )
        return True

    def focus_first(self) -> bool:
        return False

    def focus_last(self) -> bool:
        return False

    @property
    def extra_keys(self) -> frozenset[int]:
        return self._EXTRA_KEYS
