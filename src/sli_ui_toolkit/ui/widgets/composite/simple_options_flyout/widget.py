from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

import logging
import time
from collections.abc import Sequence

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.config import get_flyout_timings
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.managers.ui_font import UiFont, rebase_font, ui_font
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.composite.base_flyout import (
    BaseFlyout,
    resolve_flyout_animation,
    slide_start_delta,
)

from . import animation as _animation
from . import geometry as _geometry
from .row import _SimpleRow, _design_font

logger = logging.getLogger(__name__)


class SimpleOptionsFlyout(BaseFlyout):
    item_chosen = Signal(int)
    closed = Signal()

    # Identity for host ``GroupShowPolicy`` (interp / combo pickers, etc.).
    flyout_group = "options"

    MARGIN = 8
    APPEAR_EXTRA_Y = 6
    MAX_VISIBLE_ITEMS = 12
    WINDOW_MARGIN = 8

    def __init__(self, parent_widget=None, *, animation: str | None = None):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        # Per-instance show-animation override for show_aligned/show_below.
        # None resolves to the process-wide default_flyout_animation ("none"
        # unless a host configures it) — see resolve_flyout_animation.
        self._default_animation = animation
        self._options: list[str] = []
        self._rows: list[QWidget] = []
        self._current_index: int = -1
        self._item_height = 36
        self._item_font = ui_font()
        # Design-space row font. Rows re-resolve it on every live UiScale
        # change (and on each populate), so the flyout's text size follows
        # interface-scale changes instead of freezing at first-open size.
        self._item_font_design = _design_font(self._item_font)
        self._max_visible_items = self.MAX_VISIBLE_ITEMS
        UiScale.get_instance().scale_changed.connect(self._on_ui_scale_changed)
        timings = get_flyout_timings()
        self._move_duration_ms = timings.flyout_animation_duration_ms
        self._move_easing = QEasingCurve.Type.OutQuad
        self._drop_offset_px = timings.dropdown_drop_offset_px
        self._anim: (
            QParallelAnimationGroup | QPropertyAnimation | QVariantAnimation | None
        ) = None
        self._anchor_widget: QWidget | None = None

        self._main_layout.setContentsMargins(
            self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN
        )

        self.content_layout.setSpacing(0)
        self.content_layout.setContentsMargins(2, 2, 2, 2)

        self._scroll_area = QScrollArea(self.container)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBar(MinimalistScrollBar())
        self._scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self._scroll_area.viewport().setAutoFillBackground(False)
        self._scroll_area.viewport().setStyleSheet("background: transparent;")

        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._rows_layout.addStretch()
        self._scroll_area.setWidget(self._rows_container)
        self.content_layout.addWidget(self._scroll_area)

        self.hide()

    def set_max_visible_items(self, n: int) -> None:
        self._max_visible_items = max(1, int(n))

    def set_list_padding(
        self, padding: int | tuple[int, int, int, int]
    ) -> None:
        """Set the inset between the panel border and the row list.

        Rows are often rounded ``Button`` capsules: with a tight inset the
        first/last row's edge sits on the panel border and gets clipped by
        the rounded corners. Call before ``set_rows``/``populate``/``show_*``;
        an ``int`` applies to all sides, a 4-tuple gives
        ``(left, top, right, bottom)``.
        """
        if isinstance(padding, int):
            self.content_layout.setContentsMargins(
                padding, padding, padding, padding
            )
        else:
            left, top, right, bottom = padding
            self.content_layout.setContentsMargins(left, top, right, bottom)
        self._update_size()

    def set_row_height(self, h: int):
        self._item_height = max(28, int(h))

    def set_row_font(self, f: QFont):
        # Design-space input (see docstring): keep it so rows can re-resolve
        # on live UiScale changes; _item_font stays the scale-resolved
        # variant used for metrics.
        design = QFont(f)
        family = UiFont.get_instance().family()
        if family:
            design.setFamily(family)
        self._item_font_design = design
        self._item_font = rebase_font(design)

    def row_widget(self, index: int) -> QWidget | None:
        """Return the live row widget at ``index``, or ``None``."""
        if not (0 <= index < len(self._rows)):
            return None
        return self._rows[index]

    def rows(self) -> tuple[QWidget, ...]:
        """All installed row widgets, in list order."""
        return tuple(self._rows)

    def set_rows(self, rows: Sequence[QWidget]) -> None:
        """Replace the list content with arbitrary row widgets.

        The composite owns the flyout display, long-list scrolling and
        sizing; the host owns the row widgets and their look (any
        ``QWidget``). A row that exposes a ``clicked`` signal is wired to
        :attr:`item_chosen` with the row's index.
        """
        self._options = []
        self._current_index = -1
        self._set_rows_raw(rows, connect_click=True)

    def _set_rows_raw(self, rows: Sequence[QWidget], *, connect_click: bool) -> None:
        self._rows_container.setUpdatesEnabled(False)
        try:
            self._clear_rows()
            self._rows = list(rows)
            for index, row in enumerate(self._rows):
                if connect_click:
                    clicked = getattr(row, "clicked", None)
                    if clicked is not None:
                        try:
                            clicked.connect(
                                lambda *_, _i=index: self.item_chosen.emit(_i)
                            )
                        except TypeError:
                            pass
                self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
            self._update_size()
        finally:
            self._rows_container.setUpdatesEnabled(True)

    def _clear_rows(self) -> None:
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(0)
            if w := item.widget():
                w.hide()
                w.setParent(None)
                w.deleteLater()
            del item
        self._rows = []

    def populate(self, labels: list[str], current_index: int = -1):
        """Convenience: fill from plain labels with the default simple rows."""
        self._options = list(labels)
        self._current_index = (
            current_index if 0 <= current_index < len(self._options) else -1
        )
        rows = []
        for i, text in enumerate(self._options):
            row = _SimpleRow(
                i,
                text,
                i == self._current_index,
                self._item_height,
                self._item_font_design,
            )
            row.rowClicked.connect(self._on_row_clicked)
            rows.append(row)
        self._set_rows_raw(rows, connect_click=False)

    def _on_ui_scale_changed(self, _factor: float) -> None:
        self._item_font = rebase_font(self._item_font_design)
        # Row gaps are design px; re-apply so they grow with the rows (the
        # flyout is cached across opens, so build-time values would freeze).
        self._rows_layout.setSpacing(scaled_px(2))
        # Rows re-resolve their own label fonts in their own scale_changed
        # handlers; defer so this re-fit runs after them and sees fresh
        # sizeHints (connection order alone would run us first).
        QTimer.singleShot(0, self._deferred_update_size)

    def _deferred_update_size(self) -> None:
        # A singleShot callback is not cancelled by widget destruction; bail
        # quietly when the flyout was deleted between schedule and firing.
        try:
            import shiboken6  # type: ignore[attr-defined]

            if not shiboken6.Shiboken.isValid(self):
                return
        except Exception:
            pass
        self._update_size()

    def _update_size(
        self,
        match_width: int = 0,
        exact_match: bool = False,
        available_height: int | None = None,
    ):
        _geometry.update_size(
            self,
            match_width=match_width,
            exact_match=exact_match,
            available_height=available_height,
        )

    def show_aligned(self, *args, **kwargs):
        # Re-fit after populate so BaseFlyout.adjustSize cannot keep a stale
        # oversized hint from an earlier open.
        self._update_size()
        # Per-instance override wins unless the call passed an explicit value.
        if kwargs.get("animation") is None and self._default_animation is not None:
            kwargs["animation"] = self._default_animation
        return super().show_aligned(*args, **kwargs)

    def show_below(self, anchor_widget: QWidget, exact_width_match: bool = True):
        if self.isVisible() and self._anchor_widget is anchor_widget:
            self._just_opened = False
            self.hide()
            return

        self._anchor_widget = anchor_widget
        # Mirrors BaseFlyout.show_aligned's keyboard-vs-mouse trigger check
        # (see there for the full rationale) -- _grab_focus reads this flag
        # to pick OtherFocusReason (draws the ring) vs MouseFocusReason
        # (suppresses it). Without it, the flag stays at its getattr default
        # of False even when Enter/Space opened this dropdown, so the first
        # row grabs focus silently and no ring appears until an arrow key
        # explicitly moves focus (which does set OtherFocusReason itself).
        raw_reason = getattr(anchor_widget, "_last_focus_reason", None)
        if raw_reason is not None:
            self._anchor_keyboard_focus = raw_reason not in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.MenuBarFocusReason,
            )
        else:
            self._anchor_keyboard_focus = getattr(anchor_widget, "_keyboard_focus", False)
        self._ensure_overlay_parent(anchor_widget)
        self.flyout_manager.request_show(self)

        if self._anim:
            self._anim.stop()
            self._anim = None

        anchor_width = anchor_widget.frameGeometry().width()
        if anchor_width <= 0:
            anchor_width = anchor_widget.geometry().width()
        if anchor_width <= 0:
            anchor_width = anchor_widget.width()

        self._just_opened = True
        self._open_timestamp = time.monotonic()

        offset = self.APPEAR_EXTRA_Y - self.MARGIN
        gap = self.WINDOW_MARGIN

        if self.overlay_layer is not None and not self.isWindow():
            parent_widget = self.parentWidget()
            avail = parent_widget.rect() if parent_widget is not None else None
            anchor_rect = (
                self.overlay_layer.anchor_rect(anchor_widget)
                if hasattr(self.overlay_layer, "anchor_rect")
                else None
            )
            if avail is not None and anchor_rect is not None:
                # size-based edges (not QRect.bottom()/top() inclusive pixels)
                anchor_top_edge = anchor_rect.y()
                anchor_bottom_edge = anchor_rect.y() + anchor_rect.height()
                space_below = avail.bottom() - anchor_bottom_edge - offset - gap
                space_above = anchor_top_edge - avail.top() - offset - gap
                budget = max(space_below, space_above)
                self._update_size(
                    match_width=anchor_width,
                    exact_match=exact_width_match,
                    available_height=budget,
                )
            else:
                self._update_size(match_width=anchor_width, exact_match=exact_width_match)

            position = "bottom"
            if avail is not None and anchor_rect is not None:
                anchor_top_edge = anchor_rect.y()
                anchor_bottom_edge = anchor_rect.y() + anchor_rect.height()
                if (anchor_bottom_edge + offset + self.height()) > avail.bottom() - gap \
                        and (anchor_top_edge - offset - self.height()) >= avail.top() + gap:
                    position = "top"
            rect = self._overlay_rect_relative_to_anchor(
                anchor_widget,
                self.size(),
                position=position,
                offset=offset,
            )
            final_x = rect.x()
            total_width, total_height = self.width(), self.height()
            # Recompute Y with size-based edges — place_surface_rect still uses
            # inclusive QRect.bottom()/top() and lands 1px into the anchor.
            if anchor_rect is not None:
                if position == "bottom":
                    final_y = anchor_rect.y() + anchor_rect.height() + offset
                else:
                    final_y = anchor_rect.y() - offset - total_height
            else:
                final_y = rect.y()
        else:
            parent_widget = self.parentWidget()
            use_parent_coords = parent_widget is not None and not self.isWindow()

            def _map(point: QPoint) -> QPoint:
                if use_parent_coords:
                    assert parent_widget is not None
                    return anchor_widget.mapTo(parent_widget, point)
                return anchor_widget.mapToGlobal(point)

            # Prefer size-based edges. QRect.bottomLeft() is the inclusive
            # last pixel (height-1) and short-changes clearance by 1px.
            anchor_top_left = _map(QPoint(0, 0))
            anchor_size = anchor_widget.size()
            anchor_bottom_y = anchor_top_left.y() + max(1, anchor_size.height())
            anchor_top_y = anchor_top_left.y()
            anchor_center_x = _map(anchor_widget.rect().center()).x()

            if use_parent_coords:
                assert parent_widget is not None
                avail = parent_widget.rect()
            else:
                try:
                    screen = anchor_widget.screen() or QGuiApplication.screenAt(
                        QPoint(anchor_top_left.x(), anchor_bottom_y)
                    )
                    if screen is None:
                        raise RuntimeError("no screen")
                    avail = screen.availableGeometry()
                except Exception:
                    primary_screen = QGuiApplication.primaryScreen()
                    assert primary_screen is not None
                    avail = primary_screen.availableGeometry()

            space_below = avail.bottom() - anchor_bottom_y - offset - gap
            space_above = anchor_top_y - avail.top() - offset - gap
            budget = max(space_below, space_above)
            self._update_size(
                match_width=anchor_width,
                exact_match=exact_width_match,
                available_height=budget,
            )
            total_width, total_height = self.width(), self.height()

            if space_below >= total_height or space_below >= space_above:
                final_y = anchor_bottom_y + offset
            else:
                final_y = anchor_top_y - offset - total_height
            final_x = int(anchor_center_x - total_width / 2) + 2

            final_x = max(avail.left(), min(final_x, avail.right() - total_width))
            final_y = max(avail.top(), min(final_y, avail.bottom() - total_height))
            anchor_rect = QRect(anchor_top_left, anchor_size)

        # Resolve the show animation the same way BaseFlyout.show_aligned
        # does: per-instance override, else the process-wide default
        # (default_flyout_animation), else "none".
        mode = resolve_flyout_animation(self._default_animation)
        self._fade.fade_out_enabled = "fade" in mode
        want_slide = "slide" in mode
        want_fade = "fade" in mode

        end_pos = QPoint(final_x, final_y)
        final_rect = QRect(end_pos, QSize(total_width, total_height))
        if not want_slide:
            start_pos = end_pos
        elif anchor_rect is None:
            # Overlay path without geometry — fall back to unclamped drop.
            start_pos = QPoint(final_x, final_y - self._drop_offset_px)
        else:
            dx, dy = slide_start_delta(
                final_rect,
                anchor_rect,
                distance=self._drop_offset_px,
                animation_axis="vertical",
                shadow_radius=self.SHADOW_RADIUS,
                ux=0.0,
                uy=1.0,
                length=1.0,
            )
            start_pos = QPoint(final_x + dx, final_y + dy)

        self.move(start_pos)

        if want_fade:
            # Snapshot the fully-opaque content before the first paint; fade
            # is composited by BaseFlyout.paintEvent (this subclass inherits
            # it), so a pure "fade" show never moves the flyout.
            self._fade.capture(self)
            self._fade.set_opacity(self, 0.0)

        # Prefer QWidget.show so BaseFlyout registration / active state stay in
        # sync (request_show already ran above; BaseFlyout.show would re-enter
        # it). But BaseFlyout.show() is also where nav-section registration
        # and keyboard-focus grabbing happen -- skipping it entirely left a
        # show_below()'d flyout (e.g. the interpolation dropdown) visible but
        # invisible to keyboard nav: Tab/arrows never delivered a single key
        # to it and it never took focus, so the user could open it but never
        # reach its rows without a mouse. Redo just those two steps here.
        from PySide6.QtWidgets import QWidget as _QWidget

        self._previous_focus_widget = QApplication.focusWidget()
        _QWidget.show(self)
        self.raise_()

        if not self.isVisible():
            logger.warning(
                "SimpleOptionsFlyout: Widget failed to become visible after show()"
            )
            self.show()

        if not getattr(self, "_skip_nav_register", False):
            self._register_nav_section()
        if not getattr(self, "_skip_focus_grab", False):
            self._grab_focus()
            w = self.window()
            if w is not None and not w.isActiveWindow():
                w.activateWindow()

        if exact_width_match:
            actual_width_after = self.width()
            if actual_width_after != total_width:
                logger.warning(
                    f"SimpleOptionsFlyout.show_below: Width changed after show! "
                    f"Before={total_width}, After={actual_width_after}, anchor_width={anchor_width}"
                )
                self.setFixedSize(total_width, total_height)

        _animation.start_show_animation(self, want_slide, want_fade, start_pos, end_pos)

    def _on_animation_finished(self):
        _animation.on_animation_finished(self)

    def _on_row_clicked(self, idx: int):
        self.item_chosen.emit(idx)
        if hasattr(self, "_just_opened"):
            self._just_opened = False
        self.hide()

    def hide(self):
        super().hide()
        if self.parent_widget:
            win = self.parent_widget.window()
            # Restore keyboard focus to the host window only when nothing
            # else in the app took it (e.g. a dialog opened from a row click).
            # On Wayland an activateWindow() whose token surface does not
            # match the pointer's focus surface is denied by the compositor,
            # which marks the host window as demanding attention and surfaces
            # a "«App» is ready" notification — exactly what happens when a
            # dialog is active but the cursor still hovers the host window.
            active = QApplication.activeWindow()
            if win and (active is None or active is win):
                win.activateWindow()
                win.setFocus()

    def hideEvent(self, e):
        # Never swallow hideEvent: ignoring it after hide() already ran leaves
        # host flags (e.g. _interp_popup_open) desynced because closed is skipped.
        # Open-click races are handled by FlyoutManager anchor hits / host toggle.
        if hasattr(self, "_just_opened"):
            self._just_opened = False

        super().hideEvent(e)

        if self._anim:
            self._anim.stop()
            self._anim = None

        try:
            self.closed.emit()
        except Exception:
            pass

