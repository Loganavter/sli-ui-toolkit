"""Reusable ``NavigationSection`` implementations.

App-specific sections (e.g. a session-picker card grid) stay in the host
app; this module holds sections generic enough to serve any host built on
this toolkit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import shiboken6

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.managers.nav_rows import group_visual_rows
from sli_ui_toolkit.ui.managers.navigation_debug import nav_debug, nav_debug_enabled
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


def value_control_is_editing(widget) -> bool:
    """Duck-typed edit-mode query (``is_editing() -> bool``).

    A value control that implements the value-edit contract reports ``True``
    only while the user has entered its explicit edit mode (Enter). Controls
    without the attribute are never "editing". Never raises: navigation runs
    from an app-wide event filter, so a broken query must not take arrows down.
    """
    is_editing = getattr(widget, "is_editing", None)
    if not callable(is_editing):
        return False
    try:
        return bool(is_editing())
    except Exception:
        return False


def arrow_gate_open(widget) -> bool:
    """True when navigation arrows may be trial-dispatched to *widget*.

    The value-edit contract: a control that implements ``is_editing()`` only
    receives arrows while it reports edit mode — while it reports not-editing
    the section keeps the arrow for ring navigation (Up/Down rows, Left/Right
    inside a row). A control without the attribute keeps today's behaviour
    (gate open), so nothing else breaks.
    """
    if getattr(widget, "is_editing", None) is None:
        return True
    return value_control_is_editing(widget)

# [nav-*] trace lines fire on every arrow-key navigate() call. Gated on the
# opt-in nav flag at call time (off by default even under the host's
# --debug) — host-app ``docs/dev/LOGGING.md`` unique-prefix convention, see
# ``navigation_debug`` (``SLI_NAV_DEBUG``, legacy alias ``UI_NAV_DEBUG``).
def _ensure_visible(widget: QWidget) -> None:
    """Make *widget* visible inside its parent QScrollArea, if any.

    Used for help/settings navigation: when the newly focused button is
    below the viewport (tall hub, filtered sidebar, long settings page),
    the scroll area should follow focus — same as Qt's default
    ensureWidgetVisible on focus, but explicit here so AutoNavigation's
    container-focused bootstrap and programmatic focus_first also scroll.
    """
    try:
        from PySide6.QtWidgets import QScrollArea

        area: QWidget | None = widget.parentWidget()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        if isinstance(area, QScrollArea):
            area.ensureWidgetVisible(widget, 0, 40)
    except Exception:
        pass


class ToolbarRowsSection:
    """Up/Down between toolbar rows, Left/Right between buttons in a row.

    ``NavigationManager`` leaves Left/Right to native widget handling by
    default (tab bars, spin boxes, ...) — this section opts back in via
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
        on_exit_left: Callable[..., bool] | None = None,
        on_exit_right: Callable[..., bool] | None = None,
    ) -> None:
        self._rows_provider = rows_provider
        self._tag = tag
        self._on_exit_left = on_exit_left
        self._on_exit_right = on_exit_right

    def _rows(self) -> list[QWidget]:
        """Visible rows in VISUAL order (top to bottom).

        Rows arrive from ``rows_provider``; for ``NavRowBuilder`` hosts that
        order is already visual, but nothing enforced it, so a host appending
        rows as panels are built could hand them back in a different order and
        Down/Up would step by list index instead of by geometry (the "index
        order instead of visual rows" defect the flyout path had).

        The y-sort is therefore applied ONLY when every row lives in the SAME
        container (a plain toolbar/footer: one parent, geometry is the truth).
        A host whose rows span containers — the video-editor dialog's form
        rows, the export tab's scroll pane, its toolbar and timeline — has an
        explicit order that global y DESTROYS: a scroll pane's rows carry
        global y values that interleave with the sibling containers (measured
        regression 2026-10-19: ``test_export_tab_fields_walk_in_visual_order``
        and ``test_up_walks_rows_in_visual_order`` went red the moment this
        sort was added). Cross-container layouts keep the host's order; the
        sort is stable, so rows sharing a y band keep the host's order too.
        """
        rows = [r for r in self._rows_provider() if r is not None and r.isVisible()]
        if len(rows) < 2:
            return rows

        parents = {r.parentWidget() for r in rows}
        if len(parents) > 1:
            return rows

        def _center_y(widget: QWidget) -> float:
            try:
                return float(widget.mapToGlobal(widget.rect().center()).y())
            except Exception:
                return 0.0

        return sorted(rows, key=_center_y)

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
        # Value-edit gate: a control that implements ``is_editing()`` only gets
        # arrows while editing (see ``arrow_gate_open`` / NAVIGATION.md §1.1) —
        # otherwise a focused Slider would eat the navigation keys.
        if not arrow_gate_open(widget):
            return False
        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        widget.keyPressEvent(event)
        return event.isAccepted()

    @staticmethod
    def _caret_at_boundary(key: int, widget: QWidget) -> bool:
        """True when a text-entry widget's caret sits at *key*'s edge.

        A line edit (stock ``QLineEdit`` or a ``CustomLineEdit``) accepts
        Left/Right to move the caret; at the edge it must yield to navigation so
        the row can be exited. Duck-typed so the toolkit stays generic. Returns
        False for any widget without a caret (so non-text controls keep the
        "widget handled it" behaviour), or when a selection exists (Left/Right
        then collapse the selection — that is caret movement, not an exit).
        """
        try:
            if widget.hasSelectedText():
                return False
        except Exception:
            return False
        try:
            pos = int(widget.cursorPosition())
            end = len(str(widget.text()))
        except Exception:
            return False
        if key == Qt.Key.Key_Left:
            return pos <= 0
        if key == Qt.Key.Key_Right:
            return pos >= end
        return False

    def _focus_first_in(self, row: QWidget, reason: Qt.FocusReason) -> bool:
        items = self._focusable(row)
        if not items:
            return False
        items[0].setFocus(reason)
        _ensure_visible(items[0])
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
        if nav_debug_enabled():
            items = self._focusable(row)
            col = items.index(widget) if widget in items else -1
            nav_debug(
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
            # Флайоут-владелец кнопки на стороне "below" (нижняя панель).
            # Для "above" (PanelVisibility/Color) Down не входит — туда входит Up.
            from sli_ui_toolkit.managers import NavigationManager

            extension = NavigationManager.get_instance().extension_for(widget, "below")
            if extension is not None and hasattr(extension, "focus_first_child"):
                if extension.focus_first_child():
                    return True
            if idx < len(rows) - 1:
                return self._focus_near_in(rows[idx + 1], widget, reason)
            if nav_debug_enabled():
                nav_debug('[nav-%s] at bottom idx=%d/%d key=Down — nowhere to scroll down', self._tag, idx, len(rows))
            # Last row — yield (e.g. canvas/no further row below).
            return False
        if key == Qt.Key.Key_Up:
            # Симметрично Down — вход на сторону "above" (верхние панели
            # PanelVisibility/ColorOptions, а также value-пилюля ScrollValueButton).
            from sli_ui_toolkit.managers import NavigationManager as _NMUp

            _ext_up = _NMUp.get_instance().extension_for(widget, "above")
            if _ext_up is not None and hasattr(_ext_up, "focus_first_child"):
                if _ext_up.focus_first_child():
                    return True
            if idx > 0:
                return self._focus_near_in(rows[idx - 1], widget, reason)
            if nav_debug_enabled():
                nav_debug('[nav-%s] at top idx=%d/%d key=Up — nowhere to scroll up', self._tag, idx, len(rows))
            # First row — yield so NavigationManager can hand off upward
            # (title bar / tab strip).
            return False
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            # Флайоуты сбоку (side="left"/"right") — входят по Left/Right,
            # как "above"→Up и "below"→Down. Библиотека пока только QWidget,
            # поэтому side — метаданная без геометрии.
            from sli_ui_toolkit.managers import NavigationManager as _NMLR

            _side_key = "left" if key == Qt.Key.Key_Left else "right"
            _ext_lr = _NMLR.get_instance().extension_for(widget, _side_key)
            if _ext_lr is not None and hasattr(_ext_lr, "focus_first_child"):
                if _ext_lr.focus_first_child():
                    return True
            # Scrollable controls (ScrollValueButton, Slider, SpinBox) handle
            # Left/Right themselves to adjust value — don't steal focus.
            # Same trial-dispatch as Up/Down above.
            if self._widget_handles(key, widget):
                # Text-entry widgets accept Left/Right for caret movement — but
                # at the caret edge (and with no selection) they must YIELD so
                # the row can be exited; otherwise focus is trapped in the field
                # forever ("[nav] consumed (no movement)", gallery filter edit).
                if not self._caret_at_boundary(key, widget):
                    return True
            items = self._focusable(row)
            if widget not in items:
                return False
            cur = items.index(widget)
            step = 1 if key == Qt.Key.Key_Right else -1
            target = cur + step
            if 0 <= target < len(items):
                items[target].setFocus(reason)
                _ensure_visible(items[target])
                return True
            if key == Qt.Key.Key_Left and self._on_exit_left is not None:
                try:
                    if self._on_exit_left(reason=reason):
                        return True
                except TypeError:
                    try:
                        if self._on_exit_left():
                            return True
                    except TypeError:
                        return True
                return True
            if key == Qt.Key.Key_Right and self._on_exit_right is not None:
                try:
                    if self._on_exit_right(reason=reason):
                        return True
                except TypeError:
                    try:
                        if self._on_exit_right():
                            return True
                    except TypeError:
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
        _ensure_visible(target)
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
        on_exit_right: Callable[..., bool] | None = None,
    ) -> None:
        self._list = list_widget
        self._on_exit_right = on_exit_right

    def owns(self, widget: QWidget) -> bool:
        return widget is self._list or self._list.isAncestorOf(widget)

    def navigate(self, key: int, widget: QWidget) -> bool:
        idx = self._list.index_of_button(widget)
        nav_debug(
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
            if nav_debug_enabled():
                nav_debug('[nav-iconlist] at bottom idx=%s count=%s key=Down — nowhere to scroll down (consumed)', idx, self._list.count())
            return True
        if key == Qt.Key.Key_Up:
            if idx is None:
                return False
            if idx > 0:
                from sli_ui_toolkit.ui.managers.nav_graph import focus_reason as _nav_focus_reason
                _reason = _nav_focus_reason()
                return self._focus_visible(idx - 1, _reason)
            if nav_debug_enabled():
                nav_debug('[nav-iconlist] at top idx=%s count=%s key=Up — nowhere to scroll up', idx, self._list.count())
            return False
        if key == Qt.Key.Key_Right:
            # Поддержка side="right" флайаутов (Up→above, Down→below уже в ToolbarRowsSection)
            # Для IconList: Right входит в привязанный флайаут справа, если есть side="right"
            from sli_ui_toolkit.managers import NavigationManager as _NMR

            _ext_r = _NMR.get_instance().extension_for(widget, "right")
            if _ext_r is not None:
                if hasattr(_ext_r, "focus_first_child") and _ext_r.focus_first_child():
                    return True
            if self._on_exit_right is not None:
                return bool(self._on_exit_right())
            return False
        if key == Qt.Key.Key_Left:
            from sli_ui_toolkit.managers import NavigationManager as _NML

            _ext_l = _NML.get_instance().extension_for(widget, "left")
            if _ext_l is not None:
                if hasattr(_ext_l, "focus_first_child") and _ext_l.focus_first_child():
                    return True
            return False
        return False

    def _focus_visible(self, visible_idx: int, reason: Qt.FocusReason) -> bool:
        btn = self._list.row_button(visible_idx)
        if btn is None:
            return False
        btn.setFocus(reason)
        _ensure_visible(btn)
        return True

    def focus_first(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        # Entering the list (from a vertical neighbor above, or via a
        # Left-key handoff from content) always lands on whatever row is
        # already selected -- not literally the first/last row -- since
        # this list stays synced 1:1 with the visible content page.
        btn = self._list.current_row_button()
        if btn is not None:
            btn.setFocus(reason)
            _ensure_visible(btn)
            return True
        return self._focus_visible(0, reason)

    def focus_last(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        return self.focus_first(ref_x, reason=reason)

    @property
    def extra_keys(self) -> frozenset[int]:
        return frozenset({Qt.Key.Key_Right})


class AutoNavigationSection:
    """Zero-config navigation for any container — no manual rows.

    Находит все StrongFocus листы внутри owner, кластеризует по y в ряды,
    внутри ряда сортирует по x. Up/Down ходят между рядами, Left/Right внутри
    ряда, Up/Down с side="above/below" — во флайаут. Заменяет
    calendar_manager / checkbox_manager и т.д. — один класс вместо 100.

    The row banding is the shared one
    (:func:`sli_ui_toolkit.ui.managers.nav_rows.group_visual_rows`) — the same
    the flyout traversal uses, so "a row is a centre-y band, x inside a row"
    holds on both paths. Focus on *owner* or on a container it lives in (the
    dialog window, a central widget, a page) is a bootstrap: the first arrow
    enters the rows. Claiming that ancestor chain is what makes a dialog whose
    section is registered on an inner container traversable at all — before,
    such a dialog swallowed every arrow key (owner report 2026-10-19: 12×
    Down left focus on the dialog) and ``focus_nearest()`` always returned
    ``False`` because the inherited implementation read row *containers* this
    section never had.

    Использование::

        from sli_ui_toolkit.managers import auto_navigation
        auto_navigation(calendar_widget)  # Up→сверху, Left→слева без 40 строк

    Или декларативно через WidgetDescriptor: owner.widget_descriptor =
    WidgetDescriptor(navigation=AutoNavigationSection(owner))
    """

    def __init__(
        self,
        owner: QWidget,
        *,
        tag: str = "auto",
        on_exit_left: Callable[..., bool] | None = None,
        on_exit_right: Callable[..., bool] | None = None,
    ) -> None:
        self._owner = owner
        self._tag = tag
        self._on_exit_left = on_exit_left
        self._on_exit_right = on_exit_right

    # ------------------------------------------------------------------
    # Row discovery
    # ------------------------------------------------------------------

    def _visual_rows(self) -> list[list[QWidget]]:
        """Rescan the owner's focusable leaves into VISUAL rows (never cached).

        Always a fresh scan: dialogs and help hubs rebuild their content
        between key presses, so a cached row could hold a deleted widget or
        miss new ones. ``group_visual_rows`` drops dead widgets, orders rows by
        y and x-sorts inside a row.
        """
        try:
            candidates = [
                w
                for w in self._owner.findChildren(QWidget)
                if shiboken6.isValid(w)  # type: ignore[attr-defined]
                and w.focusPolicy() == Qt.FocusPolicy.StrongFocus
                and w.isVisible()
                and w.isEnabled()
                and w is not self._owner
            ]
        except Exception:
            return []
        return group_visual_rows(candidates)

    @staticmethod
    def _row_index(rows: list[list[QWidget]], widget: QWidget) -> int | None:
        for idx, row in enumerate(rows):
            if widget in row:
                return idx
        return None

    def owns(self, widget: QWidget) -> bool:
        """The owner, everything inside it, and the containers it lives in.

        The ancestor half is deliberate: focus regularly rests on the dialog
        window (or an intermediate page/central widget) rather than on a
        control, and without claiming it ``NavigationManager`` dropped every
        arrow key for a dialog that registered only an auto section. Siblings
        (a flyout, another page) are not claimed — only widgets *containing*
        the owner.
        """
        try:
            if widget is self._owner or self._owner.isAncestorOf(widget):
                return True
            return widget.isAncestorOf(self._owner)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Section protocol
    # ------------------------------------------------------------------

    def navigate(self, key: int, widget: QWidget) -> bool:
        from sli_ui_toolkit.ui.managers.nav_graph import focus_reason as _nav_focus_reason

        reason = _nav_focus_reason()
        rows = self._visual_rows()
        row_index = self._row_index(rows, widget)
        if row_index is None:
            # Focus is on the owner, on a container the owner lives in, or on a
            # non-row descendant: the first arrow ENTERS the rows instead of
            # being dropped (the "dialog arrow walk does nothing at all").
            return self._bootstrap(key)
        if nav_debug_enabled():
            items = rows[row_index]
            col = items.index(widget) if widget in items else -1
            nav_debug(
                "[nav-%s] navigate key=%s widget=%s row_idx=%d/%d col_idx=%d/%d",
                self._tag, key, widget_label(widget), row_index, len(rows), col, len(items),
            )
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            # Give the focused widget itself first refusal — a spinner-like
            # control may want Up/Down to step its own value. Same
            # trial-dispatch the row section uses.
            if ToolbarRowsSection._widget_handles(key, widget):
                return True
        if key == Qt.Key.Key_Down:
            from sli_ui_toolkit.managers import NavigationManager

            extension = NavigationManager.get_instance().extension_for(widget, "below")
            if extension is not None and hasattr(extension, "focus_first_child"):
                if extension.focus_first_child():
                    return True
            if row_index < len(rows) - 1:
                return self._focus_near_in_row(rows[row_index + 1], widget, reason)
            if nav_debug_enabled():
                nav_debug(
                    "[nav-%s] at bottom row_idx=%s/%s key=Down — nowhere to scroll down (consumed)",
                    self._tag, row_index, len(rows),
                )
            # Bottom row — consume so the manager does not re-deliver.
            return True
        if key == Qt.Key.Key_Up:
            from sli_ui_toolkit.managers import NavigationManager as _NMUp

            ext_up = _NMUp.get_instance().extension_for(widget, "above")
            if ext_up is not None and hasattr(ext_up, "focus_first_child"):
                if ext_up.focus_first_child():
                    return True
            if row_index > 0:
                return self._focus_near_in_row(rows[row_index - 1], widget, reason)
            if self._tag == "help-sidebar":
                # Help search+list column: Up at its top yields so the manager
                # hands off to the bar above it.
                if nav_debug_enabled():
                    nav_debug(
                        "[nav-auto] at top row_idx=%s/%s key=Up — yield to previous section (help-sidebar)",
                        row_index, len(rows),
                    )
                return False
            if nav_debug_enabled():
                nav_debug(
                    "[nav-auto] at top row_idx=%s/%s key=Up — nowhere to scroll up (consumed)",
                    row_index, len(rows),
                )
            return True
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            from sli_ui_toolkit.managers import NavigationManager as _NMLR

            side = "left" if key == Qt.Key.Key_Left else "right"
            ext_lr = _NMLR.get_instance().extension_for(widget, side)
            if ext_lr is not None and hasattr(ext_lr, "focus_first_child"):
                if ext_lr.focus_first_child():
                    return True
            # Value-stepping controls (slider/spinbox/scroll pill) handle
            # Left/Right themselves; a text field does too EXCEPT at the caret
            # edge, where it must yield so the row can be exited.
            if ToolbarRowsSection._widget_handles(key, widget):
                if not ToolbarRowsSection._caret_at_boundary(key, widget):
                    return True
            row = rows[row_index]
            if widget not in row:
                return False
            cur = row.index(widget)
            step = 1 if key == Qt.Key.Key_Right else -1
            nxt = cur + step
            if 0 <= nxt < len(row):
                row[nxt].setFocus(reason)
                _ensure_visible(row[nxt])
                return True
            if key == Qt.Key.Key_Left and self._on_exit_left is not None:
                return self._invoke_exit(self._on_exit_left, reason)
            if key == Qt.Key.Key_Right and self._on_exit_right is not None:
                return self._invoke_exit(self._on_exit_right, reason)
            # Row edge: consume rather than wrap into an adjacent row — Up/Down
            # already own row transitions.
            return True
        return False

    def _bootstrap(self, key: int) -> bool:
        """First arrow while focus is not on a row: enter the rows."""
        from sli_ui_toolkit.ui.managers.nav_graph import focus_reason as _nav_focus_reason

        reason = _nav_focus_reason()
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            return self.focus_first(reason=reason)
        if key == Qt.Key.Key_Up:
            return self.focus_last(reason=reason)
        if key == Qt.Key.Key_Left and self._on_exit_left is not None:
            return self._invoke_exit(self._on_exit_left, reason)
        return False

    def focus_first(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        rows = self._visual_rows()
        if not rows:
            return False
        return self._focus_in_row(rows[0], ref_x, reason)

    def focus_last(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        rows = self._visual_rows()
        if not rows:
            return False
        return self._focus_in_row(rows[-1], ref_x, reason)

    def focus_nearest(self, pos, *, reason: Qt.FocusReason) -> bool:
        """Land on the row nearest *pos*'s y, then the widget nearest its x.

        A click can land on any row (not just the first/last like
        ``focus_first``/``focus_last``), so a click-driven re-anchor needs the
        row nearest the click's y. Returns ``True`` when focus was set.
        """
        rows = self._visual_rows()
        if not rows:
            return False
        row = min(rows, key=lambda r: abs(self._row_center_y(r) - pos.y()))
        return self._focus_in_row(row, pos.x(), reason)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _focus_in_row(self, row: list[QWidget], ref_x: float | None, reason: Qt.FocusReason) -> bool:
        row = [
            w
            for w in row
            if shiboken6.isValid(w)  # type: ignore[attr-defined]
            and w.isVisible()
            and w.isEnabled()
        ]
        if not row:
            return False
        if ref_x is None:
            target = row[0]
        else:
            target = min(row, key=lambda w: abs(self._center_x(w) - ref_x))
        target.setFocus(reason)
        _ensure_visible(target)
        return True

    def _focus_near_in_row(self, row: list[QWidget], reference: QWidget, reason: Qt.FocusReason) -> bool:
        """Land on the row member horizontally closest to *reference*.

        The standard 2D directional-navigation rule (tvOS Focus Engine,
        Windows XYFocus, W3C CSS Spatial Navigation): Down/Up focuses the
        nearest candidate in that direction instead of a fixed index, so focus
        stays roughly under/above where the user was.
        """
        return self._focus_in_row(row, self._center_x(reference), reason)

    @staticmethod
    def _center_x(widget: QWidget) -> float:
        try:
            return float(widget.mapToGlobal(widget.rect().center()).x())
        except Exception:
            return 0.0

    @staticmethod
    def _row_center_y(row: list[QWidget]) -> float:
        if not row:
            return 0.0
        try:
            return float(row[0].mapToGlobal(row[0].rect().center()).y())
        except Exception:
            return 0.0

    @staticmethod
    def _invoke_exit(callback: Callable[..., bool], reason: Qt.FocusReason) -> bool:
        """Call a host exit callback, tolerating either call convention."""
        try:
            return bool(callback(reason=reason))
        except TypeError:
            try:
                return bool(callback())
            except TypeError:
                return True

    @property
    def extra_keys(self) -> frozenset[int]:
        return frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})


__all__ = ["AutoNavigationSection", "IconListNavSection", "ToolbarRowsSection"]