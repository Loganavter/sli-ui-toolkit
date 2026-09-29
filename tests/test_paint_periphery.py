"""Task 1 (paint periphery) regression tests.

Covers: LoadingSpinner hide auto-stop + UiScale sizing, MarqueeState
accent pinning and SunburstChartWidget theme refresh, ListPanel painter-path
styling (no QSS), and the MeasuredHeights full-measurement contract pin.
"""

from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.palettes import FLUENT_DARK, FLUENT_LIGHT
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale
from sli_ui_toolkit.ui.widgets.atomic.loading_spinner import LoadingSpinner
from sli_ui_toolkit.ui.widgets.composite.list_panel import ListPanel
from sli_ui_toolkit.ui.widgets.composite.sunburst_chart.chart_widget import (
    SunburstChartWidget,
)
from sli_ui_toolkit.ui.widgets.overlays.marquee_state import (
    DEFAULT_MARQUEE_ACCENT,
    MarqueeState,
)
from sli_ui_toolkit.ui.widgets.virtual_list.window import MeasuredHeights
from sli_ui_toolkit.widgets import LoadingSpinner as PublicSpinner


@pytest.fixture()
def hermetic_theme(qapp):
    """Snapshot/restore the process-wide theme + scale singletons."""
    tm = ThemeManager.get_instance()
    scale = UiScale.get_instance()
    saved_light = copy.deepcopy(tm._light_palette)
    saved_dark = copy.deepcopy(tm._dark_palette)
    saved_theme = tm.get_current_theme()
    saved_factor = scale.factor()
    tm.register_palettes(
        light_palette=copy.deepcopy(FLUENT_LIGHT),
        dark_palette=copy.deepcopy(FLUENT_DARK),
    )
    tm.set_theme("light", qapp, await_ripples=False)
    yield tm
    tm.register_palettes(light_palette=saved_light, dark_palette=saved_dark)
    tm.set_theme(saved_theme, qapp, await_ripples=False)
    scale.set_factor(saved_factor)
    qapp.processEvents()


def _build_panel(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 400)
    panel = ListPanel(
        list_num=1,
        item_height=36,
        item_font=None,
        get_current_index=lambda n: 0,
        on_item_selected=lambda *a: None,
        on_item_context_menu=lambda *a: None,
        on_reorder=lambda *a: None,
        on_move_between_lists=lambda *a: None,
        on_update_drop_indicator=lambda *a: None,
        on_clear_drop_indicator=lambda *a: None,
        parent=host,
    )
    host.show()
    return host, panel


# -- LoadingSpinner --------------------------------------------------------


def test_spinner_public_export_is_scaled_widget():
    assert PublicSpinner is LoadingSpinner
    assert LoadingSpinner.SIZE_PX == 40


def test_spinner_start_stop(qapp, qtbot, hermetic_theme):
    spinner = LoadingSpinner()
    qtbot.addWidget(spinner)
    assert not spinner.is_spinning()
    spinner.start()
    assert spinner.is_spinning()
    spinner.stop()
    assert not spinner.is_spinning()


def test_spinner_auto_stops_on_hide_and_resumes_on_show(
    qapp, qtbot, hermetic_theme
):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(200, 200)
    spinner = LoadingSpinner(parent=host)
    host.show()
    spinner.show()
    qapp.processEvents()
    spinner.start()
    assert spinner.is_spinning()
    spinner.hide()
    qapp.processEvents()
    assert not spinner.is_spinning()
    spinner.show()
    qapp.processEvents()
    assert spinner.is_spinning()
    spinner.stop()


def test_spinner_explicit_stop_while_hidden_stays_stopped(
    qapp, qtbot, hermetic_theme
):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(200, 200)
    spinner = LoadingSpinner(parent=host)
    host.show()
    spinner.show()
    qapp.processEvents()
    spinner.start()
    spinner.hide()
    qapp.processEvents()
    spinner.stop()  # explicit cancel while hidden clears the resume request
    spinner.show()
    qapp.processEvents()
    assert not spinner.is_spinning()


