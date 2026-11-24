"""The public ``Splitter``: the divider is one device pixel wide.

``QSplitter`` is in every host toolkit, but the one thing hosts cannot
reproduce cheaply is the dialog shell's separator: a single **device** pixel of
``dialog.border`` centred in the handle, crisp at 125 % / 150 % / 200 %, with a
``surface.background`` gap on both sides. Before this module every host either
lived with QStyle's 1-*logical*-px line (two blended device columns at a
fractional ratio) or hand-painted its own band.

The tests below pin behaviour, not implementation: the painted strip is exactly
one device column/row at DPR 1.0 / 1.5 / 2.0 in both orientations, the handle
width follows ``UiScale``, ``setSizes``/``sizes`` round-trips, a collapsible
child really collapses to 0, a double-click gives the panes equal shares, and
``SidebarDialogShell`` uses this class rather than a private copy.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.composite import dialog_shell
from sli_ui_toolkit.widgets import (
    SidebarDialogShell,
    Splitter,
    SplitterHandle,
    hairline_rect,
)

HORIZONTAL = Qt.Orientation.Horizontal
VERTICAL = Qt.Orientation.Vertical


@pytest.fixture(autouse=True)
def _light_theme(qapp):
    """A registered palette, so ``dialog.border`` is a known colour."""
    theme = ThemeManager.get_instance()
    theme.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    theme.set_theme("light", qapp, await_ripples=False)
    qapp.processEvents()
    yield theme
    theme.set_theme("light", qapp, await_ripples=False)
    qapp.processEvents()


def _pane(label: str) -> QWidget:
    pane = QWidget()
    pane.setObjectName(label)
    return pane


def _shown_splitter(qapp, orientation, size=(512, 300), **kwargs) -> Splitter:
    splitter = Splitter(orientation, **kwargs)
    splitter.addWidget(_pane("first"))
    splitter.addWidget(_pane("second"))
    splitter.resize(*size)
    splitter.show()
    qapp.processEvents()
    return splitter


def _extent(splitter: Splitter) -> int:
    if splitter.orientation() == HORIZONTAL:
        return splitter.width()
    return splitter.height()


def _available(splitter: Splitter) -> int:
    """Extent a drag may distribute: total minus the handles between panes."""
    return _extent(splitter) - splitter.handleWidth() * (splitter.count() - 1)


def _paint_handle(handle: SplitterHandle, dpr: float) -> QImage:
    """Paint the handle onto a device with the requested ratio.

    ``QWidget.render()`` always paints at the widget's own ratio (1.0
    offscreen), so it cannot reach a fractional path; ``_paint_divider`` is
    the same painter code ``paintEvent`` runs, on the device given.
    """
    logical_w, logical_h = handle.width(), handle.height()
    image = QImage(
        int(round(logical_w * dpr)),
        int(round(logical_h * dpr)),
        QImage.Format.Format_ARGB32,
    )
    image.fill(QColor(0, 0, 0, 0))
    image.setDevicePixelRatio(dpr)
    painter = QPainter(image)
    try:
        handle._paint_divider(painter)
    finally:
        painter.end()
    return image


def _painted_cells(image: QImage, *, across_columns: bool) -> list[int]:
    """Indices of device cells that differ from the surface fill (one line)."""
    if across_columns:
        fixed, count = image.height() // 2, image.width()
        pixel = lambda index: image.pixel(index, fixed)  # noqa: E731
    else:
        fixed, count = image.width() // 2, image.height()
        pixel = lambda index: image.pixel(fixed, index)  # noqa: E731
    surface = QColor(pixel(0)).name()
    return [
        index
        for index in range(count)
        if QColor(pixel(index)).name() != surface
    ]


@pytest.mark.parametrize("dpr", [1.0, 1.5, 2.0])
@pytest.mark.parametrize(
    "orientation,across_columns",
    [(HORIZONTAL, True), (VERTICAL, False)],
    ids=["horizontal", "vertical"],
)
def test_the_divider_is_exactly_one_device_pixel_wide(
    qapp, _light_theme, orientation, across_columns, dpr
):
    """One crisp device column (or row), never two blended ones, never a 2-px band."""
    splitter = _shown_splitter(
        qapp, orientation, size=(512, 300) if orientation == HORIZONTAL else (300, 512)
    )
    try:
        handle = splitter.handle(1)
        image = _paint_handle(handle, dpr)
        painted = _painted_cells(image, across_columns=across_columns)
        total = image.width() if across_columns else image.height()

        assert len(painted) == 1, f"expected one device cell at DPR {dpr}: {painted}"
        assert painted[0] not in (0, total - 1), (
            f"the divider sits on the handle edge at DPR {dpr}"
        )
        # Crisp, not blended: the cell is the border token itself.
        border = _light_theme.get_color("dialog.border").name()
        if across_columns:
            actual = QColor(image.pixel(painted[0], image.height() // 2)).name()
        else:
            actual = QColor(image.pixel(image.width() // 2, painted[0])).name()
        assert actual == border, f"divider is not the dialog border at DPR {dpr}"
    finally:
        splitter.close()


def test_hairline_rect_lands_on_whole_device_columns():
    """The geometry helper, independent of any widget/style."""
    for dpr in (1.0, 1.25, 1.5, 2.0):
        rect = hairline_rect(extents=8.0, length=40.0, dpr=dpr, vertical=True)
        left = rect.left() * dpr
        right = rect.right() * dpr
        assert left == pytest.approx(round(left))
        assert right - left == pytest.approx(1.0)


def test_the_handle_paints_its_own_divider_not_the_style(qapp):
    splitter = _shown_splitter(qapp, HORIZONTAL)
    try:
        assert isinstance(splitter.handle(1), SplitterHandle)
        assert splitter.handle(1).splitter() is splitter
    finally:
        splitter.close()


def test_the_handle_width_follows_the_interface_scale(qapp):
    splitter = _shown_splitter(qapp, HORIZONTAL)
    try:
        assert splitter.handle_width() == 6
        assert splitter.handleWidth() == scaled_px(6) == 6

        UiScale.get_instance().set_factor(1.25)
        qapp.processEvents()
        assert splitter.handleWidth() == scaled_px(6) == 8

        # Back down: the metric must return, not stick.
        UiScale.get_instance().set_factor(1.0)
        qapp.processEvents()
        assert splitter.handleWidth() == 6
    finally:
        splitter.close()


def test_a_theme_change_repaints_the_divider_in_the_new_border_colour(qapp, _light_theme):
    splitter = _shown_splitter(qapp, HORIZONTAL)
    try:
        handle = splitter.handle(1)
        _light_theme.set_color("dialog.border", QColor("#123456"))
        qapp.processEvents()
        assert handle._line_color.name() == "#123456"
    finally:
        splitter.close()


@pytest.mark.parametrize("orientation", [HORIZONTAL, VERTICAL], ids=["horizontal", "vertical"])
def test_setSizes_round_trips(qapp, orientation):
    size = (512, 300) if orientation == HORIZONTAL else (300, 512)
    splitter = _shown_splitter(qapp, orientation, size=size)
    try:
        available = _available(splitter)
        first = available // 3
        splitter.setSizes([first, available - first])
        assert splitter.sizes() == [first, available - first]
        assert sum(splitter.sizes()) == available
    finally:
        splitter.close()


def test_a_collapsible_child_collapses_to_zero(qapp):
    splitter = _shown_splitter(qapp, HORIZONTAL)
    try:
        assert splitter.childrenCollapsible() is True
        available = _available(splitter)
        splitter.setSizes([0, available])
        assert splitter.sizes()[0] == 0
    finally:
        splitter.close()


def test_a_non_collapsible_child_keeps_its_minimum(qapp):
    splitter = _shown_splitter(qapp, HORIZONTAL, children_collapsible=False)
    try:
        assert splitter.childrenCollapsible() is False
        pane = splitter.widget(0)
        assert pane is not None
        pane.setMinimumWidth(120)
        splitter.setSizes([0, _available(splitter)])
        assert splitter.sizes()[0] >= 120
    finally:
        splitter.close()


@pytest.mark.parametrize("orientation", [HORIZONTAL, VERTICAL], ids=["horizontal", "vertical"])
def test_double_click_gives_the_panes_equal_shares(qapp, orientation):
    size = (520, 300) if orientation == HORIZONTAL else (300, 520)
    splitter = _shown_splitter(qapp, orientation, size=size)
    try:
        available = _available(splitter)
        splitter.setSizes([40, available - 40])
        handle = splitter.handle(1)

        event = QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            QPointF(1.0, 1.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        handle.mouseDoubleClickEvent(event)

        first, second = splitter.sizes()
        assert abs(first - second) <= 1, (first, second)
        assert first + second == available
    finally:
        splitter.close()


def test_a_right_button_double_click_does_not_reset(qapp):
    splitter = _shown_splitter(qapp, HORIZONTAL)
    try:
        available = _available(splitter)
        splitter.setSizes([40, available - 40])
        before = splitter.sizes()
        event = QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            QPointF(1.0, 1.0),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        splitter.handle(1).mouseDoubleClickEvent(event)
        assert splitter.sizes() == before
    finally:
        splitter.close()


def test_sidebar_shell_uses_the_public_splitter(qapp):
    """One implementation: the shell's ``.splitter`` is the exported class."""
    shell = SidebarDialogShell(resizable_sidebar=True)
    shell.resize(900, 500)
    shell.show()
    qapp.processEvents()
    try:
        assert isinstance(shell.splitter, Splitter)
        assert isinstance(shell.splitter.handle(1), SplitterHandle)
        # The private duplicate is gone, not merely unused.
        assert not hasattr(dialog_shell, "_SidebarDialogSplitter")
        assert not hasattr(dialog_shell, "_DialogSplitterHandle")
        # The shell's own geometry is unchanged: 6 design px, non-collapsible.
        assert shell.splitter.handleWidth() == scaled_px(6) == 6
        assert shell.splitter.childrenCollapsible() is False
        assert shell.splitter.orientation() == HORIZONTAL
        assert shell.splitter.sizes()[0] == scaled_px(200)
    finally:
        shell.close()
