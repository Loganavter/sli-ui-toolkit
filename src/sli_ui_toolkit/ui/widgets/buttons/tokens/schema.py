"""Button variant token schema — маппинг variant → theme token prefix.

Вынесено из _painter.py чтобы добавление нового variant не требовало редактирования painter.
Аналог MaterialDesignVersion tokens в Flutter или buttonVariantStyles в MUI.
"""

BUTTON_VARIANT_SCHEMA: dict[str, str] = {
    "default": "button.toggle",
    "accent": "button.default",
    "delete": "button.delete",
    "primary": "button.primary",
    "surface": "button.dialog.default",
    "ghost": "button.toggle",  # ghost использует toggle токены (но с особой логикой в resolver)
    "subtle": "button.toggle",  # subtle тоже
    # Добавление нового варианта (например, "warning"): одна строчка здесь, ничего в painter
    # "warning": "button.warning",
}
