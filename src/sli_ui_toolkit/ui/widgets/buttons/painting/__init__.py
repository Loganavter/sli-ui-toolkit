"""Button painting system — разделение ответственности для рисования.

Аналог QStyle::drawControl в Qt / RenderObject.paint в Flutter.
"""

from .context import ButtonDrawContext
from .painter import ButtonPainterV2

__all__ = ["ButtonDrawContext", "ButtonPainterV2"]
