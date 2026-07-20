from PySide6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from sli_ui_toolkit.config import get_dragdrop_service
from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import apply_text_color, rebase_font, ui_font
from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState

DEFAULT_MINUS_ICON = "remove"
DEFAULT_PLUS_ICON = "add"


class _RatingRowBgLayer(Layer):
    """Position-aware rounded BG: outer corners use outer_r, internal use inner_r.

    Reads `widget.position` ∈ {"first","middle","last","only"} и `widget.is_current`,
    `widget._is_being_dragged`. Inset фон на 2px.
    """

    INNER_R = 5
    OUTER_R = 8

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        states = ctx.effective_states
        is_selected = bool(getattr(widget, "is_selected", False))
        is_active = (
            widget.is_current
            or is_selected
            or ButtonState.HOVERED in states
            or ButtonState.PRESSED in states
        )
        key = "list_item.background.hover" if is_active else "list_item.background.normal"
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if widget._is_being_dragged:
            p.setOpacity(0.35)
        p.setPen(Qt.PenStyle.NoPen)
        if is_selected:
            # Soft accent wash for ctrl+LMB-selected rows — including the
            # current row when it is part of the selection (its accent bar
            # still shows on top).
            accent = QColor(tm.get_color("accent"))
            base = QColor(tm.get_color(key))
            fill = QColor(
                int(round(accent.red() * 0.38 + base.red() * 0.62)),
                int(round(accent.green() * 0.38 + base.green() * 0.62)),
                int(round(accent.blue() * 0.38 + base.blue() * 0.62)),
            )
            p.setBrush(fill)
        else:
            p.setBrush(tm.get_color(key))
        bg_rect = ctx.rect.toRect().adjusted(2, 2, -2, -2)
        pos = widget.position
        if pos == "middle":
            p.drawRoundedRect(bg_rect, self.INNER_R, self.INNER_R)
        else:
            r = bg_rect
            tl = self.OUTER_R if pos in ("first", "only") else self.INNER_R
            tr = self.OUTER_R if pos in ("first", "only") else self.INNER_R
            bl = self.OUTER_R if pos in ("last", "only") else self.INNER_R
            br = self.OUTER_R if pos in ("last", "only") else self.INNER_R
            path = QPainterPath()
            path.moveTo(r.left() + tl, r.top())
            path.lineTo(r.right() - tr, r.top())
            path.arcTo(r.right() - 2 * tr, r.top(), 2 * tr, 2 * tr, 90, -90)
            path.lineTo(r.right(), r.bottom() - br)
            path.arcTo(r.right() - 2 * br, r.bottom() - 2 * br, 2 * br, 2 * br, 0, -90)
            path.lineTo(r.left() + bl, r.bottom())
            path.arcTo(r.left(), r.bottom() - 2 * bl, 2 * bl, 2 * bl, -90, -90)
            path.lineTo(r.left(), r.top() + tl)
            path.arcTo(r.left(), r.top(), 2 * tl, 2 * tl, 180, -90)
            path.closeSubpath()
            p.drawPath(path)
        if widget._is_being_dragged:
            p.setOpacity(1.0)


