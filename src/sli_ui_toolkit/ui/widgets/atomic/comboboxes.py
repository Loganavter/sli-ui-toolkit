"""Compatibility re-export for older atomic ScrollableComboBox imports."""

from sli_ui_toolkit.deprecations import (
    ATOMIC_SCROLLABLE_COMBOBOX_MODULE,
    warn_deprecated,
)

warn_deprecated(ATOMIC_SCROLLABLE_COMBOBOX_MODULE, stacklevel=2)

from sli_ui_toolkit.ui.widgets.comboboxes.scrollable_combobox import ScrollableComboBox

__all__ = ["ScrollableComboBox"]
