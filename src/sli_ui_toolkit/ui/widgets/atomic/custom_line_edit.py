from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402
from typing import Literal

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QLineEdit

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import apply_text_color, apply_ui_font
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.helpers import (
    UnderlineConfig,
    apply_editable_text_behavior,
    draw_bottom_underline,
)

TextAlignment = Qt.AlignmentFlag | Literal["left", "center", "right"]


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
        alignment: TextAlignment = Qt.AlignmentFlag.AlignLeft,
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
        pad_h = scaled_px(self.H_PADDING)
        self.setTextMargins(
            pad_h,
            self.V_PADDING,
            pad_h,
            self.V_PADDING,
        )
        self.setTextAlignment(alignment)
        self.setFixedHeight(scaled_px(self.HEIGHT))
        self.setProperty("custom-line-edit", True)
        self.setProperty("class", "primary")
        apply_editable_text_behavior(self)
        # Native QLineEdit text renders with widget.font(); apply_ui_font
        # pins the UI face at the current UiScale factor and re-resolves on
        # font_changed AND scale_changed — otherwise the text stays at the
        # design size while the chrome around it scales.
        apply_ui_font(self)
        self._apply_theme_style()
        try:
            self.theme_manager.theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass
        UiScale.get_instance().scale_changed.connect(self.on_scale_changed)

    def on_scale_changed(self, _factor: float) -> None:
        pad_h = scaled_px(self.H_PADDING)
        self.setTextMargins(pad_h, self.V_PADDING, pad_h, self.V_PADDING)
        self.setFixedHeight(scaled_px(self.HEIGHT))
        self.updateGeometry()
        self.update()

    def minimumSizeHint(self) -> QSize:
        # QLineEdit's stock minimumSizeHint reserves space for one full
        # character and grows with the (scaled) font — two such edits next
        # to their "Имя:" labels eat the labels' width when the row is
        # tight. A zero-width floor lets the edit yield to its neighbor
        # labels (text still scrolls/elides inside); vertical minimum stays
        # the fixed scaled height.
        from PySide6.QtCore import QSize

        return QSize(0, scaled_px(self.HEIGHT))

    def _style_prefix(self) -> str:
        btn_class = str(self.property("class") or "")
        return "button.primary" if btn_class == "primary" else "button.default"

    def setTextAlignment(self, alignment: Qt.AlignmentFlag | str) -> None:
        """Set text alignment using Qt flags or 'left' / 'center' / 'right'."""
        self.setAlignment(self._normalize_alignment(alignment))

    def textAlignment(self):
        return self.alignment()

    def set_text_alignment(self, alignment: Qt.AlignmentFlag | str) -> None:
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

    def _normalize_alignment(self, alignment: Qt.AlignmentFlag | str) -> Qt.AlignmentFlag:
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
        # Direct update(): repaint is deferred by Qt itself; a singleShot(0)
        # kept a live Python wrapper alive past deleteLater and called
        # update() on the freed C++ widget on the next event-loop turn.
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update()

    def _on_theme_changed(self):
        self._apply_theme_style()
        self.update()

    def _apply_theme_style(self):
        text = self.theme_manager.get_color("dialog.text")
        accent = self.theme_manager.get_color("accent")
        # Palette, not stylesheet: any QSS on the widget (even color-only)
        # makes Qt ignore setFont() when painting, which would freeze the
        # text at the design size (UiFont.apply is a no-op visually).
        apply_text_color(self, text)
        palette = QPalette(self.palette())
        palette.setColor(QPalette.ColorRole.Highlight, accent)
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, text)
        self.setPalette(palette)
        self.setAttribute(Qt.WidgetAttribute.WA_SetPalette, True)

    def paintEvent(self, event):
        rect = self.rect()
        radius = scaled_px(self.RADIUS)
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
                        arc_radius=float(self.RADIUS),
                        vertical_offset=0.0,
                    )
                else:
                    underline_config = UnderlineConfig(
                        color=self._underline_color,
                        alpha=60,
                        thickness=self._underline_thickness or 1.0,
                        arc_radius=float(self.RADIUS),
                        vertical_offset=0.0,
                    )

                draw_bottom_underline(painter, rect, self.theme_manager, underline_config)
            finally:
                painter.restore()
                painter.end()
        except Exception:
            pass

CustomLineEdit.inspect_spec = InspectSpec(
    family="CustomLineEdit",
    state=(
        SpecField("text", "text"),
        SpecField("placeholder", "placeholderText"),
        SpecField("alignment", "textAlignment"),
        SpecField("underline_color", "underlineColor"),
        SpecField("underline_thickness", "underlineThickness"),
        SpecField("focused_underline_color", "focusedUnderlineColor"),
        SpecField("focused_underline_thickness", "focusedUnderlineThickness"),
    ),
    token_family=("dialog.input.background", "input.border.thin", "dialog.text", "accent"),
    docs='docs/user/INPUTS_API.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
CustomLineEdit.widget_descriptor = WidgetDescriptor(
    family=CustomLineEdit.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(CustomLineEdit.inspect_spec, 'config', ()),
        state=CustomLineEdit.inspect_spec.state,
        token_family=getattr(CustomLineEdit.inspect_spec, 'token_family', ()),
        regions=getattr(CustomLineEdit.inspect_spec, 'regions', False),
        layers=getattr(CustomLineEdit.inspect_spec, 'layers', False),
        docs=getattr(CustomLineEdit.inspect_spec, 'docs', ''),
    ),
)