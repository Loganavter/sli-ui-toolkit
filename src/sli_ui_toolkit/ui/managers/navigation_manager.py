"""App-wide keyboard navigation manager.

Catches arrow keys on ``QApplication`` *before* any widget-specific handling
(scroll areas, tab bars, etc.), solving the ``QAbstractScrollArea`` intercept
problem at its root.

Follows the same singleton + register/unregister pattern as
``FlyoutManager``.

Widgets declare a ``NavigationSpec`` (attached as ``navigation_spec`` class
attribute) that tells the manager how to navigate within them.  The manager
is generic — it knows nothing about cards, tabs, or panels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

from PySide6.QtCore import QEvent, Qt, QObject
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

_ARROWS = frozenset({Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Left, Qt.Key.Key_Right})
_EXIT_DOWN = frozenset({Qt.Key.Key_Down})
_EXIT_UP = frozenset({Qt.Key.Key_Up})
_HORIZONTAL = frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})

_KEY_NAMES = {v: k.split(".")[-1] for k, v in Qt.Key.__members__.items()}


def _key_name(key: int) -> str:
    return _KEY_NAMES.get(key, f"0x{key:X}")


# ------------------------------------------------------------------
# Navigation spec — widgets attach this as a class attribute
# ------------------------------------------------------------------


@dataclass(slots=True)
class NavigationSpec:
    """Self-description for keyboard navigation, attached to a widget class
    as ``navigation_spec``.

    Follows the same pattern as ``InspectSpec``: the widget declares how
    it navigates, the manager delegates to it.

    Example::

        class MyWidget(QWidget):
            navigation_spec = NavigationSpec(
                navigate=_my_navigate,
                focus_first=_my_focus_first,
                focus_last=_my_focus_last,
            )
    """

    #: ``(key, widget) -> bool``: handle arrow key while *widget* is focused.
    #: Return True if consumed, False to yield to adjacent section.
    navigate: Callable[[int, QObject], bool] = field(repr=False)
    #: ``() -> bool``: focus the first widget.  Return success.
    focus_first: Callable[[], bool] = field(repr=False)
    #: ``() -> bool``: focus the last widget.  Return success.
    focus_last: Callable[[], bool] = field(repr=False)


# ------------------------------------------------------------------
# Legacy protocol (kept for backward compat)
# ------------------------------------------------------------------


@runtime_checkable
class NavigationSection(Protocol):
    """Protocol for a navigable UI section."""

    def owns(self, widget: QObject) -> bool: ...
    def navigate(self, key: int, widget: QObject) -> bool: ...
    def focus_first(self) -> bool: ...
    def focus_last(self) -> bool: ...


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
        self._sections: list[tuple[QObject, NavigationSection | NavigationSpec]] = []
        self._event_filter_installed = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, owner: QObject, spec: NavigationSection | NavigationSpec) -> None:
        """Register a navigation section/spec for *owner*.

        *owner* is the widget that ``owns()`` checks are relative to
        (for ``NavigationSpec``, ownership is ``owner.isAncestorOf(w) or w is owner``).
        """
        if owner not in [o for o, _ in self._sections]:
            self._sections.append((owner, spec))
            self._install_event_filter()

    def unregister(self, owner: QObject) -> None:
        try:
            self._sections = [(o, s) for o, s in self._sections if o is not owner]
        except ValueError:
            return
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

    def _neighbor(self, owner: QObject, direction: int) -> tuple[QObject, NavigationSection | NavigationSpec] | None:
        idx = self._section_index(owner)
        if idx is None:
            return None
        target = idx + direction
        if 0 <= target < len(self._sections):
            return self._sections[target]
        return None

    def _owns(self, owner: QObject, spec: NavigationSection | NavigationSpec, widget: QObject) -> bool:
        if isinstance(spec, NavigationSpec):
            return owner.isAncestorOf(widget) or widget is owner
        return spec.owns(widget)

    def _navigate(self, spec: NavigationSection | NavigationSpec, key: int, widget: QObject) -> bool:
        return spec.navigate(key, widget)

    def _focus_first(self, spec: NavigationSection | NavigationSpec) -> bool:
        return spec.focus_first()

    def _focus_last(self, spec: NavigationSection | NavigationSpec) -> bool:
        return spec.focus_last()

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
            if not self._owns(owner, spec, focused):
                continue

            if _debug:
                logger.debug(
                    "[nav] key=%s focused=%s(%s) section=%s",
                    _key_name(key),
                    type(focused).__name__,
                    getattr(focused, "objectName", lambda: "")() or "",
                    type(owner).__name__,
                )
            if self._navigate(spec, key, focused):
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
                if neighbor is not None and self._focus_first(neighbor[1]):
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
                if neighbor is not None and self._focus_last(neighbor[1]):
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

        return False
