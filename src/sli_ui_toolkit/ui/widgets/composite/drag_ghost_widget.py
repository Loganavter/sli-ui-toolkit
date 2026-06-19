from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

class DragGhostWidget(QWidget):
    def __init__(self, parent=None):
        if parent is None:
            raise ValueError("DragGhostWidget requires an in-window parent widget")
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pixmap = QPixmap()
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)

        self.setOpacity(1.0)

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.setFixedSize(pixmap.size())
        self.update()

    def setOpacity(self, opacity):
        self._opacity_effect.setOpacity(max(0.0, min(1.0, float(opacity))))

    def move(self, pos):
        if isinstance(pos, QPoint) and self.parentWidget() is not None:
            return super().move(self.parentWidget().mapFromGlobal(pos))
        return super().move(pos)

    def paintEvent(self, event):
        if self._pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 8.0, 8.0)
        painter.setClipPath(path)
        painter.drawPixmap(self.rect(), self._pixmap)
