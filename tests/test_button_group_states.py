"""Group-mirrored state survives a region rebuild.

``set_regions`` builds fresh runtime state per region id. A host that changes
its region layout while the pointer is inside (the app's ``ScrollValueButton``
grows a value half on enter and rebuilds on every value change) used to leave
the NEW region idle while its group sibling stayed hovered — measured: the
digit capsule resolved only the base background on a hovered body, so the
digit read as "outside the hover family".
"""

from __future__ import annotations

from PySide6.QtCore import QPointF

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.widgets import Button, ButtonRegion, VerticalSplit


def _theme() -> None:
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")


def _button(qtbot, region: ButtonRegion) -> Button:
    _theme()
    button = Button(regions=[region], size=(36, 36))
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)
    return button


def _split_regions(*, extra: ButtonRegion | None = None) -> list[ButtonRegion]:
    regions = [
        ButtonRegion(id="icon", group="split", weight=1.1, clip_content=True),
        ButtonRegion(id="value", text="5", group="split", weight=0.9),
    ]
    if extra is not None:
        regions.append(extra)
    return regions


def _hover(button: Button) -> None:
    button._update_hover_region(QPointF(button.rect().center()))


def test_region_added_during_hover_inherits_group_hover(qtbot):
    button = _button(qtbot, ButtonRegion(id="icon", group="split", weight=1.0))
    _hover(button)
    assert ButtonState.HOVERED in button.region_states("icon")

    button.set_regions(_split_regions(), split=VerticalSplit())

    assert ButtonState.HOVERED in button.region_states("icon")
    assert ButtonState.HOVERED in button.region_states("value")


def test_region_added_while_idle_stays_idle(qtbot):
    button = _button(qtbot, ButtonRegion(id="icon", group="split", weight=1.0))

    button.set_regions(_split_regions(), split=VerticalSplit())

    assert ButtonState.HOVERED not in button.region_states("icon")
    assert ButtonState.HOVERED not in button.region_states("value")


def test_other_group_does_not_inherit_hover(qtbot):
    button = _button(qtbot, ButtonRegion(id="icon", group="split", weight=1.0))
    _hover(button)

    button.set_regions(
        _split_regions(extra=ButtonRegion(id="other", text="x", group="solo")),
        split=VerticalSplit(),
    )

    assert ButtonState.HOVERED in button.region_states("value")
    assert ButtonState.HOVERED not in button.region_states("other")


def test_region_added_while_checked_inherits_group_checked(qtbot):
    button = _button(qtbot, ButtonRegion(id="icon", group="split", weight=1.0))
    button.setRegionChecked("icon", True, emit=False)
    assert ButtonState.CHECKED in button.region_states("icon")

    button.set_regions(_split_regions(), split=VerticalSplit())

    assert ButtonState.CHECKED in button.region_states("value")


def test_inherited_hover_clears_on_leave(qtbot):
    button = _button(qtbot, ButtonRegion(id="icon", group="split", weight=1.0))
    _hover(button)
    button.set_regions(_split_regions(), split=VerticalSplit())
    assert ButtonState.HOVERED in button.region_states("value")

    button.setHoverActive(False)

    assert ButtonState.HOVERED not in button.region_states("icon")
    assert ButtonState.HOVERED not in button.region_states("value")
