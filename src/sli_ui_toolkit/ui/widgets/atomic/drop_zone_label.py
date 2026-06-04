import os

from PyQt6.QtCore import QRectF, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label

def _file_path_from_url(url: QUrl) -> str:
    path = url.toLocalFile()
    if path:
        return path
    value = url.toString().strip()
    if value.startswith("file:///"):
        path = value[8:].lstrip("/").replace("|", ":", 1).replace("/", os.sep)
        return os.path.normpath(path) if path else ""
    if value.startswith("file://"):
        path = value[7:].replace("|", ":", 1).replace("/", os.sep)
        return os.path.normpath(path) if path else ""
    return ""

def _paths_from_urls_and_uri_list(mime, urls: list) -> list[str]:
    paths = [_file_path_from_url(url) for url in urls]
    if any(paths):
        return paths
    if not mime.hasFormat("text/uri-list"):
        return []
    raw = mime.data("text/uri-list").data().decode("utf-8", errors="replace")
    for line in raw.splitlines():
        part = line.strip()
        if not part or not part.startswith("file:"):
            continue
        path = _file_path_from_url(QUrl(part))
        if path and path not in paths:
            paths.append(path)
    return paths

class DropZoneLabel(Label):
    file_dropped = pyqtSignal(str)
    drop_zone_drag_active = pyqtSignal(bool)
    drop_zone_hover_state_changed = pyqtSignal(bool)

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent, variant="adaptive")
        self.setAcceptDrops(True)
        self.setMouseTracking(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(80)
        self._drag_active = False
        self._hovered = False
        self._theme_manager = ThemeManager.get_instance()
        try:
            self._theme_manager.theme_changed.connect(self.update)
        except Exception:
            pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent = self._theme_manager.get_color("accent")
        try:
            border_normal = self._theme_manager.get_color("dialog.border")
        except Exception:
            border_normal = QColor("#aaaaaa")

        if self._drag_active:
            border_color = QColor(accent)
            fill = QColor(accent)
            fill.setAlpha(40)
        else:
            border_color = QColor(border_normal)
            fill = QColor(0, 0, 0, 0)

        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        painter.setBrush(fill)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 10.0, 10.0)

        pen = QPen(border_color, 2.0)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 10.0, 10.0)
        painter.end()

        super().paintEvent(event)

    def _accept_drag(self, event):
        if event.source() is not None:
            return False
        mime = event.mimeData()
        return mime.hasUrls() or mime.hasFormat("text/uri-list")

    def dragEnterEvent(self, event):
        if not self._accept_drag(event):
            event.ignore()
            return
        event.acceptProposedAction()
        event.accept()
        self._drag_active = True
        self.update()
        self.drop_zone_drag_active.emit(True)

    def dragMoveEvent(self, event):
        if not self._accept_drag(event):
            event.ignore()
            return
        event.acceptProposedAction()
        event.accept()

    def dragLeaveEvent(self, event):
        self._drag_active = False
        self.update()
        self.drop_zone_drag_active.emit(False)
        event.accept()

    def dropEvent(self, event):
        self._drag_active = False
        self.update()
        self.drop_zone_drag_active.emit(False)
        if not self._accept_drag(event):
            event.ignore()
            return

        mime = event.mimeData()
        urls = list(mime.urls()) if mime.hasUrls() else []
        if not urls and mime.hasFormat("text/uri-list"):
            raw = mime.data("text/uri-list").data().decode("utf-8", errors="replace")
            for line in raw.splitlines():
                part = line.strip()
                if part.startswith("file:"):
                    urls.append(QUrl(part))

        paths = _paths_from_urls_and_uri_list(mime, urls)
        if paths and paths[0]:
            local_path = paths[0]
            QTimer.singleShot(0, lambda path=local_path: self.file_dropped.emit(path))
        event.acceptProposedAction()
        event.accept()

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)
