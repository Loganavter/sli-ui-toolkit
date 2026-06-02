"""Button painting primitives — атомарные рисующие операции.

Каждый примитив отвечает за одну визуальную часть кнопки.
Добавление нового типа контента = один новый файл, не трогая существующие.
"""

from . import background, badge, edge, icon, icon_text, rows, strikethrough, text, underline

__all__ = [
    "background",
    "badge",
    "edge",
    "icon",
    "icon_text",
    "rows",
    "strikethrough",
    "text",
    "underline",
]
