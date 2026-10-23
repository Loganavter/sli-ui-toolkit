from __future__ import annotations

import logging
from enum import IntEnum
from typing import Any

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.core.debug_flags import any_flag
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import apply_ui_font
from sli_ui_toolkit.ui.managers.ui_metrics import connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px

logger = logging.getLogger(__name__)

# Canonical toolkit var for adaptive tab-strip key traces. Call-time check,
# ``[TAB-BAR]`` prefix on every line, off by default even under host
# ``--debug``. Never mutates logger levels at import time.
_TABSTRIP_DEBUG_VARS = ("SLI_TABSTRIP_DEBUG",)


def _tabstrip_debug_enabled() -> bool:
    """True when tab-strip tracing was opted in via env."""
    return any_flag(*_TABSTRIP_DEBUG_VARS)


def _tabstrip_debug(message: str, *args) -> None:
    """Env-gated tab-strip trace line (already carries its ``[TAB-BAR]`` prefix)."""
    if _tabstrip_debug_enabled():
        logger.debug(message, *args)


class ButtonPosition(IntEnum):
    """Tab-button slot side (same integer values as the standard tab API)."""

    LeftSide = 0
    RightSide = 1


def _position_key(position) -> int:
    """Canonical int key for a button slot (accepts this enum or a host enum)."""
    return int(getattr(position, "value", position))


