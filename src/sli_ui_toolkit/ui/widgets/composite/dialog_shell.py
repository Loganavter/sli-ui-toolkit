from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.composite.sidebar_nav_list import IconListWidget
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px

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

        self._apply_dialog_surface()
        try:
            ThemeManager.get_instance().theme_changed.connect(
                self._on_theme_changed
            )
        except Exception:
            pass

    def _apply_dialog_surface(self) -> None:
        """Paint the scroll surface with the ``dialog.background`` token.

        The viewport and the content widget are stock QWidgets: with the
        host's QSS active they auto-fill the QPalette Window role, which
        hosts keep darker than the dialog surface token (the app's dark
        palette: Window ``#1e1e1e`` vs ``dialog.background`` ``#2b2b2b``) —
        the empty page area then renders near-black against the gray
        panels. A per-widget palette is NOT enough here: ``QStyle::polish``
        at ``show()`` (and on any host stylesheet re-apply) resets widget
        palettes to the app palette. A widget-level stylesheet survives
        polish, so the surface is set as ``background-color`` on the scroll
        area (cascades to the viewport and the content widget) and re-tinted
        on ``theme_changed``.
        """
        try:
            color = QColor(ThemeManager.get_instance().get_color("surface.background"))
        except Exception:
            return
        self.scroll_area.setStyleSheet(f"background-color: {color.name()};")

    def _on_theme_changed(self, *_args) -> None:
        """Re-tint the scroll surface after a theme switch. Bound method, so
        the connection dies with the widget (a lambda would survive the
        widget and raise on the deleted C++ view)."""
        try:
            self._apply_dialog_surface()
        except RuntimeError:
            pass

class _SurfaceWidget(QWidget):
    """Paints its own surface from the ``dialog.background`` token.

    Host QSS background rules do not paint on a parented plain QWidget
    (``WA_StyledBackground`` is only set for the exact ``QWidget`` class as
    a top level; subclasses and parented instances fall back to the QPalette
    ``Window`` role, which hosts keep darker than the dialog surface token —
    the same mechanism ``ScrollableDialogPage._apply_dialog_surface`` works
    around). An explicit ``paintEvent`` fill is the reliable path; the color
    is re-read on ``theme_changed`` so palette overrides via ``set_color``
    take effect.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._surface_color = QColor("#000000")
        self._apply_dialog_surface()
        try:
            ThemeManager.get_instance().theme_changed.connect(
                self._on_theme_changed
            )
        except Exception:
            pass

    def _apply_dialog_surface(self) -> None:
        try:
            self._surface_color = QColor(
                ThemeManager.get_instance().get_color("surface.background")
            )
        except Exception:
            self._surface_color = QColor(self.palette().window().color())

    def _on_theme_changed(self, *_args) -> None:
        try:
            self._apply_dialog_surface()
            self.update()
        except RuntimeError:
            pass

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._surface_color)
        painter.end()


class SidebarDialogShell(QWidget):
    def __init__(
        self,
        *,
        sidebar_width: int = 200,
        content_margins: tuple[int, int, int, int] = (20, 20, 20, 20),
        content_spacing: int = 10,
        sidebar_header: QWidget | None = None,
        resizable_sidebar: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._sidebar_width = int(sidebar_width)
        self.sidebar_column = None
        self.sidebar_header = None
        self.sidebar = IconListWidget()
        self._apply_sidebar_width()
        self.sidebar.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        if sidebar_header is not None:
            # A fixed header (e.g. a search field) pinned above the nav list.
            # The whole column tracks the sidebar width so the header stretches
            # with it on scale changes.
            self.sidebar_column = QWidget()
            self._sidebar_column_layout = QVBoxLayout(self.sidebar_column)
            self._sidebar_column_layout.setContentsMargins(0, 0, 0, 0)
            self._sidebar_column_layout.setSpacing(0)
            self._sidebar_column_layout.addWidget(sidebar_header)
            self._sidebar_column_layout.addWidget(self.sidebar, 1)
            self.sidebar_header = sidebar_header
            sidebar_widget: QWidget = self.sidebar_column
        else:
            sidebar_widget = self.sidebar
        self._apply_sidebar_width()

        self.content_area = _SurfaceWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(*content_margins)
        self.content_layout.setSpacing(content_spacing)

        self.pages_stack = QStackedWidget()
        self.content_layout.addWidget(self.pages_stack)

        if resizable_sidebar:
            # Draggable divider between the sidebar column and the content
            # area (same interaction as the Help dialog's splitter).
            self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
            self.splitter.setObjectName("SidebarDialogSplitter")
            self.splitter.setChildrenCollapsible(False)
            self.splitter.setHandleWidth(scaled_px(6))
            self.splitter.addWidget(sidebar_widget)
            self.splitter.addWidget(self.content_area)
            self.splitter.setStretchFactor(0, 0)
            self.splitter.setStretchFactor(1, 1)
            self.splitter.setSizes(
                [
                    scaled_px(self._sidebar_width),
                    scaled_px(600),
                ]
            )
            self.main_layout.addWidget(self.splitter, 1)
        else:
            self.splitter = None
            self.main_layout.addWidget(sidebar_widget)
            self.main_layout.addWidget(self.content_area, 1)
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)

    def _apply_sidebar_width(self) -> None:
        if self.sidebar_column is not None:
            self.sidebar_column.setMinimumWidth(scaled_px(self._sidebar_width))
        self.sidebar.setMinimumWidth(scaled_px(self._sidebar_width))

    def _on_scale_changed(self, _factor: float) -> None:
        # The sidebar is the fixed divider between nav and content: at a
        # bigger factor the nav rows (fonts/icons) grow, so the width must
        # grow with them or the row text clips.
        self._apply_sidebar_width()
        self.updateGeometry()
        self.update()
