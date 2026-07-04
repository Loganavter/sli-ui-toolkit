from sli_ui_toolkit.ui.widgets.buttons.button import Button, ButtonConfig, ButtonRow
from sli_ui_toolkit.ui.widgets.buttons.button_group import ButtonGroup
from sli_ui_toolkit.ui.widgets.buttons.regions import (
    ButtonRegion,
    CustomSplit,
    Divider,
    GridSplit,
    HorizontalSplit,
    RegionHandle,
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
    ShapeSpec,
    ToggleBehavior,
)

from sli_ui_toolkit.deprecations import (
    BUTTON_COMPAT_DEPRECATIONS,
    LEGACY_BUTTON_GROUP_NAMES,
    LEGACY_BUTTON_NAMES,
    LEGACY_BUTTON_SENTINELS,
    raise_missing_attribute,
    resolve_deprecated_attribute,
)

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
    "RegionHandle",
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
    "ShapeSpec",
    "ToggleBehavior",
]


def __getattr__(name: str):
    values = {
        **{legacy: Button for legacy in LEGACY_BUTTON_NAMES},
        **{legacy: ButtonGroup for legacy in LEGACY_BUTTON_GROUP_NAMES},
        **{legacy: Button for legacy in LEGACY_BUTTON_SENTINELS},
    }
    if name in values:
        return resolve_deprecated_attribute(
            module_name=__name__,
            name=name,
            registry=BUTTON_COMPAT_DEPRECATIONS,
            values=values,
            stacklevel=2,
        )
    raise_missing_attribute(__name__, name)
