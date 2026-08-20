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
from PySide6.QtCore import QEvent, Qt, QObject, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from .navigation_debug import _key_name, logger, widget_label
from .realign import ClickRealignCoordinator

_ARROWS = frozenset({Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Left, Qt.Key.Key_Right})
_EXIT_DOWN = frozenset({Qt.Key.Key_Down})
_EXIT_UP = frozenset({Qt.Key.Key_Up})
_HORIZONTAL = frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})


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

    def focus_first(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        """Move focus to the first widget in this section.  Return success.

        ``ref_x`` is the global x of the widget focus is leaving (when the
        manager has one -- always the case for a keyboard-driven
        cross-section Up/Down handoff), so a section spanning a horizontal
        row can land on whichever of its own widgets is closest to that x
        instead of unconditionally jumping to its leftmost/rightmost
        control regardless of where the user actually was. ``None`` means
        no reference is available (e.g. a caller entering the section
        without prior focus context) -- fall back to a fixed default.

        ``reason`` is the Qt.FocusReason that must be used for the
        resulting setFocus() — callers must pass
        NavigationManager.current_focus_reason() (or nav_graph.focus_reason())
        so mouse vs keyboard modality is explicit, not hidden.
        """
        ...

    def focus_last(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        """Move focus to the last widget in this section.  Return success.

        See ``focus_first`` for ``ref_x``. ``reason`` is mandatory
        (see ``focus_first``).
        """
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
        self._extensions_below: dict[QWidget, QWidget] = {}
        self._extension_owners: dict[QWidget, QWidget] = {}
        self._event_filter_installed = False
        self._last_keyboard_focus: QWidget | None = None
        # False until first keyboard input; flips on every MouseButtonPress
        # / KeyPress after that. Prevents initial ActiveWindowFocusReason
        # on first window show (CsdMenuTrigger) from flashing the focus ring
        # before the user ever touched the keyboard (log 20:00:45 ActiveWindow).
        self._last_input_keyboard: bool = False
        # Click-to-keyboard realign state (last click position, whether a
        # realign is still pending) -- see ClickRealignCoordinator's own
        # docstring in realign.py for the full rationale.
        self._realign = ClickRealignCoordinator()

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

    def current_focus_reason(self) -> Qt.FocusReason:
        """Central FocusReason policy — mouse → no ring, keyboard → ring.

        All programmatic setFocus() for navigation must go through here
        (or nav_graph.focus_reason()) so modality is explicit.  Breaking
        change in 4.0: focus_first/last now require this reason.
        """
        return Qt.FocusReason.OtherFocusReason if self._last_input_keyboard else Qt.FocusReason.MouseFocusReason

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

    def declare_graph(self, specs: list[tuple[QObject, NavigationSection]]) -> None:
        """Declare the full navigation graph in explicit visual order.

        Breaking 4.0: replaces implicit ordering by ``register()`` call order
        with an explicit graph.  ``specs`` is top→bottom (title_bar →
        tab_strip → picker → toolbar).  Clears previous sections and
        re-registers in given order.  Prefer this over scattered
        ``register()`` for static shell graphs; ``register()`` remains for
        dynamic tab/flyout sections.

        Validates that every section's ``focus_first``/``focus_last``
        accepts ``reason`` (new 4.0 signature) and that graph is topologically
        sorted by ``mapToGlobal(y)`` would fail.
        """
        # Clear existing shell sections (keep flyout sections that are not in new graph? For POC, clear all)
        for owner, _ in list(self._sections):
            self.unregister(owner)
        for owner, spec in specs:
            self.register(owner, spec)

    def register(self, owner: QObject, spec: NavigationSection) -> None:
        """Register a navigation section.

        *owner* is the QObject that owns the widget subtree (used for
        identity and deduplication).  *spec* implements the
        ``NavigationSection`` protocol.

        .. deprecated:: 4.0 — prefer ``declare_graph()`` for static shell
           graphs; ``register()`` remains for dynamic tab/flyout sections.
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
            # A host typically calls setFocus() on the bare owner widget
            # right around registration (e.g. a tab's on_activated()) --
            # but that widget usually has no FocusLayer ring of its own, so
            # until the user presses an arrow key (which the eventFilter's
            # bootstrap-on-owner handles, see navigate()) nothing visibly
            # reads as focused. Land the ring immediately instead of
            # waiting for that first keypress. Deferred one tick: right at
            # registration the section's own content (toolbar buttons,
            # etc.) is often not yet isVisible() (layout/show still
            # pending), so an eager focus_first() here would just find
            # nothing -- by the next event-loop iteration it has.
            QTimer.singleShot(0, lambda o=owner, s=spec: self._bootstrap_if_still_owner(o, s))

    def _bootstrap_if_still_owner(self, owner: QObject, spec: NavigationSection) -> None:
        if not shiboken6.isValid(self) or (owner, spec) not in self._sections:
            return
        current = QApplication.focusWidget()
        if current is not owner:
            # Something else already grabbed focus since registration
            # (user clicked elsewhere, another section bootstrapped, tab
            # switched away again) -- don't steal it back.
            #
            # Also skip when _grab_focus already landed focus on a child
            # of this section (e.g. a flyout's first row).  The bootstrap
            # would re-focus via OtherFocusReason, overriding the
            # MouseFocusReason _grab_focus carefully chose for a
            # mouse-opened flyout and lighting up the focus ring.
            owns = current is not None and spec.owns(current)
            logger.debug(
                "[nav] bootstrap skip: owner=%s current=%s owns=%s",
                type(owner).__name__,
                widget_label(current),
                owns,
            )
            return
        logger.debug(
            "[nav] bootstrap focus_first: owner=%s reason=%s",
            type(owner).__name__,
            self.current_focus_reason().name,
        )
        spec.focus_first(reason=self.current_focus_reason())

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

    def link_below(self, owner: QWidget, flyout: QWidget) -> None:
        """Register *flyout* as the keyboard-navigable continuation
        directly below *owner*.

        Mirrors ``FlyoutManager.link()``'s registry style — a plain
        owner→flyout (and reverse) lookup table, not a callback threaded
        through some section's constructor, so any ``NavigationSection``
        can offer this without knowing which specific flyout (if any) is
        currently attached to a given widget, and any flyout can find its
        way back to the exact widget it's attached to.

        Intended use: a section whose ``navigate()`` would otherwise move
        past *owner* on a boundary key (e.g. ``ToolbarRowsSection`` jumping
        to the next row on ``Key_Down``) should first check
        :meth:`extension_below` and, if set, focus into the flyout instead.
        The flyout's own boundary handling (e.g. Up from its first control)
        can symmetrically check :meth:`extension_owner` to return focus to
        *owner* specifically — generic section adjacency
        (:meth:`_neighbor`) has no notion that a flyout belongs to one
        particular widget rather than to the whole row/section.

        Several widgets can link the *same* flyout (e.g. every button in a
        group, all opening one shared panel below the group) — the reverse
        lookup :meth:`extension_owner` therefore isn't fixed at link time;
        it tracks whichever owner was most recently used to actually enter
        the flyout (stamped by :meth:`extension_below` itself, since that's
        only ever called right before entering), not just any arbitrary one
        of the widgets linked to it.

        The link is a static registration, not tied to *flyout*'s current
        visibility — :meth:`extension_below` filters on that at lookup
        time, so callers don't need to unlink on every hide, only when the
        pairing itself goes away (or never, for a long-lived owner+flyout
        pair — both sides auto-drop on destruction, same as
        :meth:`register`).
        """
        if isinstance(owner, QObject):
            owner.destroyed.connect(lambda _obj=None, o=owner: self.unlink_below(o))
        if isinstance(flyout, QObject):
            flyout.destroyed.connect(lambda _obj=None, o=owner: self.unlink_below(o))
        self._extensions_below[owner] = flyout

    def unlink_below(self, owner: QWidget) -> None:
        flyout = self._extensions_below.pop(owner, None)
        if flyout is not None and self._extension_owners.get(flyout) is owner:
            self._extension_owners.pop(flyout, None)

    def extension_below(self, owner: QWidget) -> QWidget | None:
        """Return the flyout linked below *owner* via :meth:`link_below`,
        if one is registered, valid, and currently visible — else ``None``.

        Also stamps *owner* as this flyout's current :meth:`extension_owner`
        — see the note on multiple owners in :meth:`link_below`.
        """
        flyout = self._extensions_below.get(owner)
        if flyout is None:
            return None
        if not shiboken6.isValid(flyout) or not flyout.isVisible():
            return None
        self._extension_owners[flyout] = owner
        return flyout

    def extension_owner(self, flyout: QWidget) -> QWidget | None:
        """Return the widget *flyout* was linked below via
        :meth:`link_below`, if it's still valid and visible — else
        ``None``.
        """
        owner = self._extension_owners.get(flyout)
        if owner is None:
            return None
        if not shiboken6.isValid(owner) or not owner.isVisible():
            return None
        return owner

    def focus_section_for_owner(self, owner: QObject) -> bool:
        """Focus into the ``NavigationSection`` registered for *owner*
        (its :meth:`NavigationSection.focus_first`), or ``False`` if none
        is registered.

        A live lookup against the current registry — nothing cached, so
        nothing to go stale — for callers that need to re-enter a specific
        section by identity rather than by spatial adjacency
        (:meth:`_neighbor`, which only knows registration order). E.g. a
        sidebar list handing focus to whichever content page is currently
        active, via a callable the host wires in (see
        ``IconListNavSection``'s ``on_exit_right``).
        """
        for candidate_owner, spec in self._sections:
            if candidate_owner is owner:
                return spec.focus_first(reason=self.current_focus_reason())
        return False

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
            _debug = logger.isEnabledFor(logging.DEBUG)
            if _debug and widget is not None:
                logger.debug(
                    "[nav] FocusIn reason=%s widget=%s kb_focus=%s widget_reason=%s",
                    reason.name,
                    widget_label(widget),
                    getattr(widget, "_keyboard_focus", None),
                    getattr(widget, "_last_focus_reason", None),
                )
            if reason in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.MenuBarFocusReason,
            ):
                # Mouse click — clear keyboard focus tracking so flyouts
                # opened from mouse don't show the ring inside.
                # Manager-level ring-preserve: don't clear on programmatic
                # Mouse steals while navigating via keyboard (last_input True)
                # — those steals would otherwise evaporate the ring globally
                # (e.g. ColorSettingsButton -> Capture Ring Mouse, log 19:17:06).
                # Real mouse clicks have already flipped last_input to False via
                # MouseButtonPress, so they still clear.
                if not self._last_input_keyboard:
                    self._last_keyboard_focus = None
                else:
                    # Keep last_keyboard_focus, and ensure the newly focused
                    # Button doesn't evaporate ring (Button.focusInEvent also
                    # has a preserve, this is the manager-side counterpart).
                    if _debug:
                        logger.debug(
                            "[nav] FocusIn Mouse but last_input keyboard — preserve last_keyboard_focus=%s",
                            widget_label(self._last_keyboard_focus),
                        )
            elif widget is not None:
                self._last_keyboard_focus = widget
                # Focus moved for a real keyboard-ish reason (arrow
                # navigation, Tab, programmatic OtherFocusReason) -- the
                # click that set realign_pending, if any, has already been
                # superseded by legitimate focus movement, so the next
                # arrow press should navigate from here, not jump back to
                # the click point.
                self._realign.realign_pending = False
            # Global evaporation guard: if keyboard navigation is active but
            # this FocusIn left no widget with ring, force ring on the new
            # focus (covers any future widget that might still steal with
            # MouseFocusReason despite per-widget grab_focus=False fixes).
            try:
                if self._last_input_keyboard and widget is not None and hasattr(widget, "_keyboard_focus"):
                    if not getattr(widget, "_keyboard_focus", False):
                        has_ring = False
                        for w in QApplication.allWidgets():
                            try:
                                if w is not widget and w.hasFocus() and getattr(w, "_keyboard_focus", False):
                                    has_ring = True
                                    break
                            except Exception:
                                continue
                        if not has_ring:
                            widget._keyboard_focus = True
                            try:
                                widget.update()
                            except Exception:
                                pass
                            if _debug:
                                logger.debug(
                                    "[nav] global ring-preserve forced _keyboard_focus True on %s",
                                    widget_label(widget),
                                )
            except Exception:
                pass
            return False  # never consume FocusIn

        if event.type() == QEvent.Type.MouseButtonPress:
            # A mouse click anywhere must kill the keyboard focus ring even
            # when it doesn't change focus at all (clicking the already-
            # focused widget again, or clicking a non-focusable area) — in
            # both cases no FocusIn/FocusOut fires, so the ring-suppression
            # in Button.focusInEvent never runs on its own.
            self._last_input_keyboard = False
            pos_fn = getattr(event, "globalPosition", None)
            _debug = logger.isEnabledFor(logging.DEBUG)
            if pos_fn is not None:
                self._realign.last_click_pos = pos_fn().toPoint()
                self._realign.realign_pending = True
                if _debug:
                    clicked_at = QApplication.widgetAt(self._realign.last_click_pos)
                    logger.debug(
                        "[nav] MouseButtonPress pos=(%d, %d) widgetAt=%s",
                        self._realign.last_click_pos.x(),
                        self._realign.last_click_pos.y(),
                        widget_label(clicked_at),
                    )
            focused = QApplication.focusWidget()
            if _debug:
                logger.debug(
                    "[nav] MouseButtonPress focused=%s keyboard_focus=%s",
                    widget_label(focused),
                    getattr(focused, "_keyboard_focus", None) if focused else None,
                )
            if focused is not None:
                changed = False
                if getattr(focused, "_keyboard_focus", False):
                    focused._keyboard_focus = False
                    changed = True
                # Always stamp _last_focus_reason on mouse press so flyouts
                # reading it at open time see MouseFocusReason — even when
                # the click re-focused a widget that still carried a stale
                # keyboard reason from a previous Tab/arrow grant (focusIn
                # doesn't re-fire on an already-focused widget).
                old_reason = getattr(focused, "_last_focus_reason", None)
                if hasattr(focused, "_last_focus_reason"):
                    focused._last_focus_reason = Qt.FocusReason.MouseFocusReason
                    changed = True
                if changed:
                    focused.update()
                    if _debug:
                        logger.debug(
                            "[nav] MouseButtonPress cleared ring on %s (was kb=%s reason=%s→Mouse)",
                            widget_label(focused),
                            getattr(focused, "_keyboard_focus", None),
                            old_reason.name if old_reason is not None else "None",
                        )
            self._last_keyboard_focus = None
            return False  # never consume MouseButtonPress

        if event.type() != QEvent.Type.KeyPress:
            return False

        self._last_input_keyboard = True
        key = event.key()
        _debug = logger.isEnabledFor(logging.DEBUG)

        # Whether this press already realigned focus onto the last click
        # point. The two `return False` sites below normally yield a key
        # to Qt's ordinary delivery, which targets whatever widget Qt
        # resolved as the receiver *before* this filter ran -- a
        # setFocus() here can't retarget that same event, only the next
        # one. When realignment did move focus, those sites instead
        # forward this exact event straight to the newly-focused widget's
        # keyPressEvent() (the same trial-dispatch technique
        # ToolbarRowsSection._widget_handles uses) and consume it
        # themselves, rather than trusting Qt to redeliver to the right
        # place.
        realigned = False
        if key in _ARROWS and self._realign.realign_pending:
            self._realign.realign_pending = False
            realigned = self._realign.realign_to_last_click(self)
            if _debug and realigned:
                logger.debug("[nav] %s realigned to click", _key_name(key))

        if _debug and key in _ARROWS:
            focused = QApplication.focusWidget()
            logger.debug(
                "[nav] eventFilter key=%s focused=%s sections=%d %s",
                _key_name(key),
                widget_label(focused),
                len(self._sections),
                [(type(s).__name__, type(o).__name__) for o, s in self._sections],
            )

        if key not in _ARROWS or key in _HORIZONTAL:
            # Not a plain vertical arrow — only intercept if a section that
            # owns the focused widget explicitly requests this key via
            # extra_keys. This covers both non-arrow extra keys (Enter/
            # Escape for flyouts) and Left/Right: by default Left/Right are
            # left alone for native widget handlers (QTabBar, QSpinBox,
            # etc.), but a section can opt in (e.g. ToolbarRowsSection, to
            # move focus within a toolbar row) by listing them in
            # extra_keys — nothing changes for sections that don't.
            focused = QApplication.focusWidget()
            if focused is None:
                return False
            wants_key = any(
                key in getattr(spec, "extra_keys", frozenset())
                for owner, spec in self._sections
                if spec.owns(focused) or focused is owner
            )
            if _debug and not wants_key:
                logger.debug(
                    "[nav] extra_keys: key=%s focused=%s wants_key=False sections=%d",
                    _key_name(key),
                    widget_label(focused),
                    len(self._sections),
                )
            if not wants_key:
                return self._realign.yield_to_native(focused, event, realigned)
        else:
            focused = QApplication.focusWidget()
            if focused is None:
                return False

        if realigned:
            # The ring was invisible before this press (mouse click
            # suppresses it -- see MouseButtonPress handling above), so the
            # user has no idea where realignment just silently placed real
            # Qt focus. Also stepping navigate() in this same press would
            # look like the ring jumped two items from the click instead of
            # one -- there's nothing visible to anchor "one step" against
            # yet. Consume this press as reveal-only; a second press then
            # steps normally from the now-visible ring.
            if _debug:
                logger.debug(
                    "[nav] %s: reveal-only after click realign, ring at %s",
                    _key_name(key), widget_label(focused),
                )
            return True

        for owner, spec in self._sections:
            if not spec.owns(focused):
                # The registered owner widget itself can legitimately hold
                # focus (e.g. right after its page becomes active, before
                # anything inside it has been explicitly focused) without
                # `owns()` claiming it -- a section's `owns()` typically
                # matches its *content* (rows/children), not the bare
                # owner. Bootstrap into the section on any arrow key
                # instead of silently dropping it: this also sidesteps
                # activation-time races where the content wasn't focusable
                # yet (hidden/disabled) when the owner first got focus.
                if focused is owner and key in _ARROWS and spec.focus_first(reason=self.current_focus_reason()):
                    if _debug:
                        new_focus = QApplication.focusWidget()
                        logger.debug(
                            "[nav] %s bootstrap -> %s via %s",
                            _key_name(key),
                            widget_label(new_focus),
                            type(owner).__name__,
                        )
                    return True
                continue

            if _debug:
                logger.debug(
                    "[nav] key=%s focused=%s section=%s",
                    _key_name(key),
                    widget_label(focused),
                    type(owner).__name__,
                )
            if spec.navigate(key, focused):
                if _debug:
                    new_focus = QApplication.focusWidget()
                    if new_focus is not focused:
                        logger.debug(
                            "[nav] -> %s",
                            widget_label(new_focus),
                        )
                    else:
                        logger.debug("[nav] consumed (no movement)")
                return True

            # Section declined — try adjacent section on boundary keys.
            ref_x = focused.mapToGlobal(focused.rect().center()).x()
            if key in _EXIT_DOWN:
                neighbor = self._neighbor(owner, +1)
                if neighbor is not None and neighbor[1].focus_first(ref_x, reason=self.current_focus_reason()):
                    if _debug:
                        new_focus = QApplication.focusWidget()
                        logger.debug(
                            "[nav] -> %s via %s",
                            widget_label(new_focus),
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
                if neighbor is not None and neighbor[1].focus_last(ref_x, reason=self.current_focus_reason()):
                    if _debug:
                        new_focus = QApplication.focusWidget()
                        logger.debug(
                            "[nav] -> %s via %s",
                            widget_label(new_focus),
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
        return self._realign.yield_to_native(focused, event, realigned)


