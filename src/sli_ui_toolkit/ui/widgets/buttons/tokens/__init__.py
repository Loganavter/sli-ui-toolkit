"""Token resolution system — отделяет "какой цвет" от "как рисовать".

Аналог Qt's QPalette / Flutter's ThemeData + MaterialStateProperty / MUI's tokens.
"""

from .schema import BUTTON_VARIANT_SCHEMA
from .resolver import TokenResolver

__all__ = ["BUTTON_VARIANT_SCHEMA", "TokenResolver"]
