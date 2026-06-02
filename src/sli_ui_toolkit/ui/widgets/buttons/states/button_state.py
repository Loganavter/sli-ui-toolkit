"""Button state machine — явное перечисление всех возможных состояний.

Заменяет разбросанные bool-атрибуты (_pressed, _hovered, _checked, _is_scrolling)
на единую FrozenSet, как в Flutter's MaterialState или WinUI3's VisualStateGroup.

Добавление нового состояния = одна строчка в enum, без синхронизации с painter.
"""

from enum import Enum, auto

class ButtonState(Enum):
    """Все возможные визуальные состояния кнопки."""
    HOVERED = auto()
    PRESSED = auto()
    CHECKED = auto()
    DISABLED = auto()
    SCROLLING = auto()
    FOCUSED = auto()
    # Развитие: LOADING, ERROR, VALID легко добавляются одной строкой


StateSet = frozenset[ButtonState]
"""Immutable set текущих активных состояний. Аналог FrozenSet[MaterialState] в Flutter."""
