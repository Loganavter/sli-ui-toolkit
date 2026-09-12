from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import (
    ContextMenu,
    ContextMenuAction,
    ContextMenuBuilder,
    ContextMenuSeparator,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu.rows import SeparatorRow as _SeparatorRow
from sli_ui_toolkit.ui.widgets.helpers.rounded_clip import RoundedClipEffect


def test_context_menu_is_public():
    from sli_ui_toolkit import widgets

    assert widgets.ContextMenu is ContextMenu
    assert widgets.ContextMenuAction is ContextMenuAction
    assert widgets.ContextMenuBuilder is ContextMenuBuilder


def test_context_menu_is_in_app_widget_not_separate_window(qtbot):
    from sli_ui_toolkit.config import configure_toolkit

    configure_toolkit(context_menu_surface="in_window")
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = ContextMenuBuilder().action("rename", "Rename").build(parent)

    assert not menu.isWindow()
    assert menu.parentWidget() is not None


def test_context_menu_popup_surface_is_window(qtbot):
    from PySide6.QtCore import QPoint

    parent = QWidget()
    parent.resize(640, 480)
    qtbot.addWidget(parent)
    parent.show()

    menu = ContextMenu(
        parent,
        entries=(ContextMenuAction("rename", "Rename"),),
        surface="popup",
    )
    assert menu.isWindow()
    assert menu.is_popup_surface()
    assert menu._logical_parent is parent
    # Keep QWidget parent for Wayland transient positioning (not parentless).
    assert menu.parentWidget() is parent
    assert menu.overlay_layer is None

    cursor = parent.mapToGlobal(QPoint(80, 80))
    menu.popup_at(cursor)
    qtbot.wait(10)
    assert menu.isVisible()
    assert menu.contains_global(cursor) is False
    panel_tl = menu.container.mapToGlobal(QPoint(0, 0))
    inside_panel = panel_tl + QPoint(
        menu.container.width() // 2, menu.container.height() // 2
    )
    assert menu.contains_global(inside_panel) is True
    # Geometry should track the open cursor, not default to screen center.
    assert abs(menu.pos().x() - cursor.x()) <= 8
    assert abs(menu.pos().y() - cursor.y()) <= 8
    menu.hide()


def test_context_menu_builder_creates_rows(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = (
        ContextMenuBuilder()
        .action("rename", "Rename", shortcut="F2")
        .separator()
        .action("remove", "Remove", enabled=False, danger=True)
        .build(parent)
    )

    assert [row._text for row in menu._rows] == ["Rename", "Remove"]
    assert menu._rows[0]._shortcut_text == "F2"
    assert not menu._rows[1].isEnabled()
    assert menu._rows[1]._danger is True


def test_context_menu_trims_duplicate_separators(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = ContextMenu(
        parent,
        entries=[
            ContextMenuSeparator(),
            ContextMenuAction("rename", "Rename"),
            ContextMenuSeparator(),
            ContextMenuSeparator(),
        ],
    )

    separator_rows = [
        menu.content_layout.itemAt(i).widget()
        for i in range(menu.content_layout.count())
        if isinstance(menu.content_layout.itemAt(i).widget(), _SeparatorRow)
    ]
    assert separator_rows == []
    assert [row._text for row in menu._rows] == ["Rename"]


def test_context_menu_submenu_and_trigger_signal(qtbot):
    parent = QWidget()
    parent.resize(400, 300)
    qtbot.addWidget(parent)
    parent.show()
    triggered = []
    menu = ContextMenu(
        parent,
        entries=[
            ContextMenuAction(
                "edit",
                "Edit",
                children=(ContextMenuAction("rename", "Rename", data={"id": 1}),),
            )
        ],
        on_triggered=lambda action_id, data: triggered.append((action_id, data)),
        surface="popup",
    )

    edit_row = menu._rows[0]
    assert edit_row._has_children

    edit_row.clicked.emit()
    submenu = menu._open_submenu
    assert submenu is not None
    assert submenu.isWindow()

    submenu._rows[0].clicked.emit()

    assert triggered == [("rename", {"id": 1})]
    assert not menu.isVisible()


def test_context_menu_flips_above_when_below_does_not_fit(qtbot):
    """Near the window bottom, flip above the anchor instead of sliding over it."""
    from PySide6.QtCore import QPoint

    from sli_ui_toolkit.config import configure_toolkit

    configure_toolkit(context_menu_surface="in_window")
    parent = QWidget()
    parent.resize(480, 200)
    qtbot.addWidget(parent)
    parent.show()

    anchor = QWidget(parent)
    anchor.setGeometry(64, 150, 120, 28)
    anchor.show()

    menu = ContextMenu(
        parent,
        entries=(
            ContextMenuAction("sort.date", "По дате"),
            ContextMenuAction("sort.name", "По имени"),
        ),
    )
    menu.show_aligned(
        anchor,
        anchor_point="bottom-left",
        flyout_point="top-left",
        offset=2,
        animation="none",
    )
    qtbot.wait(10)

    anchor_top = anchor.mapToGlobal(QPoint(0, 0)).y()
    panel_bottom = menu.container.mapToGlobal(
        QPoint(0, menu.container.height())
    ).y()
    # Opaque panel should sit above the button, not through its center.
    assert panel_bottom <= anchor_top + 1
    menu.hide()


def test_context_menu_bottom_left_aligns_visible_panel(qtbot):
    """Shadow halo must not shift the opaque panel right of the anchor."""
    from PySide6.QtCore import QPoint

    from sli_ui_toolkit.config import configure_toolkit

    configure_toolkit(context_menu_surface="in_window")
    parent = QWidget()
    parent.resize(480, 360)
    qtbot.addWidget(parent)
    parent.show()

    anchor = QWidget(parent)
    anchor.setGeometry(64, 48, 120, 28)
    anchor.show()

    menu = ContextMenu(
        parent,
        entries=(
            ContextMenuAction("sort.date", "По дате"),
            ContextMenuAction("sort.name", "По имени"),
        ),
    )
    menu.show_aligned(
        anchor,
        anchor_point="bottom-left",
        flyout_point="top-left",
        offset=2,
        animation="none",
    )
    qtbot.wait(10)

    anchor_left = anchor.mapToGlobal(QPoint(0, 0)).x()
    panel_left = menu.container.mapToGlobal(QPoint(0, 0)).x()
    assert abs(panel_left - anchor_left) <= 1

    anchor_bottom = anchor.mapToGlobal(QPoint(0, anchor.height())).y()
    panel_top = menu.container.mapToGlobal(QPoint(0, 0)).y()
    # offset=2 + shadow=8 → opaque panel clears the button; outer top ≥ button bottom.
    assert panel_top >= anchor_bottom + 2
    assert panel_top <= anchor_bottom + 2 + menu.SHADOW_RADIUS + 1
    assert menu.mapToGlobal(QPoint(0, 0)).y() >= anchor_bottom
    menu.hide()


def test_context_menu_relayout_after_font_change(qtbot):
    from PySide6.QtGui import QFont, QFontMetrics
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()

    entries = [
        ContextMenuAction("file.open_project", "Open Project…"),
        ContextMenuAction("file.save_project", "Save Project…"),
    ]
    menu = ContextMenu(parent, entries=entries)
    menu.show_aligned(parent, "bottom-left", "top-left", animation="none")
    qtbot.wait(10)
    menu.hide()

    app = QApplication.instance()
    larger = QFont(app.font())
    larger.setPointSize(larger.pointSize() + 2)
    app.setFont(larger)

    menu.show_aligned(parent, "bottom-left", "top-left", animation="none")
    qtbot.wait(10)

    open_row = menu._rows[0]
    fm = QFontMetrics(open_row.font())
    available = (
        open_row.width()
        - open_row._check_gutter
        - open_row._trailing_width
        - 12
    )
    elided = fm.elidedText(
        open_row._text, Qt.TextElideMode.ElideRight, available
    )
    assert elided == open_row._text
    assert open_row.width() >= open_row.sizeHint().width()


def test_context_menu_container_uses_rounded_clip(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = ContextMenu(
        parent,
        entries=(ContextMenuAction("a", "One"), ContextMenuAction("b", "Two")),
    )
    effect = menu.container.graphicsEffect()
    assert isinstance(effect, RoundedClipEffect)
    assert effect.radius() == menu.CONTENT_RADIUS


def test_context_menu_row_positions(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = ContextMenu(
        parent,
        entries=(
            ContextMenuAction("a", "One"),
            ContextMenuAction("b", "Two"),
            ContextMenuAction("c", "Three"),
        ),
    )
    assert [row.position for row in menu._rows] == ["first", "middle", "last"]


def test_popup_at_keeps_open_cursor_outside_menu_hitbox(qtbot):
    from PySide6.QtCore import QPoint

    parent = QWidget()
    parent.resize(640, 480)
    qtbot.addWidget(parent)
    parent.show()

    menu = ContextMenu(
        parent,
        entries=(ContextMenuAction("x.remove", "Remove"),),
    )
    cursor = parent.mapToGlobal(QPoint(80, 80))
    menu.popup_at(cursor)
    qtbot.wait(10)

    assert menu.isVisible()
    # Open cursor must not be inside the opaque panel (dismiss hit-test).
    assert menu.contains_global(cursor) is False
    # Shadow halo of the outer widget may still cover the cursor — that is OK
    # as long as contains_global ignores it.
    panel_tl = menu.container.mapToGlobal(QPoint(0, 0))
    inside_panel = panel_tl + QPoint(
        menu.container.width() // 2, menu.container.height() // 2
    )
    assert menu.contains_global(inside_panel) is True

    menu.hide()


def test_popup_fade_snapshot_captured_after_show(qtbot):
    """Fade snapshot of a popup menu must be taken after show().

    Regression: popup_at grabbed the fade cache BEFORE show() — grab() of a
    never-shown top-level window misses content (the shadowed corners of the
    translucent panel), so at fade start the top-left corner looked already
    opaque while the rest faded in.
    """
    from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit

    parent = QWidget()
    parent.resize(900, 700)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitExposed(parent)

    configure_toolkit(timings=FlyoutTimingConfig(default_flyout_animation="fade"))
    try:
        menu = ContextMenu(
            parent,
            entries=(ContextMenuAction("copy", "Copy path"),),
            surface="popup",
        )
        qtbot.addWidget(menu)
        menu.popup_at(menu.mapToGlobal(menu.rect().topLeft()) if False else parent.mapToGlobal(parent.rect().center()))
        qtbot.waitExposed(menu)

        cache = menu._fade.cache
        assert cache is not None and not cache.isNull()
        image = cache.toImage()
        assert image.width() > 0 and image.height() > 0
        # The snapshot must contain opaque panel pixels (menu content), not
        # be an empty/transparent capture of an unmapped window.
        opaque = 0
        for y in range(0, image.height(), 3):
            for x in range(0, image.width(), 3):
                if image.pixelColor(x, y).alpha() > 200:
                    opaque += 1
        assert opaque > 0, (
            "fade snapshot of the popup menu is empty — grab() ran before "
            "the window was shown and missed the content"
        )
    finally:
        from sli_ui_toolkit.config import reset_toolkit_config

        reset_toolkit_config()


def test_submenu_rows_get_the_scaled_ui_font(qtbot):
    """Submenu rows must carry the scale-resolved UI font, not the inherited one.

    Regression (live in Improve-ImgSLI): the tab-strip context menu's "New
    Tab" submenu rendered its rows at the unscaled inherited font (12pt
    while the parent menu rows were at 24pt) — the constructor's
    set_entries -> _relayout_widths pass did not stick in that host, and a
    second pass before show does.
    """
    from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit
    from sli_ui_toolkit.managers import UiScale
    from sli_ui_toolkit.ui.managers.ui_font import ui_font

    configure_toolkit(timings=FlyoutTimingConfig(default_flyout_animation="none"))
    parent = QWidget()
    parent.resize(900, 700)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitExposed(parent)

    try:
        UiScale.get_instance().set_factor(2.0)
        menu = ContextMenu(
            parent,
            entries=(
                ContextMenuAction(
                    "new",
                    "New Tab",
                    children=(
                        ContextMenuAction("new.image_compare", "Image Compare"),
                        ContextMenuAction("new.multi_compare", "Multi Compare"),
                    ),
                ),
            ),
            surface="popup",
        )
        qtbot.addWidget(menu)
        menu.popup_at(parent.mapToGlobal(parent.rect().center()))
        menu._rows[0].click()
        qtbot.wait(10)

        sub = menu._open_submenu
        assert sub is not None, "clicking the parent row must open the submenu"
        expected = ui_font().pointSizeF()
        for row in sub._rows:
            assert row.font().pointSizeF() == expected, (
                f"submenu row {row._text!r} font {row.font().pointSizeF()}pt "
                f"is not the scale-resolved {expected}pt (inherited design "
                "font leaked into the submenu)"
            )
    finally:
        UiScale.get_instance().set_factor(1.0)