class _RatingRowIndicatorLayer(Layer):
    """Левый accent-бар для current row."""

    def applies(self, ctx) -> bool:
        return bool(getattr(ctx.widget, "is_current", False))

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        rect = ctx.rect.toRect()
        pen = QPen(tm.get_color("accent"))
        pen.setWidth(3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p = ctx.painter
        if widget._is_being_dragged:
            p.setOpacity(0.35)
        p.setPen(pen)
        x = rect.left() + pen.width()
        p.drawLine(x, rect.top() + 7, x, rect.bottom() - 7)
        if widget._is_being_dragged:
            p.setOpacity(1.0)


class _RatingRowSeparatorLayer(Layer):
    """Вертикальный separator между rating_label и name_label (только image-type)."""

    def applies(self, ctx) -> bool:
        widget = ctx.widget
        return widget.item_type == "image" and getattr(widget, "rating_label", None) is not None

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        p = ctx.painter
        if widget._is_being_dragged:
            p.setOpacity(0.35)
        p.setPen(QPen(tm.get_color("separator.color"), 1))
        x_pos = widget.rating_label.geometry().right() + widget.layout.spacing() // 2
        p.drawLine(x_pos, 6, x_pos, widget.height() - 6)
        if widget._is_being_dragged:
            p.setOpacity(1.0)


class RatingListItem(Button):
    itemSelected = Signal(int)
    itemSelectionToggled = Signal(int)
    itemRightClicked = Signal(int)

    def __init__(
        self,
        index,
        text,
        rating,
        full_path: str,
        list_num: int | None = None,
        get_rating=None,
        increment_rating=None,
        decrement_rating=None,
        create_rating_gesture=None,
        on_update_drop_indicator=None,
        on_clear_drop_indicator=None,
        parent=None,
        is_current: bool = False,
        item_height: int = 36,
        item_font: QFont = None,
        item_type="image",
        position="middle",
        wheel_requires_focus: bool = False,
        *,
        image_number: int | None = None,
    ):
        # `item_type`/`position` нужны кастомным layer'ам ещё до super().__init__,
        # потому что Button.__init__ может вызвать update()/paint в зависимости
        # от theme bootstrap.
        self.item_type = item_type
        self.position = position
        self.is_current = is_current
        self.is_selected = False
        self._is_being_dragged = False
        self.rating_label = None
        super().__init__(
            text="",
            size=(0, item_height),
            corner_radius=8,
            wheel_requires_focus=wheel_requires_focus,
            layers=[
                _RatingRowBgLayer(),
                RippleLayer(),
                _RatingRowIndicatorLayer(),
                _RatingRowSeparatorLayer(),
            ],
            parent=parent,
        )
        self.index = index
        self.full_path = full_path
        if list_num is None:
            list_num = image_number
        if list_num is None:
            raise TypeError("RatingListItem requires list_num (or legacy image_number)")
        self.list_num = int(list_num)
        self._get_rating = get_rating
        self._increment_rating = increment_rating
        self._decrement_rating = decrement_rating
        self._create_rating_gesture = create_rating_gesture
        self._on_update_drop_indicator = on_update_drop_indicator
        self._on_clear_drop_indicator = on_clear_drop_indicator

        self.theme_manager.theme_changed.connect(self.update_styles)

        self.drag_start_pos = QPoint()
        self._drag_start_pos_global = QPointF()

        self.tooltip_timer = QTimer(self)
        self.tooltip_timer.setSingleShot(True)
        self.tooltip_timer.setInterval(500)
        self.tooltip_timer.timeout.connect(self._show_tooltip)

        # Row click → external selection. Button.clicked не срабатывает, если
        # release пришёл по child-Button'у (Qt потребит event на ребёнке) или
        # если start drag отменил его (см. mouseReleaseEvent).
        # Guard: nested +/- must never select/close the flyout even if a press
        # still bubbles (pre-accept Button handlers).
        self.clicked.connect(self._emit_item_selected_from_row)
        self.rightClicked.connect(lambda: self.itemRightClicked.emit(self.index))

        self.layout = QHBoxLayout(self)

        # Right margin is wider so the + button keeps a visible gap from the
        # (2px-inset) row background edge.
        self.layout.setContentsMargins(2, 2, 4, 2)
        self.layout.setSpacing(6)

        if self.item_type == "image":
            self.rating_label = QLabel(str(rating), self)
            self.rating_label.setFixedWidth(25)
            self.rating_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rating_label.setObjectName("ratingLabel")

        self.name_label = QLabel(text, self)
        self.name_label.setObjectName("nameLabel")
        self.name_label.setMinimumWidth(0)
        self.name_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction
        )

        self.name_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

        base_font = rebase_font(item_font) if item_font else ui_font()
        self.name_label.setFont(base_font)

        if self.item_type == "image":

            base_px = base_font.pixelSize()
            if base_px <= 0:
                base_px = QFontMetrics(base_font).height()
            rating_font = rebase_font(base_font, pixel_size=max(8, base_px - 3))
            self.rating_label.setFont(rating_font)

            self.btn_minus = Button(
                resolve_icon(DEFAULT_MINUS_ICON), icon_size=14, parent=self
            )
            self.btn_plus = Button(
                resolve_icon(DEFAULT_PLUS_ICON), icon_size=14, parent=self
            )
            self.btn_minus.setObjectName("minusButton")
            self.btn_plus.setObjectName("plusButton")
            for btn in [self.btn_minus, self.btn_plus]:
                btn.setFixedSize(22, 22)
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

            self.layout.addWidget(self.rating_label)
            self.layout.addWidget(self.name_label, 1)
            self.layout.addWidget(self.btn_minus)
            self.layout.addWidget(self.btn_plus)

            self.btn_plus.clicked.connect(self._on_plus_clicked)
            self.btn_minus.clicked.connect(self._on_minus_clicked)
            self.btn_plus.pressed.connect(lambda: self._on_button_pressed(self.btn_plus))
            self.btn_minus.pressed.connect(lambda: self._on_button_pressed(self.btn_minus))
            self.btn_plus.released.connect(
                lambda: self._on_button_released(self.btn_plus)
            )
            self.btn_minus.released.connect(
                lambda: self._on_button_released(self.btn_minus)
            )
            self._gesture_tx = None
            self._active_button = None
            self._is_drag_initiated = False
            self.btn_plus.installEventFilter(self)
            self.btn_minus.installEventFilter(self)
        else:
            self.layout.addWidget(self.name_label, 1)

        self.update_styles()

    def set_dragging_state(self, is_dragging: bool):
        self._is_being_dragged = bool(is_dragging)
        self.update()

    @property
    def image_number(self) -> int:
        return self.list_num

    @image_number.setter
    def image_number(self, value: int) -> None:
        self.list_num = int(value)

    def set_selected(self, selected: bool) -> None:
        selected = bool(selected)
        if self.is_selected == selected:
            return
        self.is_selected = selected
        self._sync_rating_button_selection_background()
        self.update()

    def _sync_rating_button_selection_background(self) -> None:
        if self.item_type != "image":
            return
        color = QColor(self.theme_manager.get_color("accent")) if self.is_selected else None
        self.btn_minus.set_override_bg_color(color)
        self.btn_plus.set_override_bg_color(color)

    def _find_panel(self):
        widget = self.parentWidget()
        while widget is not None:
            if widget.objectName() == "UnifiedFlyoutPanel":
                return widget
            widget = widget.parentWidget()
        return None

    def drag_indices(self) -> list[int]:
        """Indices to move: multi-selection if this row is in it, else self."""
        panel = self._find_panel()
        if panel is None:
            return [self.index]
        getter = getattr(panel, "selected_indices", None)
        if not callable(getter):
            return [self.index]
        selected = sorted(getter())
        if self.index in selected and len(selected) > 1:
            return selected
        return [self.index]

    def set_batch_dragging_state(self, dragging: bool, indices) -> None:
        panel = self._find_panel()
        if panel is not None and hasattr(panel, "set_items_dragging"):
            panel.set_items_dragging(indices, bool(dragging))
            return
        self.set_dragging_state(dragging)

    def eventFilter(self, obj, event):
        item_type = getattr(self, "item_type", None)
        if item_type != "image":
            return super().eventFilter(obj, event)

        btn_plus = getattr(self, "btn_plus", None)
        btn_minus = getattr(self, "btn_minus", None)
        if obj in (btn_plus, btn_minus):
            if event.type() == QEvent.Type.MouseMove and (
                event.buttons() & Qt.MouseButton.LeftButton
            ):
                if self._active_button is obj and not self._is_drag_initiated:
                    try:
                        obj._initial_delay_timer.stop()
                        obj._repeat_timer.stop()
                    except Exception:
                        pass
                    distance = (
                        event.globalPosition() - self._drag_start_pos_global
                    ).manhattanLength()
                    if distance >= QApplication.startDragDistance():
                        self._cancel_button_interaction()

                return True

        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        if not self.shouldHandleWheelEvent(event):
            return
        if self.item_type != "image":
            return

        pos = event.position().toPoint()

        if self.rating_label.geometry().contains(pos):
            delta = event.angleDelta().y()
            if delta > 0:
                self._increment_rating(self.list_num, self.index)
            else:
                self._decrement_rating(self.list_num, self.index)
            self._update_label_from_store()
            event.accept()
        else:

            event.ignore()

    def update_styles(self):
        tm = self.theme_manager
        apply_text_color(self.name_label, tm.get_color("list_item.text.normal"))
        if self.item_type == "image":
            apply_text_color(
                self.rating_label, tm.get_color("list_item.text.rating")
            )
            self.btn_minus.setIcon(resolve_icon(DEFAULT_MINUS_ICON))
            self.btn_plus.setIcon(resolve_icon(DEFAULT_PLUS_ICON))
            self._sync_rating_button_selection_background()
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.full_path:
            self.tooltip_timer.start()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()

    def mousePressEvent(self, event: QMouseEvent):
        self.tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self._drag_start_pos_global = event.globalPosition()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._is_drag_initiated:
            return
        if not self._drag_allowed():
            return

        current_global_pos = self.mapToGlobal(event.pos())
        start_global_pos = self.mapToGlobal(self.drag_start_pos)
        distance = (current_global_pos - start_global_pos).manhattanLength()

        if distance >= QApplication.startDragDistance():
            if self.item_type == "image" and self._active_button:
                try:
                    self._active_button._initial_delay_timer.stop()
                    self._active_button._repeat_timer.stop()
                except Exception:
                    pass
                if self._gesture_tx is not None:
                    self._gesture_tx.rollback()
                    self._gesture_tx = None

            self.tooltip_timer.stop()
            PathTooltip.get_instance().hide_tooltip()

            self._is_drag_initiated = True
            panel = self._find_panel()
            if panel is not None and self.index not in panel.selected_indices():
                # Dragging a row outside the marquee selection collapses it;
                # dragging a selected row keeps it (multi-move).
                panel.clear_selection()
            service = get_dragdrop_service()
            if service is not None and not service.is_dragging():
                service.start_drag(self, event)
            self._notify_flyout_drop_indicator(event.globalPosition())

    def _drag_allowed(self) -> bool:
        widget = self.parentWidget()
        while widget is not None:
            getter = getattr(widget, "is_drag_enabled", None)
            if callable(getter):
                return bool(getter())
            widget = widget.parentWidget()
        return True

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._is_drag_initiated:
            # Drag swallowed the click — clear PRESSED state without firing
            # Button.clicked → itemSelected.
            self._pressed = False
            self._pressed_region = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

        if (
            self.item_type == "image"
            and self._gesture_tx is not None
            and self._active_button is None
        ):
            self._gesture_tx.commit()
            self._gesture_tx = None
            self._update_label_from_store()

        self._is_drag_initiated = False
        self._active_button = None
        self._notify_flyout_clear_indicator()

    def _emit_item_selected_from_row(self) -> None:
        if self.item_type == "image":
            # Nested +/- previously bubbled an unaccepted press to this row,
            # which selected the item and closed UnifiedFlyout.
            under = self.childAt(self.mapFromGlobal(QCursor.pos()))
            if under is self.btn_plus or under is self.btn_minus:
                return
            if under is not None and (
                self.btn_plus.isAncestorOf(under) or self.btn_minus.isAncestorOf(under)
            ):
                return
        modifiers = QApplication.keyboardModifiers()
        if modifiers & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ):
            self.itemSelectionToggled.emit(self.index)
            return
        self.itemSelected.emit(self.index)

    def _on_plus_clicked(self):
        if self._is_drag_initiated or self._active_button not in (None, self.btn_plus):
            return
        self._clear_panel_selection()
        if self._gesture_tx is not None:
            self._gesture_tx.apply_delta(+1)
        else:
            self._increment_rating(self.list_num, self.index)
        self._update_label_from_store()

    def _on_minus_clicked(self):
        if self._is_drag_initiated or self._active_button not in (None, self.btn_minus):
            return
        self._clear_panel_selection()
        if self._gesture_tx is not None:
            self._gesture_tx.apply_delta(-1)
        else:
            self._decrement_rating(self.list_num, self.index)
        self._update_label_from_store()

    def _clear_panel_selection(self):
        panel = self._find_panel()
        if panel is not None and hasattr(panel, "clear_selection"):
            panel.clear_selection()

    def _on_button_pressed(self, button):
        if self.item_type != "image":
            return
        self._active_button = button
        self._drag_start_pos_global = QPointF(QCursor.pos())
        self.drag_start_pos = self.mapFromGlobal(QCursor.pos())
        starting_score = self._get_rating(self.list_num, self.index)
        self._gesture_tx = self._create_rating_gesture(
            self.list_num,
            self.index,
            starting_score,
        )

    def _on_button_released(self, button):
        if self._active_button is not button:
            return
        if self._gesture_tx is not None and not self._is_drag_initiated:
            self._gesture_tx.commit()
            self._gesture_tx = None
            self._update_label_from_store()
        self._active_button = None

    def _cancel_button_interaction(self):
        if self._gesture_tx is not None:
            self._gesture_tx.rollback()
            self._gesture_tx = None
        self._active_button = None

    def _update_label_from_store(self):
        if self.item_type != "image":
            return
        self.rating_label.setText(str(self._get_rating(self.list_num, self.index)))

    def _show_tooltip(self):
        if self.full_path:
            PathTooltip.get_instance().show_tooltip(
                QCursor.pos(), self.full_path
            )

    def _notify_flyout_drop_indicator(self, global_pos):
        self._on_update_drop_indicator(global_pos)

    def _notify_flyout_clear_indicator(self):
        self._on_clear_drop_indicator()
