"""Row widgets and paint layers for context menus."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.managers.ui_font import rebase_family, ui_font
from sli_ui_toolkit.ui.widgets.buttons.button import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.layers.background import rounded_rect_path
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
    ContextMenuAction,
    _DANGER_COLOR,
    _ROW_H_PADDING,
    _measure_text_width,
    _shortcut_display_text,
)
from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import normalized_icon_pixmap


class SeparatorRow(QWidget):
    _H_INSET = 4

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedHeight(scaled_px(9))

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        color = ThemeManager.get_instance().get_color("separator.color")
        y = self.height() // 2
        inset = scaled_px(self._H_INSET)
        painter.setPen(QPen(color, 1))
        painter.drawLine(inset, y, self.width() - inset, y)
        painter.end()


class SectionTitleRow(QWidget):
    def __init__(self, text: str, parent: QWidget):
        super().__init__(parent)
        self._text = text
        self.setFixedHeight(scaled_px(24))

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setPen(QPen(ThemeManager.get_instance().get_color("dialog.text")))
        painter.setFont(ui_font(pixel_size=11, bold=True))
        painter.drawText(
            self.rect().adjusted(scaled_px(12), 0, -scaled_px(12), 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._text,
        )
        painter.end()

    def sizeHint(self):
        font = ui_font(pixel_size=11, bold=True)
        fm = QFontMetrics(font)
        return QSize(_measure_text_width(fm, self._text) + scaled_px(24), scaled_px(24))


class _RowBgLayer(Layer):
    INNER_R = 4
    OUTER_R = 5

    def applies(self, ctx) -> bool:
        widget = ctx.widget
        if not widget.isEnabled():
            return False
        states = ctx.effective_states
        return (
            widget._submenu_open
            or widget.isChecked()
            or ButtonState.HOVERED in states
            or ButtonState.PRESSED in states
        )

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        rect = QRectF(ctx.rect.toRect().adjusted(2, 1, -2, -1))
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(tm.get_color("list_item.background.hover")))
        pos = getattr(widget, "position", "middle")
        if pos == "middle":
            p.drawRoundedRect(rect, self.INNER_R, self.INNER_R)
            return
        tl = self.OUTER_R if pos in ("first", "only") else self.INNER_R
        tr = self.OUTER_R if pos in ("first", "only") else self.INNER_R
        bl = self.OUTER_R if pos in ("last", "only") else self.INNER_R
        br = self.OUTER_R if pos in ("last", "only") else self.INNER_R
        p.drawPath(rounded_rect_path(rect, (tl, tr, br, bl)))


class _CurrentIndicatorLayer(Layer):
    """Left accent bar for the current (checked) picker row — matches SimpleOptionsFlyout."""

    def applies(self, ctx) -> bool:
        widget = ctx.widget
        return bool(widget.isEnabled() and widget.isChecked())

    def draw(self, ctx, tm: ThemeManager) -> None:
        rect = ctx.rect.toRect()
        pen = QPen(tm.get_color("accent"))
        pen.setWidth(scaled_px(3))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(pen)
        x = rect.left() + pen.width()
        p.drawLine(
            x, rect.top() + scaled_px(7), x, rect.bottom() - scaled_px(7)
        )


class _RowContentLayer(Layer):
    _DISABLED_OPACITY = 0.4
    # Match combobox secondary/hint text: readable but clearly subordinate.
    _SHORTCUT_ALPHA_DARK = 140
    _SHORTCUT_ALPHA_LIGHT = 120

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        p = ctx.painter
        rect = ctx.rect.toRect()
        disabled = not widget.isEnabled()

        if widget._danger and not disabled:
            text_color = _DANGER_COLOR
        else:
            text_color = tm.get_color("dialog.text")

        if disabled:
            p.save()
            p.setOpacity(self._DISABLED_OPACITY)

        x = widget._check_gutter
        if widget._icon_pixmap is not None:
            icon_size = scaled_px(widget.ICON_SIZE)
            icon_rect = QRect(x, (rect.height() - icon_size) // 2, icon_size, icon_size)
            p.drawPixmap(icon_rect, widget._icon_pixmap)
            x += icon_size + scaled_px(8)

        p.setPen(QPen(text_color))
        # The row's font is already scale-resolved (set by the menu's
        # _relayout_widths via ui_font()); paint_font()/rebase() would treat
        # it as design space and multiply the UiScale factor a SECOND time,
        # painting the label ~factor^2 large and pushing it out of the row.
        # rebase_family() is the size-preserving, family-only variant.
        font = rebase_family(widget.font())
        p.setFont(font)
        fm = QFontMetrics(font)
        text_y = rect.center().y() + 5
        available = max(0, rect.width() - x - widget._trailing_width - scaled_px(_ROW_H_PADDING))
        if widget._text and fm.horizontalAdvance(widget._text) <= available:
            display_text = widget._text
        else:
            display_text = fm.elidedText(
                widget._text, Qt.TextElideMode.ElideRight, available
            )
        p.drawText(x, text_y, display_text)

        if widget._shortcut_text:
            shortcut_color = QColor(text_color)
            shortcut_color.setAlpha(
                self._SHORTCUT_ALPHA_DARK
                if tm.is_dark()
                else self._SHORTCUT_ALPHA_LIGHT
            )
            p.setPen(QPen(shortcut_color))
            sc_width = fm.horizontalAdvance(widget._shortcut_text)
            p.drawText(
                rect.width() - scaled_px(_ROW_H_PADDING) - sc_width, text_y, widget._shortcut_text
            )
        elif widget._has_children:
            # Painted chevron instead of the "›" glyph: the single-arrow
            # character is very narrow (≈4px at 12pt — half the width of
            # ">"), so it reads as a tiny dot at any UI scale and looked
            # like it never scaled. A polygon scales with scaled_px() and
            # stays visually comparable to the row text.
            cy = rect.center().y()
            sx = rect.width() - scaled_px(16)
            arm = scaled_px(5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(text_color))
            p.drawPolygon(
                QPolygonF(
                    [
                        QPointF(sx, cy - arm),
                        QPointF(sx + arm, cy),
                        QPointF(sx, cy + arm),
                    ]
                )
            )

        if disabled:
            p.restore()


class ContextMenuRow(Button):
    ROW_HEIGHT = 32
    ICON_SIZE = 16

    def __init__(self, action: ContextMenuAction, *, check_gutter: int, parent: QWidget):
        super().__init__(
            text="",
            size=(0, scaled_px(self.ROW_HEIGHT)),
            corner_radius=5,
            toggle=bool(action.checkable),
            layers=[_RowBgLayer(), RippleLayer(), _CurrentIndicatorLayer(), _RowContentLayer()],
            parent=parent,
        )
        self._text = action.text
        self._danger = action.danger
        self._has_children = bool(action.children)
        self._check_gutter = check_gutter
        self._icon_pixmap = (
            normalized_icon_pixmap(action.icon, scaled_px(self.ICON_SIZE)) if action.icon else None
        )
        self._shortcut_text = "" if action.children else _shortcut_display_text(action.shortcut)
        self._trailing_width = 0
        if self._shortcut_text:
            self._trailing_width = QFontMetrics(self.font()).horizontalAdvance(self._shortcut_text) + scaled_px(8)
        elif self._has_children:
            self._trailing_width = scaled_px(20)
        self._submenu_open = False
        self._has_text = bool(self._text)
        self.position = "only"
        self.action_id = action.action_id
        self.setEnabled(action.enabled)
        if action.checkable:
            self.setChecked(bool(action.checked), emit=False)
        if action.tooltip:
            self.setToolTip(action.tooltip)
        self.refresh_metrics()

    def refresh_metrics(self) -> None:
        fm = QFontMetrics(self.font())
        if self._shortcut_text:
            self._trailing_width = fm.horizontalAdvance(self._shortcut_text) + scaled_px(8)
        elif self._has_children:
            self._trailing_width = scaled_px(20)
        else:
            self._trailing_width = 0
        self.updateGeometry()

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        text_w = _measure_text_width(fm, self._text)
        icon_w = scaled_px(self.ICON_SIZE) + scaled_px(8) if self._icon_pixmap is not None else 0
        w = (
            self._check_gutter
            + icon_w
            + text_w
            + self._trailing_width
            + scaled_px(_ROW_H_PADDING)
        )
        return QSize(w, scaled_px(self.ROW_HEIGHT))

    def minimumSizeHint(self):
        return self.sizeHint()

    def set_submenu_open(self, is_open: bool) -> None:
        self._submenu_open = is_open
        self.update()

    def set_position(self, position: str) -> None:
        if self.position != position:
            self.position = position
            self.update()


# Private aliases kept for callers that still use the old underscore names.
_SeparatorRow = SeparatorRow
_SectionTitleRow = SectionTitleRow
_ContextMenuRow = ContextMenuRow
