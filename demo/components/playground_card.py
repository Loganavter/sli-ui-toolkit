"""Interactive Button playground — preview + library controls in a single card."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.widgets import (
    Button,
    CheckBox,
    CustomGroupWidget,
    Label,
    RadioButton,
    Slider,
    SpinBox,
)


MENU_ITEMS = [("Option A", "a"), ("Option B", "b"), ("Long Option C", "c")]


def _radio_row(values: list[str], default: str) -> tuple[QWidget, QButtonGroup, dict[str, RadioButton]]:
    host = QWidget()
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    group = QButtonGroup(host)
    radios: dict[str, RadioButton] = {}
    for v in values:
        rb = RadioButton(v)
        if v == default:
            rb.setChecked(True)
        group.addButton(rb)
        layout.addWidget(rb)
        radios[v] = rb
    layout.addStretch()
    return host, group, radios


class ButtonPlaygroundCard(CustomGroupWidget):
    """All Button knobs in a single composable card."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(title_text="Live Button Playground", parent=parent)

        self._button: Button | None = None
        self._picked_color = QColor("#4CAF50")
        self._picked_color.setAlpha(255)
        self._underline_color = QColor("#808080")
        self._underline_color.setAlpha(255)

        preview_holder = QWidget()
        preview_holder.setMinimumHeight(80)
        self._preview_layout = QHBoxLayout(preview_holder)
        self._preview_layout.setContentsMargins(0, 8, 0, 8)
        self._preview_layout.addStretch()
        self._preview_layout.addStretch()
        self.add_widget(preview_holder)

        self._event_label = Label("No events yet", pixel_size=10)
        self.add_widget(self._event_label)

        variant_host, self._variant_group, self._variant_radios = _radio_row(
            ["default", "surface", "ghost"], "default"
        )
        mode_host, self._mode_group, self._mode_radios = _radio_row(
            ["normal", "toggle", "scrollable", "long press", "menu"], "normal"
        )

        self.width_spin = self._spin(72, 360, 132)
        self.height_spin = self._spin(28, 120, 40)
        self.radius_spin = self._spin(0, 24, 4)
        self.icon_size_spin = self._spin(8, 48, 22)
        self.badge_spin = self._spin(0, 999, 0)
        self.underline_thickness_spin = self._spin(1, 6, 1)
        self.enabled_check = self._check(True)
        self.checked_check = self._check(False)
        self.underline_check = self._check(False)
        self.footer_check = self._check(False)
        self.custom_color_check = self._check(False)

        self.color_pick_btn = Button(text="Pick color", variant="surface", size=(110, 32))
        self.color_pick_btn.clicked.connect(self._pick_color)
        self._color_swatch = Button(text="", variant="default", size=(28, 22))
        self._refresh_swatch()

        self.underline_color_pick_btn = Button(text="Underline color", variant="surface", size=(140, 32))
        self.underline_color_pick_btn.clicked.connect(self._pick_underline_color)
        self._underline_color_swatch = Button(text="", variant="default", size=(28, 22))
        self._refresh_underline_swatch()

        self.alpha_slider = Slider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(0, 255)
        self.alpha_slider.setValue(255)

        color_row_host = QWidget()
        color_row = QHBoxLayout(color_row_host)
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(8)
        color_row.addWidget(self.color_pick_btn)
        color_row.addWidget(self._color_swatch)
        color_row.addSpacing(12)
        color_row.addWidget(self.underline_color_pick_btn)
        color_row.addWidget(self._underline_color_swatch)
        color_row.addStretch()

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        row = 0
        row = self._add_row(grid, row, "Variant", variant_host)
        row = self._add_row(grid, row, "Mode", mode_host)
        row = self._add_row(
            grid,
            row,
            "Geometry",
            self._inline_controls(
                ("W", self.width_spin),
                ("H", self.height_spin),
                ("R", self.radius_spin),
                ("Icon", self.icon_size_spin),
                ("Badge", self.badge_spin),
                ("Line", self.underline_thickness_spin),
            ),
        )
        row = self._add_row(
            grid,
            row,
            "State",
            self._inline_controls(
                ("Enabled", self.enabled_check),
                ("Checked", self.checked_check),
                ("Underline", self.underline_check),
                ("Footer", self.footer_check),
                ("Custom bg", self.custom_color_check),
            ),
        )
        row = self._add_row(grid, row, "Color", color_row_host)
        row = self._add_row(grid, row, "Alpha", self.alpha_slider)
        self.add_widget(grid_host)

        self._connect()
        self._rebuild()

    # ---------- helpers ----------

    def _spin(self, lo: int, hi: int, val: int) -> SpinBox:
        s = SpinBox(default_value=val, underline_color=QColor("#808080"))
        s.setRange(lo, hi)
        return s

    def _check(self, checked: bool) -> CheckBox:
        c = CheckBox()
        c.setChecked(checked)
        return c

    def _inline_controls(self, *items: tuple[str, QWidget]) -> QWidget:
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for label, widget in items:
            if isinstance(widget, CheckBox):
                widget.setText(label)
            else:
                layout.addWidget(Label(label, pixel_size=10))
            layout.addWidget(widget)
            layout.addSpacing(4)
        layout.addStretch()
        return host

    def _add_row(self, grid: QGridLayout, row: int, label: str, editor) -> int:
        grid.addWidget(Label(label, pixel_size=11), row, 0)
        if isinstance(editor, (QHBoxLayout, QVBoxLayout)):
            grid.addLayout(editor, row, 1)
        else:
            grid.addWidget(editor, row, 1)
        return row + 1

    def _selected(self, radios: dict[str, RadioButton]) -> str:
        for name, rb in radios.items():
            if rb.isChecked():
                return name
        return next(iter(radios))

    def _variant(self) -> str:
        return self._selected(self._variant_radios)

    def _mode(self) -> str:
        return self._selected(self._mode_radios)

    def _refresh_swatch(self) -> None:
        self._color_swatch.set_background_color(QColor(self._picked_color))

    def _refresh_underline_swatch(self) -> None:
        self._underline_color_swatch.set_background_color(QColor(self._underline_color))

    def _pick_color(self) -> None:
        chosen = QColorDialog.getColor(
            self._picked_color, self, "Pick button color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if chosen.isValid():
            self._picked_color = chosen
            self.alpha_slider.setValue(chosen.alpha())
            self._refresh_swatch()
            if not self.custom_color_check.isChecked():
                self.custom_color_check.setChecked(True)
            self._apply()

    def _pick_underline_color(self) -> None:
        chosen = QColorDialog.getColor(
            self._underline_color, self, "Pick underline color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if chosen.isValid():
            self._underline_color = chosen
            self._refresh_underline_swatch()
            if not self.underline_check.isChecked():
                self.underline_check.setChecked(True)
            self._apply()

    def _connect(self) -> None:
        self._variant_group.buttonToggled.connect(lambda *_: self._rebuild())
        self._mode_group.buttonToggled.connect(lambda *_: self._rebuild())
        for spin in (self.width_spin, self.height_spin, self.radius_spin,
                     self.icon_size_spin, self.badge_spin,
                     self.underline_thickness_spin):
            spin.valueChanged.connect(self._apply)
        for chk in (self.enabled_check, self.checked_check, self.underline_check,
                    self.footer_check, self.custom_color_check):
            chk.toggled.connect(self._apply)
        self.alpha_slider.valueChanged.connect(self._on_alpha)

    def _on_alpha(self, val: int) -> None:
        self._picked_color.setAlpha(int(val))
        self._refresh_swatch()
        self._apply()

    def _bg_color(self) -> QColor | None:
        if not self.custom_color_check.isChecked():
            return None
        c = QColor(self._picked_color)
        c.setAlpha(self.alpha_slider.value())
        return c

    def _text(self) -> str:
        return "Menu" if self._mode() == "menu" else "Preview"

    def _rebuild(self, *args) -> None:
        if self._button is not None:
            self._preview_layout.removeWidget(self._button)
            self._button.deleteLater()
            self._button = None

        mode = self._mode()
        kwargs = {
            "icon": "settings",
            "text": self._text(),
            "variant": self._variant(),
            "size": (self.width_spin.value(), self.height_spin.value()),
            "corner_radius": self.radius_spin.value(),
            "icon_size": self.icon_size_spin.value(),
            "show_underline": self.underline_check.isChecked(),
            "background_color": self._bg_color(),
        }
        if mode == "toggle":
            kwargs["toggle"] = True
        elif mode == "scrollable":
            kwargs["scrollable"] = (0, 100)
        elif mode == "long press":
            kwargs["long_press"] = True
        elif mode == "menu":
            kwargs["menu"] = MENU_ITEMS

        self._button = Button(**kwargs)
        self._button.clicked.connect(lambda: self._set_event("clicked"))
        self._button.toggled.connect(lambda checked: self._set_event(f"toggled: {checked}"))
        self._button.valueChanged.connect(lambda v: self._set_event(f"value: {v}"))
        self._button.longPressed.connect(lambda: self._set_event("long pressed"))
        self._button.menuTriggered.connect(lambda v: self._set_event(f"menu: {v}"))
        self._preview_layout.insertWidget(1, self._button, 0, Qt.AlignmentFlag.AlignCenter)
        self._apply()

    def _apply(self, *args) -> None:
        if self._button is None:
            return
        self._button.setVariant(self._variant())
        self._button.setFixedSize(self.width_spin.value(), self.height_spin.value())
        self._button.setCornerRadiusPx(self.radius_spin.value())
        self._button.setIconSizePx(self.icon_size_spin.value())
        badge = self.badge_spin.value()
        self._button.setBadge(badge if badge > 0 else None)
        self._button.setEnabled(self.enabled_check.isChecked())
        self.underline_check.setEnabled(True)
        self._button.setShowUnderline(self.underline_check.isChecked())
        self._button.setUnderlineColor(
            QColor(self._underline_color) if self.underline_check.isChecked() else None
        )
        self._button.setUnderlineThickness(self.underline_thickness_spin.value())
        self._button.set_footer_mode(self.footer_check.isChecked())
        self._button.set_background_color(self._bg_color())

        if self._mode() == "toggle":
            self._button.setChecked(self.checked_check.isChecked(), emit=False)
            self.checked_check.setEnabled(True)
        else:
            self.checked_check.setEnabled(False)

        self._button.updateGeometry()
        self._button.update()

    def _set_event(self, text: str) -> None:
        self._event_label.setText(text)
