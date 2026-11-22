"""`ConsoleView` follow-the-tail and clipped-edge fade.

Owner, 2026-11-22: "при достижении низа скролла, пусть само постоянно держит этот скролл" and a fade at the edge where
the content continues. Both are behaviours, so both are asserted as gestures: the view pins itself at the bottom while
new lines arrive, scrolling away detaches it, scrolling back re-attaches it, and the fade reports which edges are
actually cut.
"""

from __future__ import annotations

import pytest

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.composite.console_view import ConsoleView


@pytest.fixture(autouse=True)
def _palettes(qapp):
    manager = ThemeManager.get_instance()
    manager.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    manager.set_theme(FLUENT_DARK)
    yield
    manager.set_theme(FLUENT_LIGHT)


def _console(qapp, lines: int = 200) -> ConsoleView:
    view = ConsoleView()
    view.resize(320, 120)
    view.show()
    for index in range(lines):
        view.append(f"line {index}")
    qapp.processEvents()
    return view


def test_a_log_started_empty_follows_its_tail(qapp):
    view = _console(qapp)
    assert view.auto_follow() is True
    assert view.is_at_bottom() is True

    view.append_lines([f"more {i}" for i in range(20)])
    qapp.processEvents()
    assert view.is_at_bottom() is True, "the tail stays in view while the user has not touched the scroll"


def test_scrolling_away_detaches_and_scrolling_back_reattaches(qapp):
    view = _console(qapp)
    view.set_scroll_value(0)
    qapp.processEvents()
    assert view.auto_follow() is False
    assert view.is_at_bottom() is False

    view.append("while scrolled up")
    assert view.scroll_value() == 0, "the user's position is not stolen by new lines"

    view.set_scroll_value(view._vbar.maximum())
    qapp.processEvents()
    assert view.auto_follow() is True

    view.append("back at the bottom")
    qapp.processEvents()
    assert view.is_at_bottom() is True, "reaching the bottom re-arms the sticky follow"


def test_set_auto_follow_is_the_explicit_switch(qapp):
    view = _console(qapp)
    view.set_auto_follow(False)
    assert view.auto_follow() is False
    assert view.is_at_bottom() is True, "disabling the follow does not move the view by itself"

    view.set_auto_follow(True)
    assert view.is_at_bottom() is True


def test_the_fade_reports_the_edges_that_are_actually_cut(qapp):
    view = _console(qapp)
    assert view.edge_fade_enabled() is False, "opt-in: a host decides"

    view.set_edge_fade_enabled(True)
    assert view.edge_fade_enabled() is True
    assert view.edge_fade_sides() == (True, False), "at the bottom only the top edge continues"

    view.set_scroll_value(0)
    assert view.edge_fade_sides() == (False, True), "at the top only the bottom edge continues"

    view.set_edge_fade_enabled(False)
    assert view.edge_fade_enabled() is False


def test_content_that_fits_has_no_edge_to_fade(qapp):
    view = ConsoleView()
    view.resize(320, 300)
    view.show()
    view.append("one line")
    qapp.processEvents()
    view.set_edge_fade_enabled(True)
    assert view.edge_fade_sides() == (False, False)
