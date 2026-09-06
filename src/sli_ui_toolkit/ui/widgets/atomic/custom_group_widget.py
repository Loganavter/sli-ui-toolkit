from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from typing import Literal

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import paint_font, ui_font
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px

CaptionStyle = Literal["top", "bottom"]
CornerRadii = tuple[int, int, int, int]


def _normalize_corner_radii(
    corner_radius: int | None,
    corner_radii: CornerRadii | None,
    fallback: int = 0,
) -> CornerRadii:
    if corner_radii is not None:
        tl, tr, br, bl = corner_radii
        return (int(tl), int(tr), int(br), int(bl))
    base = int(corner_radius) if corner_radius is not None else fallback
    return (base, base, base, base)


def _rounded_rect_path(rect: QRectF, radii: CornerRadii) -> QPainterPath:
    """Rectangle path with independent per-corner radii, clockwise from
    top-left. Local copy of ``buttons.layers.background.rounded_rect_path``
    — duplicated rather than imported to keep this module import-cycle-free
    from ``buttons`` (which itself re-exports ``ButtonGroup`` from here)."""
    max_r = min(rect.width(), rect.height()) / 2.0
    tl, tr, br, bl = (min(max(0, float(r)), max_r) for r in radii)
    path = QPainterPath()
    path.moveTo(rect.left() + tl, rect.top())
    path.lineTo(rect.right() - tr, rect.top())
    if tr > 0:
        path.arcTo(rect.right() - 2 * tr, rect.top(), 2 * tr, 2 * tr, 90.0, -90.0)
    path.lineTo(rect.right(), rect.bottom() - br)
    if br > 0:
        path.arcTo(rect.right() - 2 * br, rect.bottom() - 2 * br, 2 * br, 2 * br, 0.0, -90.0)
    path.lineTo(rect.left() + bl, rect.bottom())
    if bl > 0:
        path.arcTo(rect.left(), rect.bottom() - 2 * bl, 2 * bl, 2 * bl, 270.0, -90.0)
    path.lineTo(rect.left(), rect.top() + tl)
    if tl > 0:
        path.arcTo(rect.left(), rect.top(), 2 * tl, 2 * tl, 180.0, -90.0)
    path.closeSubpath()
    return path


