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
import os
from typing import Protocol, runtime_checkable

import shiboken6
from PySide6.QtCore import QEvent, QPoint, Qt, QObject, QTimer
from PySide6.QtWidgets import QApplication, QWidget

# [nav] trace lines fire on every focus/key event once the host app's
# --debug is on, drowning out other subsystems' debug output. Gated on its
# own opt-in flag, off by default even under --debug -- same convention as
# sidebar_nav_list/debug.py's SLI_UI_NAVLIST_DEBUG.
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

    def focus_first(self, ref_x: float | None = None) -> bool:
        """Move focus to the first widget in this section.  Return success.

        ``ref_x`` is the global x of the widget focus is leaving (when the
        manager has one -- always the case for a keyboard-driven
        cross-section Up/Down handoff), so a section spanning a horizontal
        row can land on whichever of its own widgets is closest to that x
        instead of unconditionally jumping to its leftmost/rightmost
        control regardless of where the user actually was. ``None`` means
        no reference is available (e.g. a caller entering the section
        without prior focus context) -- fall back to a fixed default.
        """
        ...

    def focus_last(self, ref_x: float | None = None) -> bool:
        """Move focus to the last widget in this section.  Return success.

        See ``focus_first`` for ``ref_x``.
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
        # True until the first mouse click; flips on every MouseButtonPress
        # / KeyPress after that. Lets focus-restore code (e.g. BaseFlyout
        # closing after an outside click) pick MouseFocusReason vs
        # OtherFocusReason based on how the user is *currently* driving the
        # app, instead of hardcoding a keyboard reason regardless of cause.
        self._last_input_keyboard: bool = True
        # Where the pointer last went down, and whether that click still
        # needs to be reconciled with the next arrow press. A mouse click
        # always kills the visible ring (see MouseButtonPress handling
        # below) but only *sometimes* moves Qt's actual focusWidget() (only
        # when the click landed on something focusable) -- when it doesn't
        # (empty space, a label, a disabled control), Qt's focus silently
        # stays on whatever was focused before the click. Resuming arrow
        # navigation from that stale widget makes the ring reappear
        # somewhere the user never looked at. Instead, the first arrow key
        # after a click re-anchors the ring on whichever widget is actually
        # nearest the click point, then lets that same key press navigate
        # from there.
        self._last_click_pos: QPoint | None = None
        self._realign_pending: bool = False

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
        if QApplication.focusWidget() is not owner:
            # Something else already grabbed focus since registration
            # (user clicked elsewhere, another section bootstrapped, tab
            # switched away again) -- don't steal it back.
            return
        spec.focus_first()

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
    # Click-to-keyboard handoff
    # ------------------------------------------------------------------

    def _owning_section_for(
        self, widget: QWidget
    ) -> tuple[QObject, NavigationSection, bool] | None:
        """Walk *widget*'s ancestor chain for the first registered section
        that claims it.

        Returns ``(owner, spec, is_bare_owner)``, where ``is_bare_owner`` is
        ``True`` when the match came from hitting the section's bare
        ``owner`` widget rather than a real content match via ``owns()`` --
        e.g. a click on a row container's padding, not any actual row
        content. ``owns()`` matches (any registered section, checked at
        every ancestor level before falling back to identity) take
        priority over a bare-owner match at a shallower level, so a click
        on real content always resolves to that content's own section.
        """
        target = widget
        while target is not None:
            for owner, spec in self._sections:
                if spec.owns(target):
                    return owner, spec, False
            for owner, spec in self._sections:
                if target is owner:
                    return owner, spec, True
            target = target.parentWidget()
        return None

    def _realign_to_last_click(self) -> bool:
        """Move focus to whichever registered section's widget is nearest
        the last mouse-click point, so a stale ``focusWidget()`` (see
        ``_realign_pending`` on the constructor) doesn't drive the next
        arrow press. Returns ``True`` if focus was moved.
        """
        pos = self._last_click_pos
        if pos is None:
            return False
        clicked = QApplication.widgetAt(pos)
        if clicked is None:
            return False
        found = self._owning_section_for(clicked)
        if found is None:
            return False
        owner, spec, is_bare_owner = found
        # The clicked widget itself is the nearest candidate by definition
        # -- prefer it directly over asking the section to guess from an
        # x-coordinate alone, which only ever considers its first/last row.
        # Skip this when the match only came from hitting the bare owner
        # (e.g. row padding, or a click that landed on the section's outer
        # container rather than any real content) -- that widget commonly
        # carries StrongFocus purely to support the arrow-key bootstrap
        # path (see register()'s _bootstrap_if_still_owner), not as a
        # meaningful landing spot; focus_first() is the section's own idea
        # of the right entry point instead.
        if (
            not is_bare_owner
            and clicked.focusPolicy() == Qt.FocusPolicy.StrongFocus
            and clicked.isVisible()
            and clicked.isEnabled()
        ):
            clicked.setFocus(Qt.FocusReason.OtherFocusReason)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "[nav] realign: click -> %s directly",
                    type(clicked).__name__,
                )
            return True
        if spec.focus_first(pos.x()):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "[nav] realign: click -> nearest in %s",
                    type(owner).__name__,
                )
            return True
        return False

    def _yield_to_native(self, focused: QWidget | None, event, realigned: bool) -> bool:
        """Hand *event* to *focused*'s own ``keyPressEvent`` (Left/Right on
        a tab strip, a spin box, etc. — anything this manager itself
        declines to own).

        Ordinarily this just means returning ``False`` and letting Qt's own
        delivery run its course — Qt already resolved the event's receiver
        before this filter ran, and if focus was never touched here that
        resolved receiver is still the right one. But when this same press
        just realigned focus via :meth:`_realign_to_last_click`, that
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
                # Focus moved for a real keyboard-ish reason (arrow
                # navigation, Tab, programmatic OtherFocusReason) -- the
                # click that set _realign_pending, if any, has already been
                # superseded by legitimate focus movement, so the next
                # arrow press should navigate from here, not jump back to
                # the click point.
                self._realign_pending = False
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
            pos_fn = getattr(event, "globalPosition", None)
            if pos_fn is not None:
                self._last_click_pos = pos_fn().toPoint()
                self._realign_pending = True
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
        if key in _ARROWS and self._realign_pending:
            self._realign_pending = False
            realigned = self._realign_to_last_click()
            if _debug and realigned:
                logger.debug("[nav] %s realigned to click", _key_name(key))

        if _debug and key in _ARROWS:
            focused = QApplication.focusWidget()
            logger.debug(
                "[nav] eventFilter key=%s focused=%s sections=%d %s",
                _key_name(key),
                type(focused).__name__ if focused else None,
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
                    type(focused).__name__ if focused else None,
                    len(self._sections),
                )
            if not wants_key:
                return self._yield_to_native(focused, event, realigned)
        else:
            focused = QApplication.focusWidget()
            if focused is None:
                return False

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
                if focused is owner and key in _ARROWS and spec.focus_first():
                    if _debug:
                        new_focus = QApplication.focusWidget()
                        logger.debug(
                            "[nav] %s bootstrap -> %s(%s) via %s",
                            _key_name(key),
                            type(new_focus).__name__,
                            getattr(new_focus, "objectName", lambda: "")() or "",
                            type(owner).__name__,
                        )
                    return True
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
            ref_x = focused.mapToGlobal(focused.rect().center()).x()
            if key in _EXIT_DOWN:
                neighbor = self._neighbor(owner, +1)
                if neighbor is not None and neighbor[1].focus_first(ref_x):
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
                if neighbor is not None and neighbor[1].focus_last(ref_x):
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
        return self._yield_to_native(focused, event, realigned)