def test_spinner_size_follows_ui_scale(qapp, qtbot, hermetic_theme):
    spinner = LoadingSpinner()
    qtbot.addWidget(spinner)
    assert spinner.width() == 40
    UiScale.get_instance().set_factor(1.5)
    assert spinner.width() == 60
    assert spinner.sizeHint().width() == 60
    UiScale.get_instance().set_factor(1.0)
    assert spinner.width() == 40
    spinner.start()
    spinner.grab()  # paint smoke
    spinner.stop()


# -- MarqueeState accent ----------------------------------------------------

# The in-paint state carries no theme connection: the default accent is
# fixed and set_accent() pins explicitly. Hosts (gallery, ListPanel) push
# their own accent per theme switch.


def test_marquee_default_accent_is_theme_independent(
    qapp, qtbot, hermetic_theme
):
    host = QWidget()
    qtbot.addWidget(host)
    state = MarqueeState(host)
    assert state.accent().name() == QColor(DEFAULT_MARQUEE_ACCENT).name()
    hermetic_theme.set_theme("dark", qapp, await_ripples=False)
    qapp.processEvents()
    assert state.accent().name() == QColor(DEFAULT_MARQUEE_ACCENT).name()


def test_marquee_custom_accent_pins(
    qapp, qtbot, hermetic_theme
):
    host = QWidget()
    qtbot.addWidget(host)
    state = MarqueeState(host)
    state.set_accent(QColor("#9eccef"))
    hermetic_theme.set_theme("dark", qapp, await_ripples=False)
    qapp.processEvents()
    assert state.accent().name() == "#9eccef"


# -- SunburstChartWidget ---------------------------------------------------


def test_sunburst_default_background_follows_theme(
    qapp, qtbot, hermetic_theme
):
    chart = SunburstChartWidget()
    qtbot.addWidget(chart)
    assert chart._bg_color.name() == QColor(
        FLUENT_LIGHT["dialog.background"]
    ).name()
    hermetic_theme.set_theme("dark", qapp, await_ripples=False)
    qapp.processEvents()
    assert chart._bg_color.name() == QColor(
        FLUENT_DARK["dialog.background"]
    ).name()


def test_sunburst_custom_background_survives_theme_change(
    qapp, qtbot, hermetic_theme
):
    chart = SunburstChartWidget()
    qtbot.addWidget(chart)
    chart.set_background_color(QColor("#123456"))
    hermetic_theme.set_theme("dark", qapp, await_ripples=False)
    qapp.processEvents()
    assert chart._bg_color.name() == "#123456"


# -- ListPanel painter path -------------------------------------------------


def test_list_panel_uses_no_qss(qapp, qtbot, hermetic_theme):
    _host, panel = _build_panel(qtbot)
    qapp.processEvents()
    assert panel.styleSheet() == ""
    assert panel.scroll_area.styleSheet() == ""
    assert panel.content_widget.styleSheet() == ""
    assert panel.property("_sli_surface_filter") is True
    # Theme switch must not reintroduce stylesheets — painter path only.
    hermetic_theme.set_theme("dark", qapp, await_ripples=False)
    qapp.processEvents()
    assert panel.styleSheet() == ""
    assert panel.scroll_area.styleSheet() == ""
    panel.grab()  # surface-filter paint smoke


# -- MeasuredHeights contract ----------------------------------------------


def test_measured_heights_reports_partial_coverage():
    heights = MeasuredHeights()
    heights.set_count(4)
    assert not heights.is_fully_measured
    heights.set_height(0, 20)
    heights.set_height(1, 20)
    assert not heights.is_fully_measured
    heights.set_height(2, 20)
    heights.set_height(3, 20)
    assert heights.is_fully_measured
    assert heights.total() == 80


def test_measured_heights_shrink_drops_coverage():
    heights = MeasuredHeights()
    heights.set_count(2)
    heights.set_height(0, 10)
    heights.set_height(1, 10)
    assert heights.is_fully_measured
    heights.set_count(3)
    assert not heights.is_fully_measured
