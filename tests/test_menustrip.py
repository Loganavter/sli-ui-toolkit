"""MenuStrip: title-bar menu triggers over the shared ContextMenu model.

Covers the contract the widget exists for: triggers render their titles,
a trigger opens the dropdown for its own entries (rows keep shortcut /
disabled / danger / section / submenu semantics from ``ContextMenuEntry``),
one menu is open at a time, ``reveal`` targets the owning menu, and the
keyboard paths (Left/Right between triggers, Down/Enter open, Esc closes)
work both with a host-registered navigation section and without one.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection
from sli_ui_toolkit.widgets import (
    ContextMenuAction,
    ContextMenuSection,
    ContextMenuSeparator,
    MenuStrip,
    MenuStripMenu,
)


def _make_strip(qtbot, menus=()):
    """A shown host with one strip; returns (host, strip)."""
    host = QWidget()
    host.resize(900, 600)
    layout = QVBoxLayout(host)
    strip = MenuStrip(host)
    layout.addWidget(strip)
    layout.addStretch(1)
    qtbot.addWidget(host)
    if menus and isinstance(menus[0], MenuStripMenu):
        strip.set_menus(menus)
    else:
        for title, entries in menus:
            strip.add_menu(title, entries)
    host.show()
    qtbot.waitExposed(host)
    return host, strip


def _open_via_click(qapp, strip, index=0):
    QTest.mouseClick(strip._triggers[index], Qt.MouseButton.LeftButton)
    qapp.processEvents()
    return strip.current_menu()


FILE_ENTRIES = (
    ContextMenuAction("file.new", "New", shortcut="Ctrl+N"),
    ContextMenuAction("file.open", "Open…", shortcut="Ctrl+O"),
    ContextMenuAction("file.save", "Save", enabled=False),
    ContextMenuSeparator(),
    ContextMenuAction("file.quit", "Quit", danger=True),
)

HELP_ENTRIES = (ContextMenuAction("help.about", "About"),)


# ---------------------------------------------------------------------------
# public surface / content
# ---------------------------------------------------------------------------


def test_menu_strip_is_public():
    from sli_ui_toolkit import widgets

    assert widgets.MenuStrip is MenuStrip
    assert widgets.MenuStripMenu is MenuStripMenu
    assert "MenuStrip" in widgets.__all__
    assert "MenuStripMenu" in widgets.__all__


def test_triggers_render_at_their_titles(qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES), ("Help", HELP_ENTRIES)])

    assert strip.menu_titles() == ["File", "Help"]
    assert [trigger._text for trigger in strip._triggers] == ["File", "Help"]
    assert all(trigger.isVisible() for trigger in strip._triggers)


def test_set_menus_accepts_specs_and_pairs(qtbot):
    _host, strip = _make_strip(
        qtbot,
        [
            MenuStripMenu(title="View", entries=(ContextMenuAction("view.zoom", "Zoom"),)),
            ("Help", HELP_ENTRIES),
        ],
    )

    assert strip.menu_titles() == ["View", "Help"]
    assert strip.menu_count() == 2


def test_invalid_surface_is_rejected(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    with pytest.raises(ValueError):
        MenuStrip(host, surface="floating")


def test_click_opens_menu_with_its_rows(qapp, qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES), ("Help", HELP_ENTRIES)])

    menu = _open_via_click(qapp, strip, 0)

    assert menu is not None and menu.isVisible()
    assert [row._text for row in menu._rows] == ["New", "Open…", "Save", "Quit"]
    assert menu._rows[0]._shortcut_text == "Ctrl+N"
    assert menu._rows[1]._shortcut_text == "Ctrl+O"
    assert menu._rows[2].isEnabled() is False
    assert menu._rows[3]._danger is True
    # One separator between Save and Quit: 4 action rows + 1 separator.
    assert menu.content_layout.count() == 5


def test_section_renders_title_and_rows(qapp, qtbot):
    entries = (
        ContextMenuAction("view.zoom", "Zoom"),
        ContextMenuSection(
            entries=(ContextMenuAction("view.panel", "Panel"),),
            title="Layout",
        ),
    )
    _host, strip = _make_strip(qtbot, [("View", entries)])

    menu = _open_via_click(qapp, strip, 0)

    assert [row._text for row in menu._rows] == ["Zoom", "Panel"]
    titles = [
        item._text
        for item in menu.container.findChildren(QWidget)
        if type(item).__name__ == "SectionTitleRow"
    ]
    assert titles == ["Layout"]


def test_submenu_entry_reuses_context_menu_model(qapp, qtbot):
    entries = (
        ContextMenuAction(
            "view.zoom",
            "Zoom",
            children=(ContextMenuAction("view.zoom.in", "Zoom In"),),
        ),
    )
    _host, strip = _make_strip(qtbot, [("View", entries)])

    menu = _open_via_click(qapp, strip, 0)

    assert menu is not None
    assert menu._rows[0]._has_children is True
    # Opening the branch materialises the reused child model.
    QTest.mouseClick(menu._rows[0], Qt.MouseButton.LeftButton)
    qapp.processEvents()
    branch = menu._open_submenu
    assert branch is not None
    assert [row._text for row in branch._rows] == ["Zoom In"]


# ---------------------------------------------------------------------------
# one menu at a time / closing
# ---------------------------------------------------------------------------


def test_only_one_menu_open_at_a_time(qapp, qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES), ("Help", HELP_ENTRIES)])

    file_menu = _open_via_click(qapp, strip, 0)
    assert file_menu is not None
    closed: list[bool] = []
    file_menu.aboutToHide.connect(lambda: closed.append(True))

    help_menu = _open_via_click(qapp, strip, 1)

    assert help_menu is not None and help_menu is not file_menu
    assert strip.current_menu() is help_menu
    assert strip._open_index == 1
    assert closed == [True], "opening the second menu must close the first"


def test_clicking_the_open_trigger_closes_it(qapp, qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES)])

    assert _open_via_click(qapp, strip, 0) is not None

    QTest.mouseClick(strip._triggers[0], Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert strip.current_menu() is None


def test_outside_click_closes(qapp, qtbot):
    host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES)])
    assert _open_via_click(qapp, strip, 0) is not None

    QTest.mouseClick(host, Qt.MouseButton.LeftButton, pos=QPoint(10, 400))
    qapp.processEvents()

    assert strip.current_menu() is None


def test_action_click_emits_id_and_data(qapp, qtbot):
    calls: list[tuple[str, object]] = []
    per_menu: list[tuple[str, object]] = []
    entries = (ContextMenuAction("file.new", "New", data={"cmd": "new"}),)
    _host, strip = _make_strip(qtbot, [("File", entries)])
    strip.actionTriggered.connect(lambda action_id, data: calls.append((action_id, data)))
    strip._menus[0].on_triggered = lambda action_id, data: per_menu.append((action_id, data))

    menu = _open_via_click(qapp, strip, 0)
    QTest.mouseClick(menu._rows[0], Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert calls == [("file.new", {"cmd": "new"})]
    assert per_menu == [("file.new", {"cmd": "new"})]
    assert strip.current_menu() is None


# ---------------------------------------------------------------------------
# reveal
# ---------------------------------------------------------------------------


def test_reveal_opens_the_owning_menu(qapp, qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES), ("Help", HELP_ENTRIES)])

    row = strip.reveal("help.about")

    assert strip.current_menu() is not None
    assert strip._open_index == 1
    assert row is not None and row.action_id == "help.about"
    assert row._pulse is True


def test_reveal_switches_from_another_menu(qapp, qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES), ("Help", HELP_ENTRIES)])
    assert _open_via_click(qapp, strip, 0) is not None

    row = strip.reveal("help.about", pulse=False)

    assert strip._open_index == 1
    assert row is not None and row.action_id == "help.about"
    assert row._pulse is False


def test_reveal_unknown_action_is_a_no_op(qapp, qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES)])

    assert strip.reveal("nope.missing") is None
    assert strip.current_menu() is None


def test_reveal_submenu_child_opens_the_owner_menu(qapp, qtbot):
    entries = (
        ContextMenuAction(
            "view.zoom",
            "Zoom",
            children=(ContextMenuAction("view.zoom.in", "Zoom In"),),
        ),
    )
    _host, strip = _make_strip(qtbot, [("View", entries)])

    row = strip.reveal("view.zoom.in")

    # The child row does not exist until the branch opens, but the owning
    # menu must still come up.
    assert row is None
    assert strip.current_menu() is not None
    assert strip._open_index == 0


def test_pulse_decays(qapp, qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES)])
    menu = _open_via_click(qapp, strip, 0)
    row = menu._rows[0]

    row.pulse(duration_ms=20)
    assert row._pulse is True

    qtbot.wait(80)
    assert row._pulse is False


# ---------------------------------------------------------------------------
# keyboard
# ---------------------------------------------------------------------------


def test_navigation_section_owns_the_strip(qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES), ("Help", HELP_ENTRIES)])

    section = strip.navigation_section()

    assert isinstance(section, ToolbarRowsSection)
    assert section.owns(strip._triggers[0])
    assert Qt.Key.Key_Left in section.extra_keys
    assert Qt.Key.Key_Right in section.extra_keys


def test_left_right_moves_between_triggers(qapp, qtbot):
    host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES), ("Help", HELP_ENTRIES)])
    NavigationManager.get_instance().register(host, strip.navigation_section())

    strip._triggers[0].setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    assert QApplication.focusWidget() is strip._triggers[0]

    QTest.keyClick(strip._triggers[0], Qt.Key.Key_Right)
    qapp.processEvents()
    assert QApplication.focusWidget() is strip._triggers[1]

    QTest.keyClick(strip._triggers[1], Qt.Key.Key_Left)
    qapp.processEvents()
    assert QApplication.focusWidget() is strip._triggers[0]


def test_down_opens_and_escape_closes_with_a_nav_section(qapp, qtbot):
    host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES), ("Help", HELP_ENTRIES)])
    NavigationManager.get_instance().register(host, strip.navigation_section())

    strip._triggers[1].setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    QTest.keyClick(strip._triggers[1], Qt.Key.Key_Down)
    qapp.processEvents()
    menu = strip.current_menu()
    assert menu is not None, "Down on a trigger must open its menu"
    assert strip._open_index == 1
    assert [row._text for row in menu._rows] == ["About"]

    QTest.keyClick(menu, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert strip.current_menu() is None


def test_down_opens_without_a_nav_section(qapp, qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES)])
    strip._triggers[0].setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    QTest.keyClick(strip._triggers[0], Qt.Key.Key_Down)
    qapp.processEvents()

    assert strip.current_menu() is not None
    assert strip._open_index == 0


def test_enter_opens_the_focused_trigger(qapp, qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES), ("Help", HELP_ENTRIES)])
    strip._triggers[0].setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    QTest.keyClick(strip._triggers[0], Qt.Key.Key_Return)
    qapp.processEvents()

    assert strip.current_menu() is not None
    assert strip._open_index == 0


def test_empty_strip_has_no_navigation_row(qtbot):
    _host, strip = _make_strip(qtbot, [])

    section = strip.navigation_section()

    assert strip.menu_titles() == []
    assert section.focus_first(reason=Qt.FocusReason.OtherFocusReason) is False
    assert section.owns(strip) is False


def test_clear_removes_every_trigger(qapp, qtbot):
    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES), ("Help", HELP_ENTRIES)])
    assert _open_via_click(qapp, strip, 0) is not None

    strip.clear()

    assert strip.menu_titles() == []
    assert strip._triggers == []
    assert strip.current_menu() is None
    assert strip.navigation_section().focus_first(reason=Qt.FocusReason.OtherFocusReason) is False


# ---------------------------------------------------------------------------
# translation keys
# ---------------------------------------------------------------------------


def test_translation_keys_resolve_titles_and_rows(qapp, qtbot):
    translations = {
        "menu.file": "File",
        "action.new": "New",
    }
    host = QWidget()
    layout = QVBoxLayout(host)
    strip = MenuStrip(host)
    layout.addWidget(strip)
    layout.addStretch(1)
    qtbot.addWidget(host)
    strip.set_translator(lambda key, lang: translations[key])
    strip.add_menu(
        "",
        (ContextMenuAction("file.new", "", text_key="action.new"),),
        text_key="menu.file",
    )
    host.show()
    qtbot.waitExposed(host)

    assert strip.menu_titles() == ["File"]
    assert strip._triggers[0]._text == "File"

    translations["menu.file"] = "Файл"
    translations["action.new"] = "Новый"
    strip.retranslate("ru")

    assert strip._triggers[0]._text == "Файл"

    menu = _open_via_click(qapp, strip, 0)
    assert [row._text for row in menu._rows] == ["Новый"]


# -- the trigger label is the menu family's ink --------------------------------
#
# A trigger is a `Button`, whose content layer falls back to `dialog.text`; the
# strip is a menu surface, so it hands the trigger `menu.text` and re-resolves it
# on every theme change (the button variant plate is untouched).

def _pixels_matching(image, colour, tolerance: int = 60) -> int:
    count = 0
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if (
                abs(pixel.red() - colour.red()) <= tolerance
                and abs(pixel.green() - colour.green()) <= tolerance
                and abs(pixel.blue() - colour.blue()) <= tolerance
            ):
                count += 1
    return count


def test_trigger_ink_follows_the_menu_token_on_theme_change(qapp, qtbot):
    from PySide6.QtGui import QColor

    from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager

    manager = ThemeManager.get_instance()
    light = dict(FLUENT_LIGHT)
    light.update({"menu.text": QColor("#00ff00"), "dialog.text": QColor("#0000ff")})
    dark = dict(FLUENT_DARK)
    dark.update({"menu.text": QColor("#ffff00"), "dialog.text": QColor("#0000ff")})
    manager.register_palettes(light, dark)
    manager.set_theme("light", qapp, await_ripples=False)
    manager._flush_pending_theme()

    _host, strip = _make_strip(qtbot, [("File", FILE_ENTRIES)])
    trigger = strip._triggers[0]

    light_ink = trigger.grab().toImage()
    assert _pixels_matching(light_ink, QColor("#00ff00")) > 0, "the trigger label reads `menu.text`"
    assert _pixels_matching(light_ink, QColor("#0000ff")) == 0, "`dialog.text` no longer paints the trigger"

    manager.set_theme("dark", qapp, await_ripples=False)
    manager._flush_pending_theme()
    qapp.processEvents()
    dark_ink = trigger.grab().toImage()
    assert _pixels_matching(dark_ink, QColor("#ffff00")) > 0, "a theme switch re-resolves the trigger ink"
    assert _pixels_matching(dark_ink, QColor("#00ff00")) == 0
