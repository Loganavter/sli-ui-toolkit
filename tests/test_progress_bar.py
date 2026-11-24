"""`ProgressBar` — the standalone painted progress bar (track, chunk, states, indeterminate)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QProgressBar

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.widgets import ProgressBar

BAR_W = 200
BAR_H = 10


@pytest.fixture(params=["light", "dark"])
def theme(request, qapp):
    manager = ThemeManager.get_instance()
    manager.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    manager.set_theme(request.param, qapp, await_ripples=False)
    manager._flush_pending_theme()  # type: ignore[attr-defined]
    yield request.param
    manager.set_theme("light", qapp, await_ripples=False)
    manager._flush_pending_theme()  # type: ignore[attr-defined]


def _render(widget, size=(BAR_W, BAR_H)) -> QImage:
    widget.resize(*size)
    image = QImage(size[0], size[1], QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    return image


def _token(name: str):
    return ThemeManager.get_instance().get_color(name)


# -- determinate fill ---------------------------------------------------


@pytest.mark.parametrize("percent", [25, 50, 75])
def test_fill_ratio_is_read_from_the_tokens_in_both_themes(qapp, theme, percent):
    bar = ProgressBar(value=percent)
    image = _render(bar)
    # Midline samples: the far-left end is rounded, so 25%/50%/75% are interior points for every ratio here.
    inside = int(BAR_W * (percent / 100.0) / 2)
    outside = int(BAR_W * (percent / 100.0) + (BAR_W - BAR_W * percent / 100.0) / 2)
    assert image.pixelColor(inside, BAR_H // 2) == _token("progress.fill")
    assert image.pixelColor(outside, BAR_H // 2) == _token("progress.track.background")


def test_zero_value_paints_only_the_track(qapp, theme):
    image = _render(ProgressBar(value=0))
    assert image.pixelColor(20, BAR_H // 2) == _token("progress.track.background")
    assert image.pixelColor(BAR_W // 2, BAR_H // 2) == _token("progress.track.background")


def test_full_value_paints_the_chunk_across_the_track(qapp, theme):
    image = _render(ProgressBar(value=100))
    assert image.pixelColor(BAR_W // 2, BAR_H // 2) == _token("progress.fill")
    assert image.pixelColor(BAR_W - 20, BAR_H // 2) == _token("progress.fill")


# -- states -------------------------------------------------------------


@pytest.mark.parametrize(
    "state, token",
    [("normal", "progress.fill"), ("success", "progress.success"), ("error", "progress.error")],
)
def test_state_selects_its_token(qapp, theme, state, token):
    bar = ProgressBar(value=100, state=state)
    assert bar.state() == state
    image = _render(bar)
    assert image.pixelColor(BAR_W // 2, BAR_H // 2) == _token(token)


def test_state_swap_repaints_from_the_new_token(qapp, theme):
    bar = ProgressBar(value=100)
    assert _render(bar).pixelColor(100, 5) == _token("progress.fill")
    bar.setState("success")
    assert _render(bar).pixelColor(100, 5) == _token("progress.success")
    bar.setState("error")
    assert _render(bar).pixelColor(100, 5) == _token("progress.error")


def test_unknown_state_is_rejected(qapp):
    with pytest.raises(ValueError):
        ProgressBar(state="warning")


def test_progress_success_exists_in_both_palettes():
    # A host reads this token directly; before it existed the read fell back to the accent and the designed green
    # never appeared.
    for palette in (FLUENT_LIGHT, FLUENT_DARK):
        assert "progress.success" in palette
        assert "progress.fill" in palette
        assert "progress.error" in palette


# -- range --------------------------------------------------------------


def test_value_is_clamped_to_the_range(qapp):
    bar = ProgressBar(minimum=10, maximum=20, value=5)
    assert bar.value() == 10
    bar.setValue(999)
    assert bar.value() == 20
    bar.setRange(0, 100)
    assert (bar.minimum(), bar.maximum()) == (0, 100)


def test_an_inverted_range_keeps_one_step(qapp):
    bar = ProgressBar()
    bar.setRange(50, 10)
    assert bar.minimum() == 50
    assert bar.maximum() == 51
    assert bar.value() == 50


def test_setting_a_narrower_range_reclamps_the_value(qapp):
    bar = ProgressBar(value=90)
    bar.setRange(0, 50)
    assert bar.value() == 50


# -- indeterminate ------------------------------------------------------


def test_indeterminate_ticks_only_while_visible(qapp, qtbot):
    bar = ProgressBar(indeterminate=True)
    qtbot.addWidget(bar)
    bar.show()
    assert bar.isIndeterminate() is True
    assert bar._timer.isActive()

    bar.hide()
    assert bar._timer.isActive() is False
    bar.show()
    assert bar._timer.isActive() is True

    bar.setIndeterminate(False)
    assert bar._timer.isActive() is False


def test_indeterminate_true_while_hidden_does_not_start_the_timer(qapp, qtbot):
    bar = ProgressBar()
    qtbot.addWidget(bar)
    bar.hide()
    bar.setIndeterminate(True)
    assert bar._timer.isActive() is False
    bar.show()
    assert bar._timer.isActive() is True


def test_a_tick_moves_the_chunk_instead_of_the_value(qapp, theme, qtbot):
    bar = ProgressBar(indeterminate=True, value=10)
    qtbot.addWidget(bar)
    first = _render(bar)
    bar._tick()
    bar._tick()
    second = _render(bar)
    assert first != second
    assert bar.value() == 10


# -- text and geometry --------------------------------------------------


def test_text_is_opt_in_and_paints_nothing_by_default(qapp, theme):
    assert ProgressBar().text() is None
    plain = _render(ProgressBar(value=100))
    labelled = ProgressBar(value=100, text="")
    assert labelled.text() == ""
    assert _render(labelled) == plain
    labelled.setText("42%")
    assert labelled.text() == "42%"
    assert _render(labelled) != plain
    labelled.setText(None)
    assert labelled.text() is None
    assert _render(labelled) == plain


def test_size_hint_follows_the_design_px_height_through_ui_scale(qapp):
    scale = UiScale.get_instance()
    original = scale.factor()
    try:
        scale.set_factor(1.0)
        hint = ProgressBar().sizeHint()
        assert hint.height() == 6

        scale.set_factor(2.0)
        doubled = ProgressBar(height=8).sizeHint()
        assert doubled.height() == 16
    finally:
        scale.set_factor(original)


def test_it_is_a_plain_painted_widget_not_a_qprogressbar(qapp):
    bar = ProgressBar()
    assert isinstance(bar, QProgressBar) is False
    assert bar.styleSheet() == ""
