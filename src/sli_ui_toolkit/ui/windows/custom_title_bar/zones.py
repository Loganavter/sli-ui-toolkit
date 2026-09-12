"""CustomTitleBar zone layout — title, leading/trailing zones, balance.

The title bar's chrome is a fixed-slot row
``[leading][left_balance][stretch][center][stretch][trailing][right_balance][buttons]``;
this mixin owns everything about zones, the centered-title balance spacers,
scaling, and the corner mask for the control cluster. The window-control
buttons and the drag surface live in the sibling mixins.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.atomic.text_labels import (
    Label,
    LabelVariantSpec,
    register_label_variant,
)
from sli_ui_toolkit.ui.widgets.buttons import Button

TitleAlign = Literal["center", "leading"]
TitleBarZone = Literal["leading", "trailing", "center"]


def resolve_titlebar_color(token: str, *, fallback: str = "Window") -> QColor:
    """Resolve a title-bar palette token with a safe fallback chain."""
    tm = ThemeManager.get_instance()
    color = tm.try_get_color(token)
    if color is not None and color.isValid():
        return color
    color = tm.try_get_color(fallback)
    if color is not None and color.isValid():
        return color
    return tm.get_color("WindowText" if token.endswith(".text") else "Window")


def _ensure_titlebar_label_variant() -> None:
    # Always (re)register: get_label_variant() silently falls back to "body"
    # when a name is missing, so a KeyError guard never ran and the title
    # stayed at body size (12px) regardless of this spec.
    register_label_variant(
        LabelVariantSpec(
            "titlebar",
            pixel_size=16,
            color_token="titlebar.text",
        )
    )


def _zone_host(parent: QWidget) -> QWidget:
    host = QWidget(parent)
    host.setObjectName("TitleBarZoneHost")
    host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    host.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    host.setAutoFillBackground(False)
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    host.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    return host


class _TitleBarLayoutApi:
    """Mixin: zones, title alignment, balance spacers, scaling, corner mask.

    Not a QWidget itself — mixed into CustomTitleBar; relies on instance
    attributes assigned in ``CustomTitleBar.__init__`` (``_layout``, zone
    hosts, ``_title_label``, ``_app_icon_label``, ``_controls_handle``,
    ``_left_balance``, ``_balance_spacer``, ``_buttons_container``,
    ``_target_window``) and on QWidget methods (isVisible, repaint, update,
    updateGeometry). Mixin methods from the sibling modules it calls
    (``_resize_buttons_container``, ``register_drag_exclusion``) are
    declared here only for mypy.
    """

    # Declared here only so mypy can resolve them across the mixin split —
    # the real assignments live in CustomTitleBar.__init__ (widget.py), the
    # sibling mixins, or QWidget itself. Plain annotations only (no
    # `= value`); QWidget-provided names are ``Any`` (a precise Callable
    # would clash with QWidget's own definition when the mixin precedes it
    # in the MRO).
    _layout: Any
    _leading_host: QWidget
    _trailing_host: QWidget
    _center_host: QWidget
    _title_label: Any
    _app_icon_label: QLabel | None
    _controls_handle: Any
    _left_balance: QWidget
    _balance_spacer: QWidget
    _controls: Any
    _target_window: Any
    _title_align: TitleAlign
    _title_visible: bool
    _balance_resync_scheduled: bool
    _design_height: int
    _design_icon_slot: int
    _design_button_width: int
    height: Any
    CORNER_RADIUS: int
    ICON_SIZE: int
    isVisible: Any
    repaint: Any
    setFixedHeight: Any
    update: Any
    updateGeometry: Any
    window: Any
    clearMask: Any
    register_drag_exclusion: Any

    def on_scale_changed(self, _factor: float) -> None:
        self.setFixedHeight(scaled_px(self._design_height))
        self._controls.set_design(
            self._design_button_width, self.height(), self.CORNER_RADIUS
        )
        # The corner mask clips the cluster to the rounded top-right arc. It
        # is normally re-applied on the bar's resizeEvent — but a scale
        # change resizes the cluster here, and if the bar's own resize
        # event lands before/without this, the mask stays at the previous
        # factor's width and masks the rescaled buttons away (the close
        # button "disappears" on scale increase). Re-apply it now, with the
        # cluster at its final size.
        try:
            self._apply_corner_mask()
        except Exception:
            pass
        # Child sizeHints (menu strip remeasure, title Label font, window
        # controls) refresh in their own scale_changed handlers, which may
        # run AFTER this one. Defer the full re-layout + balance so it sees
        # fresh sizes — otherwise the zone hosts and the centered title keep
        # their pre-scale geometry (clipped title text, menu buttons
        # overflowing the strip) until some unrelated event happens to
        # re-activate the layout.
        self._schedule_balance_resync()
        self.updateGeometry()
        self.update()

    def set_icon(self, icon: QIcon | None) -> None:
        """Show a leading app icon (draggable with the title bar chrome)."""
        if icon is None or icon.isNull():
            if self._app_icon_label is not None:
                self._app_icon_label.hide()
                self._sync_balance_spacer()
                self._schedule_balance_resync()
            return

        if self._app_icon_label is None:
            label = QLabel(self._leading_host)
            label.setObjectName("CustomTitleBarAppIcon")
            label.setFixedSize(
                scaled_px(self._design_icon_slot), scaled_px(self._design_height)
            )
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Keep drag on the icon slot — it is chrome, not a control.
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._app_icon_label = label
            self._zone_layout("leading").insertWidget(0, label)

        pixmap = icon.pixmap(self.ICON_SIZE, self.ICON_SIZE)
        self._app_icon_label.setPixmap(pixmap)
        self._app_icon_label.show()
        self._sync_balance_spacer()
        self._schedule_balance_resync()

    def _stretch_indices(self) -> tuple[int, int]:
        # [leading][left_balance][stretch][center][stretch][trailing][right_balance][buttons]
        return (2, 4)

    def _apply_title_alignment(self) -> None:
        before_idx, after_idx = self._stretch_indices()
        if self._title_align == "center":
            self._layout.setStretch(before_idx, 1)
            self._layout.setStretch(after_idx, 1)
            self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self._layout.setStretch(before_idx, 0)
            self._layout.setStretch(after_idx, 1)
            self._title_label.setAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )

    def _zone_layout(self, zone: TitleBarZone) -> QHBoxLayout:
        host = {
            "leading": self._leading_host,
            "trailing": self._trailing_host,
            "center": self._center_host,
        }[zone]
        layout = host.layout()
        assert isinstance(layout, QHBoxLayout)
        return layout

    def _clear_zone(self, zone: TitleBarZone) -> None:
        layout = self._zone_layout(zone)
        keep: set[QLabel] = {self._title_label}
        if zone == "leading" and self._app_icon_label is not None:
            keep.add(self._app_icon_label)
        for index in reversed(range(layout.count())):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None or widget in keep:
                continue
            layout.takeAt(index)
            # hide + detach immediately: deleteLater alone leaves the old
            # leading-zone widget painting until the next event-loop turn
            # (ghost «Справка» between File and Help on first show).
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()

    def _set_zone_widget(self, zone: TitleBarZone, widget: QWidget | None) -> None:
        if zone == "center" and widget is None:
            self._clear_zone("center")
            layout = self._zone_layout("center")
            if layout.indexOf(self._title_label) < 0:
                layout.addWidget(self._title_label)
            self._title_label.setVisible(self._title_visible)
            return

        self._clear_zone(zone)
        if widget is None:
            if zone == "center":
                layout = self._zone_layout("center")
                if layout.indexOf(self._title_label) < 0:
                    layout.addWidget(self._title_label)
                self._title_label.setVisible(self._title_visible)
            return
        layout = self._zone_layout(zone)
        layout.addWidget(widget)
        if zone != "center":
            self.register_drag_exclusion(widget)

    def set_leading(self, widget: QWidget | None) -> None:
        self._set_zone_widget("leading", widget)
        self._sync_balance_spacer()
        self._schedule_balance_resync()

    def set_trailing(self, widget: QWidget | None) -> None:
        self._set_zone_widget("trailing", widget)
        self._sync_balance_spacer()
        self._schedule_balance_resync()

    def set_center(self, widget: QWidget | None) -> None:
        self._set_zone_widget("center", widget)

    def set_title(self, title: str, *, align: TitleAlign | None = None) -> None:
        self._title_label.setText(title)
        if align is not None:
            self.set_title_alignment(align)
        else:
            self._sync_balance_spacer()
            self._schedule_balance_resync()

    def set_title_alignment(self, align: TitleAlign) -> None:
        self._title_align = align
        self._apply_title_alignment()
        self._sync_balance_spacer()
        self._schedule_balance_resync()

    def set_title_visible(self, visible: bool) -> None:
        self._title_visible = visible
        self._title_label.setVisible(visible)

    def add_widget(self, widget: QWidget, *, zone: TitleBarZone = "leading") -> QWidget:
        layout = self._zone_layout(zone)
        layout.addWidget(widget)
        self.register_drag_exclusion(widget)
        self._sync_balance_spacer()
        self._schedule_balance_resync()
        return widget

    def add_button(self, button: Button, *, zone: TitleBarZone = "leading") -> Button:
        self.add_widget(button, zone=zone)
        return button

    def add_buttons(
        self, buttons: Sequence[Button], *, zone: TitleBarZone = "leading"
    ) -> QWidget:
        row = _zone_host(self)  # type: ignore[arg-type]
        row_layout = row.layout()
        assert row_layout is not None
        for button in buttons:
            row_layout.addWidget(button)
            self.register_drag_exclusion(button)
        layout = self._zone_layout(zone)
        if layout.count() == 0:
            layout.addWidget(row)
            self.register_drag_exclusion(row)
        else:
            for button in buttons:
                layout.addWidget(button)
            row.deleteLater()
        self._sync_balance_spacer()
        self._schedule_balance_resync()
        return row

    def _chrome_side_widths(self) -> tuple[int, int]:
        leading = self._zone_content_width(self._leading_host)
        trailing = self._zone_content_width(self._trailing_host)
        buttons = self._controls_handle.size_hint_width()
        return leading, trailing + buttons

    @staticmethod
    def _zone_content_width(host: QWidget) -> int:
        """Width of zone chrome, even before the host sizeHint catches up."""
        hint = max(host.sizeHint().width(), host.minimumSizeHint().width())
        if hint > 0:
            return hint
        layout = host.layout()
        if layout is None:
            return max(host.width(), 0)
        total = layout.contentsMargins().left() + layout.contentsMargins().right()
        visible = 0
        for index in range(layout.count()):
            item = layout.itemAt(index)
            child = item.widget() if item is not None else None
            if child is None or child.isHidden():
                continue
            visible += 1
            total += max(
                child.sizeHint().width(),
                child.minimumSizeHint().width(),
                child.width(),
            )
        if visible > 1:
            total += max(0, layout.spacing()) * (visible - 1)
        return max(total, host.width(), 0)

    def _schedule_balance_resync(self) -> None:
        """Re-measure chrome after the next layout pass.

        Leading-zone rebuilds / language changes often sync while the new
        leading widget still reports ``sizeHint().width() == 0``. A left pad
        matching the window buttons then sticks after the widget lays out,
        shoving the centered title off-center.

        While the bar is still hidden, run sync immediately — a deferred pass
        after the first show paint leaves a ghost of translucent menu labels.
        """
        if self._title_align != "center":
            return
        if not self.isVisible():
            self._sync_balance_spacer()
            return
        if self._balance_resync_scheduled:
            return
        self._balance_resync_scheduled = True

        def _run() -> None:
            self._balance_resync_scheduled = False
            try:
                import shiboken6

                if not shiboken6.isValid(self):  # type: ignore[attr-defined]
                    return
            except Exception:
                pass
            # Re-run the zone layout with the children's current sizeHints
            # even when the balance itself is a no-op (leading-aligned
            # titles), so a deferred scale/font resync cannot leave zone
            # hosts at stale widths.
            self._layout.invalidate()
            self._layout.activate()
            self._sync_balance_spacer()
            # Translucent ghost triggers do not erase themselves on move.
            self.repaint()

        QTimer.singleShot(0, _run)

    def _sync_balance_spacer(self) -> None:
        if self._title_align != "center":
            self._left_balance.setFixedWidth(0)
            self._balance_spacer.setFixedWidth(0)
            return
        left, right = self._chrome_side_widths()
        if left < right:
            self._left_balance.setFixedWidth(right - left)
            self._balance_spacer.setFixedWidth(0)
        else:
            self._left_balance.setFixedWidth(0)
            self._balance_spacer.setFixedWidth(left - right)
        # setFixedWidth alone does not always reflow an already-laid-out
        # title bar (deferred language resync); force the stretch pair to
        # recompute so the title stays visually centered.
        self._layout.invalidate()
        self._layout.activate()
        self.updateGeometry()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_balance_spacer()
        self._apply_corner_mask()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_corner_mask()
        # The layout may have been activated while the bar was still hidden
        # (construction / pre-show balance syncs), when the zone hosts had
        # no sizeHints yet — leaving them stuck at tiny widths (clipped menu
        # buttons, elided title) for the first visible frame. The bar is
        # visible now and its children have real sizeHints: re-run the
        # layout + balance before the first paint.
        try:
            self._layout.invalidate()
            self._layout.activate()
            self._sync_balance_spacer()
        except Exception:
            pass

    def _apply_corner_mask(self) -> None:
        from sli_ui_toolkit.ui.windows.rounded_body import (
            apply_top_trailing_rounded_mask,
        )

        # Title bar paints its own AA rounded fill — a full-bar setMask would
        # stair-case that edge. Only clip the control cluster so the close
        # button cannot poke through the top-right arc.
        self.clearMask()
        window = self._target_window if self._target_window is not None else self.window()
        squared = bool(
            window is not None
            and (window.isMaximized() or window.isFullScreen())
        )
        buttons = getattr(self, "_controls", None)
        if buttons is not None:
            apply_top_trailing_rounded_mask(
                buttons,
                radius=float(self.CORNER_RADIUS),
                squared=squared,
            )
