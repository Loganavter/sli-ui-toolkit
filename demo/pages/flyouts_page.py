"""Flyouts page — overlay menus triggered by buttons."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import (
    BaseFlyout,
    Button,
    IconAction,
    IconActionFlyout,
    IndexedToggleFlyout,
    Label,
    ScrollableComboBox,
    SimpleOptionsFlyout,
    Slider,
    Switch,
    UnifiedFlyout,
    UnifiedFlyoutItem,
)

from demo.components import GalleryPage


def _trigger(text: str, on_click) -> Button:
    btn = Button(text=text, variant="surface")
    btn.clicked.connect(lambda: on_click(btn))
    return btn


class _FontFlyout(BaseFlyout):
    """Example of composing a multi-control flyout with BaseFlyout's builder API."""

    settings_changed = pyqtSignal(int, int, QColor, QColor, bool, str, int)

    def __init__(self, parent_widget: QWidget) -> None:
        super().__init__(parent_widget)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setSpacing(8)

        self.size_slider = self._slider(50, 400, 100)
        self.weight_slider = self._slider(0, 100, 50)
        self.opacity_slider = self._slider(5, 100, 100)
        self.color_swatch = self.make_color_swatch(QColor("#ffffff"))
        self.bg_color_swatch = self.make_color_swatch(QColor("#000000"))
        self.draw_bg_switch = Switch()

        self.add_row("Font size", self.size_slider)
        self.add_row("Bold", self.weight_slider)
        self.add_row("Opacity", self.opacity_slider)
        self.add_row("Color", self.color_swatch)
        self.add_row("Background", self.bg_color_swatch)
        self.add_row("Draw text background", self.draw_bg_switch)
        _, self._pos_group, self._pos_radios = self.add_radio_row(
            "Text position",
            [("At edges", "edges"), ("Near split line", "split_line")],
            default="edges",
        )

        for sl in (self.size_slider, self.weight_slider, self.opacity_slider):
            sl.valueChanged.connect(self._emit)
        self.color_swatch.colorChanged.connect(lambda *_: self._emit())
        self.bg_color_swatch.colorChanged.connect(lambda *_: self._emit())
        self.draw_bg_switch.checkedChanged.connect(self._emit)
        for rb in self._pos_radios.values():
            rb.toggled.connect(lambda *_: self._emit())

        self.hide()

    @staticmethod
    def _slider(lo: int, hi: int, val: int) -> Slider:
        s = Slider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        s.setMinimumWidth(160)
        return s

    def _placement(self) -> str:
        for value, rb in self._pos_radios.items():
            if rb.isChecked():
                return value
        return "edges"

    def _emit(self, *_) -> None:
        self.settings_changed.emit(
            self.size_slider.value(),
            self.weight_slider.value(),
            self.color_swatch.color(),
            self.bg_color_swatch.color(),
            self.draw_bg_switch.isChecked(),
            self._placement(),
            self.opacity_slider.value(),
        )


class _HoverTriggerButton(Button):
    def __init__(
        self,
        text: str,
        on_hover,
        on_leave=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text=text, variant="surface", parent=parent)
        self._on_hover = on_hover
        self._on_leave = on_leave

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._on_hover(self)

    def leaveEvent(self, event) -> None:
        if self._on_leave is not None:
            self._on_leave()
        super().leaveEvent(event)


