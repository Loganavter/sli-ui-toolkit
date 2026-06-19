"""Buttons gallery page — full Button feature showcase."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.buttons.content import ButtonRow
from sli_ui_toolkit.widgets import (
    Button,
    ButtonGroup,
    InstancesCounterButton,
)

from demo.components import ButtonPlaygroundCard, GalleryPage


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

        scroll_btn = Button(icon="line_weight", scrollable=(0, 10), variant="default")
        scroll_btn.setValue(3)
        self.add_card(
            "Scrollable (icon + auto value chip)",
            scroll_btn,
            "Прокрутите колесом мыши — значение отрисовывается под иконкой "
            "автоматически (icon + value chip).",
        )

        scroll_toggle_btn = Button(
            icon="line_weight", toggle=True, scrollable=(0, 10), variant="default"
        )
        scroll_toggle_btn.setValue(0)
        self.add_card(
            "Scrollable + Toggle (count=0 → 'off' popup)",
            scroll_toggle_btn,
            "При значении 0 popup сверху показывает иконку divider_hidden "
            "(или текст 'off', если иконка не настроена).",
        )

        lp_btn = Button(
            text="Hold me…", long_press=True, long_press_ms=600,
            background_color=QColor("#D93025"),
        )
        lp_btn.longPressed.connect(lambda: lp_btn.setText("Long-pressed!"))
        self.add_card("Long Press", lp_btn, "Удерживайте кнопку 600 мс.")

        wide_menu = Button(text="Actions", menu=MENU_LONG, variant="surface")
        self.add_card(
            "Button menu",
            wide_menu,
            "Dropdown не уже кнопки и расширяется под самый длинный пункт.",
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
