"""ButtonPainter v2 — оркестратор рисования через архитектуру primitives + context.

Вместо монолита с 18 параметрами, работает с ButtonDrawContext и вызывает primitives.
Добавление нового примитива не требует изменения этого файла.
"""

from PyQt6.QtGui import QPainter

from sli_ui_toolkit.theme import ThemeManager
from ..tokens import TokenResolver
from .context import ButtonDrawContext
from . import primitives


class ButtonPainterV2:
    """Оркестратор — вызывает primitives в правильном порядке."""

    def __init__(self, theme_manager: ThemeManager):
        self._tm = theme_manager
        self._resolver = TokenResolver(theme_manager)

    def paint(self, ctx: ButtonDrawContext) -> None:
        """Рисует кнопку через примитивы, переданные в контексте.

        Порядок слоёв:
        1. background + border
        2. content (текст/иконка/rows в зависимости от типа)
        3. badge
        4. bottom edge
        5. underline
        6. strikethrough
        """
        painter = ctx.painter

        # 1. Фон и граница
        primitives.background.draw_background_and_border(ctx, self._resolver, self._tm)

        # 2. Контент — диспетчеризация по типу
        self._paint_content(ctx)

        # 3. Badge
        primitives.badge.draw_badge(ctx, self._tm)

        # 4. Bottom edge (декоративная полоса)
        primitives.edge.draw_bottom_edge(ctx, self._tm)

        # 5. Underline (кастомное подчёркивание)
        primitives.underline.draw_underline(ctx, self._tm)

        # 6. Strikethrough (ошибка/отключено)
        primitives.strikethrough.draw_strikethrough(ctx, self._tm)

    def _paint_content(self, ctx: ButtonDrawContext) -> None:
        """Диспетчеризация по типу контента.

        Добавление нового типа контента:
        1. Создать RowsContent / IconContent / TextContent dataclass
        2. Добавить case в эту функцию
        3. Создать примитив в painting/primitives/
        """
        if ctx.content is None:
            return

        # Import here to avoid circular imports
        from ..config import TextContent, RowsContent, IconContent, IconTextContent

        match ctx.content:
            case RowsContent() as rows_content:
                primitives.rows.draw_rows(ctx, rows_content.rows, self._tm,
                                         compact=rows_content.compact,
                                         row_gap=rows_content.row_gap)
            case TextContent() as text_content:
                primitives.text.draw_text_only(ctx, text_content.text, self._tm)
            case IconTextContent() as icon_text:
                primitives.icon_text.draw_icon_and_text(ctx, icon_text.text, self._tm)
            case IconContent():
                primitives.icon.draw_icon(ctx, self._tm)
            case _:
                pass
