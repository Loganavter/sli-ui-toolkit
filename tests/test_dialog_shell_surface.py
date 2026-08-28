"""ScrollableDialogPage paints its scroll surface with the
``dialog.background`` token — not the raw QPalette Window role.

Hosts keep ``Window`` darker than the dialog surface token (the app's dark
palette: Window ``#1e1e1e`` vs ``dialog.background`` ``#2b2b2b``); with a
host QSS active, stock viewport/content QWidgets auto-fill the Window role,
so the empty page area rendered near-black against the gray panels.

A per-widget palette is NOT enough here: ``QStyle::polish`` at ``show()``
(and on any host stylesheet re-apply) resets widget palettes to the app
palette. The surface is therefore set as a widget-level ``background-color``
stylesheet on the scroll area (survives polish), re-tinted on
``theme_changed``.
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
    assert "background-color: #222222;" in page.scroll_area.styleSheet()


def test_page_surface_survives_polish_on_show(qapp, qtbot, themed):
    """QStyle::polish at show() resets widget palettes — the stylesheet
    must survive it, or the page falls back to the dark Window role."""
    page = ScrollableDialogPage()
    qtbot.addWidget(page)
    page.show()
    qapp.processEvents()
    assert "background-color: #222222;" in page.scroll_area.styleSheet()


def test_page_surface_re_tints_on_theme_switch(qapp, qtbot, themed):
    page = ScrollableDialogPage()
    qtbot.addWidget(page)
    themed.set_theme("dark", qapp, await_ripples=False)
    themed._flush_pending_theme()  # type: ignore[attr-defined]
    assert "background-color: #333333;" in page.scroll_area.styleSheet()