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
import os
import traceback
from typing import Any, Callable

# [flyout-nav] trace lines fire on every flyout show/hide once the host
# app's --debug is on, drowning out other subsystems' debug output. Gated
# on its own opt-in flag, off by default even under --debug -- same
# convention as sidebar_nav_list/debug.py's SLI_UI_NAVLIST_DEBUG.
logger = logging.getLogger(__name__)
if os.environ.get("SLI_UI_NAV_DEBUG", "").strip().lower() in (
    "",
    "0",
    "false",
    "no",
    "off",
):
    logger.setLevel(logging.WARNING)
else:
    logger.setLevel(logging.DEBUG)


def _is_alive_and_enabled(widget: QWidget | None) -> bool:
    if widget is None:
        return False
    try:
        return bool(widget.isVisible() and widget.isEnabled())
    except RuntimeError:
        return False


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
        # _unregister_nav_section() clears window.setFocusProxy(self)
        # synchronously, which makes Qt fall back to focusing the window's
        # first tab-order widget (CsdMenuTrigger) right then and there. It
        # used to run at the top of hide(), well before this method's fade
        # animation finishes -- so that fallback focus jump happened first,
        # and _restore_focus_policies() above only corrected it ~100ms
        # later once the fade completed, producing a visible CsdMenuTrigger
        # flash on every keyboard-driven close (e.g. Escape). Running it
        # after the restore closes that window.
        self._unregister_nav_section()
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
        logger.debug(
            "[flyout-nav] show() _previous_focus_widget=%s anchor_widget=%s anchor_kbd=%s",
            type(self._previous_focus_widget).__name__ if self._previous_focus_widget else None,
            type(getattr(self, "_anchor_widget", None)).__name__ if getattr(self, "_anchor_widget", None) else None,
            getattr(self, "_anchor_keyboard_focus", None),
        )
        window = self.parent().window() if self.parent() else None
        self._window_active_on_show = bool(window is not None and window.isActiveWindow())
        QWidget.show(self)  # type: ignore[arg-type]
        # show_aligned(grab_focus=False) sets _skip_focus_grab, which by
        # default also skips nav-section registration -- a purely
        # informational flyout (e.g. a value-preview pill) must not steal
        # keyboard focus *or* arrow-key routing from whatever the user was
        # already on. register_nav_section=True (also from show_aligned)
        # opts a grab_focus=False flyout back into registration without
        # grabbing focus -- for a flyout meant to read as a seamless
        # extension of its anchor's own controls (e.g.
        # MagnifierSettingsFlyout): the user keeps freely navigating the
        # anchor's buttons, and can still arrow (Up/Down) or click into this
        # flyout's own content, instead of arrow keys skipping over it
        # entirely to whatever's next in the app's unrelated tab order.
        skip_register = getattr(
            self, "_skip_nav_register", getattr(self, "_skip_focus_grab", False)
        )
        if not skip_register:
            # Register as a NavigationSection so arrow keys are routed here
            # instead of to the underlying section.
            self._register_nav_section()
        if getattr(self, "_skip_focus_grab", False):
            return
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
        # If the trigger had keyboard focus (arrow/Tab navigation), grant
        # the first child an OtherFocusReason so the focus ring is drawn
        # inside the flyout.  Mouse-opened flyouts keep MouseFocusReason
        # to suppress the ring.
        anchor_kbd = getattr(self, "_anchor_keyboard_focus", False)
        reason = Qt.FocusReason.OtherFocusReason if anchor_kbd else Qt.FocusReason.MouseFocusReason
        if target is not None:
            target.setFocus(reason)
        else:
            self.setFocus(reason)
        # Remembered so a fade-in's mid-animation child-hiding (see
        # FlyoutFadeController.sync_container_visibility) — which forces Qt
        # to yank focus off `target` onto the flyout itself, since Qt clears
        # focus from any widget in a subtree that gets hidden — can be
        # undone once the children are shown again (_on_show_animation_finished).
        self._grab_focus_target = target
        self._grab_focus_reason = reason

        logger.debug(
            "[flyout-nav] _grab_focus weakened=%d target=%s reason=%s anchor_kbd=%s",
            len(self._weakened_focus_ancestors),
            type(target).__name__ if target else "self",
            reason.name,
            anchor_kbd,
        )

    @staticmethod
    def _first_focusable(widget: QWidget, *, reverse: bool = False) -> QWidget | None:
        """Return the first (or, with ``reverse=True``, last) leaf
        StrongFocus descendant in layout order, or ``None``.

        A "leaf" is a StrongFocus widget that has no StrongFocus children —
        this skips containers like QScrollArea and finds the actual
        interactive buttons/rows.
        """
        children = widget.findChildren(QWidget)
        if reverse:
            children = list(reversed(children))
        for child in children:
            if child.focusPolicy() == Qt.FocusPolicy.StrongFocus:
                has_strong_child = any(
                    c.focusPolicy() == Qt.FocusPolicy.StrongFocus
                    for c in child.findChildren(QWidget)
                )
                if not has_strong_child:
                    return child
        return None

    def focus_first_child(self) -> bool:
        """Move keyboard focus to this flyout's first focusable control.

        Public counterpart to :meth:`_grab_focus` for callers that want to
        focus into an already-visible, not-yet-focused flyout on demand
        (e.g. a ``NavigationSection`` entering a linked flyout via
        :func:`~sli_ui_toolkit.managers.NavigationManager.extension_below`)
        without going through the full show()/register/weaken-ancestors
        flow. Returns ``False`` if the flyout has no focusable content.
        """
        target = self._first_focusable(self)
        if target is None:
            return False
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def focus_last_child(self) -> bool:
        """Same as :meth:`focus_first_child`, landing on the last control."""
        target = self._first_focusable(self, reverse=True)
        if target is None:
            return False
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def _restore_focus_policies(self) -> None:
        """Restore focus policies of ancestors weakened by :meth:`_grab_focus`.

        Called from :meth:`_finish_hide` so the window regains StrongFocus
        only after the flyout is actually gone — not on a timer.
        Restores focus to the widget that had it before the flyout opened,
        preferring the anchor widget (the explicit trigger) over the
        captured ``_previous_focus_widget`` which may point to MainWindow
        if focus shifted between the trigger click and ``show()``.
        """
        weakened = getattr(self, "_weakened_focus_ancestors", None)
        if weakened is None:
            logger.debug("[flyout-nav] _restore_focus_policies: no weakened list")
            return
        for w, policy in weakened:
            w.setFocusPolicy(policy)
        weakened.clear()
        # Prefer _anchor_widget (the explicit trigger passed to show_aligned)
        # over _previous_focus_widget (QApplication.focusWidget() at show()
        # time — may already be MainWindow if focus shifted). Either can
        # reference a widget whose underlying C++ object was since deleted
        # (e.g. its host tore down while this flyout was still open) --
        # querying isVisible()/isEnabled() on that raises RuntimeError from
        # shiboken rather than returning False, so guard both like
        # InterpolationFlyoutController._is_alive_and_visible does.
        anchor = getattr(self, "_anchor_widget", None)
        prev = getattr(self, "_previous_focus_widget", None)
        target = anchor if _is_alive_and_enabled(anchor) else prev
        actual_before = QApplication.focusWidget()
        logger.debug(
            "[flyout-nav] _restore_focus_policies: anchor=%s prev=%s target=%s actual_before=%s",
            type(anchor).__name__ if anchor else None,
            type(prev).__name__ if prev else None,
            type(target).__name__ if target else None,
            type(actual_before).__name__ if actual_before else None,
        )
        if _is_alive_and_enabled(target):
            # OtherFocusReason unconditionally would light up the keyboard
            # focus ring on the trigger even when the flyout closed because
            # of an outside mouse click — key off whether the user is
            # currently driving the app with the keyboard or the mouse.
            from sli_ui_toolkit.managers import NavigationManager
            restore_reason = (
                Qt.FocusReason.OtherFocusReason
                if NavigationManager.get_instance().last_input_was_keyboard()
                else Qt.FocusReason.MouseFocusReason
            )
            target.setFocus(restore_reason)
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
        # Give the actually-focused descendant first refusal on the
        # non-arrow extra keys (Return/Enter/Escape) -- its own native
        # keyPressEvent may do something specific to it (a combo box
        # opening its own dropdown on Enter) that this flyout's generic
        # handling below doesn't know about at all. Without this, `widget`
        # was accepted as a parameter but never actually used: every key
        # went straight to the flyout's own keyPressEvent, which only
        # special-cases clicking a focused Button -- any other focused
        # control's own Enter handling was silently unreachable.
        #
        # Deliberately scoped to _EXTRA_KEYS only, NOT _NAV_KEYS (arrows):
        # QAbstractSlider natively accepts all four arrow keys regardless
        # of orientation, so a Slider given first refusal on Up/Down would
        # always win and step its own value -- silently breaking row-to-row
        # / extension_below navigation (see ToolbarRowsSection,
        # NavigationManager.link_below) for any slider inside a flyout.
        # Arrow keys keep going straight to this flyout's own
        # _navigate_focusable, matching the existing, established behavior.
        if key in self._EXTRA_KEYS and widget is not None and widget is not self._flyout:
            child_event = QKeyEvent(
                QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier,
            )
            widget.keyPressEvent(child_event)
            if child_event.isAccepted():
                logger.debug(
                    "[flyout-nav] navigate key=%s → delivered to focused %s (accepted)",
                    hex(key), type(widget).__name__,
                )
                return True
        event = QKeyEvent(
            QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier,
        )
        self._flyout.keyPressEvent(event)
        logger.debug(
            "[flyout-nav] navigate key=%s → delivered to %s (accepted=%s)",
            hex(key), type(self._flyout).__name__, event.isAccepted(),
        )
        # Reporting True unconditionally here used to trap Up/Down inside
        # any flyout permanently: NavigationManager's own boundary hand-off
        # to an adjacent registered section (_neighbor(), see
        # navigation_manager.py) only triggers when the owning section
        # *declines* the key by returning False. A flyout whose own
        # keyPressEvent already moved focus to its next/previous internal
        # control (or "clicked" a focused row on Enter) did accept the
        # event, so this still reports True for those cases exactly as
        # before -- it only starts reporting False once the flyout's own
        # navigation runs out of children to move to, letting Up/Down
        # escape back out at that boundary instead of being silently
        # swallowed forever.
        return event.isAccepted()

    def focus_first(self) -> bool:
        return self._flyout.focus_first_child()

    def focus_last(self) -> bool:
        return self._flyout.focus_last_child()

    @property
    def extra_keys(self) -> frozenset[int]:
        return self._EXTRA_KEYS
