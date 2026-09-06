from __future__ import annotations

import os
import time
from collections import deque
from collections.abc import Callable

from PySide6.QtCore import QObject, QPoint, QTimer

from sli_ui_toolkit.config import get_flyout_timings


def _timer_debug_enabled() -> bool:
    for _var in ("SLI_FLYOUT_DEBUG", "IMGSLI_FLYOUT_DEBUG", "FLYOUT_DEBUG"):
        if os.environ.get(_var, "").strip().lower() not in (
            "",
            "0",
            "false",
            "no",
            "off",
        ):
            return True
    return False


class DecisionJournal:
    """Ring-buffer decision log for hover/auto-hide post-mortems.

    Hover close decisions scatter across event handlers and timer
    callbacks; when a panel "hangs open", the causal chain is invisible
    in normal logs. Every show/hide/schedule/cancel/retry lands here with
    a timestamp, so one excerpt (or describe_state() via the UI inspector)
    shows the full chain. Shared by AnchoredFlyoutAutoHide and host
    hover controllers (e.g. Improve-ImgSLI magnifier settings).
    """

    def __init__(self, owner: str, maxlen: int = 60) -> None:
        self._owner = owner
        self._entries: deque = deque(maxlen=maxlen)

    def note(self, event: str, detail: str = "") -> None:
        try:
            self._entries.append((round(time.monotonic(), 3), event, detail))
        except Exception:
            pass
        if _timer_debug_enabled():
            import logging

            logging.getLogger("ImproveImgSLI").warning(
                "[%s] %s %s", self._owner, event, detail
            )

    def snapshot(self) -> list:
        return list(self._entries)

class DelayedActionTimer(QObject):
    def __init__(self, callback: Callable[[], None], parent=None, interval_ms: int = 0):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(callback)
        if interval_ms > 0:
            self._timer.setInterval(interval_ms)

    def start(self, ms: int | None = None):
        if ms is not None:
            self._timer.start(ms)
        else:
            self._timer.start()

    def stop(self):
        self._timer.stop()

    def is_active(self) -> bool:
        return self._timer.isActive()

    def interval(self) -> int:
        return self._timer.interval()

    def set_interval(self, ms: int):
        self._timer.setInterval(ms)

