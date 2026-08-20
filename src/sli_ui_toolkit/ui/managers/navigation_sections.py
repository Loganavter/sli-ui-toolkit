"""Reusable ``NavigationSection`` implementations.

App-specific sections (e.g. a session-picker card grid) stay in the host
app; this module holds sections generic enough to serve any host built on
this toolkit.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QWidget

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
    """

    def __init__(
        self,
        rows_provider: Callable[[], list[QWidget | None]],
        *,
        tag: str = "toolbar-rows",
    ) -> None:
        self._rows_provider = rows_provider
        self._tag = tag

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

    def _focus_first_in(self, row: QWidget) -> bool:
        items = self._focusable(row)
        if not items:
            return False
        items[0].setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def _focus_near_in(self, row: QWidget, reference: QWidget) -> bool:
        """Like ``_focus_first_in``, but land on the item horizontally
        closest to ``reference`` on screen, instead of always the first.

        This is the standard 2D directional-navigation rule (tvOS Focus
        Engine, Windows XYFocus, W3C CSS Spatial Navigation, Netflix's TV
        UI): moving Down/Up focuses the nearest candidate in that
        direction rather than a fixed index, so focus lands roughly
        under/above where the user actually was.
        """
        items = self._focusable(row)
        if not items:
            return False
        ref_x = reference.mapToGlobal(reference.rect().center()).x()
        target = min(
            items,
            key=lambda w: abs(w.mapToGlobal(w.rect().center()).x() - ref_x),
        )
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def navigate(self, key: int, widget: QWidget) -> bool:
        rows = self._rows()
        row = self._row_of(widget)
        if row is None or row not in rows:
            return False
        idx = rows.index(row)
        logger.debug(
            "[nav-%s] navigate key=%s widget=%s row_idx=%d/%d",
            self._tag, key, type(widget).__name__, idx, len(rows),
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
                return self._focus_near_in(rows[idx + 1], widget)
            # Last row — yield (e.g. canvas/no further row below).
            return False
        if key == Qt.Key.Key_Up:
            if idx > 0:
                return self._focus_near_in(rows[idx - 1], widget)
            # First row — yield so NavigationManager can hand off upward
            # (title bar / tab strip).
            return False
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            items = self._focusable(row)
            if widget not in items:
                return False
            cur = items.index(widget)
            step = 1 if key == Qt.Key.Key_Right else -1
            target = cur + step
            if 0 <= target < len(items):
                items[target].setFocus(Qt.FocusReason.OtherFocusReason)
            # Row edge: consume anyway (don't fall through to native
            # handling, which does nothing for a plain Button) rather than
            # wrap into an adjacent row — Up/Down already own row transitions.
            return True
        return False

    def focus_first(self) -> bool:
        rows = self._rows()
        return bool(rows) and self._focus_first_in(rows[0])

    def focus_last(self) -> bool:
        rows = self._rows()
        return bool(rows) and self._focus_first_in(rows[-1])

    @property
    def extra_keys(self) -> frozenset[int]:
        return frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})


__all__ = ["ToolbarRowsSection"]