class _AdaptiveTabBar(QWidget):
    _RADIUS = 8.0
    # Bar-wide floor only: a single tab's floor is ``_min_tab_width`` (below),
    # never this value — a 10 px tab has no room for a close slot or a glyph.
    _MIN_WIDTH = 10
    _WIDTH_SCALE = 1.15
    _SIDE_PADDING = 12
    _HORIZONTAL_INSET = 2
    _TEXT_SAFETY = 6
    _CLOSE_GAP = 2
    _CLOSE_RIGHT_MARGIN = 2
    _TEXT_FADE = 26
    _SELECTED_SHADOW_OFFSET = 0.5
    _SELECTED_SHADOW_SPREAD = 1
    _TEXT_HEIGHT_PADDING = 16
    # Compressed tabs stop here: a couple of glyphs of text beside the close
    # slot. Below this the tab carries no readable label, so the bar switches
    # to horizontal scrolling instead of squeezing further (owner report
    # 2026-10-23: tabs must not turn into a scrolling list while labels are
    # still readable).
    _MIN_TEXT_WIDTH = 12
    # Side arrow gutter (design px) shown only while the bar scrolls.
    _ARROW_WIDTH = 22
    _ARROW_HALF_WIDTH = 3.5
    _ARROW_HALF_HEIGHT = 5.5
    _ARROW_STROKE = 1.6
    _ARROW_REPEAT_MS = 80
    _WHEEL_STEP = 40

    currentChanged = Signal(int)
    tabContextMenuRequested = Signal(int, QPoint)
    tabCloseRequested = Signal(int)

    def __init__(self, *, close_button_design_width: int, parent=None):
        super().__init__(parent)
        # DESIGN px (1.0-factor baseline), never a scaled snapshot: the tab
        # width resolves the close reservation through ``scaled_px`` at use
        # time (``_close_reserve_width``). A scaled value cached here at
        # construction went stale the moment UiScale changed afterwards —
        # the slots rescale (``_CloseButtonSlot.resync``) while every tab
        # stayed (new − old) px too narrow, i.e. the owner's "tab shrinks
        # after the app applies its saved scale" report.
        self._close_button_design_width = max(0, int(close_button_design_width))
        self._visual_tab_height = 36
        self._hover_index = -1
        self._current_index = -1
        self._focused_index = -1
        self._scroll_offset = 0
        self._keyboard_focus = False
        # Scroll mode is the LAST resort: ``_arrows_active`` is set by
        # ``_relayout`` only when the tabs cannot fit even at their minimum
        # width. While it is False the bar compresses instead of scrolling.
        self._arrows_active = False
        self._hover_arrow = -1
        self._pressed_arrow = -1
        self._repeat_direction = 0
        self._arrow_repeat = QTimer(self)
        self._arrow_repeat.setInterval(self._ARROW_REPEAT_MS)
        self._arrow_repeat.timeout.connect(self._repeat_arrow)
        # Each entry: {"text": str, "data": Any, "tooltip": str, "buttons": {ButtonPosition: QWidget|None}}
        self._tabs: list[dict] = []
        self._rects: list[QRect] = []
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # Text is painted natively with widget.font(); pin the scaled UI face
        # and re-resolve on a metrics change — otherwise tab text and width
        # math stay at the design size while the strip grows.
        apply_ui_font(self)
        # ``apply_ui_font`` re-applies a LATER font change (startup font
        # correction) via ``UiFont.apply``, but that only calls ``setFont`` —
        # the cached ``_rects`` (paint + hit-test) are recomputed ONLY in
        # ``_relayout``. Without this connection the tab rects stayed at the
        # transient fallback font's width until an unrelated relayout — the
        # "first tab too small for ~0.5 s, then grows" report. The unified
        # channel coalesces a same-turn font+scale pair into one refresh.
        connect_ui_metrics(self, self._on_metrics_changed)

    def _on_metrics_changed(self) -> None:
        """Re-fit cached rects/close slots when the UI font or scale changes.

        The close slots bake their size from the button at creation; re-fit
        them BEFORE the relayout positions them, so the buttons stay inside
        their tabs at the new metrics. The bar's own font is re-asserted
        first: ``standard_tab_width`` measures with ``self.font()`` (the same
        font the painter uses), and the width must be recomputed from the
        *settled* UI font — a bar whose pinned font lagged the metrics change
        that woke us would re-fit its rects from the stale face and keep the
        narrower tab the owner reported.
        """
        apply_ui_font(self)
        self._resync_close_slots()
        self._relayout()
        self.updateGeometry()
        self.update()

    def _resync_close_slots(self) -> None:
        for index in range(len(self._tabs)):
            slot = self.tabButton(index, ButtonPosition.RightSide)
            resync = getattr(slot, "resync", None)
            if callable(resync):
                resync()

    def refresh_close_slot_geometry(self) -> None:
        """Re-place the close slots and re-fit the rects after a rebuild.

        ``AdaptiveTabStrip.refresh_close_buttons`` creates/removes slots;
        the tab width reserves the REAL slot width when one is placed (see
        ``_close_reserve_width``), so the rects must be recomputed once the
        pass is over. Slots that the policy keeps are also explicitly shown
        and placed here, so a policy that shows the close button can never
        leave it hidden (or parked at a stale x) behind an earlier
        ``hide()``/``setParent(None)`` cycle.
        """
        for index in range(len(self._tabs)):
            slot = self.tabButton(index, ButtonPosition.RightSide)
            if slot is not None and slot.isHidden():
                slot.show()
        self._relayout()

    def set_visual_tab_height(self, height: int) -> None:
        self._visual_tab_height = max(1, int(height))
        self.updateGeometry()
        self.update()

    # -- tab collection management (tab-bar-compatible surface) --------

    def addTab(self, text: str) -> int:  # noqa: N802
        return self.insertTab(len(self._tabs), text)

    def insertTab(self, index: int, text: str) -> int:  # noqa: N802
        index = max(0, min(int(index), len(self._tabs)))
        self._tabs.insert(index, {"text": text, "data": None, "tooltip": "", "buttons": {}})
        self._rects.insert(index, QRect())
        previous_current = self._current_index
        if self._current_index == -1:
            self._current_index = index
        elif index <= self._current_index:
            self._current_index += 1
        self._relayout()
        self.updateGeometry()
        self.update()
        if self._current_index != previous_current:
            self.currentChanged.emit(self._current_index)
        return index

    def removeTab(self, index: int) -> None:  # noqa: N802
        if not (0 <= index < len(self._tabs)):
            return
        entry = self._tabs.pop(index)
        self._rects.pop(index)
        for widget in entry["buttons"].values():
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        previous_current = self._current_index
        if not self._tabs:
            self._current_index = -1
        elif index < self._current_index:
            self._current_index -= 1
        elif index == self._current_index:
            self._current_index = min(index, len(self._tabs) - 1)
        self._relayout()
        self.updateGeometry()
        self.update()
        if self._current_index != previous_current:
            self.currentChanged.emit(self._current_index)

    def count(self) -> int:
        return len(self._tabs)

    def currentIndex(self) -> int:  # noqa: N802
        return self._current_index

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if index == self._current_index or not (0 <= index < len(self._tabs)):
            return
        self._current_index = index
        # Keep keyboard focus in sync with selection when selection
        # changes programmatically or via mouse.
        self._focused_index = index
        self._ensure_visible(index)
        self._position_tab_buttons()
        self.update()
        self.currentChanged.emit(index)

    def _focusedTab(self) -> int:
        if 0 <= self._focused_index < len(self._tabs):
            return self._focused_index
        return self._current_index

    def _move_focus(self, delta: int) -> None:
        count = len(self._tabs)
        if count == 0:
            return
        base = self._focusedTab()
        if base < 0:
            base = self._current_index if self._current_index >= 0 else 0
        new = (base + delta) % count
        if new == self._focused_index:
            return
        self._focused_index = new
        self._ensure_visible(new)
        self._position_tab_buttons()
        self.update()

    def _activate_focused(self) -> bool:
        idx = self._focusedTab()
        if 0 <= idx < len(self._tabs) and idx != self._current_index:
            self.setCurrentIndex(idx)
            return True
        return False

    def tabText(self, index: int) -> str:  # noqa: N802
        return self._tabs[index]["text"]

    def setTabText(self, index: int, text: str) -> None:  # noqa: N802
        self._tabs[index]["text"] = text
        self._relayout()
        self.updateGeometry()
        self.update()

    def tabData(self, index: int) -> Any:  # noqa: N802
        return self._tabs[index]["data"]

    def setTabData(self, index: int, data: Any) -> None:  # noqa: N802
        self._tabs[index]["data"] = data

    def tabToolTip(self, index: int) -> str:  # noqa: N802
        if not (0 <= index < len(self._tabs)):
            return ""
        return self._tabs[index]["tooltip"]

    def setTabToolTip(self, index: int, text: str) -> None:  # noqa: N802
        self._tabs[index]["tooltip"] = text

    def tabButton(self, index: int, position) -> QWidget | None:  # noqa: N802
        if not (0 <= index < len(self._tabs)):
            return None
        return self._tabs[index]["buttons"].get(_position_key(position))

    def setTabButton(self, index: int, position, widget: QWidget | None) -> None:  # noqa: N802
        key = _position_key(position)
        existing = self._tabs[index]["buttons"].get(key)
        if existing is not None and existing is not widget:
            existing.hide()
            existing.setParent(None)
            existing.deleteLater()
        self._tabs[index]["buttons"][key] = widget
        if widget is not None:
            widget.setParent(self)
            widget.show()
        self._position_tab_buttons()

    def tabAt(self, pos: QPoint) -> int:  # noqa: N802
        # A tab scrolled under an arrow gutter is not clickable, even though
        # its (translated) rect still contains the point.
        if not self._viewport_rect().contains(pos):
            return -1
        for index, rect in enumerate(self._visual_rects()):
            if rect.contains(pos):
                return index
        return -1

    def tabRect(self, index: int) -> QRect:  # noqa: N802
        if not (0 <= index < len(self._rects)):
            return QRect()
        return self._rects[index].translated(-self._scroll_offset, 0)

    # -- sizing ----------------------------------------------------------

    def standard_tab_width(self, index: int) -> int:
        text_width = QFontMetrics(self.font()).horizontalAdvance(self._tabs[index]["text"])
        natural = (
            text_width
            + scaled_px(self._SIDE_PADDING) * 2
            + scaled_px(self._HORIZONTAL_INSET)
            + scaled_px(self._TEXT_SAFETY)
        )
        return max(scaled_px(self._MIN_WIDTH), round(natural * self._WIDTH_SCALE))

    def _close_reserve_width(self, index: int) -> int:
        """Close-button width reserved in tab *index*'s width.

        Derived from the REAL slot whenever one is placed (its own scaled
        size — a host may swap in a differently sized button via
        ``setTabButton``), else from the design size resolved at the current
        UiScale factor. Both branches agree for the toolkit's own slots
        (``_CloseButtonSlot.resync`` sizes from the same design value), so
        selecting a tab never changes any tab's width — the reservation is
        simply never a *stale* number.
        """
        slot = self.tabButton(index, ButtonPosition.RightSide)
        if slot is not None and slot.width() > 0:
            return slot.width()
        return scaled_px(self._close_button_design_width)

    def _natural_tab_width(self, index: int) -> int:
        """Width that shows the whole label plus the close slot."""
        return (
            self.standard_tab_width(index)
            + self._close_reserve_width(index)
            + scaled_px(self._CLOSE_GAP)
        )

    def _min_text_width(self) -> int:
        """Narrowest readable label: about two glyphs of the UI font.

        Measured from ``MM`` (two widest common glyphs) with a design-px floor,
        so the compression floor follows the real font instead of a guess.
        """
        return max(
            scaled_px(self._MIN_TEXT_WIDTH),
            QFontMetrics(self.font()).horizontalAdvance("MM"),
        )

    def _min_tab_width(self, index: int) -> int:
        """Width at which a tab still shows a couple of letters.

        Everything that cannot shrink (both side paddings, the inset, the
        close slot and its gap) is kept; only the text area is allowed to
        collapse to ``_min_text_width``. Below this the bar scrolls instead.
        """
        return (
            scaled_px(self._SIDE_PADDING) * 2
            + scaled_px(self._HORIZONTAL_INSET)
            + self._min_text_width()
            + self._close_reserve_width(index)
            + scaled_px(self._CLOSE_GAP)
        )

    def full_tabs_width(self) -> int:
        return sum(
            self._natural_tab_width(index) for index in range(len(self._tabs))
        )

    def _tab_height(self) -> int:
        native = QFontMetrics(self.font()).height() + scaled_px(self._TEXT_HEIGHT_PADDING)
        return max(native, self._visual_tab_height)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.full_tabs_width(), self._tab_height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._MIN_WIDTH, self._tab_height())

    # -- layout / scrolling ----------------------------------------------

    def _relayout(self) -> None:
        """Lay tabs out: natural width → compressed → scrolling.

        Three regimes, in this order (owner report 2026-10-23 — the bar used
        to jump straight to scrolling as soon as the natural widths missed):

        1. every tab fits at its natural width — nothing changes;
        2. the labels do not fit, but every tab still fits at
           ``_min_tab_width`` (a couple of glyphs beside the close slot) —
           tabs are compressed proportionally, no scrolling;
        3. even the minimum widths overflow — the bar scrolls horizontally,
           tabs keep their natural (readable) width, and the side arrow
           gutters appear. Scrolling over unreadable stubs would defeat the
           point of scrolling.
        """
        count = len(self._tabs)
        if count == 0:
            self._rects = []
            self._arrows_active = False
            self._scroll_offset = 0
            self._stop_arrow_repeat()
            self._position_tab_buttons()
            self.update()
            return
        natural = [self._natural_tab_width(index) for index in range(count)]
        minimums = [self._min_tab_width(index) for index in range(count)]
        available = max(0, self.width())
        if sum(natural) <= available:
            widths = natural
            self._arrows_active = False
        elif sum(minimums) <= available:
            widths = self._compressed_widths(available, natural, minimums)
            self._arrows_active = False
        else:
            widths = natural
            self._arrows_active = True
        if not self._arrows_active:
            self._stop_arrow_repeat()
        x = self._arrow_gutter()
        for index, width in enumerate(widths):
            self._rects[index] = QRect(x, 0, width, self._tab_height())
            x += width
        self._clamp_scroll_offset()
        self._position_tab_buttons()
        self.update()

    @staticmethod
    def _compressed_widths(
        available: int, natural: list[int], minimums: list[int]
    ) -> list[int]:
        """Shrink tabs proportionally to their shrinkable room.

        Each tab gives up a share of ``natural - minimum`` proportional to
        that room, so a long label loses more than a short one and no tab
        ever drops below ``minimums``. The float targets sum EXACTLY to
        ``available``; flooring then hands the residue to the largest
        fractional parts so the row ends on the right pixel.
        """
        room = [max(0, n - m) for n, m in zip(natural, minimums)]
        total_room = sum(room)
        deficit = sum(natural) - available
        if total_room <= 0 or deficit <= 0:
            return list(natural)
        factor = min(1.0, deficit / total_room)
        target = [n - r * factor for n, r in zip(natural, room)]
        widths = [int(value) for value in target]
        residue = available - sum(widths)
        if residue > 0:
            order = sorted(
                range(len(target)),
                key=lambda i: target[i] - widths[i],
                reverse=True,
            )
            for offset in range(min(residue, len(order))):
                widths[order[offset]] += 1
        return widths

    # -- scroll arrows ---------------------------------------------------

    def _viewport_rect(self) -> QRect:
        """Region tabs may paint in (the side gutters belong to the arrows)."""
        gutter = self._arrow_gutter()
        return QRect(
            gutter, 0, max(0, self.width() - 2 * gutter), self.height()
        )

    def _arrow_gutter(self) -> int:
        if not self._arrows_active:
            return 0
        # Never let the gutters consume the whole bar on a tiny window.
        return min(
            scaled_px(self._ARROW_WIDTH),
            max(0, (self.width() - scaled_px(self._MIN_WIDTH)) // 2),
        )

    def _arrow_rects(self) -> tuple[QRect, QRect]:
        gutter = self._arrow_gutter()
        if gutter <= 0:
            return QRect(), QRect()
        return (
            QRect(0, 0, gutter, self.height()),
            QRect(self.width() - gutter, 0, gutter, self.height()),
        )

    def _arrow_at(self, pos: QPoint) -> int:
        """0 = left arrow, 1 = right arrow, -1 = none."""
        if not self._arrows_active:
            return -1
        left, right = self._arrow_rects()
        if left.contains(pos):
            return 0
        if right.contains(pos):
            return 1
        return -1

    def _arrow_enabled(self, direction: int) -> bool:
        if direction < 0:
            return self._scroll_offset > 0
        return self._scroll_offset < self._max_scroll_offset()

    def _max_scroll_offset(self) -> int:
        # Measured against the viewport's right edge, not its width: with the
        # arrow gutters reserved the row starts *after* the left gutter, so
        # ``total - viewport.width()`` would overscroll by one gutter.
        total = self._rects[-1].right() + 1 if self._rects else 0
        return max(0, total - self._viewport_rect().right() - 1)

    def _clamp_scroll_offset(self) -> None:
        self._scroll_offset = max(0, min(self._scroll_offset, self._max_scroll_offset()))

    def _visual_rects(self) -> list[QRect]:
        return [rect.translated(-self._scroll_offset, 0) for rect in self._rects]

    def _ensure_visible(self, index: int) -> None:
        if not (0 <= index < len(self._rects)):
            return
        viewport = self._viewport_rect()
        rect = self._rects[index]
        left = rect.left() - self._scroll_offset
        right = rect.right() - self._scroll_offset
        if left < viewport.left():
            self._scroll_offset = rect.left() - viewport.left()
        elif right > viewport.right():
            self._scroll_offset = rect.right() - viewport.right()
        self._clamp_scroll_offset()

    def _step_arrows(self, direction: int) -> bool:
        """Reveal the next whole tab; True when the offset actually moved.

        A step targets the nearest tab that is FULLY hidden on the side being
        scrolled toward, and aligns it with the leading viewport edge. A fixed
        pixel page (or "the first clipped pixel") made one click move a single
        pixel at the end of the row; a whole-tab step always lands on a
        readable label, which is what the arrows are for. No fully hidden tab
        left on that side ⇒ jump to the corresponding end.
        """
        if self._max_scroll_offset() <= 0:
            return False
        viewport = self._viewport_rect()
        before = self._scroll_offset
        target: int | None = None
        if direction > 0:
            for index in range(len(self._rects)):
                rect = self.tabRect(index)
                if rect.left() >= viewport.right():
                    target = self._scroll_offset + (rect.left() - viewport.left())
                    break
            if target is None:
                target = self._max_scroll_offset()
        else:
            for index in range(len(self._rects) - 1, -1, -1):
                rect = self.tabRect(index)
                if rect.right() < viewport.left():
                    target = self._scroll_offset - (viewport.right() - rect.right())
                    break
            if target is None:
                target = 0
        self._scroll_offset = target
        self._clamp_scroll_offset()
        if self._scroll_offset == before:
            return False
        self._position_tab_buttons()
        self.update()
        return True

    def _start_arrow_repeat(self, direction: int) -> None:
        self._repeat_direction = direction
        self._arrow_repeat.start()

    def _stop_arrow_repeat(self) -> None:
        self._repeat_direction = 0
        if self._arrow_repeat.isActive():
            self._arrow_repeat.stop()

    def _repeat_arrow(self) -> None:
        if self._repeat_direction == 0:
            self._stop_arrow_repeat()
            return
        if not self._step_arrows(self._repeat_direction):
            self._stop_arrow_repeat()

    def wheelEvent(self, event) -> None:  # noqa: N802
        """Strip scroll only — the wheel never activates a tab.

        The event is ALWAYS accepted, even when there is nothing to scroll:
        an ignored wheel propagates to the host, where it can be read as
        "next/previous tab" (the owner's report) — the strip owns the gesture
        wherever the pointer is over it.
        """
        event.accept()
        self._stop_arrow_repeat()
        if self._max_scroll_offset() <= 0:
            return
        delta = event.pixelDelta()
        dx = delta.x()
        dy = delta.y()
        if dx == 0 and dy == 0:
            angle = event.angleDelta()
            dx = angle.x()
            dy = angle.y()
        if dx == 0 and dy == 0:
            return
        step = -(dx if dx != 0 else dy) / 120 * scaled_px(self._WHEEL_STEP)
        if step == 0:
            return
        self._scroll_offset += round(step)
        self._clamp_scroll_offset()
        self._position_tab_buttons()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = self._palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(event.rect())
        painter.fillRect(self.rect(), QColor(palette["strip"]))
        # Tabs are clipped to the scroll viewport so a tab sliding under an
        # arrow gutter never paints across the arrow.
        viewport = self._viewport_rect()
        painter.setClipRect(viewport.intersected(event.rect()))
        for index in range(len(self._tabs)):
            if index != self._current_index:
                self._paint_visible_tab(painter, index, viewport, palette)
        if self._current_index >= 0:
            self._paint_visible_tab(painter, self._current_index, viewport, palette)
        painter.setClipRect(event.rect())
        if self._arrows_active:
            self._paint_arrows(painter, event.rect(), palette)

    def _paint_arrows(self, painter: QPainter, exposed_rect: QRect, palette) -> None:
        left, right = self._arrow_rects()
        for direction, rect in ((0, left), (1, right)):
            if rect.isEmpty() or not rect.intersects(exposed_rect):
                continue
            self._paint_arrow(
                painter,
                rect,
                direction,
                self._arrow_enabled(-1 if direction == 0 else 1),
                hovered=self._hover_arrow == direction,
                pressed=self._pressed_arrow == direction,
                palette=palette,
            )

    def _paint_arrow(
        self,
        painter: QPainter,
        rect: QRect,
        direction: int,
        enabled: bool,
        hovered: bool,
        pressed: bool,
        palette,
    ) -> None:
        """One chevron, painter-drawn from theme tokens (no icons, no QSS)."""
        painter.save()
        if hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette["hover"]))
            inset = scaled_px(2)
            painter.drawRoundedRect(
                rect.adjusted(inset, scaled_px(4), -inset, -scaled_px(4)),
                scaled_px(5),
                scaled_px(5),
            )
        color = QColor(palette["text"])
        if not enabled:
            color.setAlpha(70)
        elif pressed:
            color.setAlpha(255)
        else:
            color.setAlpha(200)
        thickness = max(1.0, float(scaled_px(self._ARROW_STROKE)))
        painter.setPen(
            QPen(
                color,
                thickness,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        center = rect.center()
        reach = max(1.0, float(scaled_px(self._ARROW_HALF_WIDTH)))
        lift = max(1.0, float(scaled_px(self._ARROW_HALF_HEIGHT)))
        # direction 0 = left (chevron points left), 1 = right.
        sign = 1.0 if direction == 0 else -1.0
        pointer = QPointF(center.x() - sign * reach, center.y())
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(center.x() + sign * reach, center.y() - lift),
                    pointer,
                    QPointF(center.x() + sign * reach, center.y() + lift),
                ]
            )
        )
        painter.restore()

    def _paint_visible_tab(self, painter, index, exposed_rect, palette) -> None:
        rect = self.tabRect(index)
        if rect.isValid() and rect.intersects(exposed_rect):
            self._paint_tab(painter, index, rect, palette)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            arrow = self._arrow_at(pos)
            if arrow >= 0:
                self._pressed_arrow = arrow
                direction = -1 if arrow == 0 else 1
                if self._arrow_enabled(direction):
                    self._step_arrows(direction)
                    self._start_arrow_repeat(direction)
                self.update()
                event.accept()
                return
            index = self.tabAt(pos)
            if index >= 0:
                self.setCurrentIndex(index)
                self._focused_index = index
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        _tabstrip_debug("[TAB-BAR] key=%s count=%s current=%s", key, len(self._tabs), self._current_index)
        count = len(self._tabs)
        if count == 0:
            return super().keyPressEvent(event)
        current = self._current_index if self._current_index >= 0 else 0
        if key == Qt.Key.Key_Down:
            # Hand off to the next focusable widget in the app layout
            # (typically the content area below the tab strip).
            if self.focusNextChild():
                event.accept()
                return
        if key == Qt.Key.Key_Up:
            if self.focusPreviousChild():
                event.accept()
                return
        if key == Qt.Key.Key_Left:
            # Move keyboard focus, don't activate yet — Enter confirms.
            if self._focusedTab() == 0:
                strip = self.parentWidget()
                if strip is not None:
                    add_btn = getattr(strip, "add_button", None)
                    if add_btn is not None and add_btn.isVisible():
                        add_btn.setFocus(Qt.FocusReason.OtherFocusReason)
                        event.accept()
                        return
            self._move_focus(-1)
            event.accept()
        elif key == Qt.Key.Key_Right:
            if self._focusedTab() == count - 1:
                strip = self.parentWidget()
                if strip is not None:
                    add_btn = getattr(strip, "add_button", None)
                    if add_btn is not None and add_btn.isVisible():
                        add_btn.setFocus(Qt.FocusReason.OtherFocusReason)
                        event.accept()
                        return
            self._move_focus(1)
            event.accept()
        elif key == Qt.Key.Key_Home:
            if count:
                self._focused_index = 0
                self._ensure_visible(0)
                self._position_tab_buttons()
                self.update()
            event.accept()
        elif key == Qt.Key.Key_End:
            if count:
                self._focused_index = count - 1
                self._ensure_visible(count - 1)
                self._position_tab_buttons()
                self.update()
            event.accept()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._activate_focused():
                event.accept()
                return
            super().keyPressEvent(event)
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            target = self._focusedTab()
            if 0 <= target < count:
                self.tabCloseRequested.emit(target)
                event.accept()
        else:
            super().keyPressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._pressed_arrow >= 0:
            self._stop_arrow_repeat()
            self._pressed_arrow = -1
            self.update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            pos = event.position().toPoint()
            index = self.tabAt(pos)
            if index >= 0 and not self._close_slot_contains(index, pos):
                if hasattr(event, "globalPosition"):
                    global_pos = event.globalPosition().toPoint()
                else:
                    global_pos = self.mapToGlobal(pos)
                self.tabContextMenuRequested.emit(index, global_pos)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def _close_slot_contains(self, index: int, pos: QPoint) -> bool:
        slot = self.tabButton(index, ButtonPosition.RightSide)
        if slot is None or not slot.isVisible():
            return False
        return slot.geometry().contains(pos)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position().toPoint()
        arrow = self._arrow_at(pos)
        if arrow != self._hover_arrow:
            self._hover_arrow = arrow
            self.update()
        # A gutter is not a tab: hovering an arrow must not highlight the
        # tab scrolling underneath it.
        self._set_hover_index(-1 if arrow >= 0 else self.tabAt(pos))
        super().mouseMoveEvent(event)

    def set_hover_from_global(self, global_pos) -> None:
        local_pos = self.mapFromGlobal(global_pos)
        hover_index = self.tabAt(local_pos) if self.rect().contains(local_pos) else -1
        self._set_hover_index(hover_index)

    def _set_hover_index(self, index: int) -> None:
        if index != self._hover_index:
            self._hover_index = index
            self.update()
            self._update_close_slots()

    def _update_close_slots(self) -> None:
        for index in range(len(self._tabs)):
            slot = self.tabButton(index, ButtonPosition.RightSide)
            if slot is not None:
                slot.update()
                button = getattr(slot, "button", None)
                if button is not None:
                    button.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._stop_arrow_repeat()
        self._hover_arrow = -1
        self._pressed_arrow = -1
        if self._hover_index != -1:
            self._hover_index = -1
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event):  # noqa: N802
        # Ring modality resolved centrally via NavigationManager (4.2.4):
        # input device is the source of truth, reason is only a hint.
        try:
            from sli_ui_toolkit.ui.managers.navigation_manager import (
                resolve_keyboard_focus,
            )

            self._keyboard_focus = resolve_keyboard_focus(event.reason())
        except Exception:
            # degraded, no manager
            self._keyboard_focus = event.reason() not in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.MenuBarFocusReason,
                Qt.FocusReason.PopupFocusReason,
            )
        if self._focused_index < 0 or not (0 <= self._focused_index < len(self._tabs)):
            self._focused_index = self._current_index
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):  # noqa: N802
        self._keyboard_focus = False
        super().focusOutEvent(event)
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # The width picks the layout regime (natural / compressed / scrolling),
        # so the whole layout re-runs here, not just the scroll clamp.
        self._relayout()
        # Keep the current tab (and its close button) in view when the bar
        # shrinks — plain clamping can leave it scrolled past the edge.
        if self._current_index >= 0:
            self._ensure_visible(self._current_index)
        self._position_tab_buttons()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._relayout()
            self.updateGeometry()
            self.update()

    def _position_tab_buttons(self) -> None:
        viewport = self._viewport_rect()
        for index in range(len(self._tabs)):
            slot = self.tabButton(index, ButtonPosition.RightSide)
            if slot is None:
                continue
            tab_rect = self._painted_tab_rect(self.tabRect(index))
            x = tab_rect.right() - slot.width() - scaled_px(self._CLOSE_RIGHT_MARGIN) + 1
            y = tab_rect.center().y() - slot.height() // 2
            slot.move(x, y)
            # Child widgets are not clipped by the painter: a close slot of a
            # tab scrolled under an arrow gutter would float on top of the
            # arrow. Hide it while it is not fully inside the viewport.
            slot.setVisible(viewport.contains(slot.geometry()))

    def _painted_tab_rect(self, rect: QRect) -> QRect:
        height = min(rect.height(), self._visual_tab_height)
        top = rect.top() + max(0, (rect.height() - height) // 2)
        return QRect(rect.left() + 1, top, max(0, rect.width() - 2), height)

    def _paint_tab(self, painter: QPainter, index: int, rect: QRect, palette: dict[str, str]) -> None:
        selected = index == self.currentIndex()
        hovered = not selected and index == self._hover_index
        focused = (index == self._focusedTab() and self._keyboard_focus and self.hasFocus())
        tab_rect = self._painted_tab_rect(rect)
        if selected:
            self._paint_selected_shadow(painter, tab_rect)
            self._paint_selected_background(painter, tab_rect, palette)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette["hover"]))
            painter.drawRoundedRect(tab_rect, scaled_px(self._RADIUS), scaled_px(self._RADIUS))
        # Focus ring: same style as Button's FocusLayer — accent-colored
        # QPainterPath rounded rect on the FULL tab area (including close
        # button slot) so the ring covers all child widgets.
        if focused:
            from PySide6.QtGui import QPainterPath

            factor = UiScale.get_instance().factor()
            design_radius = self._RADIUS / factor if factor > 0 else self._RADIUS
            thickness = max(1.0, 2.0 * factor)
            inset = thickness * 0.5
            ring = QRectF(rect).adjusted(inset, inset, -inset, -inset)
            if ring.width() > 0 and ring.height() > 0:
                path = QPainterPath()
                path.addRoundedRect(ring, design_radius, design_radius)
                accent_raw = palette.get("accent")
                if accent_raw is None:
                    from sli_ui_toolkit.theme import ThemeManager as _TM

                    tm2 = _TM.get_instance()
                    accent_c = tm2.try_get_color("accent")
                    accent_raw = accent_c.name() if accent_c is not None and accent_c.isValid() else tm2.get_color("accent").name()
                color = QColor(accent_raw)
                color.setAlpha(220)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(QPen(color, thickness))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
                painter.restore()

        text_right = tab_rect.right() - scaled_px(self._SIDE_PADDING)
        close_slot = self.tabButton(index, ButtonPosition.RightSide)
        has_close = close_slot is not None and close_slot.isVisible()
        if has_close and close_slot is not None:
            text_right = min(text_right, close_slot.geometry().left() - scaled_px(self._CLOSE_GAP))
        text_rect = QRect(
            tab_rect.left() + scaled_px(self._SIDE_PADDING),
            tab_rect.top(),
            max(0, text_right - tab_rect.left() - scaled_px(self._SIDE_PADDING) + 1),
            tab_rect.height(),
        )
        if text_rect.width() <= 0:
            return
        metrics = QFontMetrics(self.font())
        raw_text = self.tabText(index)
        needs_fade = has_close and metrics.horizontalAdvance(raw_text) > text_rect.width()
        text = raw_text if needs_fade else metrics.elidedText(
            raw_text, Qt.TextElideMode.ElideRight, text_rect.width()
        )
        painter.setPen(QColor(palette["text"]))
        painter.save()
        # Intersect, never replace: a plain setClipRect() drops the bar's
        # viewport clip, and a tab sliding under an arrow gutter then paints
        # its label across the chevron (caught by a live capture).
        painter.setClipRect(text_rect, Qt.ClipOperation.IntersectClip)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        painter.restore()
        if needs_fade:
            fade = QLinearGradient(text_rect.right() - scaled_px(self._TEXT_FADE), 0, text_rect.right() + 1, 0)
            fade.setColorAt(0.0, QColor(0, 0, 0, 0))
            fade.setColorAt(1.0, QColor(palette["background"]))
            painter.fillRect(
                QRect(
                    text_rect.right() - scaled_px(self._TEXT_FADE),
                    tab_rect.top(),
                    scaled_px(self._TEXT_FADE) + 1,
                    tab_rect.height(),
                ),
                fade,
            )

    def close_slot_background_color(self, slot: QWidget) -> QColor | None:
        for index in range(self.count()):
            if self.tabButton(index, ButtonPosition.RightSide) is not slot:
                continue
            if index == self.currentIndex():
                return QColor(self._palette()["background"])
            if index == self._hover_index:
                return QColor(self._palette()["hover"])
            return QColor(self._palette()["strip"])
        return None

    def _paint_selected_background(self, painter, rect, palette) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette["background"]))
        painter.drawRoundedRect(rect, scaled_px(self._RADIUS), scaled_px(self._RADIUS))
        painter.setPen(QPen(QColor(palette["border"]), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, scaled_px(self._RADIUS), scaled_px(self._RADIUS))

    def _paint_selected_shadow(self, painter, rect) -> None:
        if rect.width() <= 0 or rect.height() <= 0:
            return
        painter.save()
        painter.setClipRect(
            QRectF(
                rect.left() - 1,
                rect.bottom() - 1,
                rect.width() + 2,
                self._SELECTED_SHADOW_OFFSET + self._SELECTED_SHADOW_SPREAD + 3,
            )
        )
        painter.setPen(Qt.PenStyle.NoPen)
        soft_rect = QRectF(rect).adjusted(
            0,
            self._SELECTED_SHADOW_OFFSET,
            0,
            self._SELECTED_SHADOW_OFFSET + self._SELECTED_SHADOW_SPREAD,
        )
        painter.setBrush(QColor(0, 0, 0, 55))
        painter.drawRoundedRect(soft_rect, scaled_px(self._RADIUS), scaled_px(self._RADIUS))
        core_rect = QRectF(rect).adjusted(
            1,
            self._SELECTED_SHADOW_OFFSET - 1,
            -1,
            self._SELECTED_SHADOW_OFFSET,
        )
        painter.setBrush(QColor(0, 0, 0, 125))
        painter.drawRoundedRect(core_rect, scaled_px(self._RADIUS) - 1, scaled_px(self._RADIUS) - 1)
        painter.restore()

    def _palette(self) -> dict[str, str]:
        theme = ThemeManager.get_instance()

        def color(token: str, fallback_token: str | None = None) -> str:
            value = theme.try_get_color(token)
            if value is not None and value.isValid():
                return value.name()
            # Fallback through palette defaults (theme-aware) instead of hard light hex
            fb = fallback_token or token
            fallback_color = theme.try_get_color(fb)
            if fallback_color is not None and fallback_color.isValid():
                return fallback_color.name()
            return theme.get_color(token).name()

        return {
            "strip": color("surface.list"),
            "background": color("surface.background", "Window"),
            "border": color("separator.color"),
            "hover": color("button.toggle.background.hover"),
            "text": color("WindowText"),
        }
