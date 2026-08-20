"""Reusable ``NavigationSection`` implementations.

App-specific sections (e.g. a session-picker card grid) stay in the host
app; this module holds sections generic enough to serve any host built on
this toolkit.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import widget_label

if TYPE_CHECKING:
    # TYPE_CHECKING-only: the composite package's __init__ pulls in a lot
    # (list_panel, timeline_widget, ...) that isn't safe to import eagerly
    # from ui/managers, which loads much earlier in the app's import graph
    # (see docs/legacy/plan_combobox_baseflyout_unification.md §5 for the
    # exact circular-import trap this avoids). `from __future__ import
    # annotations` above makes the IconListWidget annotation below lazy, so
    # this import only ever runs for type checkers, never at runtime.
    from sli_ui_toolkit.ui.widgets.composite.sidebar_nav_list import IconListWidget


def _focus_reason() -> Qt.FocusReason:
    """Reason that respects mouse vs keyboard modality for new-tab bootstrap.

    `NavigationManager.last_input_was_keyboard()` tracks the last
    MouseButtonPress vs KeyPress.  A new tab opened from a mouse click
    (session picker card) should land with `MouseFocusReason` so the ring
    stays hidden; a keyboard open (Enter on picker, arrow bootstrap)
    should use `OtherFocusReason` so the ring shows.  Centralized here so
    every `setFocus` in this module follows the same policy instead of
    unconditionally lighting up the ring.
    """
    try:
        from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

        if not NavigationManager.get_instance().last_input_was_keyboard():
            return Qt.FocusReason.MouseFocusReason
    except Exception:
        pass
    return Qt.FocusReason.OtherFocusReason

# [nav-*] trace lines fire on every arrow-key navigate() call once the host
# app's --debug is on, drowning out other subsystems' debug output. Gated
# on its own opt-in flag, off by default even under --debug -- same
# convention as sidebar_nav_list/debug.py's SLI_UI_NAVLIST_DEBUG.
logger = logging.getLogger(__name__)
if os.environ.get("UI_NAV_DEBUG", "").strip().lower() in (
    "",
    "0",
    "false",
    "no",
    "off",
):
    logger.setLevel(logging.WARNING)
else:
    logger.setLevel(logging.DEBUG)


class ToolbarRowsSection:
    """Up/Down between toolbar rows, Left/Right between buttons in a row.

    ``NavigationManager`` leaves Left/Right to native widget handling by
    default (QTabBar, QSpinBox, ...) — this section opts back in via
    ``extra_keys`` so arrow navigation is symmetric: Down/Up cross rows,
    Left/Right move within the current row's focusable buttons, skipping
    disabled/hidden ones by construction (``_focusable`` already filters
    them out, so stepping to index ± 1 in that list can never land on one).

    A host's canvas/sliders (or anything else that already binds arrows to
    its own behavior, e.g. pan or value-adjustment) must be excluded from
    ``rows_provider`` — this section only ever claims widgets inside the
    given row containers.

    ``on_exit_left``, if given, is tried when Left is pressed on the
    leftmost focusable control of a row — e.g. handing off to a sidebar
    list to the left of this section's content, mirroring
    ``IconListNavSection``'s own ``on_exit_right``. Neither side needs to
    know the other's type, just a plain callable. ``None`` (the default)
    keeps the original behavior: Left/Right never escape a row, since
    Up/Down already own row-to-row (and, by extension, section-to-section)
    transitions.
    """

    def __init__(
        self,
        rows_provider: Callable[[], list[QWidget | None]],
        *,
        tag: str = "toolbar-rows",
        on_exit_left: Callable[[], bool] | None = None,
    ) -> None:
        self._rows_provider = rows_provider
        self._tag = tag
        self._on_exit_left = on_exit_left

    def _rows(self) -> list[QWidget]:
        return [r for r in self._rows_provider() if r is not None and r.isVisible()]

    def _row_of(self, widget: QWidget) -> QWidget | None:
        for row in self._rows():
            if row is widget or row.isAncestorOf(widget):
                return row
        return None

    def owns(self, widget: QWidget) -> bool:
        return self._row_of(widget) is not None

    @staticmethod
    def _focusable(row: QWidget) -> list[QWidget]:
        # Sorted by on-screen x, not findChildren()'s construction/reparent
        # order -- a widget added to the row's layout late (e.g. grouped
        # into a sub-container after other buttons were already built) can
        # sit anywhere in the QObject child list regardless of where it
        # actually renders, which would make Left/Right jump to a screen
        # position that doesn't match the arrow direction.
        items = [
            c for c in row.findChildren(QWidget)
            if (
                c.focusPolicy() == Qt.FocusPolicy.StrongFocus
                and c.isVisible() and c.isEnabled()
            )
        ]
        return sorted(items, key=lambda w: w.mapToGlobal(w.rect().center()).x())

    @staticmethod
    def _widget_handles(key: int, widget: QWidget) -> bool:
        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        widget.keyPressEvent(event)
        return event.isAccepted()

    def _focus_first_in(self, row: QWidget, reason: Qt.FocusReason) -> bool:
        items = self._focusable(row)
        if not items:
            return False
        items[0].setFocus(reason)
        return True

    def _focus_near_in(self, row: QWidget, reference: QWidget, reason: Qt.FocusReason) -> bool:
        """Like ``_focus_first_in``, but land on the item horizontally
        closest to ``reference`` on screen, instead of always the first.

        This is the standard 2D directional-navigation rule (tvOS Focus
        Engine, Windows XYFocus, W3C CSS Spatial Navigation, Netflix's TV
        UI): moving Down/Up focuses the nearest candidate in that
        direction rather than a fixed index, so focus lands roughly
        under/above where the user actually was.
        """
        ref_x = reference.mapToGlobal(reference.rect().center()).x()
        return self._focus_near_x(row, ref_x, reason)

    def navigate(self, key: int, widget: QWidget) -> bool:
        from sli_ui_toolkit.ui.managers.nav_graph import focus_reason as _nav_focus_reason
        reason = _nav_focus_reason()
        rows = self._rows()
        row = self._row_of(widget)
        if row is None or row not in rows:
            return False
        idx = rows.index(row)
        if logger.isEnabledFor(logging.DEBUG):
            items = self._focusable(row)
            col = items.index(widget) if widget in items else -1
            logger.debug(
                "[nav-%s] navigate key=%s widget=%s row_idx=%d/%d col_idx=%d/%d",
                self._tag, key, widget_label(widget), idx, len(rows), col, len(items),
            )
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            # Give the focused widget itself first refusal — a spinner-like
            # control (e.g. a scroll-driven value button) may want Up/Down
            # to step its own value rather than jump rows. NavigationManager
            # always consumes Up/Down for a widget a section owns (to avoid
            # infinite re-delivery), so the widget's keyPressEvent otherwise
            # never sees these keys at all; trial-dispatch a synthetic event
            # and respect it if accepted — same technique BaseFlyout's own
            # navigation section uses to reach a flyout's keyPressEvent.
            if self._widget_handles(key, widget):
                return True
        if key == Qt.Key.Key_Down:
            # A widget can have a flyout linked directly below it (see
            # NavigationManager.link_below) -- a persistent, ambient panel
            # that reads as part of the toolbar rather than a modal
            # popover (e.g. a hover-driven settings panel for a button
            # group). Entering it takes priority over jumping to the next
            # toolbar row, same priority as _widget_handles above: without
            # this, Down would skip straight over a panel that's visibly
            # sitting right there beneath the focused button.
            from sli_ui_toolkit.managers import NavigationManager

            extension = NavigationManager.get_instance().extension_below(widget)
            if (
                extension is not None
                and hasattr(extension, "focus_first_child")
                and extension.focus_first_child()
            ):
                return True
            if idx < len(rows) - 1:
                return self._focus_near_in(rows[idx + 1], widget, reason)
            # Last row — yield (e.g. canvas/no further row below).
            return False
        if key == Qt.Key.Key_Up:
            if idx > 0:
                return self._focus_near_in(rows[idx - 1], widget, reason)
            # First row — yield so NavigationManager can hand off upward
            # (title bar / tab strip).
            return False
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            # Scrollable controls (ScrollValueButton, Slider, SpinBox) handle
            # Left/Right themselves to adjust value — don't steal focus.
            # Same trial-dispatch as Up/Down above.
            if self._widget_handles(key, widget):
                return True
            items = self._focusable(row)
            if widget not in items:
                return False
            cur = items.index(widget)
            step = 1 if key == Qt.Key.Key_Right else -1
            target = cur + step
            if 0 <= target < len(items):
                items[target].setFocus(reason)
                return True
            if key == Qt.Key.Key_Left and self._on_exit_left is not None:
                try:
                    if self._on_exit_left(reason):  # 4.0: reason required
                        return True
                except TypeError:
                    if self._on_exit_left():
                        return True
                return True
            # Row edge (no handoff, or none configured/declined): consume
            # anyway (don't fall through to native handling, which does
            # nothing for a plain Button) rather than wrap into an adjacent
            # row — Up/Down already own row transitions.
            return True
        return False

    def focus_first(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        rows = self._rows()
        if not rows:
            return False
        if ref_x is not None:
            return self._focus_near_x(rows[0], ref_x, reason)
        return self._focus_first_in(rows[0], reason)

    def focus_last(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        rows = self._rows()
        if not rows:
            return False
        if ref_x is not None:
            return self._focus_near_x(rows[-1], ref_x, reason)
        return self._focus_first_in(rows[-1], reason)

    def _focus_near_x(self, row: QWidget, ref_x: float, reason: Qt.FocusReason) -> bool:
        items = self._focusable(row)
        if not items:
            return False
        target = min(
            items,
            key=lambda w: abs(w.mapToGlobal(w.rect().center()).x() - ref_x),
        )
        target.setFocus(reason)
        return True

    def focus_nearest(self, pos, *, reason: Qt.FocusReason) -> bool:
        """Land on whichever focusable widget across *all* rows is
        geometrically closest to *pos* (both x and y).

        Distinct from ``focus_first``/``focus_last``: those two always
        pick a *fixed* row (topmost / bottommost) because they model
        "entering this section from above/below" for cross-section
        Up/Down handoff, where ``ref_x`` only ever disambiguates the
        left/right position within that fixed row. A mouse click can land
        on *any* row, not just the first or last, so a click-driven
        re-anchor needs the row nearest the click's y, not a row fixed by
        entry direction.
        """
        rows = self._rows()
        if not rows:
            return False
        row = min(
            rows,
            key=lambda r: abs(r.mapToGlobal(r.rect().center()).y() - pos.y()),
        )
        return self._focus_near_x(row, pos.x(), reason)

    @property
    def extra_keys(self) -> frozenset[int]:
        return frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})


class IconListNavSection:
    """Up/Down between an ``IconListWidget`` sidebar's rows.

    Mirrors ``ToolbarRowsSection``'s row-to-row model for a single-column
    list: Down/Up step one row, yielding (``return False``) past the first
    or last row for ``NavigationManager``'s own vertical section handoff
    (:meth:`NavigationManager._neighbor`).

    Right is opted into via ``extra_keys`` and, if ``on_exit_right`` was
    given, hands off through it — e.g. "focus the currently active content
    page". This section has no notion of what a "content page" is, same
    separation ``ToolbarRowsSection``'s own ``on_exit_left`` keeps: the
    host wires the two sides together with plain callables, not by either
    section knowing about the other's type.
    """

    def __init__(
        self,
        list_widget: "IconListWidget",
        *,
        on_exit_right: Callable[[], bool] | None = None,
    ) -> None:
        self._list = list_widget
        self._on_exit_right = on_exit_right

    def owns(self, widget: QWidget) -> bool:
        return widget is self._list or self._list.isAncestorOf(widget)

    def navigate(self, key: int, widget: QWidget) -> bool:
        idx = self._list.index_of_button(widget)
        logger.debug(
            "[nav-iconlist] navigate key=%s widget=%s idx=%s count=%d",
            key, widget_label(widget), idx, self._list.count(),
        )
        if key == Qt.Key.Key_Down:
            from sli_ui_toolkit.ui.managers.nav_graph import focus_reason as _nav_focus_reason
            _reason = _nav_focus_reason()
            if idx is None:
                return self.focus_first(reason=_reason)
            if idx < self._list.count() - 1:
                return self._focus_visible(idx + 1, _reason)
            return False
        if key == Qt.Key.Key_Up:
            if idx is None:
                return False
            if idx > 0:
                from sli_ui_toolkit.ui.managers.nav_graph import focus_reason as _nav_focus_reason
                _reason = _nav_focus_reason()
                return self._focus_visible(idx - 1, _reason)
            return False
        if key == Qt.Key.Key_Right:
            if self._on_exit_right is not None:
                return bool(self._on_exit_right())
            return False
        return False

    def _focus_visible(self, visible_idx: int, reason: Qt.FocusReason) -> bool:
        btn = self._list.row_button(visible_idx)
        if btn is None:
            return False
        btn.setFocus(reason)
        return True

    def focus_first(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        # Entering the list (from a vertical neighbor above, or via a
        # Left-key handoff from content) always lands on whatever row is
        # already selected -- not literally the first/last row -- since
        # this list stays synced 1:1 with the visible content page.
        btn = self._list.current_row_button()
        if btn is not None:
            btn.setFocus(reason)
            return True
        return self._focus_visible(0, reason)

    def focus_last(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        return self.focus_first(ref_x, reason=reason)

    @property
    def extra_keys(self) -> frozenset[int]:
        return frozenset({Qt.Key.Key_Right})


__all__ = ["IconListNavSection", "ToolbarRowsSection"]