class AnchoredFlyoutAutoHide(QObject):
    def __init__(
        self,
        *,
        flyout,
        anchor_getter: Callable[[], object | None],
        parent=None,
        retry_ms: int | None = None,
    ):
        super().__init__(parent)
        self._flyout = flyout
        self._anchor_getter = anchor_getter
        timings = get_flyout_timings()
        self._retry_ms = (
            timings.transient_auto_hide_delay_ms
            if retry_ms is None
            else int(retry_ms)
        )
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        # Decision journal: ring buffer of (t, event, detail) for post-mortem
        # hover debugging — the retry loop below is silent by default, which
        # makes "panel hangs open" undebuggable from logs alone. Inspect via
        # describe_state() (UI inspector hook) or the flag-gated warnings.
        self._journal = DecisionJournal("auto-hide", maxlen=30)

    def _note(self, event: str, detail: str = "") -> None:
        name = type(self._flyout).__name__ if self._flyout is not None else "?"
        self._journal.note(event, f"{name} {detail}".strip())

    def describe_state(self) -> dict:
        """Snapshot for diagnostics: visibility, pending timer, recent decisions."""
        try:
            visible = bool(self._flyout.isVisible())
        except Exception:
            visible = False
        return {
            "flyout": type(self._flyout).__name__ if self._flyout is not None else None,
            "visible": visible,
            "timer_active": bool(self._timer.isActive()),
            "journal": self._journal.snapshot(),
        }

    def schedule(self, ms: int, reason: str = ""):
        self._note("schedule", f"{ms}ms {reason}".strip())
        if ms <= 0:
            self._timer.stop()
            return
        self._timer.start(ms)

    def cancel(self, reason: str = ""):
        if self._timer.isActive():
            self._note("cancel", reason)
        self._timer.stop()

    def _on_timeout(self):
        if self._flyout is None:
            return
        try:
            if not self._flyout.isVisible():
                return
        except RuntimeError:
            return

        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication

        cursor_pos = QCursor.pos()
        try:
            focus_name = type(QApplication.focusWidget()).__name__
        except Exception:
            focus_name = "?"

        # Keyboard navigation inside flyout — keep open even if cursor not over.
        # Gated on keyboard modality: a mouse-clicked focus (slider, button)
        # lingers on the widget long after the cursor left, and an unconditional
        # focus retry would pin the panel open forever once a backstop timer
        # is armed. Mouse users are governed by hover; only keyboard input
        # retains via focus.
        try:
            from sli_ui_toolkit.ui.managers.navigation_manager import (
                NavigationManager,
            )

            _kbd = bool(NavigationManager.get_instance().last_input_was_keyboard())
        except Exception:
            _kbd = False
        try:
            focused = QApplication.focusWidget()
            if focused is not None and (
                self._flyout.isAncestorOf(focused) or focused is self._flyout
            ):
                if _kbd:
                    self._note(
                        "timeout:retry",
                        f"kbd focus inside ({type(focused).__name__}) cursor={cursor_pos.x()},{cursor_pos.y()}",
                    )
                    self.schedule(self._retry_ms, "focus-inside")
                    return
            anchor = self._anchor_getter()
            if anchor is not None and focused is not None:
                if anchor.isAncestorOf(focused) or focused is anchor:
                    if _kbd:
                        self._note(
                            "timeout:retry",
                            f"kbd focus on anchor ({type(focused).__name__}) cursor={cursor_pos.x()},{cursor_pos.y()}",
                        )
                        self.schedule(self._retry_ms, "focus-anchor")
                        return
            # PanelVisibilityFlyout opened via Enter — keep open while keyboard
            # navigation is active, even if focus is on toolbar outside flyout
            if getattr(self._flyout, "_keyboard_navigation_active", False):
                self._note("timeout:retry", "_keyboard_navigation_active")
                self.schedule(self._retry_ms, "kbd-nav")
                return
        except Exception:
            pass

        try:
            if self._flyout.contains_global(cursor_pos):
                self._note(
                    "timeout:retry",
                    f"cursor inside panel ({cursor_pos.x()},{cursor_pos.y()})",
                )
                self.schedule(self._retry_ms, "cursor-panel")
                return
        except Exception:
            pass

        anchor = self._anchor_getter()
        if anchor is not None:
            try:
                button_global_pos = anchor.mapToGlobal(QPoint(0, 0))
                button_rect = anchor.rect()
                button_global_rect = button_rect.translated(button_global_pos)
                if button_global_rect.contains(cursor_pos):
                    self._note("timeout:retry", "cursor on anchor")
                    self.schedule(self._retry_ms, "cursor-anchor")
                    return
            except Exception:
                pass

        if self._cursor_in_linked_child(cursor_pos):
            self._note("timeout:retry", "cursor in linked child")
            self.schedule(self._retry_ms, "cursor-linked")
            return

        try:
            self._note(
                "timeout:hide",
                f"cursor={cursor_pos.x()},{cursor_pos.y()} focus={focus_name}",
            )
            self._flyout.hide()
        except Exception:
            pass

    def _cursor_in_linked_child(self, cursor_pos) -> bool:
        """True if the cursor is over a ``FlyoutManager.link()``-ed child.

        E.g. an options dropdown opened from a combo box that lives inside
        this (hover-driven) flyout's own content: the dropdown is its own
        top-level-ish overlay widget, spatially outside both this flyout's
        own rect and its anchor's rect, so without this check the cursor
        moving onto it during a pick would read as "left both safe zones"
        and auto-hide the parent flyout out from under the dropdown.
        """
        try:
            from sli_ui_toolkit.managers import FlyoutManager
        except Exception:
            return False
        manager = FlyoutManager.get_instance()
        for child in manager.linked_children(self._flyout):
            try:
                contains_global = getattr(child, "contains_global", None)
                if child.isVisible() and contains_global and contains_global(cursor_pos):
                    return True
            except Exception:
                continue
        return False
