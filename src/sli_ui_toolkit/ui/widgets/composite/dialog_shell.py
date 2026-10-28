from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSplitterHandle,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.composite.sidebar_nav_list import IconListWidget
from sli_ui_toolkit.ui.widgets.helpers.paint_device import painter_dpr
from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_SCALE, connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px


def _scaled_metric(value: int) -> int:
    """Scale a design-px metric, keeping a deliberate ``0`` at ``0``.

    ``scaled_px`` clamps to ≥1 (a real widget never has a 0-px dimension),
    but a 0 margin/spacing means "none" — turning it into 1 px at a bigger
    factor adds a gap the design never asked for.
    """
    return 0 if value <= 0 else scaled_px(value)


def _hairline_rect(
    *, extents: float, length: float, dpr: float, vertical: bool
) -> QRectF:
    """One *device* px thick strip, centred across *extents*, snapped to the
    device grid.

    A 1-``logical``-px pen at a fractional ratio (125 % / 150 %) straddles
    two device columns and rasterizes as a blurred two-column band — the
    divider then reads as a thicker line that merges with the group border
    next to it. A strip of ``1 / dpr`` logical px whose leading edge is a
    whole number of device px covers exactly one device column, whatever
    the ratio. ``vertical`` says which axis the strip runs along (a vertical
    line in a horizontal splitter's handle).
    """
    ratio = dpr if dpr > 0.0 else 1.0
    thickness = 1.0 / ratio
    center = extents / 2.0
    # floor to the device grid; the epsilon keeps an exact device boundary
    # (e.g. 4.5 * 1.25/1.25) from landing a column early on float error.
    leading_device = math.floor((center - thickness / 2.0) * ratio + 1e-9)
    leading = leading_device / ratio
    if vertical:
        return QRectF(leading, 0.0, thickness, length)
    return QRectF(0.0, leading, length, thickness)


class _DialogSplitterHandle(QSplitterHandle):
    """Splitter handle that paints the section divider itself.

    QStyle's ``CE_Splitter`` line is drawn in device pixels at the handle's
    centre: at DPR 1.25 (the owner's 125 % screen) it lands on a fractional
    device column, so it smears over two columns and visually merges with
    the leftmost border of the controls in the column to its right. This
    handle paints one crisp device column instead (``_hairline_rect``) and
    fills the rest of its own surface, so the line always keeps a visible
    gap on both sides — no matter how narrow the handle gets.

    The line colour comes from ``dialog.border`` (re-read on
    ``theme_changed``, like ``_SurfaceWidget``), the surface from
    ``surface.background``, so the handle blends with the dialog instead of
    inheriting the host's stock splitter styling.
    """

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        super().__init__(orientation, parent)
        self._surface_color = QColor()
        self._line_color = QColor()
        self._refresh_colors()
        try:
            ThemeManager.get_instance().theme_changed.connect(
                self._on_theme_changed
            )
        except Exception:
            pass

    def _refresh_colors(self) -> None:
        surface = None
        line = None
        try:
            theme = ThemeManager.get_instance()
            surface = theme.try_get_color("surface.background")
            line = theme.try_get_color("dialog.border")
        except Exception:
            surface = None
            line = None
        palette = self.palette()
        self._surface_color = (
            QColor(surface)
            if surface is not None and surface.isValid()
            else palette.color(QPalette.ColorRole.Window)
        )
        self._line_color = (
            QColor(line)
            if line is not None and line.isValid()
            else palette.color(QPalette.ColorRole.Mid)
        )

    def _on_theme_changed(self, *_args: object) -> None:
        try:
            self._refresh_colors()
            self.update()
        except RuntimeError:
            pass

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            self._paint_divider(painter)
        finally:
            painter.end()

    def _paint_divider(self, painter: QPainter) -> None:
        """Paint the handle surface and its 1-device-px divider line.

        Split out of ``paintEvent`` so a test can paint into a device with a
        simulated fractional ratio: ``QWidget.render()`` always paints at
        the widget's own ratio, so it cannot exercise a 125 % screen
        offscreen (measured 2026-10-28).
        """
        painter.fillRect(self.rect(), self._surface_color)
        vertical = self.orientation() == Qt.Orientation.Horizontal
        extents = self.width() if vertical else self.height()
        length = self.height() if vertical else self.width()
        # The painter's device is the widget's backing store in a real
        # paint, so read the ratio from the device being painted on.
        painter.fillRect(
            _hairline_rect(
                extents=float(extents),
                length=float(length),
                dpr=painter_dpr(painter),
                vertical=vertical,
            ),
            self._line_color,
        )


