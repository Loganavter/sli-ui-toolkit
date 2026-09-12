"""Owner-managed tab button + painter content for TopTabBar."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QCursor, QFontMetrics, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.content import Content, _text_color
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.constants import (
    DEFAULT_TAB_RADIUS,
    INDICATOR_H,
    TAB_CLOSE_MARGIN,
    TAB_H_PAD,
    TAB_MIN_WIDTH,
)
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.variant import register_top_tab_variant
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

register_top_tab_variant()



class TopTabContent(Content):
    """Centered label; folder outline or accent underline when selected.
    ``close_zone`` reserves space at the right edge for an embedded close
    button (the adaptive-tab slot contract)."""

    def __init__(
        self, text: str, *, show_indicator: bool = True, close_zone: int = 0
    ) -> None:
        self.text = text
        self.show_indicator = show_indicator
        self.close_zone = max(0, int(close_zone))

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        p = ctx.painter
        style = read_widget_style(widget)
        selected = widget.isChecked()
        font = paint_font(widget)
        p.setFont(font)

        if selected and not self.show_indicator:
            self._draw_folder_outline(ctx, tm)

        if selected:
            accent = tm.try_get_color("accent")
            if accent is not None and accent.isValid():
                p.setPen(QColor(accent))
            else:
                p.setPen(_text_color(ctx, tm))
        else:
            p.setPen(style.foreground_color or _text_color(ctx, tm))

        text_rect = QRect(0, 0, widget.width(), widget.height())
        if self.show_indicator and selected:
            text_rect = text_rect.adjusted(0, 0, 0, -INDICATOR_H)
        if self.close_zone:
            text_rect = text_rect.adjusted(0, 0, -self.close_zone, 0)
        # Button width already includes TAB_H_PAD; do not subtract it again
        # or long labels (e.g. "Ручной ввод CLI") get falsely elided.
        text = p.fontMetrics().elidedText(
            self.text,
            Qt.TextElideMode.ElideRight,
            max(0, text_rect.width() - 4),
        )
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)

        if self.show_indicator and selected:
            accent = tm.try_get_color("accent")
            if accent is None or not accent.isValid():
                return
            p.fillRect(
                QRect(0, widget.height() - INDICATOR_H, widget.width(), INDICATOR_H),
                QColor(accent),
            )

    def _draw_folder_outline(self, ctx, tm: ThemeManager) -> None:
        border = tm.try_get_color("separator.color")
        if border is None or not border.isValid():
            return
        widget = ctx.widget
        p = ctx.painter
        radii = getattr(widget, "_corner_radii_px", None)
        if isinstance(radii, tuple) and len(radii) >= 2:
            radius = float(radii[0])
        else:
            try:
                radius = float(
                    getattr(widget, "_corner_radius_px", DEFAULT_TAB_RADIUS)
                    or DEFAULT_TAB_RADIUS
                )
            except Exception:
                radius = float(DEFAULT_TAB_RADIUS)
        rect = QRectF(0.5, 0.5, widget.width() - 1.0, widget.height() - 1.0)
        path = QPainterPath()
        path.moveTo(rect.left(), rect.bottom())
        path.lineTo(rect.left(), rect.top() + radius)
        path.arcTo(rect.left(), rect.top(), 2 * radius, 2 * radius, 180.0, -90.0)
        path.lineTo(rect.right() - radius, rect.top())
        path.arcTo(
            rect.right() - 2 * radius,
            rect.top(),
            2 * radius,
            2 * radius,
            90.0,
            -90.0,
        )
        path.lineTo(rect.right(), rect.bottom())
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(border), 1.0))
        p.drawPath(path)


class TopTabButton(Button):
    """Owner-managed selection (same contract as sidebar nav row buttons).

    With ``close_zone > 0`` the tab embeds a close button at its right edge
    (adaptive-tab close-slot mechanics): the text reserves the zone, the
    button is a child positioned on resize, and hovering it keeps the tab
    itself hovered (the hover coordinator only sees the child).
    """

    def __init__(self, *args, close_zone: int = 0, **kwargs) -> None:
        kwargs["toggle"] = False
        super().__init__(*args, **kwargs)
        self._close_zone = max(0, int(close_zone))
        self._close_button: QWidget | None = None
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._show_indicator = True

    def isChecked(self) -> bool:
        return ButtonState.CHECKED in self._controller.states("_main")

    def set_selected(self, selected: bool) -> None:
        self._controller.set_state("_main", ButtonState.CHECKED, bool(selected))
        self._sync_region_aliases()
        self.update()

    def set_show_indicator(self, show: bool) -> None:
        self._show_indicator = bool(show)
        self.update()

    def attach_close_button(self, button: QWidget) -> None:
        """Embed the close button inside the tab, right-aligned."""
        self._close_button = button
        button.setParent(self)
        button.show()
        button.installEventFilter(self)
        self._layout_close_button()

    def _layout_close_button(self) -> None:
        if self._close_button is None:
            return
        size = self._close_button.size()
        x = max(0, self.width() - size.width() - TAB_CLOSE_MARGIN)
        y = max(0, (self.height() - size.height()) // 2)
        self._close_button.setGeometry(x, y, size.width(), size.height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_close_button()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        # Forward hover over the close button to the tab bar (the adaptive
        # close-slot contract): the bar owns the hover index and re-paints
        # the tab + slot states from it.
        if watched is self._close_button and event.type() in (
            QEvent.Type.Enter,
            QEvent.Type.MouseMove,
            QEvent.Type.Leave,
        ):
            if event.type() == QEvent.Type.Leave:
                global_pos = QCursor.pos()
            elif hasattr(event, "globalPosition"):
                global_pos = event.globalPosition().toPoint()
            else:
                global_pos = watched.mapToGlobal(event.position().toPoint())
            bar = self.parentWidget()
            while bar is not None and not hasattr(bar, "set_hover_from_global"):
                bar = bar.parentWidget()
            if bar is not None:
                bar.set_hover_from_global(global_pos)
        return super().eventFilter(watched, event)

    def _build_content(self):
        return TopTabContent(
            self._text,
            show_indicator=self._show_indicator,
            close_zone=self._close_zone,
        )

    def _build_region_content(self, region):
        return TopTabContent(
            self._text,
            show_indicator=self._show_indicator,
            close_zone=self._close_zone,
        )

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(paint_font(self))
        text_w = fm.horizontalAdvance(self._text or "")
        # +2 absorbs hinting differences between advance and elidedText.
        width = max(TAB_MIN_WIDTH, text_w + 2 * TAB_H_PAD + 2)
        height = self.minimumHeight() or 32
        return QSize(width + self._close_zone, height)
