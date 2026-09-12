"""IconListWidget paints its surface with the ``dialog.background`` token
— not the QPalette Window role.

IconListWidget is a custom QWidget subclass, so Qt never sets
``WA_StyledBackground`` for it and application-QSS background rules
(``#SettingsSidebar { background-color: ... }``) silently no-op — the list
then renders the QPalette Window role, which hosts keep darker than the
dialog surface token (dark Window ``#1e1e1e`` vs ``dialog.background``
``#2b2b2b``). The list therefore paints its own background from the token
in ``paintEvent`` (THEMING.md's explicit-paint pattern), re-tinted on
``theme_changed`` — the same surface ownership as ``ScrollableDialogPage``.
"""

from __future__ import annotations

import pytest

from sli_ui_toolkit import ThemeManager
from sli_ui_toolkit.widgets import IconListWidget

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


def _grab_pixel_color(widget):
    return widget.grab().toImage().pixelColor(2, 2)


def test_icon_list_surface_paints_dialog_background_token(qapp, qtbot, themed):
    widget = IconListWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 300)
    assert _grab_pixel_color(widget).name() == "#222222"


def test_icon_list_surface_survives_polish_on_show(qapp, qtbot, themed):
    """QStyle::polish at show() resets widget palettes — the painted
    surface must not fall back to the (near-black) Window role."""
    widget = IconListWidget()
    qtbot.addWidget(widget)
    widget.show()
    qapp.processEvents()
    widget.resize(200, 300)
    assert _grab_pixel_color(widget).name() == "#222222"


def test_icon_list_surface_re_tints_on_theme_switch(qapp, qtbot, themed):
    widget = IconListWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 300)
    assert _grab_pixel_color(widget).name() == "#222222"

    themed.set_theme("dark", qapp, await_ripples=False)
    themed._flush_pending_theme()  # type: ignore[attr-defined]
    assert _grab_pixel_color(widget).name() == "#333333"

    themed.set_theme("light", qapp, await_ripples=False)
    themed._flush_pending_theme()  # type: ignore[attr-defined]
    assert _grab_pixel_color(widget).name() == "#222222"


def test_icon_list_refresh_icons_still_fires_on_theme_change(
    qapp, qtbot, themed, monkeypatch
):
    widget = IconListWidget()
    qtbot.addWidget(widget)
    widget.add_item("Settings", icon="settings")

    original = IconListWidget.refresh_icons
    calls = []

    def spy(self):
        calls.append(self)
        return original(self)

    monkeypatch.setattr(IconListWidget, "refresh_icons", spy)

    themed.set_theme("dark", qapp, await_ripples=False)
    themed._flush_pending_theme()  # type: ignore[attr-defined]

    assert widget in calls