SimpleOptionsFlyout.inspect_spec = InspectSpec(  # type: ignore[attr-defined]
    family="SimpleOptionsFlyout",
    state=(
        SpecField("pinned", "pinned"),
        SpecField("flyout_group", "flyout_group"),
        SpecField("anchor", "_anchor_widget", private=True),
        SpecField("fade_opacity", "_fade_opacity_proxy", private=True),
        SpecField("visible", "isVisible"),
        SpecField("row_count", "row_count"),
        SpecField("max_visible_items", "max_visible_items"),
    ),
    token_family=("flyout.background", "flyout.border", "shadow.color", "separator.color"),
    docs='docs/user/FLYOUT_SYSTEM.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

SimpleOptionsFlyout.widget_descriptor = WidgetDescriptor(
    family=SimpleOptionsFlyout.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(SimpleOptionsFlyout.inspect_spec, 'config', ()),
        state=SimpleOptionsFlyout.inspect_spec.state,
        token_family=getattr(SimpleOptionsFlyout.inspect_spec, 'token_family', ()),
        regions=getattr(SimpleOptionsFlyout.inspect_spec, 'regions', False),
        layers=getattr(SimpleOptionsFlyout.inspect_spec, 'layers', False),
        docs=getattr(SimpleOptionsFlyout.inspect_spec, 'docs', ''),
        preview_seed=getattr(SimpleOptionsFlyout.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(SimpleOptionsFlyout.inspect_spec, 'apply_config_refresh', None),
    ),
)
