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

from PySide6.QtCore import QEvent, QObject, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.regions import ButtonRegion
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.buttons.variants import VariantSpec, register_variant

class _TreeRowSplit:
    """Split for tree row: twist 12px at depth indent, content fills rest."""
    def __init__(self, depth: int, has_twist: bool):
        self._depth = depth
        self._has_twist = has_twist

    def compute(self, rect, regions):
        from PySide6.QtCore import QRectF
        if not self._has_twist:
            # single content region with indent
            indent = self._depth * 14
            return [QRectF(rect.left() + indent, rect.top(), max(0, rect.width() - indent), rect.height())]
        # two regions: twist 12px at indent, content rest
        indent = self._depth * 14
        twist_w = 12
        twist_x = rect.left() + indent + 2
        twist_rect = QRectF(twist_x, rect.top(), twist_w, rect.height())
        content_x = twist_x + twist_w + 4
        content_w = max(0, rect.right() - content_x + 1)
        content_rect = QRectF(content_x, rect.top(), content_w, rect.height())
        # regions order is [twist, content]
        return [twist_rect, content_rect]

    def dividers(self, rects):
        return []


# Tree-row variant: transparent idle, list_item.background.hover on hover/pressed.
# Uses toolkit Button pipeline instead of manual QSS/painter.
def _tree_row_bg(states, tm: ThemeManager):  # type: ignore[no-untyped-def]
    if ButtonState.HOVERED in states or ButtonState.PRESSED in states:
        c = tm.try_get_color("list_item.background.hover")
        return QColor(c) if c is not None else QColor(0, 0, 0, 12)
    return QColor(0, 0, 0, 0)


try:
    register_variant(VariantSpec("tree_row", "list_item", resolve_bg=_tree_row_bg))
except Exception:
    pass


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


