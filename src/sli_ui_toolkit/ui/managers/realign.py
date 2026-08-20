"""Click-to-keyboard realign machinery for :class:`NavigationManager`.

A mouse click always kills the visible keyboard-focus ring (see
``NavigationManager.eventFilter``'s ``MouseButtonPress`` handling) but only
*sometimes* moves Qt's actual ``focusWidget()`` (only when the click landed
on something focusable) -- when it doesn't (empty space, a label, a disabled
control), Qt's focus silently stays on whatever was focused before the
click. Resuming arrow navigation from that stale widget makes the ring
reappear somewhere the user never looked at. Instead, the first arrow key
after a click re-anchors the ring on whichever widget is actually nearest
the click point, then lets that same key press navigate from there.

``ClickRealignCoordinator`` owns ALL of this state (the last click position,
whether a realign is still pending) and takes the ``NavigationManager`` as
an explicit argument where it must touch it (the registered sections) --
mirrors ``FlyoutFadeController``'s convention in
``composite/base_flyout/animation.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QWidget

from .navigation_debug import logger as _base_logger
from .navigation_debug import widget_label

if TYPE_CHECKING:
    from .navigation_manager import NavigationManager, NavigationSection

logger: logging.Logger = _base_logger


class ClickRealignCoordinator:
    """Owns the last-click position and whether a realign is still pending."""

    last_click_pos: QPoint | None = None
    realign_pending: bool = False

    def owning_section_for(
        self, manager: "NavigationManager", widget: QWidget
    ) -> tuple[object, "NavigationSection"] | None:
        """Walk *widget*'s ancestor chain for the first registered section
        that claims it (via ``owns()``, or by being the section's bare
        ``owner`` widget -- some ``owns()`` implementations already report
        ``True`` for their own owner, e.g. ``TabStripSection``, others
        don't, so both are checked at every ancestor level).
        """
        target: QWidget | None = widget
        while target is not None:
            for owner, spec in manager._sections:
                if spec.owns(target) or target is owner:
                    return owner, spec
            target = target.parentWidget()
        return None

    def realign_to_last_click(self, manager: "NavigationManager") -> bool:
        """Move focus to whichever registered section's widget is nearest
        the last mouse-click point, so a stale ``focusWidget()`` (see
        ``realign_pending``) doesn't drive the next arrow press. Returns
        ``True`` if focus was moved.
        """
        pos = self.last_click_pos
        if pos is None:
            return False
        clicked = QApplication.widgetAt(pos)
        if clicked is None:
            return False
        found = self.owning_section_for(manager, clicked)
        if found is None:
            return False
        owner, spec = found
        # A second click landing on the same nearest widget as before (e.g.
        # clicking the same toolbar spot twice) makes setFocus() below a
        # no-op *from Qt's point of view* -- focus doesn't actually change,
        # so no FocusIn fires, so the ring-reveal that normally rides on
        # FocusIn (Button.focusInEvent flipping _keyboard_focus back on)
        # never runs. Without this, the ring stays stuck in the
        # MouseButtonPress-suppressed state forever: every subsequent
        # reveal-only press looks like it did nothing, because nothing
        # about that widget actually changed. Compare focus before/after
        # below and force the ring back on manually when it didn't.
        previously_focused = QApplication.focusWidget()
        # The clicked widget itself is the nearest candidate by definition
        # -- prefer it directly over asking the section to guess from an
        # x-coordinate alone, which only ever considers its first/last row.
        # Skip this when the click landed exactly on the section's bare
        # owner widget rather than any real content inside it (e.g. row
        # padding, or the outer strip/container itself) -- some sections'
        # owns() reports that owner as "owned" too (to support the
        # unrelated arrow-key bootstrap path, see register()'s
        # _bootstrap_if_still_owner), but it is not a meaningful landing
        # spot on its own, and may not even be the widget that actually
        # handles keys (e.g. WorkspaceTabStrip vs. its real tab_bar
        # child) -- focus_nearest()/focus_first() are the section's own
        # idea of the right entry point instead.
        if (
            clicked is not owner
            and clicked.focusPolicy() == Qt.FocusPolicy.StrongFocus
            and clicked.isVisible()
            and clicked.isEnabled()
        ):
            try:
                from sli_ui_toolkit.ui.managers.nav_graph import focus_reason as _nav_focus_reason

                clicked.setFocus(_nav_focus_reason())
            except Exception:
                clicked.setFocus(Qt.FocusReason.OtherFocusReason)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "[nav] realign: click -> %s directly",
                    widget_label(clicked),
                )
            self.force_ring_if_focus_unchanged(previously_focused)
            return True
        # focus_first(ref_x)/focus_last(ref_x) always pick a *fixed* row
        # (topmost/bottommost) -- they model "entering this section from
        # above/below" for cross-section Up/Down handoff, where ref_x only
        # disambiguates left/right within that fixed row (see
        # ToolbarRowsSection.focus_first's docstring). A click can land on
        # any row, so prefer a section's own focus_nearest(pos), which
        # picks the row nearest the click's y too, falling back to
        # focus_first(ref_x) only for sections that don't implement it
        # (fine there since those are single-row/x-only sections anyway).
        focus_nearest = getattr(spec, "focus_nearest", None)
        if focus_nearest is not None:
            # 4.0: focus_nearest now requires reason — try new API, fallback to old
            try:
                from sli_ui_toolkit.ui.managers.nav_graph import focus_reason as _nav_focus_reason

                _reason = _nav_focus_reason()
                try:
                    _realign_ok = focus_nearest(pos, reason=_reason)
                except TypeError:
                    _realign_ok = focus_nearest(pos)
            except Exception:
                _realign_ok = focus_nearest(pos)
            if _realign_ok:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "[nav] realign: click -> nearest (2D) in %s",
                        type(owner).__name__,
                    )
                self.force_ring_if_focus_unchanged(previously_focused)
                return True
        # Generic fallback: find the nearest focusable widget *above* the
        # click within the section's owner widget tree.  Covers sections
        # that don't implement focus_nearest and sections whose
        # focus_nearest doesn't cover the click area (e.g. clicking
        # below the last card in a list that also has a footer panel).
        target = self.nearest_focusable(owner, pos)
        if target is not None:
            try:
                from sli_ui_toolkit.ui.managers.nav_graph import focus_reason as _nav_focus_reason2

                target.setFocus(_nav_focus_reason2())
            except Exception:
                target.setFocus(Qt.FocusReason.OtherFocusReason)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "[nav] realign: click -> nearest (generic) %s in %s",
                    widget_label(target),
                    type(owner).__name__,
                )
            self.force_ring_if_focus_unchanged(previously_focused)
            return True
        # No focusable widget above the click — don't realign.  The
        # click landed in empty space (padding, stretch, footer area);
        # jumping to a distant widget would be disorienting.
        return False

    @staticmethod
    def nearest_focusable(owner: QWidget, pos) -> QWidget | None:
        """Find the focusable descendant of *owner* closest to *pos*,
        but only if the click is at or below the topmost candidate.
        Clicks above all focusable widgets should not trigger a realign.
        """
        local_pos = owner.mapFromGlobal(pos)
        local_y = local_pos.y()
        candidates = [
            w
            for w in owner.findChildren(QWidget)
            if (
                w.focusPolicy() != Qt.FocusPolicy.NoFocus
                and w.isVisible()
                and w.isEnabled()
            )
        ]
        if not candidates:
            return None
        topmost = min(
            candidates,
            key=lambda w: w.mapTo(owner, w.rect().center()).y(),
        )
        topmost_y = topmost.mapTo(owner, topmost.rect().center()).y()
        if local_y < topmost_y:
            return None
        best = min(
            candidates,
            key=lambda w: abs(
                w.mapTo(owner, w.rect().center()).y() - local_y
            ),
        )
        return best

    @staticmethod
    def force_ring_if_focus_unchanged(previously_focused: QWidget | None) -> None:
        """If a realign target turned out to already be the focused widget,
        ``setFocus()`` was a no-op and no ``FocusIn`` fired to flip the
        ring back on after ``MouseButtonPress`` suppressed it. Restore it
        by hand so a reveal-only press actually reveals something instead
        of looking like a no-op that repeats on every re-click.
        """
        current = QApplication.focusWidget()
        if current is None or current is not previously_focused:
            return
        if not hasattr(current, "_keyboard_focus"):
            return
        current._keyboard_focus = True
        if hasattr(current, "_last_focus_reason"):
            current._last_focus_reason = Qt.FocusReason.OtherFocusReason
        current.update()

    @staticmethod
    def yield_to_native(focused: QWidget | None, event, realigned: bool) -> bool:
        """Hand *event* to *focused*'s own ``keyPressEvent`` (Left/Right on
        a tab strip, a spin box, etc. — anything the manager itself
        declines to own).

        Ordinarily this just means returning ``False`` and letting Qt's own
        delivery run its course — Qt already resolved the event's receiver
        before this filter ran, and if focus was never touched here that
        resolved receiver is still the right one. But when this same press
        just realigned focus via :meth:`realign_to_last_click`, that
        resolved receiver is stale — Qt would deliver to whatever held
        focus before the click, not to *focused*. In that case, dispatch
        the event to *focused* directly (mirrors
        ``ToolbarRowsSection._widget_handles``'s trial-dispatch) and
        consume it ourselves instead.
        """
        if not realigned or focused is None:
            return False
        focused.keyPressEvent(event)
        return True
