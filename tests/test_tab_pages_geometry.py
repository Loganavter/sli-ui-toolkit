"""`TopTabHost` guarantees the current page's geometry.

`QStackedLayout` in its default `StackOne` mode lays out ONLY the page it shows; every other page keeps whatever size it
had when it was last current. Switch to one of those and it is shown at that stale rect: its content clips at the old
width and the strip that was never covered keeps the previous page's pixels - the host app measured pages at 434x592 and
480x515 inside a 500x571 host, cut exactly at the stale width, healed only by a window resize (RVE, 2026-11-22).

BlinkTable documented the same mechanism and patched it per pane
(`docs/dev/rendering/investigations/ui-inspector-csd-corner-clip.md:80-97`: "the QStackedWidget only lays out the current
page ... the pages were left stale while the window grew/shrunk", fix = force the current page to the stack's size on
every stack Resize). These tests put that guarantee in the host, so no consumer has to repeat it.
"""

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.host import TopTabHost


@pytest.fixture(autouse=True)
def _palettes(qapp):
    manager = ThemeManager.get_instance()
    manager.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    manager.set_theme(FLUENT_DARK)
    yield
    manager.set_theme(FLUENT_LIGHT)


def _host(qapp, pages: int = 3, size=(500, 400)):
    host = TopTabHost()
    host.resize(*size)
    host.show()
    made = []
    for index in range(pages):
        page = QWidget()
        host.addTab(page, f"P{index}")
        made.append(page)
    for _ in range(6):
        qapp.processEvents()
    return host, made


def test_a_page_that_was_never_current_is_fitted_when_it_is_shown(qapp):
    host, pages = _host(qapp)
    stack_rect = host.pages_stack.contentsRect()

    assert pages[0].size() == stack_rect.size(), "the page the stack shows is laid out by Qt anyway"

    for index in (2, 1):
        host.setCurrentIndex(index)
        for _ in range(4):
            qapp.processEvents()
        assert pages[index].size() == stack_rect.size(), (
            f"page {index} was shown at a stale size: {pages[index].size().toTuple()} instead of "
            f"{stack_rect.size().toTuple()} - its content would clip at the old width"
        )


def test_a_page_created_while_another_is_current_is_fitted_later(qapp):
    host, pages = _host(qapp, pages=2)
    late = QWidget()
    host.addTab(late, "Late")
    for _ in range(4):
        qapp.processEvents()

    host.setCurrentIndex(host.indexOf(late))
    for _ in range(4):
        qapp.processEvents()
    assert late.size() == host.pages_stack.contentsRect().size()


def test_a_stack_resize_reaches_every_page_not_only_the_current_one(qapp):
    """The inspector pane's idiom (ui/inspector/view.py:108-128): resize ALL pages and settle each.

    Sizing only the page Qt happens to show is what left the others at their creation size, and a hidden page that is
    later shown paints clipped at that old width.
    """
    host, pages = _host(qapp)
    host.resize(760, 520)
    for _ in range(6):
        qapp.processEvents()
    stack_size = host.pages_stack.size()
    assert [page.size() for page in pages] == [stack_size] * len(pages), (
        "a stack resize must reach every page"
    )


def test_a_page_with_a_scroll_area_is_settled_not_just_resized(qapp):
    """A page whose scroll area caches a sizeHint would otherwise open one frame stale (`settle_layout`)."""
    from PySide6.QtWidgets import QScrollArea, QVBoxLayout

    host = TopTabHost()
    host.resize(520, 420)
    host.show()
    plain = QWidget()
    scrolling = QWidget()
    box = QVBoxLayout(scrolling)
    area = QScrollArea()
    inner = QWidget()
    inner.setMinimumWidth(300)
    area.setWidget(inner)
    box.addWidget(area)
    host.addTab(plain, "Plain")
    host.addTab(scrolling, "Scrolling")
    for _ in range(6):
        qapp.processEvents()

    page_before, area_before = scrolling.width(), area.width()
    host.resize(760, 520)
    for _ in range(6):
        qapp.processEvents()

    assert scrolling.size() == host.pages_stack.size()
    # Margin-independent: the scroll area must absorb the page's growth in the SAME call (that is what settling the
    # page's layout buys - without it the area keeps the opening-time width until the next event-loop turn).
    assert scrolling.width() > page_before, "the page itself grew"
    margins = scrolling.layout().contentsMargins()
    expected = scrolling.contentsRect().width() - margins.left() - margins.right()
    assert area.width() == expected, (
        f"the page's own layout did not re-run with the resize: the scroll area is {area.width()} px wide where the "
        f"page's content rect allows {expected}"
    )
    assert area.width() != area_before, "the scroll area kept the opening-time width (unsettled layout)"
