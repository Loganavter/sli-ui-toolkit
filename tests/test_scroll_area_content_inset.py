"""`content_inset` — the stock frame inset a QScrollArea has and an overlay area did not.

Measured on a host migration: ``QScrollArea``'s default ``StyledPanel`` frame shrinks the viewport by one pixel on every
side, so replacing it with ``OverlayScrollArea`` (which sets ``NoFrame`` and owns ``setViewportMargins`` for its bar)
widened the content from 1008 to 1010 px and shifted every child - a 2.5 % whole-page pixel deviation with no style
difference at all. The knob reproduces the stock geometry; the tests pin that it insets all four sides, that it adds to
(not replaces) the bar's reserved margin, and that the default is unchanged.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import OverlayScrollArea, SurfaceScrollArea


def _area(cls=OverlayScrollArea, **options) -> OverlayScrollArea:
    area = cls(**options)
    content = QWidget()
    content.setMinimumSize(200, 2000)  # force vertical overflow so a margin would be reserved
    area.setWidget(content)
    area.resize(300, 200)
    area.show()
    area._update_scrollbar_visibility()
    return area


def test_default_inset_is_zero(qapp):
    area = _area()
    assert area.viewportMargins().left() == 0
    assert area.viewportMargins().top() == 0


def test_inset_shrinks_the_viewport_on_all_four_sides(qapp):
    plain = _area()
    inset = _area(content_inset=1)
    assert inset.viewport().width() == plain.viewport().width() - 2
    assert inset.viewport().height() == plain.viewport().height() - 2
    margins = inset.viewportMargins()
    assert (margins.left(), margins.top()) == (1, 1)


def test_inset_adds_to_the_reserved_bar_margin(qapp):
    reserve = _area(reserve_scrollbar_space=True, scrollbar_width=10)
    with_inset = _area(reserve_scrollbar_space=True, scrollbar_width=10, content_inset=1)
    # The bar keeps its own gutter; the inset sits between the frame and it.
    assert with_inset.viewportMargins().right() == reserve.viewportMargins().right() + 1


def test_surface_scroll_area_forwards_the_option(qapp):
    area = _area(cls=SurfaceScrollArea, surface_token=None, content_inset=1)
    assert area.viewportMargins().left() == 1


def test_an_overlay_area_paints_nothing_behind_its_content(qapp):
    # The stock area this replaces was transparent through the page's stylesheet; deleting that stylesheet revealed the
    # palette `Window` role on half a migrated page (measured). Both the viewport and the content widget stay unpainted.
    area = _area()
    assert area.viewport().autoFillBackground() is False
    assert area.widget().autoFillBackground() is False


def test_surface_scroll_area_still_pins_after_a_widget_swap(qapp):
    area = _area(cls=SurfaceScrollArea, surface_token=None)
    replacement = QWidget()
    replacement.setMinimumSize(200, 2000)
    area.setWidget(replacement)
    assert replacement.autoFillBackground() is False
