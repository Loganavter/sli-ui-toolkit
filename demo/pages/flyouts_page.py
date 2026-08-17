"""Flyouts page — overlay menus triggered by buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import (
    BaseFlyout,
    Button,
    IconAction,
    IconActionFlyout,
    IndexedToggleFlyout,
    Label,
    ListPanel,
    ListRowSpec,
    ScrollableComboBox,
    SimpleOptionsFlyout,
    Slider,
    Switch,
)

from demo.components import GalleryPage
from demo.components.color_swatch import ColorSwatch


class _DemoRow(Button):
    """Minimal host-built ListPanel row (the assembly-pattern example)."""

    itemSelected = Signal(int)

    def __init__(self, spec: ListRowSpec):
        super().__init__(text="", size=(0, spec.item_height), parent=None)
        self.index = spec.index
        self.full_path = spec.full_path or ""
        self.is_current = spec.is_current
        self.position = spec.position
        self.is_selected = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        self.name_label = Label(spec.text)
        layout.addWidget(self.name_label)
        self.clicked.connect(lambda: self.itemSelected.emit(self.index))

    def set_selected(self, selected: bool) -> None:
        self.is_selected = bool(selected)
        self.update()

    def set_dragging_state(self, dragging: bool) -> None:
        pass


def _demo_row_factory(spec: ListRowSpec) -> _DemoRow:
    return _DemoRow(spec)


class _ListPanelPopup(BaseFlyout):
    """Tiny popup shell hosting one ListPanel — the picker assembly example."""

    item_chosen = Signal(int)

    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.panel = ListPanel(
            list_num=1,
            item_height=34,
            item_font=None,
            get_current_index=lambda list_num: 0,
            on_item_selected=lambda list_num, index: self.item_chosen.emit(index),
            on_item_context_menu=lambda *args, **kwargs: None,
            on_reorder=lambda *args, **kwargs: None,
            on_move_between_lists=lambda *args, **kwargs: None,
            on_update_drop_indicator=lambda pos: None,
            on_clear_drop_indicator=lambda: None,
        )
        self.content_layout.addWidget(self.panel)


def _trigger(text: str, on_click) -> Button:
    btn = Button(text=text, variant="surface")
    btn.clicked.connect(lambda: on_click(btn))
    return btn


class _FontFlyout(BaseFlyout):
    """Example of composing a multi-control flyout with BaseFlyout's builder API."""

    settings_changed = Signal(int, int, QColor, QColor, bool, str, int)

    def __init__(self, parent_widget: QWidget) -> None:
        super().__init__(parent_widget)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setSpacing(8)

        self.size_slider = self._slider(50, 400, 100)
        self.weight_slider = self._slider(0, 100, 50)
        self.opacity_slider = self._slider(5, 100, 100)
        self.color_swatch = ColorSwatch(QColor("#ffffff"), parent=self)
        self.bg_color_swatch = ColorSwatch(QColor("#000000"), parent=self)
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
            "целиком собрано через add_row/add_radio_row.",
        )

        # --- ListPanel: example of assembling a list picker from library
        # widgets: a generic ListPanel + a host-built row + BaseFlyout shell.
        list_holder = QWidget()
        ll = QVBoxLayout(list_holder)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        self._list_popup = None
        self._list_anchor = ScrollableComboBox()
        self._list_anchor.setFixedWidth(220)
        list_items_text = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        self._list_anchor.updateState(
            count=len(list_items_text), current_index=0,
            text=list_items_text[0], items=list_items_text,
        )
        self._list_anchor.clicked.connect(self._open_list_panel)
        ll.addWidget(self._list_anchor)
        self._list_status = Label("Кликните по кнопке списка.", pixel_size=11)
        ll.addWidget(self._list_status)
        self.add_card(
            "ListPanel (assembled picker)",
            list_holder,
            "Пример сборки из примитивов: generic ListPanel + собственная строка "
            "(row factory) + BaseFlyout как оболочка поп-апа.",
        )

        self.add_stretch()

    # -------- ListPanel example (assembly pattern) --------

    def _open_list_panel(self) -> None:
        popup = self._ensure_list_popup()
        if popup.isVisible():
            popup.hide()
            return
        popup.show_aligned(
            self._list_anchor,
            anchor_point="bottom-center",
            flyout_point="top-center",
            offset=6,
        )

    def _ensure_list_popup(self) -> "_ListPanelPopup":
        if self._list_popup is None:
            self._list_popup = _ListPanelPopup(self.window())
            self._list_popup.panel.set_row_factory(_demo_row_factory)
            self._list_popup.item_chosen.connect(self._on_list_item_chosen)
            self._list_popup.panel.clear_and_rebuild(
                [type("_I", (), {"display_name": n})() for n in
                 ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]],
                item_height=34,
                item_font=None,
                list_type="default",
                current_index=0,
            )
        return self._list_popup

    def _on_list_item_chosen(self, index: int) -> None:
        names = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        if 0 <= index < len(names):
            self._list_anchor.setCurrentIndex(index)
            self._list_status.setText(f"Выбран '{names[index]}'")

    def _show_simple(self, anchor: Button) -> None:
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
