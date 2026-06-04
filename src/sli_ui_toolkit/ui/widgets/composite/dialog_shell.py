from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.composite.sidebar_nav_list import IconListWidget

class ScrollableDialogPage(QWidget):
    def __init__(
        self,
        *,
        content_margins: tuple[int, int, int, int] = (0, 0, 12, 0),
        content_spacing: int = 15,
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBar(MinimalistScrollBar())
        self.scroll_area.setHorizontalScrollBar(MinimalistScrollBar())

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(*content_margins)
        self.content_layout.setSpacing(content_spacing)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area)

class SidebarDialogShell(QWidget):
    def __init__(
        self,
        *,
        sidebar_width: int = 200,
        content_margins: tuple[int, int, int, int] = (20, 20, 20, 20),
        content_spacing: int = 10,
        parent=None,
    ):
        super().__init__(parent)
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.sidebar = IconListWidget()
        self.sidebar.setMinimumWidth(120)
        self.sidebar.setMaximumWidth(sidebar_width)

        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(*content_margins)
        self.content_layout.setSpacing(content_spacing)

        self.pages_stack = QStackedWidget()
        self.content_layout.addWidget(self.pages_stack)

        self.main_layout.addWidget(self.sidebar)
        self.main_layout.addWidget(self.content_area, 1)
