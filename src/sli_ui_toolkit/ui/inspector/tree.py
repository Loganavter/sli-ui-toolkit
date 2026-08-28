"""Tree rows for the inspector Layout/Constructor sections.

``_TreeNodeRow`` is a web-inspector-style row — chevron polygon is
painted, ``Class#objectName`` is a child ``Label`` (mouse-transparent,
elided, ``selectable=False`` because the row itself handles hover/click);
``_nest_nodes`` rebuilds a tree from a pre-order flat list; the
``_PaneTreeMixin`` renders a node tree into a page (or a standalone
cached container for the window-level Layout tree).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label


def _nest_nodes(nodes) -> list[dict]:
    """Rebuild a tree from a pre-order ``(label, widget, indent)`` flat list.

    Each node is a child of the previous node with a strictly smaller indent
    (stack-based, like re-indenting a serialized tree).
    """
    roots: list[dict] = []
    stack: list[dict] = []
    for label, widget, indent in nodes:
        node = {"label": label, "widget": widget, "indent": indent, "children": []}
        while stack and stack[-1]["indent"] >= indent:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def _layout_tree_key(nodes) -> tuple | None:
    """Cheap staleness signature for the cached Layout tree: the window
    object, the node count and the first/last node identities. Most tree
    changes alter one of these; anything subtler costs a rebuild at worst
    (a diagnostic tool, not a hot path)."""
    first = next((w for _label, w, _indent in nodes if isinstance(w, QWidget)), None)
    if first is None:
        return None
    last = next(
        (w for _label, w, _indent in reversed(nodes) if isinstance(w, QWidget)),
        first,
    )
    return (id(first.window()), len(nodes), id(first), id(last))


class _TreeNodeRow(QWidget):
    """Web-inspector-style tree row: twist indicator + ``Class#objectName``.

    Chevron is painted (no QSS), text is a child ``Label``
    (``WA_TransparentForMouseEvents``, ``elide=True``, ``selectable=False``),
    theme-aware: chevron polygon like the timeline groups, hover background
    from ``list_item.background.hover`` (fallback ``QColor(0,0,0,12)``).
    Emits ``activated`` on a click outside the twist, ``toggled`` on a
    twist click, and ``hovered``/``unhovered`` on enter/leave so the
    controller can highlight the widget in the app via the overlay.
    """

    activated = Signal(object)
    toggled = Signal(object)
    hovered = Signal(object)
    unhovered = Signal()

    _ROW_HEIGHT = 26
    _INDENT_STEP = 14
    _CHEVRON_WIDTH = 12
    _TEXT_GAP = 4

    def __init__(
        self,
        label: str,
        widget: QWidget | None,
        *,
        has_children: bool,
        expanded: bool,
        depth: int,
        parent=None,
    ):
        super().__init__(parent)
        self._label = label
        self._widget = widget
        self._has_children = has_children
        self._expanded = expanded
        self._depth = depth
        self._hovered = False
        self.setFixedHeight(self._ROW_HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        if widget is not None or has_children:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        object_name = widget.objectName() if widget is not None else ""
        display = f"{label}#{object_name}" if object_name else label
        self._text_label = Label(display, pixel_size=13, selectable=False, elide=True, parent=self)
        self._text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    # -- public state -------------------------------------------------------

    def set_expanded(self, expanded: bool) -> None:
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self.update()

    def widget(self) -> QWidget | None:
        return self._widget

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        try:
            text_x = self._depth * self._INDENT_STEP
            if self._has_children:
                text_x += self._CHEVRON_WIDTH
            text_x += self._TEXT_GAP
            self._text_label.setGeometry(text_x, 0, max(0, self.width() - text_x - self._TEXT_GAP), self.height())
        except Exception:
            pass

    # -- events -------------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        if self._widget is not None:
            self.hovered.emit(self._widget)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        if self._widget is not None:
            self.unhovered.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._has_children and self._chevron_rect().contains(
                event.position().toPoint()
            ):
                self.toggled.emit(self._widget)
            else:
                self.activated.emit(self._widget)
        super().mousePressEvent(event)

    # -- painting -----------------------------------------------------------

    def _chevron_rect(self) -> QRect:
        x = self._depth * self._INDENT_STEP + 2
        return QRect(x, 0, self._CHEVRON_WIDTH, self.height())

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tm = ThemeManager.get_instance()
        if self._hovered:
            background = tm.try_get_color("list_item.background.hover")
            painter.fillRect(self.rect(), background or QColor(0, 0, 0, 12))
        text_color = tm.try_get_color("WindowText") or QColor(0, 0, 0)

        text_x = self._depth * self._INDENT_STEP
        if self._has_children:
            chevron_rect = self._chevron_rect()
            cy = self.height() / 2
            cx = chevron_rect.center().x()
            painter.setPen(text_color)
            painter.setBrush(text_color)
            if self._expanded:
                points = QPolygonF(
                    [
                        QPointF(cx - 3, cy - 3),
                        QPointF(cx + 3, cy - 3),
                        QPointF(cx, cy + 3),
                    ]
                )
            else:
                points = QPolygonF(
                    [
                        QPointF(cx - 3, cy - 4),
                        QPointF(cx + 3, cy),
                        QPointF(cx - 3, cy + 4),
                    ]
                )
            painter.drawPolygon(points)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            text_x += self._CHEVRON_WIDTH
        text_x += self._TEXT_GAP

        # Position the mouse-transparent Label for the text. The row's
        # Label is ``selectable=False`` (unlike field rows) because it is
        # ``WA_TransparentForMouseEvents`` — mouse goes to the row for
        # hover/click/overlay; making it selectable would be dead.
        try:
            width = max(0, self.width() - text_x - self._TEXT_GAP)
            self._text_label.setGeometry(text_x, 0, width, self.height())
            self._text_label.raise_()
        except Exception:
            pass


class _PaneTreeMixin:
    """Mixin: render a node tree into a section page (or a cached container).

    Not a QWidget itself — mixed into _InspectionPane; relies on the pane's
    ``pages`` dict, ``_expanded`` state and the ``widget_activated`` /
    ``widget_hovered`` / ``widget_hover_cleared`` signals, plus the
    rendering mixin's ``_clear`` / ``_add_title``.
    """

    # Declared here only so mypy can resolve them across the mixin split —
    # the real definitions live in _InspectionPane (view.py) or the
    # rendering mixin. Plain annotations only (no `= value`).
    pages: Any
    _expanded: dict[str, set[int]]
    widget_activated: Any
    widget_hovered: Any
    widget_hover_cleared: Any
    _clear: Any
    _add_title: Any

    def build_tree(self, nodes) -> QWidget:
        """Render the tree into a standalone container widget.

        Used for the window-level Layout cache: the whole-window tree is
        per-window (``_layout_tree_key``: window id + count + first/last
        identities), identical for every tab of that window, so it is built
        once and re-attached to the active tab instead of re-creating
        hundreds of row widgets per tab. Collapse state lives inside the
        returned widget (a fresh ``set()``, not the pane's ``_expanded``).
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        expanded: set[int] = set()
        for node in _nest_nodes(nodes):
            self._render_tree_node(layout, node, expanded, depth=0)
        return container

    def _render_tree(self, page_name: str, title: str, nodes) -> None:
        page = self.pages[page_name]
        self._clear(page)
        if not nodes:
            return
        self._add_title(page, title)
        # Rows are grouped in hierarchical zero-spacing containers (one
        # ``QVBoxLayout(spacing=0, margins=0)`` per expanded branch, see
        # ``_render_tree_node``). If rows were added directly to
        # ``page.content_layout`` (``content_spacing=4``), the 4px gaps
        # would be dead hover zones. The wrapper reduces the dead zone to
        # the widget boundary itself; per-row ``enterEvent``/``leaveEvent``
        # still emits ``unhovered``/``hovered`` across the boundary, so a
        # brief flicker at the edge remains (by design — no parent-level
        # hover tracking).
        tree = QWidget()
        tree_layout = QVBoxLayout(tree)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)
        expanded = self._expanded.setdefault(page_name, set())
        for node in _nest_nodes(nodes):
            self._render_tree_node(tree_layout, node, expanded, depth=0)
        page.content_layout.addWidget(tree)
        page.content_layout.addStretch(1)

    def _render_tree_node(self, layout, node, expanded, depth: int) -> None:
        widget = node["widget"]
        children = node["children"]
        has_children = bool(children)
        key = id(widget)
        is_expanded = has_children and key in expanded
        row = _TreeNodeRow(
            node["label"],
            widget,
            has_children=has_children,
            expanded=is_expanded,
            depth=depth,
        )
        if widget is not None:
            row.activated.connect(
                lambda _w=widget: self.widget_activated.emit(_w)
            )
            row.hovered.connect(self.widget_hovered.emit)
            row.unhovered.connect(self.widget_hover_cleared.emit)
        layout.addWidget(row)
        if not has_children:
            return
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        for child in children:
            self._render_tree_node(container_layout, child, expanded, depth + 1)
        container.setVisible(is_expanded)
        row.toggled.connect(
            lambda _w=widget, c=container, r=row, k=key: self._toggle_tree_branch(
                expanded, c, r, k
            )
        )
        layout.addWidget(container)

    def _toggle_tree_branch(
        self, expanded: set[int], container: QWidget, row: _TreeNodeRow, key: int
    ) -> None:
        if key in expanded:
            expanded.discard(key)
            container.setVisible(False)
            row.set_expanded(False)
        else:
            expanded.add(key)
            container.setVisible(True)
            row.set_expanded(True)
