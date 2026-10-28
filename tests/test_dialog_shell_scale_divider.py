"""Settings splitter: scaled divider metrics, a crisp line, a real minimum.

Owner report (2026-10-28, 125 % screen + "Interface Scale" 1.25): the line
between the nav column and the content column of the Settings dialog merged
with the leftmost border of the control groups on its right. Three separate
defects behind it, all in ``dialog_shell.py``:

* the splitter handle width and the content margins were stamped once in
  ``__init__`` — after ``UiScale.set_factor(1.25)`` the handle stayed 6 px
  (should be 8) and the margins (8, 8, 8, 8) (should be 10), while everything
  around them grew;
* the divider was drawn by QStyle: a 1 *logical* px line at a fractional
  device ratio straddles two device columns and rasterizes as a blurred band
  next to the group border;
* ``QScrollArea.minimumSizeHint()`` is a fixed ~68×68 whatever its content,
  so the right column took part in no minimum and could be squeezed under its
  own content, right up against the divider.

The tests below pin the behaviour, not the implementation: the handle width
and the margins must follow the factor, the painted line must be exactly one
device pixel wide and centred at every ratio, and the content column's width
must reach the dialog's minimum.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.composite import dialog_shell
from sli_ui_toolkit.widgets import ScrollableDialogPage, SidebarDialogShell

#: The owner's display: 125 % is fractional, which is what turns a 1-logical-px
#: style line into a two-column smear. 1.0/1.5/2.0 are the neighbours a fix
#: must not break.
FRACTIONAL_DPR = 1.25


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


def _apply_factor(qapp, factor: float) -> None:
    """Change the interface scale and let the coalesced bus deliver it."""
    UiScale.get_instance().set_factor(factor)
    qapp.processEvents()


def _build_content_column(width: int = 419, height: int = 1200) -> QWidget:
    """A stand-in for a settings page body that refuses to shrink."""
    body = QWidget()
    layout = QVBoxLayout(body)
    wide = QWidget()
    wide.setMinimumSize(width, height)
    layout.addWidget(wide)
    return body


def _shown_shell(qapp, **kwargs) -> SidebarDialogShell:
    shell = SidebarDialogShell(resizable_sidebar=True, **kwargs)
    shell.resize(900, 500)
    shell.show()
    qapp.processEvents()
    return shell


def _paint_handle(handle, dpr: float) -> QImage:
    """Paint the handle onto a device with the requested ratio.

    ``QWidget.render()`` always paints at the widget's own ratio (1.0
    offscreen), so it cannot reach the fractional path; ``_paint_divider`` is
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


def test_divider_handle_and_margins_follow_the_scale_factor(qapp):
    """The reported numbers: 6 → 8 px handle, (8, 8, 8, 8) → 10 px margins."""
    shell = _shown_shell(qapp, content_margins=(8, 8, 8, 8), content_spacing=10)
    try:
        assert shell.splitter.handleWidth() == scaled_px(6) == 6
        assert shell.content_layout.spacing() == 10

        _apply_factor(qapp, FRACTIONAL_DPR)

        assert shell.splitter.handleWidth() == scaled_px(6) == 8
        margins = shell.content_layout.contentsMargins()
        assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
            10,
            10,
            10,
            10,
        )
        assert shell.content_layout.spacing() == scaled_px(10)

        # Back down: the metrics must return to their 1.0 values, not stick.
        _apply_factor(qapp, 1.0)
        assert shell.splitter.handleWidth() == 6
        margins = shell.content_layout.contentsMargins()
        assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
            8,
            8,
            8,
            8,
        )
    finally:
        shell.close()


def test_a_zero_margin_and_spacing_stay_zero_when_scaled(qapp):
    """``scaled_px`` clamps to ≥1; a 0 margin means "none", not "1 px"."""
    shell = _shown_shell(
        qapp, content_margins=(0, 0, 0, 0), content_spacing=0
    )
    try:
        _apply_factor(qapp, 1.5)
        margins = shell.content_layout.contentsMargins()
        assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
            0,
            0,
            0,
            0,
        )
        assert shell.content_layout.spacing() == 0
    finally:
        shell.close()


