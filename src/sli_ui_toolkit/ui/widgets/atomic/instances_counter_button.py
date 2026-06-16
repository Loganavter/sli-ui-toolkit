"""InstancesCounterButton — segmented add/remove counter built on Button regions."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QWheelEvent
from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.buttons import (
    Button,
    ButtonSpec,
    ContentSpec,
    Divider,
    RegionSpec,
    RegionStyle,
    ShapeSpec,
    VerticalSplit,
)


class InstancesCounterButton(Button):
    addClicked = pyqtSignal()
    removeClicked = pyqtSignal()
    wheelScrolled = pyqtSignal(int)
    countChanged = pyqtSignal(int)

    _OUTER_SIZE = 36
    _CORNER_RADIUS = 6

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        wheel_requires_focus: bool = False,
    ) -> None:
        self._count = 1
        self._can_remove = False
        self._counter_divider = Divider(
            color_token="separator.color",
            fallback_token="dialog.border",
            thickness=1.0,
            margin=2.0,
        )
        super().__init__(
            spec=self._button_spec(),
            wheel_requires_focus=wheel_requires_focus,
            parent=parent,
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.regionClicked.connect(self._on_region_clicked)

    # ---------- public API ----------

    def set_count(self, count: int) -> None:
        count = max(1, int(count))
        if self._count != count:
            self._count = count
            self._sync_regions()
            self.countChanged.emit(count)

    set_magnifier_count = set_count

    def set_can_remove(self, can_remove: bool) -> None:
        can_remove = bool(can_remove)
        if self._can_remove != can_remove:
            self._can_remove = can_remove
            self._sync_regions()

    def count(self) -> int:
        return self._count

    magnifier_count = count

    def popup_targets(self) -> tuple[QWidget, ...]:
        return (self,)

    # ---------- events ----------

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if not self.shouldHandleWheelEvent(event):
            return
        delta = int(event.angleDelta().y())
        if delta:
            self.wheelScrolled.emit(delta)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.isAutoRepeat():
            event.accept()
            return

        key = event.key()
        if key in (
            Qt.Key.Key_Space,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Up,
            Qt.Key.Key_Plus,
        ):
            self.addClicked.emit()
            event.accept()
            return

        if key in (Qt.Key.Key_Down, Qt.Key.Key_Minus) and self._can_remove:
            self.removeClicked.emit()
            event.accept()
            return

        super().keyPressEvent(event)

    # ---------- internals ----------

    def _sync_regions(self) -> None:
        self.set_spec(self._button_spec())

    def _button_spec(self) -> ButtonSpec:
        if self._count <= 1:
            regions = (
                RegionSpec(
                    id="whole",
                    content=ContentSpec(icon="add_circle"),
                    style=RegionStyle(icon_size_px=20),
                    enabled=True,
                ),
            )
        else:
            regions = (
                RegionSpec(
                    id="top",
                    content=ContentSpec(icon="add"),
                    style=RegionStyle(icon_size_px=14),
                    enabled=True,
                ),
                RegionSpec(
                    id="bottom",
                    content=ContentSpec(icon="remove"),
                    style=RegionStyle(icon_size_px=14),
                    enabled=self._can_remove,
                ),
            )
        return ButtonSpec(
            regions=regions,
            split=VerticalSplit(),
            divider=self._counter_divider if self._count > 1 else None,
            shape=ShapeSpec(
                size=(self._OUTER_SIZE, self._OUTER_SIZE),
                corner_radius=self._CORNER_RADIUS,
                icon_size=20,
            ),
            variant="default",
        )

    def _on_region_clicked(self, region_id: str) -> None:
        if region_id in {"whole", "top"}:
            self.addClicked.emit()
        elif region_id == "bottom" and self._can_remove:
            self.removeClicked.emit()
