"""
Container that groups buttons with an optional label and border.
Replaces ButtonGroupContainer from atomic/.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import ui_font
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.buttons.layers.background import rounded_rect_path
from sli_ui_toolkit.ui.widgets.buttons.specs import CornerRadii, normalize_corner_radii

class ButtonGroup(QWidget):
    def __init__(
        self,
        buttons: list,
        label: str = "",
        parent=None,
        *,
        border_radius: int = 8,
        corner_radii: CornerRadii | None = None,
    ):
        super().__init__(parent)
        self._label = label
        self._border_width = 1
        # (top-left, top-right, bottom-right, bottom-left); border_radius is
        # the uniform shorthand, corner_radii overrides per-corner (same
        # convention as Button's ShapeSpec). Runtime-adjustable via
        # set_corner_radii -- e.g. squaring off the bottom corners while a
        # flyout is docked flush under this group.
        self._corner_radii: CornerRadii = normalize_corner_radii(
            border_radius, corner_radii, fallback=8
        )

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self._layout = QHBoxLayout(self)
        self._apply_layout_metrics()
        for button in buttons:
            self._layout.addWidget(button)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)
        UiScale.get_instance().scale_changed.connect(self.on_scale_changed)

    def on_scale_changed(self, _factor: float) -> None:
        self._apply_layout_metrics()
        self.updateGeometry()
        self.update()

    def _apply_layout_metrics(self) -> None:
        self._layout.setContentsMargins(
            scaled_px(10), scaled_px(8), scaled_px(10), scaled_px(18)
        )
        self._layout.setSpacing(scaled_px(2))

    def set_label(self, text: str):
        if self._label != text:
            self._label = text
            self.update()

    set_label_text = set_label

    def label(self) -> str:
        return self._label

    def set_corner_radii(
        self,
        corner_radii: CornerRadii | None = None,
        *,
        border_radius: int | None = None,
    ) -> None:
        """Set the border's per-corner radii.

        Pass ``corner_radii=(tl, tr, br, bl)`` for explicit control, or
        ``border_radius=N`` for a uniform value on all four. Omitting both
        restores the default (uniform 8px).
        """
        resolved = normalize_corner_radii(border_radius, corner_radii, fallback=8)
        if resolved != self._corner_radii:
            self._corner_radii = resolved
            self.update()

    def corner_radii(self) -> CornerRadii:
        return self._corner_radii

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        border_color = self.theme_manager.get_color("dialog.border")
        bg_color = self.theme_manager.get_color("Window")
        text_color = self.theme_manager.get_color("WindowText")

        rect = self.rect()
        # ui_font() returns the already-scaled base; back out the factor to
        # express "2pt smaller" in design space, then re-resolve so the
        # delta scales proportionally with UiScale.
        factor = UiScale.get_instance().factor()
        font = ui_font(point_size=max(8, ui_font().pointSizeF() / factor - 2))
        painter.setFont(font)
        fm = QFontMetrics(font)
        label_height = fm.height() if self._label else 0

        pen = QPen(border_color, self._border_width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.translate(0.5, 0.5)

        margin_v = scaled_px(3)
        margin_h = scaled_px(6)
        bottom_y = rect.height() - label_height // 2
        draw_rect = QRect(
            margin_h, margin_v,
            rect.width() - margin_h * 2 - 1,
            bottom_y - margin_v * 2,
        )
        radii = tuple(0 if v == 0 else scaled_px(v) for v in self._corner_radii)
        painter.drawPath(rounded_rect_path(QRectF(draw_rect), radii))
        painter.translate(-0.5, -0.5)

        if self._label:
            label_padding = scaled_px(3)
            center_x = rect.width() // 2
            label_w = fm.horizontalAdvance(self._label)
            label_h = fm.height()

            actual_bottom_y = bottom_y - margin_v
            gap_y = actual_bottom_y - self._border_width
            gap_height = self._border_width * 2 + 1

            painter.setPen(Qt.PenStyle.NoPen)
            gap_rect = QRect(
                center_x - label_w // 2 - label_padding,
                gap_y, label_w + label_padding * 2, gap_height,
            )
            painter.fillRect(gap_rect, bg_color)

            text_rect = QRect(
                center_x - label_w // 2,
                rect.height() - label_h - 2,
                label_w, label_h,
            )
            painter.setPen(text_color)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._label)
