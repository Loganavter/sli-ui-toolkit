"""Variant registry — единственный источник истины о вариантах кнопок.

Добавление нового варианта:
    register_variant(VariantSpec(name="warning", token_prefix="button.warning"))

Кастомная background-логика (как у ghost) — через resolve_bg-колбэк.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtGui import QColor

from sli_ui_toolkit.theme import ThemeManager

from .state import ButtonState, StateSet


BackgroundResolver = Callable[[StateSet, ThemeManager], QColor]


@dataclass(frozen=True)
class VariantSpec:
    name: str
    token_prefix: str
    resolve_bg: BackgroundResolver | None = None


def default_resolve_bg(prefix: str) -> BackgroundResolver:
    """Стандартная resolve-логика: DISABLED → PRESSED → CHECKED(±hover) → HOVERED → normal."""

    def _resolve(states: StateSet, tm: ThemeManager) -> QColor:
        if ButtonState.DISABLED in states:
            disabled = tm.try_get_color(f"{prefix}.background.disabled")
            if disabled is not None:
                return QColor(disabled)
            return QColor(tm.get_color("button.toggle.background.normal"))

        if ButtonState.PRESSED in states:
            return QColor(tm.get_color(f"{prefix}.background.pressed"))

        if ButtonState.CHECKED in states:
            checked_key = f"{prefix}.background.checked"
            if tm.try_get_color(checked_key) is not None:
                if ButtonState.HOVERED in states:
                    hover_key = f"{checked_key}.hover"
                    if tm.try_get_color(hover_key) is not None:
                        return QColor(tm.get_color(hover_key))
                return QColor(tm.get_color(checked_key))
            return QColor(tm.get_color(f"{prefix}.background.pressed"))

        if ButtonState.HOVERED in states:
            return QColor(tm.get_color(f"{prefix}.background.hover"))

        normal_key = (
            f"{prefix}.background.normal" if prefix == "button.toggle"
            else f"{prefix}.background"
        )
        return QColor(tm.get_color(normal_key))

    return _resolve


def _ghost_resolve(states: StateSet, tm: ThemeManager) -> QColor:
    if ButtonState.PRESSED in states:
        return QColor(tm.get_color("button.toggle.background.pressed"))
    if ButtonState.HOVERED in states:
        return QColor(tm.get_color("button.toggle.background.hover"))
    return QColor(0, 0, 0, 0)


_DEFAULT_VARIANTS: list[VariantSpec] = [
    VariantSpec("default", "button.toggle"),
    VariantSpec("surface", "button.dialog.default"),
    VariantSpec("ghost",   "button.toggle", resolve_bg=_ghost_resolve),
]

VARIANTS: dict[str, VariantSpec] = {v.name: v for v in _DEFAULT_VARIANTS}


def register_variant(spec: VariantSpec) -> None:
    """Зарегистрировать новый variant (или переопределить существующий)."""
    VARIANTS[spec.name] = spec


def get_variant(name: str | None) -> VariantSpec:
    """Получить VariantSpec по имени; fallback на "default" если не найдено."""
    return VARIANTS.get((name or "default").lower(), VARIANTS["default"])


def resolve_background(spec: VariantSpec, states: StateSet, tm: ThemeManager) -> QColor:
    """Главная точка входа: VariantSpec + StateSet → QColor."""
    resolver = spec.resolve_bg or default_resolve_bg(spec.token_prefix)
    return resolver(states, tm)


def get_contrasting_text_color(bg: QColor) -> QColor:
    """WCAG-luminance выбор чёрного/белого для текста на произвольном фоне."""
    r, g, b = bg.red(), bg.green(), bg.blue()
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return QColor("#000000") if luminance > 0.5 else QColor("#FFFFFF")


def _with_scaled_alpha(color: QColor, factor: float) -> QColor:
    result = QColor(color)
    result.setAlpha(max(0, min(255, int(color.alpha() * factor))))
    return result


@dataclass(frozen=True)
class CustomPalette:
    normal: QColor
    hover: QColor
    pressed: QColor
    border: QColor | None
    disabled: QColor


def _derive_tint(base: QColor) -> CustomPalette:
    """Tint-стиль без рамки. Custom background для "default" — это раскраска
    самой плашки; собственная рамка только зашумляла бы форму."""
    return CustomPalette(
        normal=_with_scaled_alpha(base, 0.18),
        hover=_with_scaled_alpha(base, 0.30),
        pressed=_with_scaled_alpha(base, 0.30),
        border=None,
        disabled=_with_scaled_alpha(base, 0.08),
    )


def _derive_tint_bordered(base: QColor) -> CustomPalette:
    """То же tint-заполнение, что у "default", но с цветной рамкой. Surface —
    это вариант "плашка-карточка": рамка отделяет её от окружения, особенно
    когда заливка совсем светлая (низкая alpha поверх Window)."""
    return CustomPalette(
        normal=_with_scaled_alpha(base, 0.18),
        hover=_with_scaled_alpha(base, 0.30),
        pressed=_with_scaled_alpha(base, 0.30),
        border=_with_scaled_alpha(base, 0.40),
        disabled=_with_scaled_alpha(base, 0.08),
    )


def _derive_ghost(base: QColor) -> CustomPalette:
    """Ghost-стиль: невидимый normal, лёгкий tint на hover/pressed, без border."""
    transparent = QColor(base)
    transparent.setAlpha(0)
    return CustomPalette(
        normal=transparent,
        hover=_with_scaled_alpha(base, 0.20),
        pressed=_with_scaled_alpha(base, 0.30),
        border=None,
        disabled=transparent,
    )


_CUSTOM_DERIVERS: dict[str, Callable[[QColor], CustomPalette]] = {
    "surface": _derive_tint_bordered,
    "ghost": _derive_ghost,
}


def derive_custom_palette(base: QColor, variant_name: str | None = None) -> CustomPalette:
    """Из произвольного цвета вывести палет состояний под конкретный variant.

    - ``default`` (и любой неизвестный) → tint-заливка без рамки.
    - ``surface`` → та же tint-заливка + tint-рамка для отделения карточки.
    - ``ghost`` → прозрачный normal, tint на hover/pressed.

    Fill у default и surface сознательно одинаковый, отличается только
    наличие собственной рамки. Если рамка нужна для default — передайте
    ``border_color=`` в конструктор Button: она идёт через
    ``override_border_color`` и применяется поверх.
    """
    deriver = _CUSTOM_DERIVERS.get((variant_name or "default").lower(), _derive_tint)
    return deriver(base)
