"""App-wide keyboard navigation manager.

Catches arrow keys on ``QApplication`` *before* any widget-specific handling
(scroll areas, tab bars, etc.), solving the ``QAbstractScrollArea`` intercept
problem at its root.

Follows the same singleton + register/unregister pattern as
``FlyoutManager``.

Sections are registered explicitly via ``register(owner, spec)`` where
*owner* is the QObject that owns the widget subtree and *spec* is a
``NavigationSection`` implementation.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import shiboken6
from PySide6.QtCore import QEvent, Qt, QObject
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

_ARROWS = frozenset({Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Left, Qt.Key.Key_Right})
_EXIT_DOWN = frozenset({Qt.Key.Key_Down})
_EXIT_UP = frozenset({Qt.Key.Key_Up})
_HORIZONTAL = frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})

_KEY_NAMES = {v: k.split(".")[-1] for k, v in Qt.Key.__members__.items()}


def _key_name(key: int) -> str:
    return _KEY_NAMES.get(key, f"0x{key:X}")


# ------------------------------------------------------------------
# Section protocol
# ------------------------------------------------------------------


@runtime_checkable
class NavigationSection(Protocol):
    """Protocol for a navigable UI section."""

    def owns(self, widget: QObject) -> bool:
        """Return ``True`` if *widget* belongs to this section."""
        ...

    def navigate(self, key: int, widget: QObject) -> bool:
        """Handle *key* press while *widget* is focused.

        Return ``True`` if the event was consumed.
        Return ``False`` if the section wants to yield to an adjacent section.
        """
        ...

    def focus_first(self) -> bool:
        """Move focus to the first widget in this section.  Return success."""
        ...

    def focus_last(self) -> bool:
        """Move focus to the last widget in this section.  Return success."""
        ...

    @property
    def extra_keys(self) -> frozenset[int]:
        """Additional keys this section wants intercepted beyond arrows.

        Flyout sections return ``{Key_Return, Key_Enter, Key_Escape}``
        so the manager routes them through ``navigate()`` — necessary
        because ``WA_ShowWithoutActivating`` blocks normal Qt routing.
        """
        return frozenset()


# ------------------------------------------------------------------
# Manager
# ------------------------------------------------------------------


class NavigationManager(QObject):
    """Process-wide keyboard navigation coordinator.

    Installs an event filter on ``QApplication`` so arrow-key events are
    intercepted *before* ``QAbstractScrollArea`` (and friends) consume them.

    Sections are ordered top-to-bottom (first registered = topmost in the
    visual hierarchy).  When a section's ``navigate()`` returns ``False``
    on a boundary key, the manager delegates to the adjacent section.

    **Contract:** Arrow key consumption on ``QApplication`` is exclusively
    owned by this class.  No other event filter, widget ``keyPressEvent``,
    or ``eventFilter`` override may consume arrow keys — they must let
    events propagate to this manager.
    """

    _instance: NavigationManager | None = None

    @classmethod
    def get_instance(cls) -> NavigationManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        super().__init__()
        self._sections: list[tuple[QObject, NavigationSection]] = []
        self._event_filter_installed = False
        self._last_keyboard_focus: QWidget | None = None
        # True until the first mouse click; flips on every MouseButtonPress
        # / KeyPress after that. Lets focus-restore code (e.g. BaseFlyout
        # closing after an outside click) pick MouseFocusReason vs
        # OtherFocusReason based on how the user is *currently* driving the
        # app, instead of hardcoding a keyboard reason regardless of cause.
        self._last_input_keyboard: bool = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def last_input_was_keyboard(self) -> bool:
        """Return ``True`` if the most recent mouse-click-or-keypress was a
        keypress, ``False`` if it was a mouse click.

        Used to pick the right ``Qt.FocusReason`` when programmatically
        restoring focus (e.g. after a flyout closes) — restoring with
        ``OtherFocusReason`` unconditionally would light up the keyboard
        focus ring even when the close was mouse-driven.
        """
        return self._last_input_keyboard

    def last_keyboard_focus(self) -> QWidget | None:
        """Return the last widget that received focus via keyboard
        (arrow/Tab/OtherFocusReason), or ``None``.

        Used by flyouts to determine whether the trigger was
        keyboard-activated (ring should show inside) vs mouse-activated
        (ring should not).
        """
        w = self._last_keyboard_focus
        if w is not None and not shiboken6.isValid(w):
            self._last_keyboard_focus = None
            return None
        return self._last_keyboard_focus

    def should_intercept(self, key: int, focused: QWidget | None = None) -> bool:
        """Return ``True`` if a registered section wants to intercept *key*.

        Checks whether any section that owns *focused* (or
        ``QApplication.focusWidget()`` when *focused* is ``None``) has
        *key* in its ``extra_keys``.  Use this in app-level event
        handlers to decide whether to yield a key to the navigation
        system instead of consuming it locally.
        """
        if focused is None:
            focused = QApplication.focusWidget()
        if focused is None:
            return False
        return any(
            key in getattr(spec, "extra_keys", frozenset())
            for _owner, spec in self._sections
            if spec.owns(focused)
        )

    def register(self, owner: QObject, spec: NavigationSection) -> None:
        """Register a navigation section.

        *owner* is the QObject that owns the widget subtree (used for
        identity and deduplication).  *spec* implements the
        ``NavigationSection`` protocol.
        """
        if owner not in [o for o, _ in self._sections]:
            self._sections.append((owner, spec))
            self._install_event_filter()
            # Callers are not always able to guarantee a matching
            # unregister() before the owner's C++ side is destroyed (e.g. a
            # widget torn down by a parent's deleteLater(), or test code
            # that never runs a tab's on_deactivated()/dispose()). Without
            # this, a stale entry sits in _sections pointing at a deleted
            # QObject; any later navigation touching it — owns(), the
            # visibility check in _neighbor() — deref's a dead C++ object,
            # which doesn't raise a catchable Python exception, it can
            # corrupt the interpreter. Auto-unregister on destruction closes
            # that gap regardless of what the caller does.
            if isinstance(owner, QWidget):
                owner.destroyed.connect(lambda _obj=None, o=owner: self.unregister(o))
            logger.debug(
                "[nav] registered section %s (owner=%s) total=%d",
                type(spec).__name__, type(owner).__name__, len(self._sections),
            )

    def unregister(self, owner: QObject) -> None:
        # A late destroyed-signal callback (see register()) can fire during
        # interpreter shutdown, after this singleton's own C++ side is
        # already gone — touching self._sections or app.removeEventFilter
        # at that point raises, harmlessly but noisily. Bail out quietly.
        if not shiboken6.isValid(self):
            return
        prev_count = len(self._sections)
        self._sections = [(o, s) for o, s in self._sections if o is not owner]
        if len(self._sections) != prev_count:
            logger.debug(
                "[nav] unregistered section %s total=%d",
                type(owner).__name__, len(self._sections),
            )
        if not self._sections:
            self._uninstall_event_filter()

    # ------------------------------------------------------------------
    # Cross-section navigation helpers
    # ------------------------------------------------------------------

    def _section_index(self, owner: QObject) -> int | None:
        for i, (o, _) in enumerate(self._sections):
            if o is owner:
                return i
        return None

    def _neighbor(self, owner: QObject, direction: int) -> tuple[QObject, NavigationSection] | None:
        idx = self._section_index(owner)
        if idx is None:
            return None
        target = idx + direction
        while 0 <= target < len(self._sections):
            candidate_owner, candidate_section = self._sections[target]
            # A section whose owner isn't currently visible belongs to a
            # background tab/page (e.g. a long-lived section registered
            # once at startup, like the session picker, that stays
            # registered while another workspace tab is active). Handing
            # focus to it would move Qt's focus widget onto something
            # off-screen — hasFocus() still reports True, but nothing ever
            # paints, so the focus ring silently vanishes app-wide. Skip
            # past it to the next section in the same direction instead.
            #
            # shiboken6.isValid() guards a widget whose C++ side was
            # deleted without a matching unregister() (e.g. a test that
            # resets NavigationManager._instance without tearing down
            # every registered section first) — isVisible() on such a
            # widget doesn't raise a catchable Python exception, it can
            # corrupt the interpreter, so it must never be called at all
            # once the object is known-invalid.
            if isinstance(candidate_owner, QWidget) and not shiboken6.isValid(candidate_owner):
                target += direction
                continue
            if not isinstance(candidate_owner, QWidget) or candidate_owner.isVisible():
                return self._sections[target]
            target += direction
        return None

    # ------------------------------------------------------------------
    # Event filter
    # ------------------------------------------------------------------

    def _install_event_filter(self) -> None:
        if self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._event_filter_installed = True

    def _uninstall_event_filter(self) -> None:
        if not self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._event_filter_installed = False

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.FocusIn:
            # Track the last widget that received focus via keyboard
            # (OtherFocusReason / TabFocusReason / ActiveWindowFocusReason)
            # so flyouts can query it at open time.
            reason = event.reason()
            widget = obj if isinstance(obj, QWidget) else None
            if reason in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.MenuBarFocusReason,
            ):
                # Mouse click — clear keyboard focus tracking so flyouts
                # opened from mouse don't show the ring inside.
                self._last_keyboard_focus = None
            elif widget is not None:
                self._last_keyboard_focus = widget
                _debug = logger.isEnabledFor(logging.DEBUG)
                if _debug:
                    logger.debug(
                        "[nav] FocusIn keyboard reason=%s widget=%s",
                        reason.name,
                        type(widget).__name__,
                    )
            return False  # never consume FocusIn

        if event.type() == QEvent.Type.MouseButtonPress:
            # A mouse click anywhere must kill the keyboard focus ring even
            # when it doesn't change focus at all (clicking the already-
            # focused widget again, or clicking a non-focusable area) — in
            # both cases no FocusIn/FocusOut fires, so the ring-suppression
            # in Button.focusInEvent never runs on its own.
            self._last_input_keyboard = False
            focused = QApplication.focusWidget()
            _debug = logger.isEnabledFor(logging.DEBUG)
            if _debug:
                logger.debug(
                    "[nav] MouseButtonPress focused=%s keyboard_focus=%s",
                    type(focused).__name__ if focused else None,
                    getattr(focused, "_keyboard_focus", None) if focused else None,
                )
            if focused is not None and getattr(focused, "_keyboard_focus", False):
                focused._keyboard_focus = False
                if hasattr(focused, "_last_focus_reason"):
                    focused._last_focus_reason = Qt.FocusReason.MouseFocusReason
                focused.update()
                if _debug:
                    logger.debug(
                        "[nav] MouseButtonPress cleared ring on %s",
                        type(focused).__name__,
                    )
            self._last_keyboard_focus = None
            return False  # never consume MouseButtonPress

        if event.type() != QEvent.Type.KeyPress:
            return False

        self._last_input_keyboard = True
        key = event.key()
        _debug = logger.isEnabledFor(logging.DEBUG)

        if _debug and key in _ARROWS:
            focused = QApplication.focusWidget()
            logger.debug(
                "[nav] eventFilter key=%s focused=%s sections=%d %s",
                _key_name(key),
                type(focused).__name__ if focused else None,
                len(self._sections),
                [(type(s).__name__, type(o).__name__) for o, s in self._sections],
            )

        if key not in _ARROWS:
            # Not an arrow — only intercept if a section that owns the
            # focused widget explicitly requests this key via extra_keys.
            focused = QApplication.focusWidget()
            if focused is None:
                return False
            wants_key = any(
                key in getattr(spec, "extra_keys", frozenset())
                for owner, spec in self._sections
                if spec.owns(focused)
            )
            if _debug and not wants_key:
                logger.debug(
                    "[nav] extra_keys: key=%s focused=%s wants_key=False sections=%d",
                    _key_name(key),
                    type(focused).__name__ if focused else None,
                    len(self._sections),
                )
            if not wants_key:
                return False
        else:
            # Left/Right: never intercept — let native widget handlers
            # (QTabBar, QSpinBox, etc.) process them.
            if key in _HORIZONTAL:
                return False
            focused = QApplication.focusWidget()
            if focused is None:
                return False

        for owner, spec in self._sections:
            if not spec.owns(focused):
                continue

            if _debug:
                logger.debug(
                    "[nav] key=%s focused=%s(%s) section=%s",
                    _key_name(key),
                    type(focused).__name__,
                    getattr(focused, "objectName", lambda: "")() or "",
                    type(owner).__name__,
                )
            if spec.navigate(key, focused):
                if _debug:
                    new_focus = QApplication.focusWidget()
                    if new_focus is not focused:
                        logger.debug(
                            "[nav] -> %s(%s)",
                            type(new_focus).__name__,
                            getattr(new_focus, "objectName", lambda: "")() or "",
                        )
                    else:
                        logger.debug("[nav] consumed (no movement)")
                return True

            # Section declined — try adjacent section on boundary keys.
            if key in _EXIT_DOWN:
                neighbor = self._neighbor(owner, +1)
                if neighbor is not None and neighbor[1].focus_first():
                    if _debug:
                        new_focus = QApplication.focusWidget()
                        logger.debug(
                            "[nav] -> %s(%s) via %s",
                            type(new_focus).__name__,
                            getattr(new_focus, "objectName", lambda: "")() or "",
                            type(neighbor[0]).__name__,
                        )
                    return True
                if _debug:
                    idx = self._section_index(owner)
                    logger.debug(
                        "[nav] no neighbor DOWN for %s idx=%s sections=%s",
                        type(owner).__name__, idx,
                        [(type(o).__name__, id(o)) for o, _ in self._sections],
                    )
            elif key in _EXIT_UP:
                neighbor = self._neighbor(owner, -1)
                if neighbor is not None and neighbor[1].focus_last():
                    if _debug:
                        new_focus = QApplication.focusWidget()
                        logger.debug(
                            "[nav] -> %s(%s) via %s",
                            type(new_focus).__name__,
                            getattr(new_focus, "objectName", lambda: "")() or "",
                            type(neighbor[0]).__name__,
                        )
                    return True
                if _debug:
                    idx = self._section_index(owner)
                    logger.debug(
                        "[nav] no neighbor UP for %s idx=%s sections=%s",
                        type(owner).__name__, idx,
                        [(type(o).__name__, id(o)) for o, _ in self._sections],
                    )

            # Section declined and no neighbor took over — consume
            # Up/Down to prevent infinite re-delivery by Qt.
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                if _debug:
                    logger.debug("[nav] consumed (no neighbor)")
                return True

        # No section claimed the focused widget.  Do NOT fall back to
        # walking the parent chain — that would incorrectly claim overlay
        # widgets (flyouts, popups) that are parented inside a section's
        # widget tree but should handle their own keyboard navigation.
        return False


