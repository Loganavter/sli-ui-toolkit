from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

import logging

from sli_ui_toolkit.core.debug_flags import any_flag
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.ui.widgets.overlays.in_window_overlay import TopLevelInWindowOverlay

_dnd_logger = logging.getLogger("sli_ui_toolkit.dnd")


def _dnd_debug_enabled() -> bool:
    return any_flag(
        "SLI_DND_DEBUG",
        "IMGSLI_DND_DEBUG",
        "IMGSLI_IMAGE_COMPARE_DEBUG",
        "IMGSLI_IC_DEBUG",
    )


def _dnd_debug(message: str, *args) -> None:
    if _dnd_debug_enabled():
        _dnd_logger.debug("[dnd-overlay] " + message, *args)


class DragDropOverlay(TopLevelInWindowOverlay):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            close_on_background=False,
            close_on_escape=False,
            close_on_deactivate=False,
        )
        self._horizontal = False
        self._texts = ("", "")
        self._target_rect = None

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # React to theme changes – otherwise border/text stay with old theme's
        # HighlightedText (dark in all themes due to alias fallback).
        try:
            tm = ThemeManager.get_instance()
            tm.theme_changed.connect(self.update)
        except Exception:
            pass

    def set_overlay_state(
        self,
        visible: bool,
        target_rect,
        horizontal: bool = False,
        text1: str = "",
        text2: str = "",
    ):
        _was_visible = self.isVisible()
        # Only log when visibility actually changes to avoid 60Hz spam
        _should_log = _dnd_debug_enabled() and (_was_visible != bool(visible) or self._texts != (text1, text2))
        if _should_log:
            _dnd_debug("set_overlay_state visible=%s->%s texts=%r", _was_visible, visible, (text1, text2))
        if target_rect is None:
            self.hide()
            return

        target_rect = target_rect.adjusted(0, 0, 0, 0)
        state_changed = (
            self._horizontal != horizontal
            or self._texts != (text1, text2)
            or self.geometry() != target_rect
            or self.isVisible() != bool(visible)
        )

        self._horizontal = horizontal
        self._texts = (text1, text2)
        self._target_rect = target_rect
        self.setGeometry(target_rect)

        if visible:
            self.raise_()
            self.show()
        else:
            self.hide()
            # Force immediate repaint of parent to avoid stale overlay frame
            # staying on screen until next RHI present (which is tied to image
            # decode). Without this, hide() is processed on next event loop
            # and the blue squares remain visible until the canvas repaints
            # after pyvips finishes (~0.5s).
            try:
                self.update()
                if self.parent():
                    self.parent().update()
            except Exception:
                pass

        if state_changed and visible:
            self.update()

    def paintEvent(self, event):
        if not self.isVisible():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        font = paint_font(self, pixel_size=20, bold=True)
        painter.setFont(font)

        margin = 10.0
        half_margin = margin / 2.0
        width = float(self.width())
        height = float(self.height())

        if self._horizontal:
            half_height = height / 2.0
            rects = [
                QRectF(
                    margin,
                    margin,
                    max(1.0, width - 2.0 * margin),
                    max(1.0, half_height - margin - half_margin),
                ),
                QRectF(
                    margin,
                    half_height + half_margin,
                    max(1.0, width - 2.0 * margin),
                    max(1.0, half_height - margin - half_margin),
                ),
            ]
        else:
            half_width = width / 2.0
            rects = [
                QRectF(
                    margin,
                    margin,
                    max(1.0, half_width - margin - half_margin),
                    max(1.0, height - 2.0 * margin),
                ),
                QRectF(
                    half_width + half_margin,
                    margin,
                    max(1.0, half_width - margin - half_margin),
                    max(1.0, height - 2.0 * margin),
                ),
            ]

        tm = ThemeManager.get_instance()
        accent = QColor(tm.get_color("accent"))
        fill = QColor(accent)
        fill.setAlpha(153)
        # Text/border on accent must be light for contrast in both themes.
        # HighlightedText resolves via alias to surface.background (white in
        # light, dark gray in dark) – dark text on blue is unreadable and
        # does not react to theme toggle. Use explicit white.
        try:
            cand = tm.try_get_color("HighlightedText")
            if cand is not None and cand.isValid():
                lum = (cand.red() * 299 + cand.green() * 587 + cand.blue() * 114) // 1000
                if lum > 150:
                    text_color = QColor(cand)
                    border = QColor(cand)
                    border.setAlpha(179)
                else:
                    text_color = QColor("#ffffff")
                    border = QColor("#ffffff")
                    border.setAlpha(179)
            else:
                text_color = QColor("#ffffff")
                border = QColor("#ffffff")
                border.setAlpha(179)
        except Exception:
            text_color = QColor("#ffffff")
            border = QColor("#ffffff")
            border.setAlpha(179)

        pen = QPen(border, 1.25)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(fill)

        for rect, text in zip(rects, self._texts):
            path = QPainterPath()
            path.addRoundedRect(rect, 10.0, 10.0)
            painter.drawPath(path)
            painter.setPen(text_color)
            painter.drawText(
                rect.adjusted(15.0, 15.0, -15.0, -15.0),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                text,
            )
            painter.setPen(pen)