class CustomGroupWidget(QWidget):
    """Draws a border + caption around arbitrary content — the one "group"
    widget for both jobs previously split across two classes:

    - ``caption="top"`` (default): caption at top-left, straddling the top
      border (a fieldset legend). Content grows vertically, sized to fit
      (``Preferred``/``Fixed``) — settings pages, dialogs.
    - ``caption="bottom"``: caption centered at the bottom, straddling the
      bottom border (was the standalone ``ButtonGroup``). Content is a
      horizontal row, shrink-to-fit (``Fixed``/``Fixed``) — toolbar button
      clusters. ``set_corner_radii()`` supports squaring off corners so the
      border can dock flush with a panel shown directly below (see
      ``tabs/image_compare/ui/magnifier_settings_flyout.py``, which mirrors
      this exact paint routine to read as one seamless capsule with it).

    Either style accepts any toolkit control via ``add_widget``/``add_layout``
    — the caption is purely cosmetic, never restricted to a particular
    content type (unlike the old ``ButtonGroup``, which only took a flat
    list of buttons at construction).
    """

    def __init__(
        self,
        title_text: str = "",
        parent=None,
        *,
        caption: CaptionStyle = "top",
        orientation: Qt.Orientation = Qt.Orientation.Vertical,
        fixed_size: bool = False,
        border_radius: int = 8,
        corner_radii: CornerRadii | None = None,
    ):
        super().__init__(parent)
        self._title_text = title_text
        self._caption: CaptionStyle = caption
        self._border_width = 1
        self._title_left_padding = 12
        self._corner_radii: CornerRadii = _normalize_corner_radii(
            border_radius, corner_radii, fallback=8
        )

        if fixed_size:
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self._content_layout = (
            QHBoxLayout(self) if orientation == Qt.Orientation.Horizontal else QVBoxLayout(self)
        )
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)
        UiScale.get_instance().scale_changed.connect(self.on_scale_changed)
        self._apply_layout_metrics()

    def on_scale_changed(self, _factor: float) -> None:
        self._apply_layout_metrics()
        self.updateGeometry()
        self.update()

    def _get_title_metrics(self):
        if not self._title_text:
            return 0, 0
        font = paint_font(self, bold=True)
        fm = QFontMetrics(font)
        return fm.horizontalAdvance(self._title_text), fm.height()

    def set_title(self, title: str):
        if self._title_text != title:
            self._title_text = title
            self._apply_layout_metrics()
            self.updateGeometry()
            self.update()

    def get_title(self):
        return self._title_text

    # Back-compat aliases (ButtonGroup's names).
    def set_label(self, text: str):
        self.set_title(text)

    set_label_text = set_label

    def label(self) -> str:
        return self.get_title()

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
        resolved = _normalize_corner_radii(border_radius, corner_radii, fallback=8)
        if resolved != self._corner_radii:
            self._corner_radii = resolved
            self.update()

    def corner_radii(self) -> CornerRadii:
        return self._corner_radii

    def _apply_layout_metrics(self) -> None:
        if self._caption == "bottom":
            self._content_layout.setContentsMargins(
                scaled_px(10), scaled_px(8), scaled_px(10), scaled_px(18)
            )
            self._content_layout.setSpacing(scaled_px(2))
        else:
            _, title_h = self._get_title_metrics()
            top_margin = int(title_h * 0.8) + 12
            self._content_layout.setContentsMargins(12, top_margin, 12, 12)
            self._content_layout.setSpacing(8)

    def add_widget(self, widget):
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        self._content_layout.addLayout(layout)

    def sizeHint(self) -> QSize:
        content_size = self._content_layout.sizeHint()
        if self._caption == "bottom":
            return content_size
        title_w, _title_h = self._get_title_metrics()
        title_full_width = self._title_left_padding + title_w + 30
        final_w = max(content_size.width(), title_full_width)
        return QSize(final_w, content_size.height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._caption == "bottom":
            self._paint_bottom_caption(painter)
        else:
            self._paint_top_caption(painter)

    def _paint_top_caption(self, painter: QPainter) -> None:
        border_color = self.theme_manager.get_color("dialog.border")
        pen = QPen(border_color, self._border_width)
        painter.setPen(pen)

        rect = self.rect()
        title_w, title_h = self._get_title_metrics()
        top_y = int(title_h / 2)

        border_rect = QRectF(0, top_y, rect.width() - 1, rect.height() - top_y - 1)
        radii = self._corner_radii
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(_rounded_rect_path(border_rect, radii))

        if self._title_text:
            text_x_start = self._title_left_padding
            text_padding = 4
            clear_rect = QRect(text_x_start, 0, title_w + (text_padding * 2), title_h)
            bg_color = self.theme_manager.get_color("surface.background")
            painter.fillRect(clear_rect, bg_color)

            font = paint_font(self, bold=True)
            painter.setFont(font)

            text_color = self.theme_manager.get_color("dialog.text")
            painter.setPen(text_color)

            draw_rect = QRect(text_x_start + text_padding, 0, title_w, title_h)
            painter.drawText(
                draw_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._title_text,
            )

    def _paint_bottom_caption(self, painter: QPainter) -> None:
        """Verbatim port of the old ``ButtonGroup.paintEvent`` — geometry
        must stay pixel-identical, ``magnifier_settings_flyout.py`` mirrors
        this exact routine to dock flush underneath a group using it."""
        border_color = self.theme_manager.get_color("dialog.border")
        bg_color = self.theme_manager.get_color("Window")
        text_color = self.theme_manager.get_color("WindowText")

        rect = self.rect()
        factor = UiScale.get_instance().factor()
        font = ui_font(point_size=max(8, ui_font().pointSizeF() / factor - 2))
        painter.setFont(font)
        fm = QFontMetrics(font)
        label_height = fm.height() if self._title_text else 0

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
        tl, tr, br, bl = self._corner_radii
        radii: CornerRadii = (
            0 if tl == 0 else scaled_px(tl),
            0 if tr == 0 else scaled_px(tr),
            0 if br == 0 else scaled_px(br),
            0 if bl == 0 else scaled_px(bl),
        )
        painter.drawPath(_rounded_rect_path(QRectF(draw_rect), radii))
        painter.translate(-0.5, -0.5)

        if self._title_text:
            label_padding = scaled_px(3)
            center_x = rect.width() // 2
            label_w = fm.horizontalAdvance(self._title_text)
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
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._title_text)


