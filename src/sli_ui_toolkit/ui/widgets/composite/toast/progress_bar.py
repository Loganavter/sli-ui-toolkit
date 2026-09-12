"""Toast family - progress bar, notification, and the stacking manager.

Folder split (the buttons/ folder is the model): one module per widget
class - ``progress_bar.py`` (painted track), ``notification.py``
(message/actions/progress layout + geometry), ``manager.py`` (id
registry, anchoring, stacking).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager


class ToastProgressBar(QWidget):
    """Painted toast progress track — accent fill, rounded ends, track background.

    Not a ``QProgressBar``: Qt stylesheets cannot reliably round the chunk or
    paint a distinct unfilled track across platforms.
    """

    def __init__(self, parent: QWidget | None = None, *, height: int = 6) -> None:
        super().__init__(parent)
        self.setObjectName("ToastProgressBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(max(2, int(height)))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._minimum = 0
        self._maximum = 100
        self._value = 0
        self._theme = ThemeManager.get_instance()
        self._theme.theme_changed.connect(self.update)

    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = int(minimum)
        self._maximum = max(int(minimum) + 1, int(maximum))
        self.setValue(self._value)

    def setValue(self, value: int) -> None:
        clamped = max(self._minimum, min(self._maximum, int(value)))
        if clamped == self._value:
            return
        self._value = clamped
        self.update()

    def value(self) -> int:
        return self._value

    def minimum(self) -> int:
        return self._minimum

    def maximum(self) -> int:
        return self._maximum

    def _track_color(self) -> QColor:
        color = self._theme.try_get_color("toast.progress.background")
        if color is not None and color.isValid():
            return QColor(color)
        # Fallback when host palette omits the token.
        base = QColor(self._theme.get_color("toast.text"))
        base.setAlpha(36 if not self._theme.is_dark() else 64)
        return base

    def _fill_color(self) -> QColor:
        color = self._theme.try_get_color("toast.progress.fill")
        if color is not None and color.isValid():
            return QColor(color)
        accent = self._theme.try_get_color("accent")
        if accent is not None and accent.isValid():
            return QColor(accent)
        return QColor("#0078D4")

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() * 0.5

        painter.setBrush(QBrush(self._track_color()))
        painter.drawRoundedRect(rect, radius, radius)

        span = max(1, self._maximum - self._minimum)
        fraction = (self._value - self._minimum) / float(span)
        if fraction > 0.0:
            fill_width = max(radius * 2.0, rect.width() * min(1.0, fraction))
            fill_width = min(fill_width, rect.width())
            fill_rect = QRectF(rect.x(), rect.y(), fill_width, rect.height())
            painter.setBrush(QBrush(self._fill_color()))
            painter.drawRoundedRect(fill_rect, radius, radius)

        painter.end()
