import logging
from enum import Enum

from sli_ui_toolkit.ui.widgets.helpers.rounded_clip import RoundedClipEffect

logger = logging.getLogger(__name__)

# Back-compat alias for in-package imports.
_RoundedClipEffect = RoundedClipEffect

class FlyoutMode(Enum):
    HIDDEN = 0
    SINGLE_LEFT = 1
    SINGLE_RIGHT = 2
    DOUBLE = 3
    SINGLE_SIMPLE = 4
