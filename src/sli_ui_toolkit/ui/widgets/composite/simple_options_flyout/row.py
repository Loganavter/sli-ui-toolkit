"""Row widget + painting for ``SimpleOptionsFlyout`` -- split out of the
single-file ``simple_options_flyout.py`` to keep the facade thin, mirroring
``base_flyout/``'s split-by-concern shape.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from sli_ui_toolkit.ui.managers.ui_font import rebase_family, rebase_font
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState

__all__ = ["_design_font", "_RowBackgroundLayer", "_CurrentIndicatorLayer", "_SimpleRow"]


def _design_font(source: QFont) -> QFont:
    """Design-space version of a scale-resolved font (divide the factor out).

    ``ui_font()`` already multiplies the factor once, while
    ``SimpleOptionsFlyout`` row fonts are design-space and re-resolved per
    UiScale change — this converts one into the other.
    """
    design = QFont(source)
    factor = UiScale.get_instance().factor()
    if factor <= 0:
        return design
    if design.pixelSize() > 0:
        design.setPixelSize(max(1, round(design.pixelSize() / factor)))
    elif design.pointSizeF() > 0:
        design.setPointSizeF(design.pointSizeF() / factor)
    return design


class _RowBackgroundLayer(Layer):
    """Inset rounded background, list_item.* tokens, hover/current → hover color."""

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        states = ctx.effective_states
        is_active = (
            widget.is_current
            or ButtonState.HOVERED in states
            or ButtonState.PRESSED in states
        )
        key = "list_item.background.hover" if is_active else "list_item.background.normal"
        rect = ctx.rect.toRect().adjusted(2, 2, -2, -2)
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(tm.get_color(key)))
        p.drawRoundedRect(rect, 5, 5)


class _CurrentIndicatorLayer(Layer):
    """Левый accent-индикатор для current row."""

    def applies(self, ctx) -> bool:
        return bool(getattr(ctx.widget, "is_current", False))

    def draw(self, ctx, tm: ThemeManager) -> None:
        rect = ctx.rect.toRect()
        pen = QPen(tm.get_color("accent"))
        pen.setWidth(scaled_px(3))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(pen)
        x = rect.left() + pen.width()
        p.drawLine(x, rect.top() + scaled_px(7), x, rect.bottom() - scaled_px(7))


class _SimpleRow(Button):
    rowClicked = Signal(int)

    def __init__(
        self,
        index: int,
        text: str,
        is_current: bool,
        item_height: int,
        item_font: QFont,
        parent: QWidget | None = None,
    ):
        super().__init__(
            text="",
            size=(0, item_height),
            corner_radius=5,
            layers=[_RowBackgroundLayer(), RippleLayer(), _CurrentIndicatorLayer()],
            parent=parent,
        )
        self.index = index
        self.text = text
        self.is_current = is_current
        self._item_height = item_height
        # item_font is design-space: resolve the scaled label font here and
        # again on every UiScale change (_apply_scale), so the row's text
        # follows live interface-scale changes instead of staying at the
        # size captured when the row was built.
        self._design_font = item_font
        layout = QHBoxLayout(self)
        # Accent indicator draws inside the left pad; keep pad tight to the label.
        layout.setContentsMargins(scaled_px(8), 0, scaled_px(8), 0)
        self.label = QLabel(text)
        self.label.setFont(rebase_font(item_font))
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.label)
        try:
            self.theme_manager.theme_changed.connect(self._apply_label_style)
        except Exception:
            pass
        self._apply_label_style()
        self.clicked.connect(lambda: self.rowClicked.emit(self.index))
        UiScale.get_instance().scale_changed.connect(self._apply_scale)

    def sizeHint(self) -> QSize:
        row_layout = self.layout()
        margins = row_layout.contentsMargins() if row_layout is not None else None
        pad = (
            (margins.left() + margins.right())
            if margins is not None
            else 16
        )
        label_w = self.label.sizeHint().width() if self.label is not None else 0
        # Design item height, scaled exactly once — same value Button's own
        # setFixedHeight(scaled_px(item_height)) applies, so the flyout's
        # container sizing matches the row widgets at any UiScale factor.
        return QSize(max(1, label_w + pad), scaled_px(self._item_height))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _apply_label_style(self):
        # Force the UI family without touching the size: the label font was
        # already scale-resolved once (rebase_font of the design font below),
        # so feeding it back through rebase_font would multiply the factor
        # a second time and blow the row up ~factor^2 at high UI scale.
        self.label.setFont(rebase_family(self.label.font()))
        self.label.setProperty("class", "option-label")

    def _apply_scale(self, _factor: float) -> None:
        # Re-resolve the design font at the new factor; keeps the row's text
        # (and its sizeHint, via the scaled label) live with the UI scale.
        self.label.setFont(rebase_font(self._design_font))
        self.updateGeometry()
        self.update()
