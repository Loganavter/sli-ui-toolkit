"""ScrollableDialogPage paints its scroll surface with the
``dialog.background`` token — not the raw QPalette Window role.

Hosts keep ``Window`` darker than the dialog surface token (the app's dark
palette: Window ``#1e1e1e`` vs ``dialog.background`` ``#2b2b2b``); the stock
viewport/content QWidgets auto-fill the Window role when a host QSS is
active, so the empty page area rendered near-black against the gray panels.
"""

from __future__ import annotations

import pytest
from sli_ui_toolkit import ThemeManager
from sli_ui_toolkit.widgets import ScrollableDialogPage

_LIGHT = {"Window": "#000000", "surface.background": "#222222"}
_DARK = {"Window": "#000000", "surface.background": "#333333"}


@pytest.fixture
def themed(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(_LIGHT, _DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    yield tm
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]


def test_page_surface_paints_dialog_background_token(qapp, qtbot, themed):
    page = ScrollableDialogPage()
    qtbot.addWidget(page)
    assert page.scroll_area.viewport().palette().window().color().name() == "#222222"
    assert page.scroll_area.viewport().autoFillBackground()
    assert page.content_widget.palette().window().color().name() == "#222222"
    assert page.content_widget.autoFillBackground()


def test_page_surface_re_tints_on_theme_switch(qapp, qtbot, themed):
    page = ScrollableDialogPage()
    qtbot.addWidget(page)
    viewport = page.scroll_area.viewport()
    themed.set_theme("dark", qapp, await_ripples=False)
    themed._flush_pending_theme()  # type: ignore[attr-defined]
    assert viewport.palette().window().color().name() == "#333333"
    assert page.content_widget.palette().window().color().name() == "#333333"