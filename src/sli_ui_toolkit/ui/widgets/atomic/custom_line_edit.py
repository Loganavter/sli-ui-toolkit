from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLineEdit

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import (
    UnderlineConfig,
    apply_editable_text_behavior,
    draw_bottom_underline,
)


class CustomLineEdit(QLineEdit):
    RADIUS = 6
    # Horizontal inset only — vertical room comes from HEIGHT so descenders
    # (у, р, g, y) are not clipped. Do not also pad via QSS.
    H_PADDING = 8
    V_PADDING = 0
    HEIGHT = 32

    def __init__(
        self,
        parent=None,
        *,
        alignment=Qt.AlignmentFlag.AlignLeft,
        underline_color: QColor | None = None,
        underline_thickness: float | None = None,
        focused_underline_color: QColor | None = None,
        focused_underline_thickness: float | None = None,
    ):
        super().__init__(parent)
        self.theme_manager = ThemeManager.get_instance()
        self._underline_color = underline_color
        self._underline_thickness = self._normalize_thickness(underline_thickness)
        self._focused_underline_color = focused_underline_color
        self._focused_underline_thickness = self._normalize_thickness(
            focused_underline_thickness
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setFrame(False)
        self.setTextMargins(
            self.H_PADDING,
            self.V_PADDING,
            self.H_PADDING,
            self.V_PADDING,
        )
        self.setTextAlignment(alignment)
        self.setFixedHeight(self.HEIGHT)
        self.setProperty("custom-line-edit", True)
        self.setProperty("class", "primary")
        apply_editable_text_behavior(self)
        self._apply_theme_style()
        try:
            self.theme_manager.theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    def _style_prefix(self) -> str:
        btn_class = str(self.property("class") or "")
        return "button.primary" if btn_class == "primary" else "button.default"

    def setTextAlignment(self, alignment) -> None:
        """Set text alignment using Qt flags or 'left' / 'center' / 'right'."""
        self.setAlignment(self._normalize_alignment(alignment))

    def textAlignment(self):
        return self.alignment()

    def set_text_alignment(self, alignment) -> None:
        self.setTextAlignment(alignment)

    def text_alignment(self):
        return self.textAlignment()

    def setUnderlineColor(self, color: QColor | None) -> None:
        self._underline_color = color
        self.setProperty("underlineColor", color)
        self.update()

    set_underline_color = setUnderlineColor

    def underlineColor(self) -> QColor | None:
        return self._underline_color

    def setUnderlineThickness(self, thickness: float | None) -> None:
        self._underline_thickness = self._normalize_thickness(thickness)
        self.setProperty("underlineThicknessPx", self._underline_thickness)
        self.update()

    set_underline_thickness = setUnderlineThickness

    def underlineThickness(self) -> float | None:
        return self._underline_thickness

    def setFocusedUnderlineColor(self, color: QColor | None) -> None:
        self._focused_underline_color = color
        self.setProperty("focusedUnderlineColor", color)
        self.update()

    def focusedUnderlineColor(self) -> QColor | None:
        return self._focused_underline_color

    def setFocusedUnderlineThickness(self, thickness: float | None) -> None:
        self._focused_underline_thickness = self._normalize_thickness(thickness)
        self.setProperty("focusedUnderlineThicknessPx", self._focused_underline_thickness)
        self.update()

    def focusedUnderlineThickness(self) -> float | None:
        return self._focused_underline_thickness

    @staticmethod
    def _normalize_thickness(thickness: float | None) -> float | None:
        return None if thickness is None else max(0.0, float(thickness))

    def _normalize_alignment(self, alignment):
        if isinstance(alignment, str):
            normalized = alignment.strip().lower().replace("-", "_")
            if normalized in {"left", "start", "leading"}:
                horizontal = Qt.AlignmentFlag.AlignLeft
            elif normalized in {"center", "centre", "middle"}:
                horizontal = Qt.AlignmentFlag.AlignHCenter
            elif normalized in {"right", "end", "trailing"}:
                horizontal = Qt.AlignmentFlag.AlignRight
            else:
                raise ValueError(
                    "alignment must be a Qt alignment or one of: left, center, right"
                )
            return horizontal | Qt.AlignmentFlag.AlignVCenter

        if alignment & (
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignHCenter
            | Qt.AlignmentFlag.AlignJustify
        ):
            return alignment | Qt.AlignmentFlag.AlignVCenter
        return alignment | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.update)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        QTimer.singleShot(0, self.update)

    def _on_theme_changed(self):
        self._apply_theme_style()
        self.update()

    def _apply_theme_style(self):
        text = self.theme_manager.get_color("dialog.text").name(QColor.NameFormat.HexArgb)
        accent = self.theme_manager.get_color("accent").name(QColor.NameFormat.HexArgb)
        # padding:0 is mandatory — app QSS often stacks padding on top of
        # setTextMargins and clips descenders / doubles the left inset.
        self.setStyleSheet(
            "QLineEdit {"
            "background: transparent;"
            "border: none;"
            "padding: 0;"
            "margin: 0;"
            f"color: {text};"
            "}"
            "QLineEdit::placeholder {"
            f"color: {text};"
            "}"
            "QLineEdit::selection {"
            f"background-color: {accent};"
            "color: #ffffff;"
            "}"
        )

    def paintEvent(self, event):
        rect = self.rect()
        radius = self.RADIUS
        rounded_rect = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = self.theme_manager.get_color("dialog.input.background")
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rounded_rect, radius, radius)
        painter.end()

        super().paintEvent(event)

        try:
            painter = QPainter(self)
            if not painter.isActive():
                return
            painter.save()
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)

                thin = QColor(self.theme_manager.get_color("input.border.thin"))
                alpha = max(8, int(thin.alpha() * 0.66))
                thin.setAlpha(alpha)
                pen = QPen(thin)
                pen.setWidthF(0.66)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rounded_rect, radius, radius)

                if self.hasFocus():
                    underline_config = UnderlineConfig(
                        color=(
                            self._focused_underline_color
                            or self.theme_manager.get_color("accent")
                        ),
                        alpha=120,
                        thickness=self._focused_underline_thickness or 1.5,
                        arc_radius=3.0,
                    )
                else:
                    underline_config = UnderlineConfig(
                        color=self._underline_color,
                        alpha=60,
                        thickness=self._underline_thickness or 1.0,
                        arc_radius=3.0,
                    )

                draw_bottom_underline(painter, rect, self.theme_manager, underline_config)
            finally:
                painter.restore()
                painter.end()
        except Exception:
            pass
