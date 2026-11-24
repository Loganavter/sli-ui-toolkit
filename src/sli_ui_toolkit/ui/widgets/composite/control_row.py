"""One labelled control, the row shape both hosts were assembling by hand.

BlinkTable's ``DialogActionBar``/directory field/``ValueSliderRow`` and
REAL-Video-Enhancer's ``_row_checkbox`` each rebuilt the same three pieces: a
title, the control, and an optional caption underneath. This class is that
composition — surface only, no behaviour: the control keeps all of its own
signals and setters, and the row never reaches into it.

Nothing here paints. The label, hint and units suffix are toolkit ``Text``
widgets, so typography follows ``label_variant``/``caption`` through
``UiScale`` and the launcher theme, and no stylesheet or palette literal is
involved.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_FONT, AXIS_SCALE, connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.text import Text

#: The two supported row shapes. ``horizontal`` puts the label in a fixed
#: left column, ``vertical`` stacks the label above the control.
ORIENTATIONS = ("vertical", "horizontal")


class ControlRow(QWidget):
    """A control with a title above (or left of) it, plus hint and units.

    ``ControlRow(control, label="Resolution", hint="…", units="px",
    label_variant="group-title")`` embeds any toolkit widget — or a plain
    ``QWidget`` composite — and keeps it reachable through :meth:`control`.
    The default ``orientation="vertical"`` stacks label / control / hint;
    ``orientation="horizontal"`` moves the label into a left column whose
    width is :attr:`LABEL_COLUMN_WIDTH` design px, re-read through
    ``UiScale`` on every scale/font change (never cached scaled at import).

    The row is a layout container only: the control's own signals remain the
    host's API, and nothing is painted here. ``label_variant`` names a text
    variant for the title (``group-title`` default); the hint and the units
    suffix use ``caption``.

    Widget lookup for hosts that need to restyle a part (no QSS):
    ``findChild(Text, "controlRowLabel")``, ``"controlRowHint"``,
    ``"controlRowUnits"``.
    """

    #: Fixed label column width in design px (horizontal orientation only).
    LABEL_COLUMN_WIDTH = 96
    #: Gap between the label column and the control.
    LABEL_SPACING = 8
    #: Gap between the stacked lines of the row.
    ROW_SPACING = 4

    def __init__(
        self,
        control: QWidget,
        *,
        label: str | None = None,
        hint: str | None = None,
        units: str | None = None,
        label_variant: str = "group-title",
        orientation: str = "vertical",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        if orientation not in ORIENTATIONS:
            raise ValueError(
                f"orientation must be one of {ORIENTATIONS!r}, got {orientation!r}"
            )
        self._orientation = orientation
        self._control: QWidget = control

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(self.ROW_SPACING)

        self._label_widget = Text(
            "", mode="plain", variant=label_variant, parent=self
        )
        self._label_widget.setObjectName("controlRowLabel")

        self._main_row = QHBoxLayout()
        self._main_row.setContentsMargins(0, 0, 0, 0)
        self._main_row.setSpacing(self.LABEL_SPACING)

        self._control_row = QHBoxLayout()
        self._control_row.setContentsMargins(0, 0, 0, 0)
        self._control_row.setSpacing(self.ROW_SPACING)
        self._control_row.addWidget(control, 1)

        self._units_widget = Text("", mode="plain", variant="caption", parent=self)
        self._units_widget.setObjectName("controlRowUnits")
        self._control_row.addWidget(
            self._units_widget,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        if orientation == "horizontal":
            self._main_row.addWidget(
                self._label_widget,
                0,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            self._main_row.addLayout(self._control_row, 1)
            root.addLayout(self._main_row)
        else:
            root.addWidget(self._label_widget, 0, Qt.AlignmentFlag.AlignLeft)
            root.addLayout(self._control_row)

        self._hint_widget = Text("", mode="plain", variant="caption", parent=self)
        self._hint_widget.setObjectName("controlRowHint")
        root.addWidget(self._hint_widget, 0, Qt.AlignmentFlag.AlignLeft)

        self.set_label(label)
        self.set_hint(hint)
        self.set_units(units)
        self._apply_label_column()
        # Font changes matter as well as scale: the title's own metrics move
        # the row's geometry, and a font swap must not leave a stale column.
        connect_ui_metrics(
            self,
            self._on_metrics_changed,
            axes=frozenset({AXIS_SCALE, AXIS_FONT}),
        )

    # -------- public API --------

    def control(self) -> QWidget:
        """The widget currently hosted by the row."""
        return self._control

    def set_control(self, control: QWidget) -> None:
        """Replace the hosted control; the previous one is released.

        "Released" means removed from this row and reparented to ``None`` —
        never deleted, so a host can re-attach it elsewhere or keep a widget
        pool. A control that is already the row's control is a no-op.
        """
        if control is self._control:
            return
        previous = self._control
        self._control_row.removeWidget(previous)
        previous.setParent(None)
        self._control = control
        self._control_row.insertWidget(0, control, 1)
        # A swap on a visible row must appear now, not on the next layout
        # pass: a widget inserted into a live layout is not auto-shown until
        # the event loop reaches it.
        if self.isVisible():
            control.show()

    def set_label(self, text: str | None) -> None:
        self._set_optional_text(self._label_widget, text)

    def set_hint(self, text: str | None) -> None:
        self._set_optional_text(self._hint_widget, text)

    def set_units(self, text: str | None) -> None:
        self._set_optional_text(self._units_widget, text)

    def orientation(self) -> str:
        """``"vertical"`` (default) or ``"horizontal"``."""
        return self._orientation

    # -------- internals --------

    @staticmethod
    def _set_optional_text(widget: Text, text: str | None) -> None:
        widget.setText(text or "")
        widget.setVisible(bool(text))

    def _apply_label_column(self) -> None:
        """Width the label column from the *unscaled* design constant.

        Reading ``scaled_px`` per call is the whole point: caching the result
        would multiply the scale twice on the next change.
        """
        if self._orientation != "horizontal":
            return
        self._label_widget.setFixedWidth(scaled_px(self.LABEL_COLUMN_WIDTH))

    def _on_metrics_changed(self, _axes: frozenset[str]) -> None:
        self._apply_label_column()
        self.updateGeometry()


__all__ = ["ControlRow", "ORIENTATIONS"]
