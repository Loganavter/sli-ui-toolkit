"""ListPanel's plate is neutral chrome: `surface.background` fill + `separator.color` hairline.

Before the migration the frame borrowed `flyout.border`: a list panel is not a
flyout, and the list family owns no border key, so the shared separator hairline
owns the edge instead. The token-ownership gate no longer reports the panel.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.composite.list_panel import ListPanel


class _Row(QLabel):
    itemSelected = Signal(int)
    itemSelectionToggled = Signal(int)
    itemRightClicked = Signal(int)

    def __init__(self, spec):
        super().__init__()
        self.index = spec.index
        self.full_path = ""
        self.is_current = False
        self.position = spec.position
        self.name_label = self

    def set_selected(self, selected):
        self.is_selected = selected

    def set_dragging_state(self, dragging):
        pass


def _panel(qtbot):
    """Build a panel and return ``(host, panel)`` — the host keeps the C++ child alive."""
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 400)
    panel = ListPanel(
        list_num=1,
        item_height=36,
        item_font=None,
        get_current_index=lambda n: 0,
        on_item_selected=lambda *a: None,
        on_item_context_menu=lambda *a: None,
        on_reorder=lambda *a: None,
        on_move_between_lists=lambda *a: None,
        on_update_drop_indicator=lambda *a: None,
        on_clear_drop_indicator=lambda *a: None,
        parent=host,
    )
    panel.set_row_factory(lambda spec: _Row(spec))
    panel.resize(220, 160)
    panel.show()
    qtbot.waitExposed(panel)
    return host, panel


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_panel_frame_is_the_neutral_separator_hairline(qapp, qtbot, theme):
    manager = ThemeManager.get_instance()
    # Unmistakable edge colours: `flyout.border` is the token the panel used to borrow.
    edge = QColor("#ff0000")
    borrowed = QColor("#0000ff")

    def _palette(base):
        palette = dict(base)
        palette.update(
            {
                "surface.background": QColor("#ffffff"),
                "separator.color": edge,
                "flyout.border": borrowed,
            }
        )
        return palette

    manager.register_palettes(_palette(FLUENT_LIGHT), _palette(FLUENT_DARK))
    manager.set_theme(theme, qapp, await_ripples=False)
    manager._flush_pending_theme()  # type: ignore[attr-defined]
    qapp.processEvents()

    host, panel = _panel(qtbot)  # the host reference keeps the child's C++ object alive
    assert host is panel.parentWidget()
    image = panel.grab().toImage()
    frame = image.pixelColor(0, panel.height() // 2)

    assert frame.red() > 180, f"{theme}: the frame is the separator hairline, got {frame.name()}"
    assert frame.blue() < frame.red() - 60, f"{theme}: the frame must not read flyout.border ({borrowed.name()})"
