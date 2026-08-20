"""Back-compat import path.

``ButtonGroup`` now lives in ``atomic.custom_group_widget`` (merged with
``CustomGroupWidget`` — see that module's docstring). Re-exported here so
``sli_ui_toolkit.ui.widgets.buttons.button_group.ButtonGroup`` keeps working
for existing imports.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.atomic.custom_group_widget import ButtonGroup

__all__ = ["ButtonGroup"]