class FlyoutsPage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Flyouts",
            subtitle="Всплывающие меню, привязанные к якорному виджету.",
            source_file=__file__,
            parent=parent,
        )

        self._action_flyout: IconActionFlyout | None = None
        self._indexed_flyout: IndexedToggleFlyout | None = None
        self._simple_flyout: SimpleOptionsFlyout | None = None
        self._font_flyout: _FontFlyout | None = None
        self._simple_options = ["Light", "Dark", "Use system setting"]
        self._simple_current_index = 0

        self._action_status = Label("Click an action in the flyout...", pixel_size=11)
        action_holder = QWidget()
        ch = QVBoxLayout(action_holder)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(6)
        ch.addWidget(_trigger("Open icon action flyout", self._show_actions))
        ch.addWidget(self._action_status)
        self.add_card(
            "IconActionFlyout",
            action_holder,
            "Единый горизонтальный flyout для кастомных icon-actions.",
        )

        self.add_card(
            "IndexedToggleFlyout",
            _HoverTriggerButton(
                "Hover indexed flyout",
                self._show_indexed,
                self._schedule_indexed_hide,
            ),
            "Слоты 1..N с переключаемым активным индексом и бейджами; открывается по наведению сверху.",
        )

        self._simple_button = Button(
            text=self._simple_options[self._simple_current_index],
            variant="surface",
        )
        self._simple_button.clicked.connect(lambda: self._show_simple(self._simple_button))
        self.add_card(
            "SimpleOptionsFlyout",
            self._simple_button,
            "Простой список текстовых опций с подсвеченным текущим.",
        )

        font_holder = QWidget()
        font_layout = QVBoxLayout(font_holder)
        font_layout.setContentsMargins(0, 0, 0, 0)
        font_layout.setSpacing(6)
        font_button = Button(text="Open text settings flyout", variant="surface")
        font_button.clicked.connect(lambda: self._show_font_settings(font_button))
        self._font_status = Label("Size 100, weight 50, opacity 100", pixel_size=11)
        self._font_status.setWordWrap(True)
        self._font_status.setMaximumWidth(320)
        font_layout.addWidget(font_button)
        font_layout.addWidget(self._font_status)
        self.add_card(
            "Font settings flyout (built via BaseFlyout)",
            font_holder,
            "Пример: размер, жирность, opacity, color swatches, background и позиция — "
            "целиком собрано через add_row/add_radio_row/make_color_swatch.",
        )

        unified_holder = QWidget()
        ul = QVBoxLayout(unified_holder)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.setSpacing(6)
        anchors_row = QWidget()
        anchors_layout = QHBoxLayout(anchors_row)
        anchors_layout.setContentsMargins(0, 0, 0, 0)
        anchors_layout.setSpacing(8)
        self._unified_anchor_left = ScrollableComboBox()
        self._unified_anchor_right = ScrollableComboBox()
        self._unified_anchor_left.setFixedWidth(220)
        self._unified_anchor_right.setFixedWidth(220)
        left_items_text = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        right_items_text = ["One", "Two", "Three", "Four"]
        self._unified_anchor_left.updateState(
            count=len(left_items_text), current_index=0,
            text=left_items_text[0], items=left_items_text,
        )
        self._unified_anchor_right.updateState(
            count=len(right_items_text), current_index=0,
            text=right_items_text[0], items=right_items_text,
        )
        anchors_layout.addWidget(self._unified_anchor_left)
        anchors_layout.addWidget(self._unified_anchor_right)
        anchors_layout.addStretch()
        ul.addWidget(anchors_row)

        self._unified_flyout: UnifiedFlyout | None = None
        self._unified_left_items = [UnifiedFlyoutItem(t) for t in left_items_text]
        self._unified_right_items = [UnifiedFlyoutItem(t) for t in right_items_text]
        self._unified_anchor_left.clicked.connect(lambda: self._open_unified_single(1))
        self._unified_anchor_right.clicked.connect(lambda: self._open_unified_single(2))
        self._unified_status = Label("Кликните по любой кнопке списка.", pixel_size=11)
        ul.addWidget(self._unified_status)
        self.add_card(
            "UnifiedFlyout (double list)",
            unified_holder,
            "Две горизонтальные кнопки-якоря открывают соответствующий список.",
        )

        self.add_stretch()

    def _show_simple(self, anchor: Button) -> None:
        if self._simple_flyout is None:
            self._simple_flyout = SimpleOptionsFlyout(parent_widget=self.window())
            self._simple_flyout.item_chosen.connect(self._on_simple_option_chosen)
        self._simple_flyout.populate(
            self._simple_options,
            current_index=self._simple_current_index,
        )
        try:
            self._simple_flyout.show_below(anchor)
        except Exception:
            self._simple_flyout.show()

    def _on_simple_option_chosen(self, index: int) -> None:
        if not 0 <= index < len(self._simple_options):
            return
        self._simple_current_index = index
        self._simple_button.setText(self._simple_options[index])

    def _show_actions(self, anchor: Button) -> None:
        if self._action_flyout is None:
            actions = [
                IconAction(action_id="add", icon="add", tooltip="Add"),
                IconAction(action_id="edit", icon="edit", tooltip="Edit"),
                IconAction(action_id="save", icon="save", tooltip="Save"),
                IconAction(action_id="delete", icon="delete", tooltip="Delete"),
            ]
            self._action_flyout = IconActionFlyout(
                parent=self.window(),
                actions=actions,
            )
            self._action_flyout.actionTriggered.connect(
                lambda action_id: self._action_status.setText(f"Last action: {action_id}")
            )
        try:
            self._action_flyout.show_aligned(
                anchor, "bottom-center", "top-center", offset=8
            )
        except Exception:
            self._action_flyout.show()

    def _show_font_settings(self, anchor: Button) -> None:
        if self._font_flyout is None:
            self._font_flyout = _FontFlyout(self.window())
            self._font_flyout.settings_changed.connect(self._on_font_settings_changed)
        if self._font_flyout.isVisible():
            self._font_flyout.hide()
            return
        self._font_flyout.show_aligned(
            anchor,
            anchor_point="top-right",
            flyout_point="bottom-left",
            offset=10,
            animation="slide",
        )

    def _on_font_settings_changed(
        self,
        size: int,
        weight: int,
        color: QColor,
        bg_color: QColor,
        draw_bg: bool,
        placement: str,
        opacity: int,
    ) -> None:
        self._font_status.setText(
            f"Size {size}, weight {weight}, opacity {opacity}, text {color.name()}, bg {bg_color.name()}, {placement}, bg={'on' if draw_bg else 'off'}"
        )

    def _show_indexed(self, anchor: Button) -> None:
        if self._indexed_flyout is None:
            self._indexed_flyout = IndexedToggleFlyout(
                parent_widget=self.window(),
                slot_count=4,
                slot_icon="check",
            )
        self._indexed_flyout.cancel_auto_hide()
        try:
            self._indexed_flyout.show_for_button(anchor)
        except Exception:
            self._indexed_flyout.show()

    def _schedule_indexed_hide(self) -> None:
        if self._indexed_flyout is not None:
            self._indexed_flyout.schedule_auto_hide(250)

    def _ensure_unified_flyout(self) -> UnifiedFlyout:
        if self._unified_flyout is None:
            self._unified_flyout = UnifiedFlyout.create_double_list(
                self.window(),
                self._unified_anchor_left,
                self._unified_anchor_right,
                left_items=self._unified_left_items,
                right_items=self._unified_right_items,
                current_left=self._unified_anchor_left.currentIndex(),
                current_right=self._unified_anchor_right.currentIndex(),
            )
            self._unified_flyout.item_chosen.connect(self._on_unified_chosen)
        return self._unified_flyout

    def _open_unified_single(self, list_num: int) -> None:
        flyout = self._ensure_unified_flyout()
        anchor = (
            self._unified_anchor_left if list_num == 1 else self._unified_anchor_right
        )
        flyout.showAsSingle(list_num, anchor)

    def _on_unified_chosen(self, list_num: int, index: int) -> None:
        anchor = (
            self._unified_anchor_left if list_num == 1 else self._unified_anchor_right
        )
        items = self._unified_left_items if list_num == 1 else self._unified_right_items
        if 0 <= index < len(items):
            anchor.setCurrentIndex(index)
            self._unified_status.setText(
                f"Список {list_num}: выбран '{items[index].display_name}'"
            )
