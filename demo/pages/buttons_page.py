"""Buttons gallery page — full Button feature showcase."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.buttons.capabilities import ButtonCapability
from sli_ui_toolkit.ui.widgets.buttons.content import ButtonRow
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.painter import default_layers
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style
from sli_ui_toolkit.widgets import (
    Button,
    ButtonGroup,
    InstancesCounterButton,
    entries_from_labeled_data,
    popup_context_menu_for_anchor,
)

from demo.components import ButtonPlaygroundCard, GalleryPage


class WheelCounterCapability(ButtonCapability):
    """Recipe: a wheel-driven value counter, built purely on the public
    ButtonCapability API. The toolkit no longer ships this as a built-in
    Button feature (no more ``scrollable=``/``valueChanged``) — apps that
    want it define their own capability like this one and attach it with
    ``button.attach_capability(...)``.
    """

    def __init__(self, min_value: int, max_value: int, start: int = 0, on_change=None):
        super().__init__()
        self.min_value = min_value
        self.max_value = max_value
        self.value = max(min_value, start)
        self._on_change = on_change
        self._button = None

    def attach(self, button, region_id=None):
        super().attach(button, region_id=region_id)
        self._button = button

    def detach(self, button):
        self._button = None

    def handle_wheel_event(self, event) -> bool:
        delta = event.angleDelta().y()
        if delta == 0:
            return False
        step = 1 if delta > 0 else -1
        new_value = max(self.min_value, min(self.max_value, self.value + step))
        if new_value != self.value:
            self.value = new_value
            if self._on_change is not None:
                self._on_change(new_value)
            if self._button is not None:
                self._button.update()
        event.accept()
        return True


class ValueBelowIconLayer(Layer):
    """Recipe: draws ``capability.value`` under the icon. Value-under-icon
    rendering used to be a built-in Button feature; now it's just a custom
    Layer passed via ``Button(layers=[...])``.
    """

    def __init__(self, capability: WheelCounterCapability):
        self._capability = capability

    def draw(self, ctx, tm) -> None:
        rect = ctx.effective_rect.toAlignedRect()
        style = read_widget_style(ctx.widget)
        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        ctx.painter.setFont(font)
        ctx.painter.setPen(style.foreground_color or QColor(tm.get_color("dialog.text")))
        value_h = 12
        value_y = rect.y() + rect.height() - value_h - 1
        ctx.painter.drawText(
            QRect(rect.x(), value_y, rect.width(), value_h),
            Qt.AlignmentFlag.AlignCenter,
            str(self._capability.value),
        )


MENU_LONG = [
    ("Save", "save"),
    ("Export PDF", "export"),
    ("Очень длинный пункт меню", "long"),
]


def _row(*widgets) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    for w in widgets:
        layout.addWidget(w)
    layout.addStretch()
    return holder


class ButtonsPage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Buttons",
            subtitle="Composable Button widget: варианты, режимы, бейджи, меню и кастомизация.",
            source_file=__file__,
            parent=parent,
        )

        self.add_card(
            title="Interactive Playground",
            widget=ButtonPlaygroundCard(),
            description="Меняйте свойства live и наблюдайте за кнопкой.",
            source_file=__file__,
        )

        self.add_section("Variants")
        default_variant_btn = Button(text="Default", variant="default")
        default_variant_btn.setForegroundColor(QColor("#7f7f7f"))
        self.add_card(
            "Default / Surface / Ghost",
            _row(
                default_variant_btn,
                Button(text="Surface", variant="surface"),
                Button(text="Ghost", variant="ghost"),
            ),
            description="Три variant-токена. subtle/primary удалены — используйте ghost/surface.",
        )

        self.add_section("Modes")
        toggle_btn = Button(text="Toggle Off", toggle=True)
        toggle_btn.toggled.connect(
            lambda v: toggle_btn.setText("Toggle On" if v else "Toggle Off")
        )
        self.add_card("Toggle", toggle_btn, "Бистабильная кнопка.")

        wheel_counter = WheelCounterCapability(min_value=0, max_value=10, start=3)
        scroll_btn = Button(
            icon="line_weight",
            variant="default",
            layers=[*default_layers(), ValueBelowIconLayer(wheel_counter)],
        )
        scroll_btn.attach_capability(wheel_counter)
        self.add_card(
            "Wheel counter (app-level recipe)",
            scroll_btn,
            "Button больше не знает про scroll-counter'ы из коробки. Это "
            "WheelCounterCapability + ValueBelowIconLayer — обе накрафчены "
            "на app-уровне поверх ButtonCapability/Layer API (см. исходник "
            "этой страницы).",
        )

        lp_btn = Button(
            text="Hold me…", long_press=True, long_press_ms=600,
            background_color=QColor("#D93025"),
        )
        lp_btn.longPressed.connect(lambda: lp_btn.setText("Long-pressed!"))
        self.add_card("Long Press", lp_btn, "Удерживайте кнопку 600 мс.")

        wide_menu = Button(text="Actions", variant="surface")
        wide_menu.clicked.connect(
            lambda *, _button=wide_menu: popup_context_menu_for_anchor(
                _button.window(),
                _button,
                entries_from_labeled_data(MENU_LONG, checkable=False),
            )
        )
        self.add_card(
            "Button menu",
            wide_menu,
            "Клик открывает ContextMenu; ширина подстраивается под самый длинный пункт.",
        )

        self.add_section("Badges")
        b2 = Button(text="Updates", variant="surface")
        b2.setBadge(12)
        b2.setBadgeStyle(filled=False, bordered=True)
        self.add_card("Badge: bordered, transparent", b2)

        b3 = Button(text="Custom fill", variant="surface")
        b3.setBadge(99)
        b3.setBadgeStyle(
            filled=True, bordered=True,
            background_color=QColor("#D93025"),
            border_color=QColor("#8C1D18"),
            text_color=QColor("#ffffff"),
        )
        self.add_card("Badge: custom fill + border + text", b3)

        self.add_section("Layout & decoration")
        footer_btn = Button(text="Footer", variant="surface")
        footer_btn.set_footer_mode(True)
        self.add_card(
            "Footer mode",
            footer_btn,
            "Кнопка в режиме нижней панели.",
        )

        custom_bg_btn = Button(text="Custom", variant="default",
                               background_color=QColor(76, 175, 80, 160))
        custom_bg_btn.setForegroundColor(QColor("#7f7f7f"))
        self.add_card(
            "Custom background + alpha",
            custom_bg_btn,
            "Произвольный фон через background_color, alpha сохраняется.",
        )

        group_btns = [Button(text=x) for x in ("Compact", "Cozy", "Spacious")]
        bg = ButtonGroup(group_btns, label="View Mode")
        self.add_card("ButtonGroup (radio-style)", bg)

        rows_btn = Button(
            rows=[
                ButtonRow(text="Title", size=12, weight="bold"),
                ButtonRow(text="subtitle", size=10),
            ],
            size=(160, 44),
            variant="surface",
        )
        self.add_card(
            "Multi-row text via `rows=`",
            rows_btn,
            "ButtonRow позволяет задавать строки с разным размером/жирностью/выравниванием.",
        )

        counter = InstancesCounterButton()
        counter.set_count(3)
        counter.set_can_remove(True)
        self.add_card(
            "Button regions: add/remove split",
            counter,
            "Одна Button-капсула с двумя region-зонами, divider и общим painter/ripple.",
        )

        self.add_stretch()