class _SidebarDialogSplitter(QSplitter):
    """Horizontal splitter whose handles draw the toolkit's divider line."""

    def createHandle(self) -> QSplitterHandle:  # noqa: N802
        return _DialogSplitterHandle(self.orientation(), self)


class ScrollableDialogPage(QWidget):
    def __init__(
        self,
        *,
        content_margins: tuple[int, int, int, int] = (0, 0, 12, 0),
        content_spacing: int = 15,
        parent=None,
    ):
        super().__init__(parent)
        # Design px, re-resolved through scaled_px on every scale change (a
        # value stamped once in __init__ never follows set_factor()).
        self._content_margins = tuple(int(v) for v in content_margins)
        self._content_spacing = int(content_spacing)
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
        self._apply_content_metrics()
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
        connect_ui_metrics(self, self._on_scale_changed, axes=frozenset({AXIS_SCALE}))

    def _apply_content_metrics(self) -> None:
        self.content_layout.setContentsMargins(
            *(_scaled_metric(value) for value in self._content_margins)
        )
        self.content_layout.setSpacing(_scaled_metric(self._content_spacing))

    def _on_scale_changed(self, *_args: object) -> None:
        self._apply_content_metrics()
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """Content width is part of the page's minimum.

        ``QScrollArea.minimumSizeHint()`` is a fixed ~68×68 whatever its
        widget, so a splitter hands the content column as little as that:
        the column shrinks under its own content and the divider lands on
        the leftmost border of the controls inside it (the Settings
        complaint, 2026-10-28). Report the content's minimum width plus the
        vertical scrollbar that must fit beside it, and leave the height at
        the base value — vertical scrolling is the page's job, horizontal
        clipping is not.
        """
        base = super().minimumSizeHint()
        content = self.content_widget
        content_width = content.minimumSizeHint().width()
        # A host may pin the width explicitly instead of through the layout
        # (Settings does: content_widget.setMinimumWidth(...)); an explicit
        # minimum is not part of minimumSizeHint().
        content_width = max(content_width, content.minimumWidth())
        chrome = 0
        if (
            self.scroll_area.verticalScrollBarPolicy()
            != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        ):
            # The bar lives beside the viewport, so its extent must be
            # reserved or the page's own minimum clips the content it exists
            # to keep. sizeHint only: an unlaid-out bar reports its 640-px
            # default width, which would pin the page wide before first show.
            chrome = max(self.scroll_area.verticalScrollBar().sizeHint().width(), 0)
        return QSize(max(base.width(), content_width + chrome), base.height())

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
        # Design px, re-resolved on scale changes (see _apply_content_metrics).
        self._content_margins = tuple(int(v) for v in content_margins)
        self._content_spacing = int(content_spacing)
        self._apply_content_metrics()

        self.pages_stack = QStackedWidget()
        self.content_layout.addWidget(self.pages_stack)

        if resizable_sidebar:
            # Draggable divider between the sidebar column and the content
            # area (same interaction as the Help dialog's splitter).
            self.splitter: QSplitter | None = _SidebarDialogSplitter(
                Qt.Orientation.Horizontal, self
            )
            self.splitter.setObjectName("SidebarDialogSplitter")
            self.splitter.setChildrenCollapsible(False)
            self._apply_divider_width()
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
        connect_ui_metrics(self, self._on_scale_changed, axes=frozenset({AXIS_SCALE}))

    def _apply_sidebar_width(self) -> None:
        if self.sidebar_column is not None:
            self.sidebar_column.setMinimumWidth(scaled_px(self._sidebar_width))
        self.sidebar.setMinimumWidth(scaled_px(self._sidebar_width))

    def _apply_divider_width(self) -> None:
        # 6 design px: wide enough that the 1-device-px divider line keeps a
        # visible gap on both sides of the handle.
        if self.splitter is not None:
            self.splitter.setHandleWidth(scaled_px(6))

    def _apply_content_metrics(self) -> None:
        self.content_layout.setContentsMargins(
            *(_scaled_metric(value) for value in self._content_margins)
        )
        self.content_layout.setSpacing(_scaled_metric(self._content_spacing))

    def _on_scale_changed(self, *_args: object) -> None:
        # The sidebar is the fixed divider between nav and content: at a
        # bigger factor the nav rows (fonts/icons) grow, so the width must
        # grow with them or the row text clips. The divider handle and the
        # content margins are design px too — stamped once in __init__ they
        # stayed at their 1.0 values while everything around them grew.
        self._apply_sidebar_width()
        self._apply_divider_width()
        self._apply_content_metrics()
        self.updateGeometry()
        self.update()
