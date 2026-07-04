"""Compatibility re-export for older atomic ComboBox imports."""

from sli_ui_toolkit.deprecations import ATOMIC_COMBOBOX_MODULE, warn_deprecated

warn_deprecated(ATOMIC_COMBOBOX_MODULE, stacklevel=2)

from sli_ui_toolkit.ui.widgets.comboboxes.combo_box import ComboBox

__all__ = ["ComboBox"]
