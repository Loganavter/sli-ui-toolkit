"""InspectorWindow + _InspectionPane — the inspector's tabbed tool window.

The pane is the thin owner: it builds the sidebar shell and routes
inspection data into section pages. Rendering lives in sibling mixins
(buttons/ folder is the model): field/page rendering in ``rendering.py``,
the Code section in ``code.py``, Layout/Constructor trees in ``tree.py``,
value formatting in ``fields.py``.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.buttons.button import Button
from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import CloseButtonPolicy
from sli_ui_toolkit.ui.widgets.composite.dialog_shell import (
    ScrollableDialogPage,
    SidebarDialogShell,
)
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.host import TopTabHost

from .code import CodeSectionEditor, build_code_section
from .contract import InspectField, WidgetInspection
from .fields import _config_snippet
from .rendering import _PaneRenderingMixin
from .tree import _TreeNodeRow, _layout_tree_key, _PaneTreeMixin



class _InspectionPane(
    _PaneRenderingMixin,
    _PaneTreeMixin,
    QWidget,
):
    """One inspection tab: sidebar sections over a single widget's data.

    A dumb view, driven through ``set_inspection`` /
    ``set_layout_nodes`` / ``set_constructor_nodes``. Interaction signals are
    forwarded by ``InspectorWindow`` to its own signals. Mixins precede
    ``QWidget`` so their members resolve first in the MRO.
    """

    #: emitted when a region row is clicked (region id)
    region_selected = Signal(str)
    #: emitted when a REF row / tree node is activated (child widget)
    widget_activated = Signal(object)
    #: emitted when a tree-row hover enters a widget (highlight in the app)
    widget_hovered = Signal(object)
    #: emitted when the tree-row hover leaves a widget
    widget_hover_cleared = Signal()

    def __init__(self, sections: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.widget: QWidget | None = None
        self._current: WidgetInspection | None = None
        self._theme_manager = None
        self._qss_rows: list[tuple[Any, bool | None]] = []
        self._token_sources: dict[str, str] = {}
        #: page name → subtree keys (``id(widget)``) the user expanded; kept
        #: across Refresh re-renders, reset on a new selection. Everything is
        #: collapsed by default.
        self._expanded: dict[str, set[int]] = {}
        self._code_section: CodeSectionEditor | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.shell = SidebarDialogShell(sidebar_width=180)
        root.addWidget(self.shell)

        self.shell.sidebar.set_items([(name,) for name in sections])
        self.shell.sidebar.enable_minimal_scrollbar()
        self.pages: dict[str, ScrollableDialogPage] = {}
        for name in sections:
            page = ScrollableDialogPage(
                content_margins=(8, 8, 8, 8), content_spacing=4
            )
            self.pages[name] = page
            self.shell.pages_stack.addWidget(page)
        self.shell.sidebar.currentRowChanged.connect(self._on_sidebar_row)
        self.shell.sidebar.setCurrentRow(0)
        # The QStackedWidget only lays out its current page when the stack's
        # layout activates; in the real window chain the pages can be left at
        # their creation size (640x480) while the stack grows/shrinks, so the
        # scroll areas inside stay stale (content not following the window).
        # Force the current page to the stack's size on every stack resize.
        self.shell.pages_stack.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent

        if (
            watched is self.shell.pages_stack
            and event.type() == QEvent.Type.Resize
        ):
            page = self.shell.pages_stack.currentWidget()
            if page is not None:
                page.resize(self.shell.pages_stack.size())
        return super().eventFilter(watched, event)

    def _on_sidebar_row(self, row: int) -> None:
        self.shell.pages_stack.setCurrentIndex(row)

    def add_section(self, name: str) -> ScrollableDialogPage:
        """Append an extra sidebar section (app layer: Native)."""
        page = ScrollableDialogPage(
            content_margins=(8, 8, 8, 8), content_spacing=4
        )
        self.pages[name] = page
        self.shell.pages_stack.addWidget(page)
        self.shell.sidebar.add_item(name)
        return page

    def show_section(self, name: str) -> None:
        """Switch the sidebar to ``name`` (used by the Code section's Docs
        button — the editor itself has no window knowledge)."""
        indexes = {section: index for index, section in enumerate(self.pages)}
        row = indexes.get(name)
        if row is not None:
            self.shell.sidebar.setCurrentRow(row)

    def set_inspection(
        self,
        inspection: WidgetInspection,
        *,
        widget: QWidget | None = None,
        theme_manager=None,
        qss_candidates=(),
        qss_dead: dict[tuple[str, str, int], bool] | None = None,
        token_sources: dict[str, str] | None = None,
    ) -> None:
        """Render the inspection into all section pages.

        ``token_sources`` optionally maps theme keys to a human source label
        (e.g. "themes.json:81") shown next to static tokens.
        """
        self.widget = widget
        self._current = inspection
        self._theme_manager = theme_manager
        self._token_sources = token_sources or {}
        self._expanded = {}
        self._qss_rows = [
            (
                rule,
                None
                if qss_dead is None
                else qss_dead.get((rule.source, rule.selector, rule.line)),
            )
            for rule in qss_candidates
        ]
        self._render_object(widget)
        self._render_fields("Config", inspection.config)
        self._render_fields("State", inspection.state)
        self._render_colors()
        self._render_regions(inspection.regions)
        self._render_layers(inspection.layers)
        self._render_theme(inspection)
        self._render_code(widget)
        self._render_docs()
        self._sync_section_visibility()

    def set_layout_nodes(self, nodes: tuple[tuple[str, object, int], ...]) -> None:
        """Layout tree rows: (label, widget_or_None, indent) — the whole
        window's tree, for context."""
        self._render_tree("Layout", "Layout tree", nodes)
        self._sync_section_visibility()

    def set_constructor_nodes(self, nodes: tuple[tuple[str, object, int], ...]) -> None:
        """Constructor rows: (label, widget_or_None, indent) — the selected
        widget's own subtree (every widget inside it)."""
        self._render_tree("Constructor", "Constructor", nodes)
        self._sync_section_visibility()

    def _render_code(self, widget: QWidget | None) -> None:
        # thin delegator: the construction lives in code.py's
        # build_code_section (owner + page passed as the first argument)
        build_code_section(self, widget)

    # -- Code section compatibility surface (delegates to the editor) --------

    @property
    def _code_view(self):
        return self._code_section.view if self._code_section is not None else None

    @property
    def _code_config_view(self):
        return self._code_section.config_view if self._code_section is not None else None

    @property
    def _code_edit_btn(self):
        return self._code_section._edit_btn if self._code_section is not None else None

    @property
    def _code_revert_btn(self):
        return self._code_section._revert_btn if self._code_section is not None else None

    @property
    def _code_save_btn(self):
        return self._code_section._save_btn if self._code_section is not None else None

    @property
    def _code_original(self) -> str:
        return self._code_section._source_original if self._code_section is not None else ""

    @property
    def _code_path(self):
        return self._code_section._path if self._code_section is not None else None

    @property
    def _code_config_original(self) -> str:
        return self._code_section._config_original if self._code_section is not None else ""

    def _sync_section_visibility(self) -> None:
        """Hide sidebar sections whose page has no content; keep the current
        row on a visible section."""
        sidebar = self.shell.sidebar
        for index, name in enumerate(self.pages):
            button = sidebar.row_button(index)
            if button is None:
                continue
            button.setVisible(self.pages[name].content_layout.count() > 0)
        current = sidebar.currentRow()
        current_button = sidebar.row_button(current)
        if current_button is not None and current_button.isVisible():
            return
        for index, name in enumerate(self.pages):
            button = sidebar.row_button(index)
            if button is not None and button.isVisible():
                sidebar.setCurrentRow(index)
                return


