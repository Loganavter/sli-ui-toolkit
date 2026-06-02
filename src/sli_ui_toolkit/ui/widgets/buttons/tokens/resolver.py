"""TokenResolver — разрешает (variant, states) → token key → QColor.

Вынесена логика из ButtonPainter._resolve_background().
Добавление нового состояния не требует правки painter — только добавить условие здесь.

Аналог MaterialStateProperty.resolve() в Flutter.
"""

from PyQt6.QtGui import QColor

from sli_ui_toolkit.theme import ThemeManager

from .schema import BUTTON_VARIANT_SCHEMA
from ..states import ButtonState, StateSet


class TokenResolver:
    """Разрешает цвет фона по варианту и набору активных состояний."""

    def __init__(self, theme_manager: ThemeManager):
        self._tm = theme_manager

    def resolve_background(
        self,
        variant: str,
        states: StateSet,
        override_bg: QColor | None = None,
        custom_bg: QColor | None = None,
    ) -> QColor:
        """Разрешить цвет фона кнопки.

        Приоритет состояний:
        1. override_bg (программное переопределение)
        2. custom_bg (произвольный цвет с auto-derivation)
        3. variant-специфичная логика (ghost, subtle, или по prefix)
        """
        if override_bg is not None:
            return override_bg

        if custom_bg is not None:
            if ButtonState.DISABLED in states:
                c = QColor(custom_bg)
                c.setAlpha(int(custom_bg.alpha() * 0.5))
                return c
            if ButtonState.PRESSED in states:
                return custom_bg.darker(115)
            if ButtonState.HOVERED in states:
                return custom_bg.lighter(108)
            return QColor(custom_bg)

        variant_lower = variant.lower()
        prefix = BUTTON_VARIANT_SCHEMA.get(variant_lower, "button.toggle")

        # Особая логика для "ghost" — почти прозрачный
        if variant_lower == "ghost":
            if ButtonState.PRESSED in states:
                return QColor(self._tm.get_color("button.toggle.background.pressed"))
            if ButtonState.HOVERED in states:
                return QColor(self._tm.get_color("button.toggle.background.hover"))
            return QColor(0, 0, 0, 0)  # полностью прозрачный

        # Особая логика для "subtle" — фон окна
        if variant_lower == "subtle":
            if ButtonState.DISABLED in states:
                return QColor(self._tm.get_color("button.toggle.background.normal"))
            if ButtonState.PRESSED in states:
                return QColor(self._tm.get_color("button.toggle.background.pressed"))
            if ButtonState.CHECKED in states:
                checked_color = self._tm.try_get_color("button.toggle.background.checked")
                if checked_color:
                    if ButtonState.HOVERED in states:
                        return QColor(self._tm.get_color("button.toggle.background.checked.hover"))
                    return QColor(checked_color)
            if ButtonState.HOVERED in states:
                return QColor(self._tm.get_color("button.toggle.background.hover"))
            return QColor(self._tm.get_color("Window"))

        # Общая логика для остальных вариантов
        if ButtonState.DISABLED in states:
            disabled_color = self._tm.try_get_color(f"{prefix}.background.disabled")
            if disabled_color is not None:
                return QColor(disabled_color)
            return QColor(self._tm.get_color("button.toggle.background.normal"))

        if ButtonState.PRESSED in states:
            return QColor(self._tm.get_color(f"{prefix}.background.pressed"))

        if ButtonState.CHECKED in states:
            checked_key = f"{prefix}.background.checked"
            if self._tm.try_get_color(checked_key) is not None:
                if ButtonState.HOVERED in states:
                    hover_key = f"{checked_key}.hover"
                    if self._tm.try_get_color(hover_key) is not None:
                        return QColor(self._tm.get_color(hover_key))
                return QColor(self._tm.get_color(checked_key))
            return QColor(self._tm.get_color(f"{prefix}.background.pressed"))

        if ButtonState.HOVERED in states:
            return QColor(self._tm.get_color(f"{prefix}.background.hover"))

        normal_key = f"{prefix}.background.normal" if prefix == "button.toggle" else f"{prefix}.background"
        return QColor(self._tm.get_color(normal_key))
