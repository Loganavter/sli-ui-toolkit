"""Centralized deprecation registry and warning helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import warnings


@dataclass(frozen=True)
class DeprecationEntry:
    symbol: str
    replacement: str
    since: str
    remove_in: str = "0.3.0"
    changelog: str | None = None
    note: str = ""

    def message(self) -> str:
        details = [
            f"{self.symbol} is deprecated since {self.since}",
            f"and will be removed in {self.remove_in}.",
            f"Use {self.replacement} instead.",
        ]
        if self.note:
            details.append(self.note)
        if self.changelog:
            details.append(f"See CHANGELOG.md section {self.changelog}.")
        return " ".join(details)


def warn_deprecated(entry: DeprecationEntry, *, stacklevel: int = 2) -> None:
    warnings.warn(entry.message(), DeprecationWarning, stacklevel=stacklevel)


def warn_deprecated_symbol(
    symbol: str,
    *,
    replacement: str,
    since: str,
    remove_in: str = "0.3.0",
    changelog: str | None = None,
    note: str = "",
    stacklevel: int = 2,
) -> None:
    warn_deprecated(
        DeprecationEntry(
            symbol=symbol,
            replacement=replacement,
            since=since,
            remove_in=remove_in,
            changelog=changelog,
            note=note,
        ),
        stacklevel=stacklevel,
    )


def resolve_deprecated_attribute(
    *,
    module_name: str,
    name: str,
    registry: Mapping[str, DeprecationEntry],
    values: Mapping[str, Any],
    stacklevel: int = 2,
) -> Any:
    entry = registry.get(name)
    if entry is None:
        raise_missing_attribute(module_name, name)
    warn_deprecated(entry, stacklevel=stacklevel)
    return values[name]


def raise_missing_attribute(module_name: str, name: str) -> None:
    raise AttributeError(
        f"module {module_name!r} has no attribute {name!r}. "
        "If this was a removed compatibility import, check CHANGELOG.md for "
        "the replacement API."
    )


LEGACY_BUTTON_NAMES = {
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

LEGACY_BUTTON_GROUP_NAMES = {"ButtonGroupContainer"}
LEGACY_BUTTON_SENTINELS = {"ButtonType", "ButtonMode"}

BUTTON_COMPAT_DEPRECATIONS = {
    **{
        name: DeprecationEntry(
            symbol=name,
            replacement="the composable Button class",
            since="0.2.11",
            changelog="0.2.11",
        )
        for name in LEGACY_BUTTON_NAMES
    },
    **{
        name: DeprecationEntry(
            symbol=name,
            replacement="ButtonGroup",
            since="0.2.11",
            changelog="0.2.11",
        )
        for name in LEGACY_BUTTON_GROUP_NAMES
    },
    **{
        name: DeprecationEntry(
            symbol=name,
            replacement="Button keyword arguments or ButtonSpec",
            since="0.2.11",
            changelog="0.2.11",
        )
        for name in LEGACY_BUTTON_SENTINELS
    },
}

ATOMIC_COMBOBOX_MODULE = DeprecationEntry(
    symbol="sli_ui_toolkit.ui.widgets.atomic.combobox",
    replacement="ComboBox from sli_ui_toolkit.widgets or sli_ui_toolkit.ui.widgets.comboboxes",
    since="0.2.11",
    changelog="0.2.11",
)

ATOMIC_SCROLLABLE_COMBOBOX_MODULE = DeprecationEntry(
    symbol="sli_ui_toolkit.ui.widgets.atomic.comboboxes",
    replacement=(
        "ScrollableComboBox from sli_ui_toolkit.widgets or "
        "sli_ui_toolkit.ui.widgets.comboboxes"
    ),
    since="0.2.11",
    changelog="0.2.11",
)

CHOICE_OVERLAY_DEPRECATIONS = {
    "ChoiceOverlay": DeprecationEntry(
        symbol="ChoiceOverlay",
        replacement="TopLevelInWindowOverlay with Button or other child widgets",
        since="0.2.11",
        changelog="0.2.11",
    ),
    "ChoiceSlot": DeprecationEntry(
        symbol="ChoiceSlot",
        replacement="OverlaySlot",
        since="0.2.11",
        changelog="0.2.11",
    ),
}

BUTTON_TRIGGERED = DeprecationEntry(
    symbol="Button.triggered",
    replacement="ContextMenu.on_triggered (menu API removed in 3.1.0)",
    since="0.2.11",
    changelog="3.1.0",
)

BUTTON_SET_CHECKED_EMIT_SIGNAL = DeprecationEntry(
    symbol="Button.setChecked(..., emit_signal=...)",
    replacement="emit=...",
    since="0.2.11",
    changelog="0.2.11",
)

BUTTON_PRIMARY_VARIANT = DeprecationEntry(
    symbol="Button variant 'primary'",
    replacement="'surface'",
    since="0.2.7",
    changelog="0.2.7",
)

BUTTON_PAINTER_PAINT = DeprecationEntry(
    symbol="ButtonPainter.paint(...)",
    replacement="Button with layers=... or the Painter pipeline",
    since="0.2.11",
    changelog="0.2.11",
)
