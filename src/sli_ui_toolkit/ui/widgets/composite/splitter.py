"""Splitter whose handle paints the toolkit's one-device-pixel divider.

Hosts that need a resizable two-pane layout (the sidebar dialog shell, a help
dialog, an editor's tool column) otherwise reach for a stock ``QSplitter`` and
paint their own separator on top: QStyle's ``CE_Splitter`` draws a 1 *logical*
px line, which at a fractional device ratio (125 % / 150 %) straddles two
device columns and rasterizes as a blurred band that merges with the border of
whatever control sits next to it.

:class:`Splitter` / :class:`SplitterHandle` are that separator, published:
the handle fills its own surface with ``surface.background`` and paints one
crisp device column of ``dialog.border`` at its centre, snapped to the device
grid by :func:`hairline_rect` — so the line is exactly one device pixel wide at
every ratio, with a visible gap on both sides. Both colours are re-read on
``theme_changed``, and the handle width is design px re-resolved through
``UiScale`` on every factor change. Nothing here is host-specific and nothing
is styled through QSS.
"""

from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPalette
from PySide6.QtWidgets import QSplitter, QSplitterHandle, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers.paint_device import painter_dpr
from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_SCALE, connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px

__all__ = ["DEFAULT_HANDLE_WIDTH", "Splitter", "SplitterHandle", "hairline_rect"]

#: Handle width in design px. Wide enough that the 1-device-px divider line
#: keeps a visible gap on both sides of the handle at every ratio.
DEFAULT_HANDLE_WIDTH = 6

#: Callable answering the Y (in the handle's own space) of a horizontal rule
#: that must meet the divider line, or ``None`` for "no rule".
FooterRuleProvider = Callable[[], "int | None"]


def hairline_rect(
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


class SplitterHandle(QSplitterHandle):
    """Splitter handle that paints the section divider itself.

    QStyle's ``CE_Splitter`` line is drawn in device pixels at the handle's
    centre: at DPR 1.25 (the owner's 125 % screen) it lands on a fractional
    device column, so it smears over two columns and visually merges with the
    leftmost border of the controls in the column to its right. This handle
    paints one crisp device column instead (``hairline_rect``) and fills the
    rest of its own surface, so the line always keeps a visible gap on both
    sides — no matter how narrow the handle gets.

    The line colour comes from ``dialog.border`` (re-read on
    ``theme_changed``), the surface from ``surface.background``, so the handle
    blends with the dialog instead of inheriting the host's stock splitter
    styling. A double-click resets the panes to equal sizes.
    """

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        super().__init__(orientation, parent)
        self._surface_color = QColor()
        self._line_color = QColor()
        #: Y (in this handle's own space) of a horizontal rule that must MEET
        #: the divider line. Qt clamps negative layout margins to zero, so a
        #: flush rule in the neighbouring pane cannot simply overhang; the
        #: handle closes the few-pixel gap itself, in the same colour and the
        #: same device column.
        self._footer_rule_y: int | None = None
        self._footer_rule_provider: FooterRuleProvider | None = None
        self._refresh_colors()
        try:
            ThemeManager.get_instance().theme_changed.connect(
                self._on_theme_changed
            )
        except Exception:
            pass

    def splitter(self) -> "Splitter":
        """The owning splitter (typed; the base class returns ``QSplitter``)."""
        return super().splitter()  # type: ignore[return-value]

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

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            owner = self.splitter()
            if isinstance(owner, Splitter):
                owner.reset_sizes()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def set_footer_rule_provider(self, provider: FooterRuleProvider | None) -> None:
        """Ask *provider* for the footer rule's row at PAINT time.

        A cached ``y`` is stale: the row's position is only known after the
        layout runs, and the owner's own resize event fires before that — the
        stub then painted at the handle's top (measured live: the rule still
        stopped 4 px short).
        """
        self._footer_rule_provider = provider
        self.update()

    def set_footer_rule_y(self, y: int | None) -> None:
        """Paint a horizontal stub at *y* so a footer rule meets this line."""
        y = None if y is None else int(y)
        if y == self._footer_rule_y:
            return
        self._footer_rule_y = y
        self.update()

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
        line = hairline_rect(
            extents=float(extents),
            length=float(length),
            dpr=painter_dpr(painter),
            vertical=vertical,
        )
        painter.fillRect(line, self._line_color)
        rule_y = self._footer_rule_y
        if self._footer_rule_provider is not None:
            try:
                answer = self._footer_rule_provider()
            except Exception:
                answer = None
            rule_y = None if answer is None else int(answer)
        if vertical and rule_y is not None:
            # A footer rule lives in the content pane, which starts at this
            # handle's right edge — so it stops a few px short of the divider
            # line. This stub carries the rule across that gap: same colour,
            # same one-device-column thickness, from the line to the edge.
            thickness = line.width()
            painter.fillRect(
                QRectF(
                    line.left(),
                    float(rule_y),
                    float(self.width()) - line.left(),
                    thickness,
                ),
                self._line_color,
            )


class Splitter(QSplitter):
    """QSplitter whose handles paint the toolkit's divider line.

    ``handle_width`` is design px (default :data:`DEFAULT_HANDLE_WIDTH`) and is
    re-resolved through ``UiScale`` when the interface factor changes, like
    every other metric in the toolkit. Everything else is inherited:
    ``setSizes``/``sizes`` round-trip, ``setChildrenCollapsible``, and the
    ``splitterMoved`` signal — this class only owns the look of the handle and
    two small conveniences (a double-click resets the panes to equal sizes).
    """

    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        parent: QWidget | None = None,
        *,
        handle_width: int = DEFAULT_HANDLE_WIDTH,
        children_collapsible: bool = True,
    ) -> None:
        super().__init__(orientation, parent)
        self._handle_width = int(handle_width)
        self.setChildrenCollapsible(children_collapsible)
        self._apply_handle_width()
        connect_ui_metrics(
            self, self._on_scale_changed, axes=frozenset({AXIS_SCALE})
        )

    def createHandle(self) -> QSplitterHandle:  # noqa: N802
        return SplitterHandle(self.orientation(), self)

    def handle(self, index: int) -> SplitterHandle:  # type: ignore[override]
        return super().handle(index)  # type: ignore[return-value]

    def handle_width(self) -> int:
        """The configured handle width in design px."""
        return self._handle_width

    def set_handle_width(self, design_px: int) -> None:
        """Set the handle width in design px and re-resolve it through scale."""
        self._handle_width = int(design_px)
        self._apply_handle_width()

    def _apply_handle_width(self) -> None:
        # A handle narrower than one px cannot be grabbed, so the design value
        # is clamped through ``scaled_px`` (which floors at 1) on the way in.
        self.setHandleWidth(max(1, scaled_px(self._handle_width)))

    def _on_scale_changed(self, *_args: object) -> None:
        self._apply_handle_width()
        self.updateGeometry()
        for index in range(1, self.count()):
            handle = self.handle(index)
            handle.update()

    def reset_sizes(self) -> None:
        """Give every pane an equal share of the current extent.

        The trailing pane takes the rounding remainder so ``sizes()`` sums to
        the extent. Pane minimum sizes still win (Qt clamps the distribution),
        which is the same rule a drag obeys.
        """
        count = self.count()
        if count <= 0:
            return
        if self.orientation() == Qt.Orientation.Horizontal:
            extent = self.width()
        else:
            extent = self.height()
        available = max(0, extent - self.handleWidth() * (count - 1))
        share = available // count
        sizes = [share] * count
        sizes[-1] += available - share * count
        self.setSizes(sizes)