class InspectorWindow(QDialog):
    """DevTools-style tool window: tabs on top, one inspection per tab.

    A non-modal top-level QDialog: host apps with the CSD auto-decoration
    pipeline (the app's Polish interceptor) get the established frameless
    title-bar chrome for free; without one the window falls back to the
    platform frame.
    """

    #: emitted when a region row is clicked (region id)
    region_selected = Signal(str)
    #: emitted when a REF row / tree node is activated (child widget)
    widget_activated = Signal(object)
    #: emitted when a tree-row hover enters a widget (highlight in the app)
    widget_hovered = Signal(object)
    #: emitted when the tree-row hover leaves a widget
    widget_hover_cleared = Signal()
    #: emitted when the "Capture tokens" button is pressed
    capture_requested = Signal()
    refresh_requested = Signal()
    #: emitted after a new inspection pane/tab is created (app layer hooks)
    pane_created = Signal(object)

    SECTIONS = (
        "Object",
        "Config",
        "State",
        "Colors",
        "Regions",
        "Layers",
        "Theme",
        "Layout",
        "Constructor",
        "Code",
        "Docs",
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("UI Inspector")
        self.setObjectName("UiInspectorWindow")
        self.setProperty("_ui_inspector_owned", True)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.resize(560, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._toolbar = QWidget()
        self.toolbar_layout = QHBoxLayout(self._toolbar)
        self.toolbar_layout.setContentsMargins(8, 6, 8, 2)
        self.toolbar_layout.setSpacing(6)
        refresh = Button(text="Refresh", variant="default", size=(0, 30))
        refresh.clicked.connect(self.refresh_requested)
        capture = Button(text="Capture tokens", variant="default", size=(0, 30))
        capture.clicked.connect(self.capture_requested)
        self.toolbar_layout.addWidget(refresh)
        self.toolbar_layout.addWidget(capture)
        self.toolbar_layout.addStretch(1)
        root.addWidget(self._toolbar)

        self.tabs = TopTabHost(
            tab_height=28, close_policy=CloseButtonPolicy.ALL
        )
        root.addWidget(self.tabs, 1)
        self.tabs.tabCloseRequested.connect(self._close_tab)

        self._pane_widgets: dict[QWidget, _InspectionPane] = {}
        #: (window_id, node count, first/last widget id) → rendered Layout
        #: tree; the whole-window tree is identical for every tab, so it is
        #: built once and re-attached to the active tab.
        self._layout_tree_cache: dict[tuple, QWidget] = {}
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._refresh_minimum_size()

    def _refresh_minimum_size(self) -> None:
        """Content-driven minimum, the app's dialog-geometry recipe.

        The pages are scroll areas and the tab host has a tiny natural
        minimum, so a ``scaled_px`` floor keeps the window usable. The
        measured toolbar/tab-bar hints (the tab bar clamped — many tabs must
        clip rather than blow the window up) let the minimum grow when more
        tabs are opened. Re-run after every tab add (``_create_pane``).
        """
        from sli_ui_toolkit.managers import scaled_px

        self.ensurePolished()
        toolbar_width = max(0, self._toolbar.sizeHint().width())
        tab_bar = self.tabs.tabBar()
        tab_bar.ensurePolished()
        tabs_width = min(
            max(0, tab_bar.sizeHint().width()), scaled_px(560)
        )
        min_width = max(scaled_px(440), toolbar_width, tabs_width)
        self.setMinimumSize(min_width, scaled_px(400))

    # -- tabs ---------------------------------------------------------------

    def active_pane(self) -> _InspectionPane | None:
        pane = self.tabs.currentWidget()
        return pane if isinstance(pane, _InspectionPane) else None

    def _create_pane(self, widget: QWidget | None, label: str) -> _InspectionPane:
        pane = _InspectionPane(self.SECTIONS, parent=self)
        pane.widget = widget
        pane.widget_activated.connect(self.widget_activated.emit)
        pane.widget_hovered.connect(self.widget_hovered.emit)
        pane.widget_hover_cleared.connect(self.widget_hover_cleared.emit)
        pane.region_selected.connect(self.region_selected.emit)
        self.pane_created.emit(pane)
        index = self.tabs.addTab(pane, label)
        self.tabs.setCurrentIndex(index)
        self._refresh_minimum_size()
        return pane

    def _ensure_pane(self) -> _InspectionPane:
        pane = self.active_pane()
        if pane is not None:
            return pane
        return self._create_pane(None, "Widget")

    def open_widget(self, widget: QWidget, label: str) -> _InspectionPane:
        """Focus the tab inspecting ``widget``, opening a new one if needed.

        Tabs are deduplicated per widget: re-opening the same widget (e.g. a
        repeated tree-row click) switches to its existing tab.
        """
        pane = self._pane_widgets.get(widget)
        if pane is None:
            pane = self._create_pane(widget, label)
            self._pane_widgets[widget] = pane
        else:
            self.tabs.setCurrentWidget(pane)
        return pane

    def _close_tab(self, index: int) -> None:
        """Close the tab at ``index`` (its X button): drop the dedupe entry,
        detach the cached Layout tree if it lives in that pane, remove the
        tab and release the pane."""
        pane = self.tabs.widget(index)
        if not isinstance(pane, _InspectionPane):
            return
        for widget, registered in list(self._pane_widgets.items()):
            if registered is pane:
                del self._pane_widgets[widget]
                break
        if self._layout_tree_cache:
            tree = next(iter(self._layout_tree_cache.values()))
            if tree.parentWidget() is pane.pages["Layout"].content_widget:
                self._detach_widget(tree)
        self.tabs.removeTab(index)
        pane.deleteLater()
        self._refresh_minimum_size()

    # -- routing to the active tab ------------------------------------------

    def set_inspection(
        self,
        inspection: WidgetInspection,
        *,
        widget: QWidget | None = None,
        theme_manager=None,
        qss_candidates=(),
        qss_dead: dict[tuple[str, str, int], bool] | None = None,
        token_sources: dict[str, str] | None = None,
    ) -> None:
        """Render the inspection into the active tab's section pages."""
        self._ensure_pane().set_inspection(
            inspection,
            widget=widget,
            theme_manager=theme_manager,
            qss_candidates=qss_candidates,
            qss_dead=qss_dead,
            token_sources=token_sources,
        )

    def set_layout_nodes(self, nodes: tuple[tuple[str, object, int], ...]) -> None:
        """Layout tree rows — the whole window's tree, for context.

        Cached per window (``_layout_tree_key``: window id + count +
        first/last identities): the tree is identical for every tab of
        that window, so it is built once and re-attached to the active tab
        instead of re-creating hundreds of row widgets on every tab open.
        Staleness is approximate — subtle changes that keep count and
        endpoints leave a stale cache until the next count/endpoint change.
        """
        pane = self._ensure_pane()
        key = _layout_tree_key(nodes)
        if key is None:
            pane.set_layout_nodes(nodes)
            return
        tree = self._layout_tree_cache.get(key)
        if tree is None:
            for stale in self._layout_tree_cache.values():
                self._detach_widget(stale)
                stale.deleteLater()
            self._layout_tree_cache.clear()
            tree = pane.build_tree(nodes)
            self._layout_tree_cache[key] = tree
        self._attach_layout_tree(pane, tree)

    def set_constructor_nodes(self, nodes: tuple[tuple[str, object, int], ...]) -> None:
        self._ensure_pane().set_constructor_nodes(nodes)

    def _on_tab_changed(self, _index: int) -> None:
        """Re-attach the cached Layout tree to the newly active tab."""
        pane = self.active_pane()
        if pane is None or not self._layout_tree_cache:
            return
        for key, tree in self._layout_tree_cache.items():
            if pane.widget is not None and id(pane.widget.window()) == key[0]:
                self._attach_layout_tree(pane, tree)
                break

    def _attach_layout_tree(self, pane: _InspectionPane, tree: QWidget) -> None:
        self._detach_widget(tree)
        # If tree was previously wrapped (wrapper contains title + tree),
        # detaching only the tree would leave the wrapper's title behind —
        # but build_tree trees are never wrapped with title, they are bare
        # tree containers. For _render_tree the wrapper is page-owned, not
        # cached, so no detach needed there.
        page = pane.pages["Layout"]
        pane._clear(page)
        # Use zero-spacing wrapper for Title → tree so the 4px page spacing
        # does not create a dead hover gap between the title and first row.
        from PySide6.QtWidgets import QVBoxLayout, QWidget

        from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label

        wrapper = QWidget()
        wlay = QVBoxLayout(wrapper)
        wlay.setContentsMargins(0, 0, 0, 0)
        wlay.setSpacing(0)
        wlay.addWidget(
            Label(
                "Layout tree",
                variant="group-title",
                pixel_size=15,
                bold=True,
                elide=True,
                selectable=True,
            )
        )
        tree.setParent(wrapper)
        wlay.addWidget(tree)
        page.content_layout.addWidget(wrapper)
        page.content_layout.addStretch(1)
        pane._sync_section_visibility()

    @staticmethod
    def _detach_widget(widget: QWidget) -> None:
        parent = widget.parentWidget()
        if parent is None:
            return
        layout = parent.layout()
        if layout is not None:
            index = layout.indexOf(widget)
            if index >= 0:
                layout.takeAt(index)
        widget.setParent(None)

    # -- forwarding helpers for the app layer -------------------------------

    @property
    def _pages(self) -> dict[str, ScrollableDialogPage]:
        pane = self.active_pane()
        return pane.pages if pane is not None else {}

    @property
    def _shell(self):
        pane = self.active_pane()
        return pane.shell if pane is not None else None

    @property
    def _current(self) -> WidgetInspection | None:
        pane = self.active_pane()
        return pane._current if pane is not None else None

    def _clear(self, page: ScrollableDialogPage) -> None:
        pane = self.active_pane()
        if pane is not None:
            pane._clear(page)

    def _add_title(self, page: ScrollableDialogPage, text: str) -> None:
        pane = self.active_pane()
        if pane is not None:
            pane._add_title(page, text)

    def _add_field_row(
        self, page: ScrollableDialogPage, field: InspectField, indent: int = 0
    ) -> None:
        pane = self.active_pane()
        if pane is not None:
            pane._add_field_row(page, field, indent)



#: App-layer and test code historically imported the tree row from here;
#: re-exported for compatibility (the real class lives in ``tree.py``).
__all__ = ["InspectorWindow", "_TreeNodeRow", "_InspectionPane"]