class ButtonGroup(CustomGroupWidget):
    """Back-compat wrapper for the old standalone ``ButtonGroup`` class —
    a bottom-caption, fixed-size, horizontal :class:`CustomGroupWidget`.
    Kept as a real subclass (not a factory function) so existing
    ``-> ButtonGroup`` annotations and ``isinstance`` checks keep working.
    Prefer constructing :class:`CustomGroupWidget` directly in new code.
    """

    def __init__(
        self,
        buttons: list,
        label: str = "",
        parent=None,
        *,
        border_radius: int = 8,
        corner_radii: CornerRadii | None = None,
    ):
        super().__init__(
            label,
            parent,
            caption="bottom",
            orientation=Qt.Orientation.Horizontal,
            fixed_size=True,
            border_radius=border_radius,
            corner_radii=corner_radii,
        )
        for button in buttons:
            self.add_widget(button)


class CustomGroupBuilder:
    """Convenience builder.

    Two equivalent APIs:
    - ``CustomGroupBuilder.create_styled_group(title)`` → ``(group, layout, title_widget)``
      for callers that want raw access to the inner layout.
    - ``builder = CustomGroupBuilder(); builder.add(w); builder.build(title=…)`` →
      ``CustomGroupWidget`` with all queued widgets/layouts already inserted.
    """

    def __init__(self) -> None:
        self._pending: list[tuple[str, object]] = []

    def add(self, widget):
        self._pending.append(("widget", widget))
        return self

    def add_layout(self, layout):
        self._pending.append(("layout", layout))
        return self

    def build(self, title: str = "") -> CustomGroupWidget:
        group = CustomGroupWidget(title)
        for kind, item in self._pending:
            if kind == "widget":
                group.add_widget(item)
            else:
                group.add_layout(item)
        self._pending.clear()
        return group

    @staticmethod
    def create_styled_group(title_text: str):
        group_widget = CustomGroupWidget(title_text)
        content_layout = group_widget._content_layout

        class TitleWidget:
            def __init__(self, group_widget):
                self._group = group_widget

            def setText(self, text):
                self._group.set_title(text)

            def text(self):
                return self._group.get_title()

        title_widget = TitleWidget(group_widget)
        return group_widget, content_layout, title_widget

CustomGroupWidget.inspect_spec = InspectSpec(
    family="CustomGroupWidget",
    state=(
        SpecField("title", "get_title"),
        SpecField("children", "children"),
    ),
    token_family=("dialog.border", "surface.background", "dialog.text"),
    docs='docs/user/INPUTS_API.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
CustomGroupWidget.widget_descriptor = WidgetDescriptor(
    family=CustomGroupWidget.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(CustomGroupWidget.inspect_spec, 'config', ()),
        state=CustomGroupWidget.inspect_spec.state,
        token_family=getattr(CustomGroupWidget.inspect_spec, 'token_family', ()),
        regions=getattr(CustomGroupWidget.inspect_spec, 'regions', False),
        layers=getattr(CustomGroupWidget.inspect_spec, 'layers', False),
        docs=getattr(CustomGroupWidget.inspect_spec, 'docs', ''),
    ),
)