def test_splitter_paints_its_own_divider_not_the_style(qapp):
    shell = _shown_shell(qapp)
    try:
        handle = shell.splitter.handle(1)
        assert isinstance(handle, dialog_shell._DialogSplitterHandle)
    finally:
        shell.close()


@pytest.mark.parametrize("dpr", [1.0, FRACTIONAL_DPR, 1.5, 2.0])
def test_divider_line_is_exactly_one_device_pixel_wide(qapp, _light_theme, dpr):
    """One crisp device column at every ratio, with a gap on both sides.

    The style line at a fractional ratio covers two columns of blended
    colour — that is the "thick divider on the group border" the owner saw.
    """
    shell = _shown_shell(qapp)
    try:
        handle = shell.splitter.handle(1)
        image = _paint_handle(handle, dpr)
        row = image.height() // 2
        columns = [
            QColor(image.pixel(x, row)).name() for x in range(image.width())
        ]
        surface = columns[0]
        painted = [index for index, name in enumerate(columns) if name != surface]

        assert len(painted) == 1, f"expected one device column, got {columns}"
        assert painted[0] not in (0, len(columns) - 1), (
            f"the divider sits on the handle edge at DPR {dpr}: {columns}"
        )
        # Crisp, not blended: the column is the border token itself.
        border = _light_theme.get_color("dialog.border").name()
        assert columns[painted[0]] == border, (
            f"divider is anti-aliased at DPR {dpr}: {columns}"
        )
    finally:
        shell.close()


def test_hairline_rect_lands_on_a_whole_device_column():
    """The geometry helper, independent of any widget/style."""
    for dpr in (1.0, FRACTIONAL_DPR, 1.5, 2.0):
        rect = dialog_shell._hairline_rect(
            extents=8.0, length=40.0, dpr=dpr, vertical=True
        )
        left_device = rect.left() * dpr
        right_device = rect.right() * dpr
        assert left_device == pytest.approx(round(left_device))
        assert right_device - left_device == pytest.approx(1.0)


def test_scroll_page_minimum_width_includes_its_content(qapp):
    """The right column's content width must reach the page's minimum.

    A stock ``QScrollArea`` reports ~68×68 regardless of its widget, so the
    column was allowed to shrink under its own content.
    """
    page = ScrollableDialogPage()
    page.content_layout.addWidget(_build_content_column())

    content_width = page.content_widget.minimumSizeHint().width()
    scrollbar = page.scroll_area.verticalScrollBar().sizeHint().width()
    hint = page.minimumSizeHint()

    assert content_width > 400
    assert hint.width() >= content_width + scrollbar
    assert hint.width() > 68
    # Height stays scrollable: only the width is a hard requirement.
    assert hint.height() == page.scroll_area.minimumSizeHint().height()


def test_shell_minimum_width_reserves_the_content_column(qapp):
    """End to end: the divider cannot be squeezed onto the group border."""
    shell = _shown_shell(qapp, sidebar_width=200)
    try:
        page = ScrollableDialogPage()
        page.content_layout.addWidget(_build_content_column())
        shell.pages_stack.addWidget(page)
        qapp.processEvents()

        content_width = page.content_widget.minimumSizeHint().width()
        margins = shell.content_layout.contentsMargins()
        required = (
            shell.sidebar.minimumWidth()
            + shell.splitter.handleWidth()
            + content_width
            + margins.left()
            + margins.right()
        )
        assert shell.minimumSizeHint().width() >= required, (
            "the right column still takes part in no minimum"
        )
        # The nav column is not the whole story either: no horizontal
        # squeeze is allowed while the handle + content fit.
        assert shell.minimumSizeHint().width() > shell.sidebar.minimumWidth() + 100
    finally:
        shell.close()
