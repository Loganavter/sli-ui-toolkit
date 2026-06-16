"""Compatibility re-export for older atomic ComboBox imports."""

import warnings

warnings.warn(
    "sli_ui_toolkit.ui.widgets.atomic.combobox is deprecated and will be "
    "removed in 0.3.0. Import ComboBox from sli_ui_toolkit.widgets or "
    "sli_ui_toolkit.ui.widgets.comboboxes instead.",
    DeprecationWarning,
    stacklevel=2,
)

from sli_ui_toolkit.ui.widgets.comboboxes.combo_box import ComboBox

__all__ = ["ComboBox"]
