"""Compatibility re-export for older atomic ScrollableComboBox imports."""

import warnings

warnings.warn(
    "sli_ui_toolkit.ui.widgets.atomic.comboboxes is deprecated and will be "
    "removed in 0.3.0. Import ScrollableComboBox from sli_ui_toolkit.widgets "
    "or sli_ui_toolkit.ui.widgets.comboboxes instead.",
    DeprecationWarning,
    stacklevel=2,
)

from sli_ui_toolkit.ui.widgets.comboboxes.scrollable_combobox import ScrollableComboBox

__all__ = ["ScrollableComboBox"]
