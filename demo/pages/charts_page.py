"""Charts page — SunburstChart with real angular segment data."""

from __future__ import annotations

import math

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import (
    Label,
    SunburstChartWidget,
    SunburstSegmentData,
)

from demo.components import GalleryPage

INNER_TOP = [
    ("Frontend", 0.40, "#4caf50"),
    ("Backend",  0.30, "#2196f3"),
    ("Docs",     0.15, "#ff9800"),
    ("Tests",    0.15, "#9c27b0"),
]

OUTER_CHILDREN = {
    "Frontend": [("Buttons", 0.55, "#66bb6a"), ("Inputs", 0.45, "#81c784")],
    "Backend":  [("API",     0.60, "#42a5f5"), ("DB",     0.40, "#64b5f6")],
    "Docs":     [("Guides",  1.00, "#ffb74d")],
    "Tests":    [("Unit",    0.65, "#ba68c8"), ("E2E",    0.35, "#ce93d8")],
}

def _build_sunburst_segments(focus: str | None = None) -> list[SunburstSegmentData]:
    """Build a two-ring sunburst dataset with explicit angles & radii."""
    segments: list[SunburstSegmentData] = []
    inner_r = 0.28
    outer_inner_r = 0.56
    outer_outer_r = 0.84

    if focus:
        cursor = math.radians(-90.0)
        children = OUTER_CHILDREN.get(focus, [])
        for sub_label, sub_share, sub_color in children:
            sweep = math.tau * sub_share
            segments.append(SunburstSegmentData(
                start_angle=cursor, end_angle=cursor + sweep,
                inner_radius=inner_r, outer_radius=outer_outer_r,
                color=sub_color, label=sub_label,
                node_id=f"outer:{focus}:{sub_label}",
                font_size=11,
                value_text=f"{sub_share:.0%}",
                tooltip=f"{focus} / {sub_label}: {sub_share:.0%}",
            ))
            cursor += sweep
        return segments

    cursor = math.radians(-90.0)
    for label, share, color in INNER_TOP:
        sweep = math.tau * share
        segments.append(SunburstSegmentData(
            start_angle=cursor, end_angle=cursor + sweep,
            inner_radius=inner_r, outer_radius=outer_inner_r,
            color=color, label=label, node_id=f"inner:{label}",
            font_size=10,
            value_text=f"{share:.0%}",
            tooltip=f"{label}: {share:.0%}",
        ))
        sub_cursor = cursor
        for sub_label, sub_share, sub_color in OUTER_CHILDREN[label]:
            sub_sweep = sweep * sub_share
            absolute_share = share * sub_share
            segments.append(SunburstSegmentData(
                start_angle=sub_cursor, end_angle=sub_cursor + sub_sweep,
                inner_radius=outer_inner_r, outer_radius=outer_outer_r,
                color=sub_color, label=sub_label,
                node_id=f"outer:{label}:{sub_label}",
                value_text=f"{absolute_share:.0%}",
                tooltip=f"{label} / {sub_label}: {absolute_share:.0%}",
                font_size=9,
            ))
            sub_cursor += sub_sweep
        cursor += sweep
    return segments


class ChartsPage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Charts",
            subtitle="Sunburst-чарт с реальными данными.",
            source_file=__file__,
            parent=parent,
        )

        chart_host = QWidget()
        chart_layout = QVBoxLayout(chart_host)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(8)

        chart = SunburstChartWidget()
        chart.setMinimumSize(360, 360)
        tm = ThemeManager.get_instance()
        bg = tm.try_get_color("dialog.background") or QColor("#ffffff")
        chart.set_background_color(bg)
        chart.set_gap_color(bg)
        text_color = tm.try_get_color("dialog.text")
        if text_color is not None:
            chart.set_center_text_color(text_color)
        status = Label("All components", pixel_size=11)
        state = {"focus": None, "selected": None}

        def render(focus: str | None = None, selected: str | None = None) -> None:
            state["focus"] = focus
            state["selected"] = selected
            chart.set_segments(
                _build_sunburst_segments(focus),
                center_text=focus or "Toolkit",
                center_sub_text=selected or "components",
            )
            if selected:
                status.setText(selected)
            elif focus:
                status.setText(f"{focus}: child segments")
            else:
                status.setText("All components")

        def restore_status() -> None:
            selected = state["selected"]
            focus = state["focus"]
            if selected:
                status.setText(str(selected))
            elif focus:
                status.setText(f"{focus}: child segments")
            else:
                status.setText("All components")

        def handle_click(segment_id: str, button: int) -> None:
            if button == 3:
                render()
                return
            parts = segment_id.split(":")
            if len(parts) >= 2 and parts[0] == "inner":
                render(focus=parts[1])
            elif len(parts) >= 3 and parts[0] == "outer":
                render(focus=parts[1], selected=parts[2])

        render()
        chart.segment_hover_enter.connect(
            lambda data, _pos: status.setText(data.tooltip or f"{data.label}: {data.value_text}")
        )
        chart.segment_hover_leave.connect(restore_status)
        chart.segment_clicked.connect(handle_click)
        chart_layout.addWidget(chart)
        chart_layout.addWidget(status)
        self.add_card(
            "SunburstChartWidget",
            chart_host,
            "Двухкольцевой sunburst с hover/click-сигналами и нормализованными радиусами.",
        )

        self.add_card(
            "TimelineWidget",
            Label(
                "TimelineWidget требует подготовленных snapshot-данных "
                "и стор, см. composite/timeline_widget/ — не показан в gallery.",
                pixel_size=11,
            ),
        )

        self.add_stretch()
