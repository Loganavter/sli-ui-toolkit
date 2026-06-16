from sli_ui_toolkit.ui.widgets.buttons.button import Button, ButtonConfig, ButtonRow
from sli_ui_toolkit.ui.widgets.buttons.button_group import ButtonGroup
from sli_ui_toolkit.ui.widgets.buttons.regions import (
    ButtonRegion,
    CustomSplit,
    Divider,
    GridSplit,
    HorizontalSplit,
    SingleRegionSplit,
    VerticalSplit,
)
from sli_ui_toolkit.ui.widgets.buttons.specs import (
    BehaviorSpec,
    ButtonSpec,
    ClickBehavior,
    ContentSpec,
    LongPressBehavior,
    MenuBehavior,
    RegionSpec,
    RegionStyle,
    ScrollBehavior,
    ShapeSpec,
    ToggleBehavior,
)

import warnings

_LEGACY_BUTTON_NAMES = {
    "IconButton",
    "SimpleIconButton",
    "ToggleIconButton",
    "ScrollableIconButton",
    "ToggleScrollableIconButton",
    "LongPressIconButton",
    "NumberedToggleIconButton",
    "UnifiedIconButton",
    "AutoRepeatButton",
    "CustomButton",
    "ToolButton",
    "ToolButtonWithMenu",
    "MagnifierInstancesButton",
}

_LEGACY_BUTTON_GROUP_NAMES = {
    "ButtonGroupContainer",
}

_LEGACY_BUTTON_SENTINELS = {
    "ButtonType",
    "ButtonMode",
}

__all__ = [
    "Button",
    "ButtonConfig",
    "ButtonRow",
    "ButtonGroup",
    "ButtonRegion",
    "CustomSplit",
    "Divider",
    "GridSplit",
    "HorizontalSplit",
    "SingleRegionSplit",
    "VerticalSplit",
    "BehaviorSpec",
    "ButtonSpec",
    "ClickBehavior",
    "ContentSpec",
    "LongPressBehavior",
    "MenuBehavior",
    "RegionSpec",
    "RegionStyle",
    "ScrollBehavior",
    "ShapeSpec",
    "ToggleBehavior",
]


def __getattr__(name: str):
    if name in _LEGACY_BUTTON_NAMES:
        warnings.warn(
            f"{name} is deprecated and will be removed in 0.3.0. "
            "Use the composable Button class instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return Button
    if name in _LEGACY_BUTTON_GROUP_NAMES:
        warnings.warn(
            f"{name} is deprecated and will be removed in 0.3.0. "
            "Use ButtonGroup instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return ButtonGroup
    if name in _LEGACY_BUTTON_SENTINELS:
        warnings.warn(
            f"{name} is deprecated and will be removed in 0.3.0. "
            "Use Button keyword arguments or ButtonSpec instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return Button
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
