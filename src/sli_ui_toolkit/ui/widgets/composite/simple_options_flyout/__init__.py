"""SimpleOptionsFlyout family — a scrollable option-row flyout built on
BaseFlyout.

Folder split (the base_flyout/ folder is the model): ``widget.py`` is the
thin facade; the row widget + its paint layers live in ``row.py``; sizing
math is in ``geometry.py``; the ``show_below`` slide/fade animation-group
construction is in ``animation.py``.
"""

from sli_ui_toolkit.ui.widgets.composite.simple_options_flyout.row import (
    _CurrentIndicatorLayer,
    _design_font,
    _RowBackgroundLayer,
    _SimpleRow,
)
from sli_ui_toolkit.ui.widgets.composite.simple_options_flyout.widget import (
    SimpleOptionsFlyout,
)

__all__ = ["SimpleOptionsFlyout"]
