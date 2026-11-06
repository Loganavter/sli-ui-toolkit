"""Host may own the horizontal axis: the overlay thumb is opt-out.

A host that draws its own horizontal control (the video editor's timeline
does, in its footer bar) must not get a second auto-hiding thumb from the
scroll area. ``set_horizontal_scrollbar_enabled(False)`` removes the
overlay thumb and its reserved bottom margin while leaving the native
``QAbstractScrollArea`` horizontal scrollbar — the actual scrolling
mechanism — fully functional. Default stays unchanged: every other host
keeps the two-bar behaviour.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.widgets import SurfaceScrollArea


def _settle() -> None:
    for _ in range(3):
        QApplication.processEvents()


def _make_area(qtbot, content_w: int, content_h: int, area_w: int = 300, area_h: int = 200):
    area = SurfaceScrollArea()
    qtbot.addWidget(area)
    content = QWidget()
    content.setFixedSize(content_w, content_h)
    area.setWidget(content)
    area.resize(area_w, area_h)
    area.show()
    qtbot.waitExposed(area)
    _settle()
    return area, content


def test_default_still_shows_the_overlay_h_thumb(qtbot):
    """The opt-in flag must not change today's behaviour for every host."""
    area, _content = _make_area(qtbot, 600, 100)
    assert area.horizontal_scrollbar_enabled() is True
    assert area.horizontalScrollBar().maximum() > area.horizontalScrollBar().minimum()
    assert area.custom_h_scrollbar.isVisible()
    qtbot.waitUntil(
        lambda: area.viewportMargins().bottom() == area.scrollbar_width(),
        timeout=2000,
    )
    assert area.overlay_horizontal_scrollbar_inset() == 0  # reserved, not floating


def test_flag_off_hides_the_thumb_and_reserves_no_margin(qtbot):
    area, _content = _make_area(qtbot, 600, 100)
    area.set_horizontal_scrollbar_enabled(False)
    _settle()
    assert area.horizontal_scrollbar_enabled() is False
    assert not area.custom_h_scrollbar.isVisible()
    assert area.viewportMargins().bottom() == 0
    assert area.overlay_horizontal_scrollbar_inset() == 0
    # The native bar is still the scrolling mechanism: its range survives
    # and it can be driven programmatically.
    native = area.horizontalScrollBar()
    assert native.maximum() > native.minimum()
    native.setValue(40)
    _settle()
    assert native.value() == 40


def test_flag_off_thumb_stays_hidden_after_scroll_activity(qtbot):
    """Value changes re-show an auto-hiding bar — the owner's flag outranks it."""
    area, _content = _make_area(qtbot, 600, 100)
    area.set_horizontal_scrollbar_enabled(False)
    _settle()
    native = area.horizontalScrollBar()
    for value in (10, 80, 0):
        native.setValue(value)
        _settle()
        assert native.value() == value
        assert not area.custom_h_scrollbar.isVisible()
    # A persistent-bar policy must not resurrect a host-owned axis either.
    area.set_scrollbar_auto_hide(None)
    native.setValue(60)
    _settle()
    assert not area.custom_h_scrollbar.isVisible()
    assert area.viewportMargins().bottom() == 0


def test_vertical_overlay_thumb_is_unaffected_by_the_horizontal_flag(qtbot):
    area, _content = _make_area(qtbot, 600, 600)
    area.set_horizontal_scrollbar_enabled(False)
    _settle()
    assert area.verticalScrollBar().maximum() > area.verticalScrollBar().minimum()
    assert area.custom_v_scrollbar.isVisible()
    assert not area.custom_h_scrollbar.isVisible()
    qtbot.waitUntil(
        lambda: area.viewportMargins().right() == area.scrollbar_width(),
        timeout=2000,
    )


def test_re_enabling_restores_the_thumb_and_its_margin(qtbot):
    area, _content = _make_area(qtbot, 600, 100)
    area.set_horizontal_scrollbar_enabled(False)
    _settle()
    assert not area.custom_h_scrollbar.isVisible()

    area.set_horizontal_scrollbar_enabled(True)
    qtbot.waitUntil(area.custom_h_scrollbar.isVisible, timeout=2000)
    qtbot.waitUntil(
        lambda: area.viewportMargins().bottom() == area.scrollbar_width(),
        timeout=2000,
    )
    area.horizontalScrollBar().setValue(25)
    _settle()
    assert area.horizontalScrollBar().value() == 25
