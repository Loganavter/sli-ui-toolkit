"""CustomTitleBar zone geometry must follow a live UiScale change.

Regression: ``on_scale_changed`` resized the chrome (bar height, window
controls cluster) but never re-ran the bar's layout. The menu strip, the
centered title label and the balance spacers all kept their pre-scale
geometry until some unrelated event re-activated the layout — at 150% the
title text clipped (center host stuck at the 100% width while its
sizeHint grew) and the leading menu buttons overflowed the strip.

The fix defers a full re-layout through ``_schedule_balance_resync`` so it
runs after every child's own ``scale_changed`` handler has refreshed its
sizeHint (the bar's handler may fire first).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.managers import UiScale, ui_font
from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar

TITLE = "Improve ImgSLI — Сравнение изображений"


def _make_host(qtbot) -> tuple[QWidget, CustomTitleBar]:
    host = QWidget()
    host.resize(1000, 300)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    bar = CustomTitleBar(parent=host, title=TITLE)
    layout.addWidget(bar)
    layout.addWidget(QWidget(host), 1)
    host.show()
    qtbot.waitExposed(host)
    return host, bar


def _title_text_width() -> int:
    return QFontMetrics(ui_font()).horizontalAdvance(TITLE)


def test_scale_change_relayouts_center_title(qtbot, qapp):
    host, bar = _make_host(qtbot)
    try:
        UiScale.get_instance().set_factor(1.0)
        qtbot.wait(20)

        center = bar._center_host
        label = bar._title_label
        assert center.width() >= center.sizeHint().width() - 1
        assert label.width() >= _title_text_width()

        hint_before = center.sizeHint().width()
        UiScale.get_instance().set_factor(1.5)
        qtbot.wait(20)

        hint_after = center.sizeHint().width()
        assert hint_after > hint_before
        # The center host must take its new sizeHint — not the pre-scale
        # width — so the title text is not clipped.
        assert center.width() == hint_after, (
            f"center host stuck at {center.width()}px, sizeHint {hint_after}px"
        )
        assert label.width() == hint_after
        assert label.width() >= _title_text_width()

        # Round-trip back to 1.0: geometry must return to the original.
        UiScale.get_instance().set_factor(1.0)
        qtbot.wait(20)
        assert center.width() == hint_before
        assert label.width() >= _title_text_width()
    finally:
        host.deleteLater()


def test_scale_change_reflows_leading_zone(qtbot, qapp):
    """A leading widget with fixed scaled sizes must not overflow the bar."""
    from PySide6.QtWidgets import QWidget as PlainWidget

    host, bar = _make_host(qtbot)
    try:
        UiScale.get_instance().set_factor(1.0)
        qtbot.wait(20)

        # Leading chrome whose width scales with UiScale (like the app's
        # CSD menu strip: fixed-size buttons in a box layout).
        leading = PlainWidget(bar)
        from PySide6.QtWidgets import QHBoxLayout

        lay = QHBoxLayout(leading)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(8)
        buttons = []
        for _ in range(2):
            btn = PlainWidget(leading)
            btn.setFixedSize(51, 28)
            buttons.append(btn)
            lay.addWidget(btn)
        bar.set_leading(leading)
        qtbot.wait(20)

        leading_w_1 = leading.width()
        for btn in buttons:
            btn.setFixedSize(76, 42)
        leading.updateGeometry()
        bar._sync_balance_spacer()
        qtbot.wait(20)

        # The strip must widen to fit its (now larger) fixed children.
        assert leading.width() > leading_w_1
        assert leading.width() >= sum(b.width() for b in buttons) + 16
    finally:
        host.deleteLater()


def test_window_control_buttons_reslot_after_scale_change(qtbot, qapp):
    """Live scale change must re-slot the window controls inside their
    container — rescaled buttons at stale slots keep old hit/hover zones
    under the new visuals (hover lights up off the window edge).

    Regression: ``_resize_buttons_container`` fixed the container width but
    the buttons resize in their OWN scale_changed handlers afterwards; the
    container's layout could keep the previous factor's slots.
    """
    from PySide6.QtWidgets import QVBoxLayout as _QVBoxLayout

    host = QWidget()
    host.resize(900, 200)
    layout = _QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    bar = CustomTitleBar(parent=host, title="Title")
    layout.addWidget(bar)
    host.show()
    qtbot.waitExposed(host)

    UiScale.get_instance().set_factor(1.0)
    qtbot.wait(30)

    def slots():
        container = bar._controls
        return [
            btn.geometry()
            for btn in (bar._controls._min_btn, bar._controls._max_btn, bar._controls._close_btn)
            if btn is not None
        ]

    before = slots()
    assert [g.width() for g in before] == [46] * len(before)
    # buttons reach the container's right edge (no gap)
    assert before[-1].right() == bar._controls.width() - 1

    UiScale.get_instance().set_factor(1.5)
    qtbot.wait(30)

    after = slots()
    assert [g.width() for g in after] == [69] * len(after)
    # fresh contiguous slots: min@0, max@69, close@138
    assert [g.x() for g in after] == [0, 69, 138][: len(after)]
    assert after[-1].right() == bar._controls.width() - 1
    # each button's hit rect must sit inside the container
    container = bar._controls
    assert all(container.rect().contains(g.center()) for g in after)


def test_close_only_bar_places_close_button_inside_container(qtbot, qapp):
    """A dialog-style bar (close button only) must place it at slot 0.

    Regression: the manual slot assignment used the index in the
    (min, max, close) enumeration — with only the close button present it
    landed at 2*width, outside the 1-control container, and the container's
    corner mask clipped it away (buttons vanished in decorated dialogs).
    """
    from PySide6.QtWidgets import QVBoxLayout as _QVBoxLayout

    host = QWidget()
    host.resize(700, 200)
    layout = _QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    bar = CustomTitleBar(
        parent=host,
        title="Settings",
        show_minimize=False,
        show_maximize=False,
        show_close=True,
    )
    layout.addWidget(bar)
    host.show()
    qtbot.waitExposed(host)

    for factor in (1.0, 1.5):
        UiScale.get_instance().set_factor(factor)
        qtbot.wait(30)
        container = bar._controls
        close = bar._controls._close_btn
        assert close is not None
        assert bar._controls._min_btn is None and bar._controls._max_btn is None
        assert close.geometry().x() == 0, (
            f"factor {factor}: close button at x={close.geometry().x()}, "
            "expected slot 0"
        )
        assert close.geometry().width() == container.width()
        assert container.rect().contains(close.geometry().center())
        assert close.isVisible()


def test_container_corner_mask_follows_scale_change(qtbot, qapp):
    """The controls container's rounded-corner mask must cover the FULL
    container after a scale change.

    Regression: the mask is re-applied on the bar's resizeEvent; a scale
    change resizes the container inside ``_resize_buttons_container`` and if
    the bar's resize event lands without it, the mask stays at the previous
    factor's width and masks the rescaled buttons away — the close button
    disappears entirely on 1.0 -> 1.5 (and is cut in half on 1.25 -> 1.5).
    """
    from sli_ui_toolkit.managers import UiScale
    from sli_ui_toolkit.theme import ThemeManager

    tm = ThemeManager.get_instance()
    registered = list(getattr(tm, "_palettes", {}) or {})
    if "light" not in registered:
        tm.register_palettes({"light": {}, "dark": {}})
    tm.set_theme("light")

    host = QWidget()
    host.resize(600, 200)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    bar = CustomTitleBar(parent=host, title="Title")
    layout.addWidget(bar)
    host.show()
    qtbot.waitExposed(host)

    for factor in (1.0, 1.25, 1.5, 2.0, 1.0):
        UiScale.get_instance().set_factor(factor)
        qtbot.wait(30)
        container = bar._controls
        mask = container.mask()
        covered = mask.boundingRect().right() + 1 if mask and not mask.isEmpty() else 0
        assert covered >= container.width(), (
            f"factor {factor}: mask covers 0..{covered - 1} but the container "
            f"is {container.width()}px wide — the rescaled close button "
            "outside the mask is not painted"
        )
        close = bar._controls._close_btn
        assert close.geometry().right() < covered, (
            f"factor {factor}: close button right {close.geometry().right()} "
            f"beyond mask coverage {covered}"
        )