class _TreeNodeRow(Button):
    """Web-inspector-style tree row as toolkit Button (no QSS).

    Uses Button variant "tree_row" (list_item.background.hover on hover,
    transparent idle) and paints the twist chevron via overlay painter.
    Emits ``activated`` on a click outside the twist, ``toggled`` on a
    twist click. Hover is handled by Button's HOVERED state; controller
    overlay is still driven via _TreeHoverFilter for gap-free tracking.
    """

    activated = Signal(object)
    toggled = Signal(object)
    hovered = Signal(object)  # compat, unused for overlay
    unhovered = Signal()  # compat, unused for overlay

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
        self._label = label
        self._widget = widget
        self._has_children = has_children
        self._expanded = expanded
        self._depth = depth
        object_name = widget.objectName() if widget is not None else ""
        display = f"{label}#{object_name}" if object_name else label
        # Button-based row with regions: twist (chevron) + content (text), no QSS.
        # Let Button handle hover/press/cursor via variant tree_row.
        if has_children:
            twist_text = "▾" if expanded else "▸"
            regions = [
                ButtonRegion(id="twist", text=twist_text, weight=0),
                ButtonRegion(id="content", text=display, weight=1),
            ]
            split = _TreeRowSplit(depth, has_twist=True)
        else:
            regions = [
                ButtonRegion(id="content", text=display, weight=1),
            ]
            split = _TreeRowSplit(depth, has_twist=False)
        super().__init__(
            regions=regions,
            split=split,
            variant="tree_row",
            size=(0, self._ROW_HEIGHT),
            content_align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            corner_radius=0,
            parent=parent,
        )
        self.setFixedHeight(self._ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if widget is not None or has_children:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Route region clicks to toggled/activated (Button handles hit-testing)
        self.regionClicked.connect(self._on_region_clicked)

    # -- public state -------------------------------------------------------

    def set_expanded(self, expanded: bool) -> None:
        if expanded == self._expanded:
            return
        self._expanded = expanded
        # Update twist chevron via region text
        if self._has_children:
            try:
                twist_text = "▾" if expanded else "▸"
                self.update_region("twist", text=twist_text)
            except Exception:
                pass
        self.update()

    def _on_region_clicked(self, region_id: str) -> None:
        if region_id == "twist" and self._has_children:
            self.toggled.emit(self._widget)
        else:
            self.activated.emit(self._widget)

    def widget(self) -> QWidget | None:
        return self._widget

    def resizeEvent(self, event) -> None:  # noqa: N802
        # Button handles its own content layout via content_padding
        super().resizeEvent(event)

    # -- events -------------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        # Let Button set HOVERED state, then emit for overlay highlight
        super().enterEvent(event)
        try:
            self.hovered.emit(self._widget)
        except Exception:
            pass

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        try:
            self.unhovered.emit()
        except Exception:
            pass



    # -- painting -----------------------------------------------------------

    def _chevron_rect(self) -> QRect:
        x = self._depth * self._INDENT_STEP + 2
        return QRect(x, 0, self._CHEVRON_WIDTH, self.height())

    def paintEvent(self, event) -> None:  # noqa: N802
        # Button paints background (tree_row) and regions (twist+content)
        super().paintEvent(event)




class _TreeHoverFilter(QObject):
    """Tree-level hover tracker — no per-row leave/enter gap.

    The tree's rows are zero-spaced (``spacing=0``) but per-row
    ``enterEvent``/``leaveEvent`` still fires a ``leave (cleared) → enter
    (hover)`` sequence on every boundary (1-50ms in logs) → overlay
    flickers and ``tree hover cleared`` spam. Instead, the tree container
    tracks the mouse itself: ``MouseMove``/``HoverMove`` finds the deepest
    ``_TreeNodeRow`` under the cursor via ``childAt`` and emits
    ``widget_hovered`` only when the hovered widget actually changes, and
    ``widget_hover_cleared`` only when the cursor leaves the tree entirely.
    No intermediate ``cleared`` between adjacent rows, no dead-gap spam.
    """

    def __init__(self, pane: Any, tree: QWidget):
        super().__init__(tree)
        self._pane = pane
        self._tree = tree
        self._current: QWidget | None = None
        self._last_cursor_shape: str | None = None
        tree.setMouseTracking(True)
        tree.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        tree.installEventFilter(self)
        # Visual cursor debug — small tooltip-like label directly at cursor
        try:
            import logging

            if logging.getLogger("sli_ui_toolkit.inspector.tree").isEnabledFor(logging.DEBUG):
                from PySide6.QtWidgets import QLabel

                self._cursor_label = QLabel("", None)  # type: ignore[attr-defined]
                self._cursor_label.setWindowFlags(
                    Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                )
                self._cursor_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                self._cursor_label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                self._cursor_label.setStyleSheet(
                    "background: rgba(30,30,30,210); color: #00ff00; font: 10px monospace; padding: 3px; border: 1px solid #00ff00; border-radius: 3px;"
                )
                self._cursor_label.hide()
            else:
                self._cursor_label = None  # type: ignore[attr-defined]
        except Exception:
            self._cursor_label = None  # type: ignore[attr-defined]

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self._tree:
            return False
        t = event.type()
        if t == QEvent.Type.Leave:
            try:
                if hasattr(self, "_cursor_label") and self._cursor_label is not None:
                    self._cursor_label.hide()
            except Exception:
                pass
            if self._current is not None:
                try:
                    import logging

                    logger = logging.getLogger("sli_ui_toolkit.inspector.controller")
                    logger.debug(
                        "tree hover cleared (tree leave) last=%s",
                        type(self._current).__name__,
                    )
                except Exception:
                    pass
                self._pane.widget_hover_cleared.emit()
                self._current = None
                # cursor back to Arrow on leave — unambiguous
                try:
                    import logging

                    dbg = logging.getLogger("sli_ui_toolkit.inspector.tree")
                    if dbg.isEnabledFor(logging.DEBUG):
                        prev = getattr(self, "_last_cursor_shape", None)
                        cur_shape = "ArrowCursor (leave)"
                        if prev is not None and prev != cur_shape:
                            dbg.debug("cursor changed: %s -> %s at tree leave", prev, cur_shape)
                        self._last_cursor_shape = cur_shape
                except Exception:
                    pass
            else:
                # leave without current hover — still ensure cursor shape reset logged once
                try:
                    import logging

                    dbg = logging.getLogger("sli_ui_toolkit.inspector.tree")
                    if dbg.isEnabledFor(logging.DEBUG):
                        if getattr(self, "_last_cursor_shape", None) != "ArrowCursor (leave)":
                            dbg.debug(
                                "cursor changed: %s -> %s at tree leave (no hover)",
                                getattr(self, "_last_cursor_shape", None),
                                "ArrowCursor (leave)",
                            )
                            self._last_cursor_shape = "ArrowCursor (leave)"
                except Exception:
                    pass
            return False
        if t in (QEvent.Type.MouseMove, QEvent.Type.HoverMove, QEvent.Type.HoverEnter):
            try:
                # position() for QHoverEvent, pos() for QMouseEvent
                if hasattr(event, "position"):
                    pos = event.position().toPoint()  # type: ignore[attr-defined]
                elif hasattr(event, "pos"):
                    pos = event.pos()  # type: ignore[attr-defined]
                else:
                    pos = event.posF().toPoint() if hasattr(event, "posF") else None
                    if pos is None:
                        return False
            except Exception:
                return False
            # childAt returns deepest child; if over Label (transparent) it
            # still returns the row because Label is WA_TransparentForMouseEvents
            w = self._tree.childAt(pos)
            row: QWidget | None = w
            # walk up through nested containers to find the row
            while row is not None and not isinstance(row, _TreeNodeRow):
                # if we hit a nested container, drill into its childAt
                # childAt already gave deepest, so walk parents
                row = row.parentWidget()
                if row is self._tree:
                    row = None
                    break
            widget = row.widget() if isinstance(row, _TreeNodeRow) else None  # type: ignore[attr-defined]
            # --- unambiguous per-move debug (every HoverMove/MouseMove, DEBUG) ---
            try:
                import logging

                dbg_logger = logging.getLogger("sli_ui_toolkit.inspector.tree")
                if dbg_logger.isEnabledFor(logging.DEBUG):
                    try:
                        # global pos for this event
                        if hasattr(event, "globalPosition"):
                            gpos_dbg = event.globalPosition().toPoint()  # type: ignore[attr-defined]
                        elif hasattr(event, "globalPos"):
                            gpos_dbg = event.globalPos()  # type: ignore[attr-defined]
                        else:
                            from PySide6.QtGui import QCursor

                            gpos_dbg = QCursor.pos()
                    except Exception:
                        gpos_dbg = None
                    # childAt raw details
                    w_at_raw = w
                    w_at_geo = w_at_raw.geometry() if w_at_raw else None
                    w_at_y_in_tree = None
                    try:
                        if w_at_raw is not None:
                            w_at_y_in_tree = w_at_raw.mapTo(self._tree, w_at_raw.rect().topLeft()).y()
                    except Exception:
                        pass
                    # row details
                    row_label = getattr(row, "_label", None) if isinstance(row, _TreeNodeRow) else None
                    row_depth = getattr(row, "_depth", None) if isinstance(row, _TreeNodeRow) else None
                    row_geo = row.geometry() if isinstance(row, _TreeNodeRow) else None
                    row_y_in_tree = None
                    try:
                        if isinstance(row, _TreeNodeRow):
                            row_y_in_tree = row.mapTo(self._tree, row.rect().topLeft()).y()
                    except Exception:
                        pass
                    widget_name = widget.objectName() if widget is not None and hasattr(widget, "objectName") else ""
                    widget_type = type(widget).__name__ if widget is not None else "None"
                    # parent chain of w for gap diagnosis
                    chain = []
                    try:
                        cur = w
                        for _ in range(5):
                            if cur is None:
                                break
                            chain.append(f"{type(cur).__name__}#{cur.objectName() if hasattr(cur, 'objectName') else ''} geo={cur.geometry() if hasattr(cur, 'geometry') else '?'}")
                            cur = cur.parentWidget()
                            if cur is self._tree or cur is None:
                                if cur is self._tree:
                                    chain.append("TreeRoot")
                                break
                    except Exception:
                        chain = [str(chain)]
                    # y coverage at this pos.y
                    h_dbg = self._tree.height()
                    inside_h_dbg = 0 <= pos.y() < h_dbg
                    # check if pos.y is inside any visible row's y-interval
                    y_covered_by = None
                    try:
                        for r in self._tree.findChildren(_TreeNodeRow):
                            if not r.isVisible():
                                continue
                            y0 = r.mapTo(self._tree, r.rect().topLeft()).y()
                            y1 = r.mapTo(self._tree, r.rect().bottomRight()).y()
                            if y0 <= pos.y() <= y1:
                                y_covered_by = f"{r._label} y={y0}..{y1} depth={r._depth}"
                                break
                    except Exception:
                        pass
                    is_gap = widget is None
                    # cursor shape for this hit (unambiguous gap signal)
                    cursor_shape = "?"
                    try:
                        if isinstance(row, _TreeNodeRow):
                            cs = row.cursor().shape()
                            cursor_shape = cs.name if hasattr(cs, "name") else str(int(cs))
                        else:
                            # gap or tree background -> actual tree cursor (usually Arrow)
                            cs = self._tree.cursor().shape()
                            cursor_shape = cs.name if hasattr(cs, "name") else str(int(cs))
                            if is_gap:
                                cursor_shape = f"{cursor_shape} (gap)"
                    except Exception:
                        cursor_shape = "?"
                    # log cursor shape change (Arrow <-> PointingHand) — unambiguous gap answer
                    try:
                        if self._last_cursor_shape is None:
                            self._last_cursor_shape = cursor_shape
                        elif cursor_shape != self._last_cursor_shape:
                            dbg_logger.debug(
                                "cursor changed: %s -> %s at tree_pos=%s gap=%s row=%s depth=%s y_covered_by=%s",
                                self._last_cursor_shape,
                                cursor_shape,
                                pos,
                                is_gap,
                                row_label,
                                row_depth,
                                y_covered_by,
                            )
                            self._last_cursor_shape = cursor_shape
                    except Exception:
                        pass
                    dbg_logger.debug(
                        "tree hit: ev=%s tree_pos=%s global=%s tree_h=%s inside_h=%s gap=%s cursor=%s childAt=%s#%s geo=%s y_in_tree=%s row=%s#%s depth=%s row_geo=%s row_y=%s y_covered_by=%s chain=%s cur=%s -> %s",
                        t.name if hasattr(t, "name") else t,
                        pos,
                        gpos_dbg,
                        h_dbg,
                        inside_h_dbg,
                        is_gap,
                        cursor_shape,
                        type(w_at_raw).__name__ if w_at_raw else "None",
                        w_at_raw.objectName() if w_at_raw and hasattr(w_at_raw, "objectName") else "",
                        w_at_geo,
                        w_at_y_in_tree,
                        row_label,
                        widget_type,
                        row_depth,
                        row_geo,
                        row_y_in_tree,
                        y_covered_by,
                        " -> ".join(chain) if chain else "[]",
                        type(self._current).__name__ if self._current else "None",
                        widget_type,
                    )
            except Exception:
                pass
            # --- cursor debug label (visual, at cursor) ---
            try:
                if hasattr(self, "_cursor_label") and self._cursor_label is not None:
                    # global pos for label placement
                    try:
                        if hasattr(event, "globalPosition"):
                            gpos = event.globalPosition().toPoint()  # type: ignore[attr-defined]
                        elif hasattr(event, "globalPos"):
                            gpos = event.globalPos()  # type: ignore[attr-defined]
                        else:
                            from PySide6.QtGui import QCursor

                            gpos = QCursor.pos()
                    except Exception:
                        from PySide6.QtGui import QCursor

                        gpos = QCursor.pos()
                    w_at_dbg = self._tree.childAt(pos)
                    gap_marker = " GAP" if widget is None else ""
                    txt = f"tree pos={pos.x()},{pos.y()} childAt={type(w_at_dbg).__name__ if w_at_dbg else 'None'}{gap_marker} cur={type(self._current).__name__ if self._current else 'None'}→{type(widget).__name__ if widget else 'None'}"
                    self._cursor_label.setText(txt)
                    self._cursor_label.adjustSize()
                    self._cursor_label.move(gpos.x() + 16, gpos.y() + 16)
                    self._cursor_label.show()
                    self._cursor_label.raise_()
            except Exception:
                pass
            # suppress None (gap) → keep current until leave; only switch on real rows
            if widget is None:
                # Stable gap: cursor over tree background but not a row.
                # Log deterministically (no QCursor guessing) — helps pinpoint
                # the visual "nothing" between buttons.
                try:
                    import logging

                    logger = logging.getLogger("sli_ui_toolkit.inspector.tree")
                    if logger.isEnabledFor(logging.DEBUG):
                        # Check if pos is actually inside tree's height but not covered
                        # (i.e., y in y_gaps)
                        h = self._tree.height()
                        inside_h = 0 <= pos.y() < h
                        w_at = self._tree.childAt(pos)
                        logger.debug(
                            "tree gap hit: tree pos=%s h=%s inside_h=%s childAt=%s (%s) geo=%s current=%s",
                            pos,
                            h,
                            inside_h,
                            type(w_at).__name__ if w_at else "None",
                            w_at.objectName() if w_at and hasattr(w_at, "objectName") else "",
                            w_at.geometry() if w_at else "None",
                            type(self._current).__name__ if self._current else "None",
                        )
                        # Also dump full gap intervals for this tree
                        _log_tree_gaps(self._tree, prefix="gap-hit")
                except Exception:
                    pass
                # Do not emit cleared immediately, keep current hover (prevents
                # flicker on 1px gaps). Cleared only on tree Leave.
                return False
            if widget is self._current:
                return False
            # switching rows — direct hover, no intermediate cleared
            try:
                import logging

                logger = logging.getLogger("sli_ui_toolkit.inspector.controller")
                row_label_dbg = getattr(row, "_label", "?") if isinstance(row, _TreeNodeRow) else "?"
                row_depth_dbg = getattr(row, "_depth", "?") if isinstance(row, _TreeNodeRow) else "?"
                row_geo_dbg = row.geometry() if isinstance(row, _TreeNodeRow) else None
                w_name = widget.objectName() if widget is not None and hasattr(widget, "objectName") else ""
                cur_name = self._current.objectName() if self._current is not None and hasattr(self._current, "objectName") else ""
                logger.debug(
                    "tree hover: %s#%s -> %s#%s at tree pos=%s row=%s depth=%s row_geo=%s childAt=%s#%s geo=%s",
                    type(self._current).__name__ if self._current else "None",
                    cur_name,
                    type(widget).__name__,
                    w_name,
                    pos,
                    row_label_dbg,
                    row_depth_dbg,
                    row_geo_dbg,
                    type(w).__name__ if w else "None",
                    w.objectName() if w and hasattr(w, "objectName") else "",
                    w.geometry() if w else None,
                )
            except Exception:
                pass
            self._current = widget
            self._pane.widget_hovered.emit(widget)
            return False
        return False


def _log_tree_gaps(tree: QWidget, *, prefix: str = "tree") -> None:
    """Deterministic gap diagnostics — no QCursor/widgetAt guessing.

    Logs layout spacing/margins, row count/heights and any vertical gap
    between consecutive visible rows (via geometry in tree coords). A gap
    !=0 means a real layout void between buttons, not a hover timing
    artifact. Also dumps per-container coverage and a full Y-coverage scan
    (every py in tree height) to pinpoint stable "nothing" gaps.
    Called after every tree build; cheap (O(n + h)).
    """
    try:
        import logging

        logger = logging.getLogger("sli_ui_toolkit.inspector.tree")
        if not logger.isEnabledFor(logging.DEBUG):
            return
        lay = tree.layout()
        spacing = lay.spacing() if lay is not None else -1
        try:
            m = lay.contentsMargins() if lay is not None else None
            margins = f"({m.left()},{m.top()},{m.right()},{m.bottom()})" if m else "None"
        except Exception:
            margins = str(m) if "m" in locals() else "?"
        rows = [r for r in tree.findChildren(_TreeNodeRow) if r.isVisible()]
        # sort by y in tree coords
        def _y(w):
            try:
                return w.mapTo(tree, w.rect().topLeft()).y()
            except Exception:
                return 999999

        rows.sort(key=_y)
        gaps: list[int] = []
        details: list[str] = []
        for i in range(len(rows) - 1):
            cur = rows[i]
            nxt = rows[i + 1]
            try:
                cur_b = cur.mapTo(tree, cur.rect().bottomLeft()).y()
                nxt_t = nxt.mapTo(tree, nxt.rect().topLeft()).y()
                gap = nxt_t - cur_b - 1
                gaps.append(gap)
                if gap != 0:
                    details.append(f"{cur._label}->{nxt._label} gap={gap} cur_geo={cur.geometry()} nxt_geo={nxt.geometry()}")
            except Exception as e:
                gaps.append(999)
                details.append(f"err {e}")
        # Y-coverage scan: every y in tree height should be covered by a visible row
        y_gaps: list[tuple[int, int]] = []
        try:
            h = tree.height()
            # Build intervals of visible rows in tree coords
            intervals: list[tuple[int, int]] = []
            for r in rows:
                try:
                    y0 = r.mapTo(tree, r.rect().topLeft()).y()
                    y1 = r.mapTo(tree, r.rect().bottomRight()).y()
                    intervals.append((y0, y1))
                except Exception:
                    pass
            intervals.sort()
            # Scan for uncovered y
            uncovered_start = None
            for y in range(h):
                covered = any(y0 <= y <= y1 for y0, y1 in intervals)
                if not covered:
                    if uncovered_start is None:
                        uncovered_start = y
                else:
                    if uncovered_start is not None:
                        y_gaps.append((uncovered_start, y - 1))
                        uncovered_start = None
            if uncovered_start is not None:
                y_gaps.append((uncovered_start, h - 1))
        except Exception as e:
            y_gaps = [(-1, -1)]
            details.append(f"y_scan err {e}")
        # also check hierarchical containers coverage
        containers: list[str] = []
        for w in tree.findChildren(QWidget):
            try:
                lay2 = w.layout()
                if lay2 is not None and lay2.spacing() != 0:
                    containers.append(f"{type(w).__name__} spacing={lay2.spacing()} geo={w.geometry()}")
                if lay2 is not None:
                    try:
                        m2 = lay2.contentsMargins()
                        if m2.left() != 0 or m2.top() != 0 or m2.right() != 0 or m2.bottom() != 0:
                            containers.append(f"{type(w).__name__} margins=({m2.left()},{m2.top()},{m2.right()},{m2.bottom()}) geo={w.geometry()}")
                    except Exception:
                        pass
                # Style pixelMetric for layout spacing (QStyle can add default spacing)
                try:
                    from PySide6.QtWidgets import QStyle

                    style = w.style()
                    if style is not None:
                        pm_spacing = style.pixelMetric(QStyle.PixelMetric.PM_LayoutVerticalSpacing, None, w)
                        pm_margin = style.pixelMetric(QStyle.PixelMetric.PM_LayoutLeftMargin, None, w)
                        if pm_spacing != 0 or pm_margin != 0:
                            containers.append(f"{type(w).__name__} style PM_VSpacing={pm_spacing} PM_LeftMargin={pm_margin}")
                except Exception:
                    pass
            except Exception:
                pass
        # Use set to dedup container messages
        uniq_containers = sorted(set(containers))
        # Detailed Y-gap dump
        y_gap_str = f" y_uncovered={y_gaps}" if y_gaps else " y_covered_fully"
        logger.debug(
            "%s gaps: spacing=%s margins=%s visible_rows=%s gaps=%s tree_geo=%s h=%s details=%s containers=%s%s",
            prefix,
            spacing,
            margins,
            len(rows),
            gaps,
            tree.geometry(),
            tree.height(),
            details if details else "all 0",
            uniq_containers if uniq_containers else "ok",
            y_gap_str,
        )
        # If any gap !=0 or y_uncovered, also dump full row table + childAt probe for gap ys
        if any(g != 0 for g in gaps) or y_gaps:
            for r in rows:
                try:
                    y = r.mapTo(tree, r.rect().topLeft()).y()
                    y1 = r.mapTo(tree, r.rect().bottomRight()).y()
                    logger.debug("  row %s y=%s..%s h=%s geo=%s depth=%s parent=%s", r._label, y, y1, r.geometry(), r._depth, type(r.parentWidget()).__name__)
                except Exception:
                    pass
            # Probe childAt for first gap y to see what widget is there
            if y_gaps:
                try:
                    gy = y_gaps[0][0]
                    # probe at x=5 and x=width/2
                    for probe_x in (5, max(5, tree.width() // 2), max(5, tree.width() - 5)):
                        pos = tree.mapFromGlobal(tree.mapToGlobal(tree.rect().topLeft()))  # dummy to avoid unused
                        from PySide6.QtCore import QPoint

                        probe_pos = QPoint(probe_x, gy)
                        w_at = tree.childAt(probe_pos)
                        w_at_global = None
                        try:
                            # also check via QApplication.widgetAt for compare
                            from PySide6.QtWidgets import QApplication
                            from PySide6.QtGui import QCursor

                            # Use tree-local childAt, not global, for deterministic
                            pass
                        except Exception:
                            pass
                        logger.debug(
                            "  gap probe y=%s x=%s childAt=%s (%s) geo=%s",
                            gy,
                            probe_x,
                            type(w_at).__name__ if w_at else "None",
                            w_at.objectName() if w_at else "",
                            w_at.geometry() if w_at else "None",
                        )
                except Exception as e:
                    logger.debug("  gap probe err %s", e)
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
        # Hover now via Button per-row enter/leave (no childAt gap); filter kept for debug only.
        # container._hover_filter = _TreeHoverFilter(self, container)  # type: ignore[attr-defined]
        _log_tree_gaps(container, prefix="build_tree")
        return container

    def _render_tree(self, page_name: str, title: str, nodes) -> None:
        page = self.pages[page_name]
        self._clear(page)
        if not nodes:
            return
        # Wrapper with spacing=0 so Title → first row has no dead 4px gap
        # (page.content_layout has content_spacing=4 for other sections).
        # Title + tree live together with zero gap; the tree itself is a
        # hierarchical zero-spacing container (one QVBoxLayout spacing=0 per
        # branch, see _render_tree_node). Hover via Button per-row signals.
        from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper_layout.addWidget(
            Label(
                title,
                variant="group-title",
                pixel_size=15,
                bold=True,
                elide=True,
                selectable=True,
            )
        )
        tree = QWidget()
        tree_layout = QVBoxLayout(tree)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)
        expanded = self._expanded.setdefault(page_name, set())
        for node in _nest_nodes(nodes):
            self._render_tree_node(tree_layout, node, expanded, depth=0)
        # tree._hover_filter = _TreeHoverFilter(self, tree)  # type: ignore[attr-defined]  # Button hover via row signals
        wrapper_layout.addWidget(tree)
        page.content_layout.addWidget(wrapper)
        page.content_layout.addStretch(1)
        _log_tree_gaps(tree, prefix=f"_render_tree:{page_name}")

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
            # Button per-row hover (Qt handles Enter/Leave, no childAt gap)
            row.hovered.connect(lambda _w=widget: self.widget_hovered.emit(_w))
            row.unhovered.connect(lambda: self.widget_hover_cleared.emit())
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
