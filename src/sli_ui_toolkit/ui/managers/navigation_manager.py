"""App-wide keyboard navigation manager.

Catches arrow keys on ``QApplication`` *before* any widget-specific handling
(scroll areas, tab bars, etc.), solving the ``QAbstractScrollArea`` intercept
problem at its root.

Follows the same singleton + register/unregister pattern as
``FlyoutManager``.

Widgets declare navigation behavior through ``WidgetDescriptor`` (see
``ui/widget_descriptor.py``).  The manager discovers sections from the
``WidgetRegistry`` or accepts direct registration.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

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
# Section protocol (backward compat + lightweight alternative)
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, owner: QObject, spec: NavigationSection | None = None) -> None:
        """Register a navigation section.

        ``(owner, spec)`` — new style: owner is the widget, spec is the section.
        ``(section,)`` — legacy style: section implements ``NavigationSection``
        protocol and is used as both owner and spec.
        """
        if spec is None:
            # Legacy: single arg — section is its own owner
            spec = owner  # type: ignore[assignment]
        if owner not in [o for o, _ in self._sections]:
            self._sections.append((owner, spec))
            self._install_event_filter()

    def unregister(self, owner: QObject) -> None:
        self._sections = [(o, s) for o, s in self._sections if o is not owner]
        if not self._sections:
            self._uninstall_event_filter()

    def auto_register_from_descriptors(self) -> None:
        """Discover and register widgets with navigation specs.

        Scans all top-level widgets and their children for instances that
        have a ``widget_descriptor`` attribute with a ``navigation`` section.
        """
        app = QApplication.instance()
        if app is None:
            return

        seen: set[int] = set()

        def _scan(widget: QObject) -> None:
            wid = id(widget)
            if wid in seen:
                return
            seen.add(wid)

            desc = getattr(widget, "widget_descriptor", None)
            if desc is not None and getattr(desc, "navigation", None) is not None:
                section = _WidgetNavigationSection(widget, desc.navigation)
                self.register(widget, section)

            for child in widget.children():
                if isinstance(child, QWidget):
                    _scan(child)

        for w in app.topLevelWidgets():
            _scan(w)

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
        if 0 <= target < len(self._sections):
            return self._sections[target]
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
        if event.type() != QEvent.Type.KeyPress:
            return False

        key = event.key()
        if key not in _ARROWS:
            return False

        # Left/Right: never intercept — let native widget handlers
        # (QTabBar, QSpinBox, etc.) process them.
        if key in _HORIZONTAL:
            return False

        focused = QApplication.focusWidget()
        if focused is None:
            return False

        _debug = logger.isEnabledFor(logging.DEBUG)

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

            # Section declined and no neighbor took over — consume
            # Up/Down to prevent infinite re-delivery by Qt.
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                if _debug:
                    logger.debug("[nav] consumed (no neighbor)")
                return True

        # Fallback: no section claimed the focused widget (e.g. focus was
        # redirected to a child by _set_child_focus).  Check if the focused
        # widget is inside any section's owner via parent chain.  Do NOT
        # call navigate() — the section already handled the transition.
        if focused is not None:
            for owner, spec in self._sections:
                w = focused
                while w is not None:
                    if spec.owns(w):
                        if _debug:
                            logger.debug(
                                "[nav] key=%s focused=%s fallback → %s",
                                _key_name(key),
                                type(focused).__name__,
                                type(owner).__name__,
                            )
                        return True
                    w = w.parentWidget()

        return False


# ------------------------------------------------------------------
# Internal: wraps class-level NavigationSection callables with instance
# ------------------------------------------------------------------


class _WidgetNavigationSection:
    """Adapts a ``WidgetDescriptor``'s ``NavigationSection`` to work with
    a specific widget instance."""

    def __init__(self, widget: QWidget, nav_section) -> None:
        self._widget = widget
        self._nav = nav_section

    def owns(self, widget: QObject) -> bool:
        return self._widget.isAncestorOf(widget) or widget is self._widget

    def navigate(self, key: int, widget: QObject) -> bool:
        return self._nav.navigate(key, widget)

    def focus_first(self) -> bool:
        return self._nav.focus_first()

    def focus_last(self) -> bool:
        return self._nav.focus_last()
