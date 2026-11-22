"""A host can build its own tab widgets; the bar only wires them.

Without the factory the strip constructed its own button, so every visual detail was a knob inside the widget (and a
plate on the button's full rect had its bottom corners cut by the pane - measured on a host's strip).
"""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import Button, TabStyle, TopTabHost


def _factory(text: str, tab_height: int, style):
    tab = Button(text=text or " ", toggle=True, size=(0, max(1, tab_height - 6)))
    return tab


def test_the_host_factory_builds_the_tab_buttons(qapp):
    host = TopTabHost(tab_factory=_factory)
    host.addTab(QWidget(), "one")
    host.addTab(QWidget(), "two")
    host.resize(400, 200)
    host.show()
    qapp.processEvents()

    buttons = [tab.button for tab in host.tab_bar._tabs]
    assert len(buttons) == 2
    assert all(isinstance(button, Button) for button in buttons), "the bar built its own button instead of the host's"
    assert all(button.height() == host.tab_bar._scaled_tab_height() - 6 for button in buttons), (
        "the bar forced its strip height onto the host's button"
    )


def test_the_bar_still_tracks_the_selection_on_a_host_button(qapp):
    host = TopTabHost(tab_factory=_factory)
    for label in ("a", "b"):
        host.addTab(QWidget(), label)
    host.show()
    qapp.processEvents()
    host.tab_bar.setCurrentIndex(1)
    qapp.processEvents()
    assert host.tab_bar._tabs[1].button.isChecked()
    assert not host.tab_bar._tabs[0].button.isChecked()


def test_no_scrollbar_when_the_tabs_already_fit(qapp):
    """`required_width` used to floor every tab at `min_width`, inventing an overflow and a phantom scrollbar.

    Five tabs whose hints summed to 466 were reported as 516 in a 498 px bar: the strip showed a scrollbar with nothing
    to scroll (owner report 2026-11-22).
    """
    host = TopTabHost(tab_factory=_factory, tab_style=TabStyle(flat=True, gap=8, min_width=88))
    for label in ("General", "Encoder Options", "Render Queue", "Advanced", "Logs"):
        host.addTab(QWidget(), label)
    host.resize(520, 60)
    host.show()
    qapp.processEvents()

    bar = host.tab_bar
    assert bar.required_width() <= bar.width(), (
        f"required {bar.required_width()} > width {bar.width()}: the strip claims an overflow it does not have"
    )
    assert not bar._h_scroll.isVisible(), "a bar that fits must not paint a scrollbar"
