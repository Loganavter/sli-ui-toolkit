"""Inspector tests — window, pane, sections and trees."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.inspector.contract import (
    FieldKind,
    InspectField,
    InspectLayer,
    InspectRegion,
    WidgetInspection,
)
from sli_ui_toolkit.ui.inspector.view import InspectorWindow
from sli_ui_toolkit.widgets import Button, ButtonRegion, Label, Switch

from tests.inspector_helpers import _build_button_inspection, _open_probe, _page_labels, _spin_event_loop

def test_window_renders_sections(qapp):
    win = InspectorWindow()
    win.set_inspection(_build_button_inspection())
    config_texts = _page_labels(win, "Config")
    assert any("variant" in t for t in config_texts)
    state_texts = _page_labels(win, "State")
    assert any("checked" in t for t in state_texts)
    region_texts = _page_labels(win, "Regions")
    assert any("cover" in t for t in region_texts)
    layer_texts = _page_labels(win, "Layers")
    assert any("BackgroundLayer" in t for t in layer_texts)


def test_region_row_emits_region_selected(qapp):
    win = InspectorWindow()
    win.set_inspection(_build_button_inspection())
    emitted: list[str] = []
    win.region_selected.connect(emitted.append)

    page = win._pages["Regions"]
    buttons = [b for b in page.content_widget.findChildren(Button) if str(getattr(b, "_text", "") or "") == "cover"]
    assert buttons
    buttons[0].click()
    assert emitted == ["cover"]


def test_ref_field_emits_widget_activated(qapp):
    win = InspectorWindow()
    child = Switch()
    inspection = WidgetInspection(
        family="Probe",
        state=(InspectField(name="child", value=child, kind=FieldKind.REF),),
    )
    win.set_inspection(inspection)
    emitted: list[object] = []
    win.widget_activated.connect(emitted.append)

    page = win._pages["State"]
    buttons = page.content_widget.findChildren(Button)
    assert buttons
    buttons[0].click()
    assert emitted == [child]


def test_theme_page_shows_static_tokens(qapp):
    from sli_ui_toolkit.theme import ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(
        {"dialog.text": "#111111", "accent": "#0078d4"},
        {"dialog.text": "#dddddd", "accent": "#0096ff"},
    )
    tm.set_theme("light", qapp)
    win = InspectorWindow()
    win.set_inspection(
        _build_button_inspection(), theme_manager=tm
    )
    texts = _page_labels(win, "Theme")
    assert any("button.toggle.background.normal" in t for t in texts)


def test_layout_nodes_render_clickable_rows(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from sli_ui_toolkit.ui.inspector.view import _TreeNodeRow

    win = InspectorWindow()
    node = Switch()
    child = Switch()
    win.set_layout_nodes((("Switch", node, 0), ("Switch", child, 1)))
    emitted: list[object] = []
    win.widget_activated.connect(emitted.append)
    page = win._pages["Layout"]
    rows = page.content_widget.findChildren(_TreeNodeRow)
    assert rows
    QTest.mouseClick(rows[1], Qt.MouseButton.LeftButton, pos=QPoint(40, 13))
    assert emitted == [child]


def test_private_fields_marked(qapp):
    inspection = WidgetInspection(
        family="Probe",
        state=(InspectField(name="progress", value=0.5, kind=FieldKind.NUMBER, private=True),),
    )
    win = InspectorWindow()
    win.set_inspection(inspection)
    texts = _page_labels(win, "State")
    assert any("progress (private)" in t for t in texts)


def test_empty_sections_hidden_in_sidebar(qapp):
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.ui.inspector import inspect_widget

    win = InspectorWindow()
    widget = QWidget()
    win.set_inspection(inspect_widget(widget), widget=widget)
    win.set_layout_nodes((("QWidget", widget, 0),))
    sidebar = win._shell.sidebar
    indexes = {name: index for index, name in enumerate(win._pages)}
    assert not sidebar.row_button(indexes["Object"]).isHidden()
    assert not sidebar.row_button(indexes["State"]).isHidden()
    assert not sidebar.row_button(indexes["Layout"]).isHidden()
    assert sidebar.row_button(indexes["Config"]).isHidden()
    assert sidebar.row_button(indexes["Regions"]).isHidden()
    assert sidebar.row_button(indexes["Layers"]).isHidden()
    assert sidebar.row_button(indexes["Theme"]).isHidden()
    assert sidebar.row_button(indexes["Constructor"]).isHidden()


def test_spec_docs_flow_into_object_section(qapp):
    """A widget spec's ``docs`` reference lands on the inspection and
    renders as a clickable ``docs`` row in the Object section (the app
    can reuse the same reference via ``spec.docs_for``)."""
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.ui.inspector.spec import InspectSpec, docs_for

    class _DocsProbe(QWidget):
        pass

    _DocsProbe.inspect_spec = InspectSpec(
        family="DocsProbe", docs="docs/user/BUTTON_API.md"
    )
    probe = _DocsProbe()

    # the reference is reachable from the widget itself (host-app reuse)
    assert docs_for(probe) == "docs/user/BUTTON_API.md"

    win = InspectorWindow()
    win.set_inspection(
        WidgetInspection(family="DocsProbe", docs=docs_for(probe)),
        widget=probe,
    )
    texts = _page_labels(win, "Object")
    assert any("docs" in t for t in texts)
    assert any("BUTTON_API.md" in t for t in texts)


def test_docs_path_resolves_against_repo_root_not_cwd(qapp, monkeypatch, tmp_path):
    """App-side runs (CWD = the host app, not the toolkit repo) must still
    find the toolkit's own docs files: the repo root is located from the
    installed package, not from the working directory."""
    from pathlib import Path

    from sli_ui_toolkit.ui.inspector.spec import _resolve_docs_path

    monkeypatch.chdir(tmp_path)
    path = Path(_resolve_docs_path("docs/user/BUTTON_API.md"))
    assert path.is_file()
    assert path.name == "BUTTON_API.md"
    assert str(path).startswith(str(tmp_path)) is False


def test_docs_section_renders_readonly(qapp):
    """The Docs section shows the widget family's docs file in the
    read-only text view (document/markdown mode), not editable."""
    from sli_ui_toolkit.ui.widgets.composite.text_view import TextView

    win = InspectorWindow()
    win.set_inspection(
        WidgetInspection(family="QWidget", docs="docs/user/BUTTON_API.md")
    )
    page = win._pages["Docs"]
    views = page.content_widget.findChildren(TextView)
    assert views, "docs page must host a text view"
    plain = views[0].plain_text()
    assert "Button Component API" in plain
    assert views[0].is_editing() is False
    assert views[0].is_document() is True
    # markdown structure is honored, not shown raw: the '# …' heading marker
    # and backtick fences disappear, fenced code survives as plain text
    assert "Button Component API Reference" in plain
    assert "# Button Component API" not in plain
    assert "```" not in plain
    assert "from sli_ui_toolkit.ui.widgets.buttons import Button" in plain
    # no docs reference → the section stays empty (hidden in the sidebar)
    win.set_inspection(WidgetInspection(family="QWidget"))
    assert win._pages["Docs"].content_layout.count() == 0


def test_code_docs_button_switches_to_docs_section(qapp, monkeypatch, tmp_path_factory):
    """The Docs button right of Full/Compact opens the Docs section."""
    from PySide6.QtWidgets import QWidget

    win = InspectorWindow()
    tmp = tmp_path_factory.mktemp("docs_probe")
    source_file = tmp / "probe_widget.py"
    source_file.write_text(
        "class _LocalProbe(QWidget):\n    pass\n", encoding="utf-8"
    )

    class _LocalProbe(QWidget):
        pass

    import inspect as _inspect

    monkeypatch.setattr(_inspect, "getsourcefile", lambda _cls: str(source_file))
    monkeypatch.setattr(
        _inspect,
        "getsourcelines",
        lambda _cls: (["class _LocalProbe(QWidget):\n", "    pass\n"], 1),
    )
    win.set_inspection(
        WidgetInspection(family="QWidget", docs="docs/user/BUTTON_API.md"),
        widget=_LocalProbe(),
    )
    pane = win.active_pane()
    page = pane.pages["Code"]
    buttons = {
        str(getattr(b, "_text", "")): b
        for b in page.content_widget.findChildren(Button)
    }
    assert "Docs" in buttons
    indexes = {name: index for index, name in enumerate(win._pages)}
    assert win._shell.sidebar.currentRow() != indexes["Docs"]
    buttons["Docs"].click()
    assert win._shell.sidebar.currentRow() == indexes["Docs"]
    # no docs reference → no button
    win.set_inspection(WidgetInspection(family="QWidget"), widget=_LocalProbe())
    qapp.processEvents()  # flush the old editor's deferred deleteLater
    buttons = {
        str(getattr(b, "_text", "")): b
        for b in pane.pages["Code"].content_widget.findChildren(Button)
    }
    assert "Docs" not in buttons


def test_qss_rules_render_inside_code_page(qapp, monkeypatch, tmp_path_factory):
    """The QSS section was merged into Code: candidate rules are assembled
    into a synthetic QSS code block at the top of the editor buffer (like
    the config snippet), no separate sidebar entry."""
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.ui.inspector.qss_scan import QssRule

    win = InspectorWindow()
    assert "QSS" not in win._pages

    tmp = tmp_path_factory.mktemp("qss_probe")
    source_file = tmp / "probe_widget.py"
    source_file.write_text(
        "class _LocalProbe(QWidget):\n    pass\n", encoding="utf-8"
    )

    class _LocalProbe(QWidget):
        pass

    import inspect as _inspect

    monkeypatch.setattr(_inspect, "getsourcefile", lambda _cls: str(source_file))
    monkeypatch.setattr(
        _inspect,
        "getsourcelines",
        lambda _cls: (["class _LocalProbe(QWidget):\n", "    pass\n"], 1),
    )
    win.set_inspection(
        WidgetInspection(family="QWidget"),
        widget=_LocalProbe(),
        qss_candidates=(
            QssRule(
                source="/virtual/style.qss",
                selector="QWidget {",
                body="background: red;",
                line=3,
            ),
            QssRule(
                source="/virtual/style.qss",
                selector="#dead {",
                body="color: blue;",
                line=9,
            ),
        ),
    )
    text = win.active_pane()._code_view.text()
    assert "QWidget {" in text
    assert "background: red;" in text
    assert "#dead {" in text
    assert "color: blue;" in text
    # the QSS block is synthetic — above the class, with the dot gutter
    # (never file content), like the config snippet
    assert text.index("QWidget {") < text.index("class _LocalProbe")
    gutter = win.active_pane()._code_view._canvas._line_number_map
    qss_line = [
        i for i, line in enumerate(text.split("\n")) if "QWidget {" in line
    ][0]
    assert gutter[qss_line] == "·"


def test_constructor_page_renders_clickable_rows(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from sli_ui_toolkit.ui.inspector.view import _TreeNodeRow

    win = InspectorWindow()
    parent = QWidget()
    child = QWidget(parent)
    grandchild = QWidget(child)
    win.set_constructor_nodes(
        (
            ("QWidget", parent, 0),
            ("QWidget", child, 1),
            ("QWidget", grandchild, 2),
        )
    )
    emitted: list[object] = []
    win.widget_activated.connect(emitted.append)
    page = win._pages["Constructor"]
    rows = page.content_widget.findChildren(_TreeNodeRow)
    assert len(rows) == 3
    QTest.mouseClick(rows[2], Qt.MouseButton.LeftButton, pos=QPoint(60, 13))
    assert emitted == [grandchild]
    assert not win._shell.sidebar.row_button(
        {name: index for index, name in enumerate(win._pages)}["Constructor"]
    ).isHidden()


def test_tree_rows_collapse_and_expand_on_twist_click(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from sli_ui_toolkit.ui.inspector.view import _TreeNodeRow

    win = InspectorWindow()
    node = QWidget()
    child = QWidget(node)
    win.set_layout_nodes((("QWidget", node, 0), ("QWidget", child, 1)))
    layout_index = {name: index for index, name in enumerate(win._pages)}["Layout"]
    win._shell.sidebar.setCurrentRow(layout_index)
    win.show()
    qapp.processEvents()
    page = win._pages["Layout"]
    rows = page.content_widget.findChildren(_TreeNodeRow)
    assert len(rows) == 2
    assert rows[0]._expanded is False
    assert not rows[1].isVisible()
    QTest.mouseClick(rows[0], Qt.MouseButton.LeftButton, pos=QPoint(5, 13))
    assert rows[0]._expanded is True
    assert rows[1].isVisible()
    QTest.mouseClick(rows[0], Qt.MouseButton.LeftButton, pos=QPoint(5, 13))
    assert rows[0]._expanded is False
    assert not rows[1].isVisible()


def test_tree_row_hover_emits_widget_signals(qapp):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent

    from sli_ui_toolkit.ui.inspector.view import _TreeNodeRow

    win = InspectorWindow()
    node = QWidget()
    child = QWidget(node)
    win.set_layout_nodes((("QWidget", node, 0), ("QWidget", child, 1)))
    hovered: list[object] = []
    cleared = []
    win.widget_hovered.connect(hovered.append)
    win.widget_hover_cleared.connect(lambda: cleared.append(1))
    page = win._pages["Layout"]
    rows = page.content_widget.findChildren(_TreeNodeRow)
    qapp.sendEvent(
        rows[1], QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10))
    )
    assert hovered == [child]
    qapp.sendEvent(rows[1], QEvent(QEvent.Type.Leave))
    assert cleared == [1]


def test_selection_moves_off_hidden_current_section(qapp):
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.ui.inspector import inspect_widget

    win = InspectorWindow()
    widget = QWidget()
    win.set_inspection(inspect_widget(widget), widget=widget)
    win.set_layout_nodes((("QWidget", widget, 0),))
    sidebar = win._shell.sidebar
    visible_row = sidebar.currentRow()
    assert visible_row >= 0
    assert not sidebar.row_button(visible_row).isHidden()


def test_open_widget_creates_deduplicated_tabs(qapp):
    from PySide6.QtWidgets import QWidget

    win = InspectorWindow()
    a = QWidget()
    b = QWidget()
    pane_a = win.open_widget(a, "A")
    assert win.tabs.count() == 1
    pane_b = win.open_widget(b, "B")
    assert win.tabs.count() == 2
    assert win.active_pane() is pane_b
    # re-opening an already-open widget switches to its tab, no duplicate
    win.open_widget(a, "A")
    assert win.tabs.count() == 2
    assert win.active_pane() is pane_a
    assert win.tabs.tabText(win.tabs.indexOf(pane_b)) == "B"


def test_tabs_route_rendering_to_their_own_pane(qapp):
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.ui.inspector import inspect_widget

    win = InspectorWindow()
    a = QWidget()
    b = QWidget()
    pane_a = win.open_widget(a, "A")
    win.set_inspection(inspect_widget(a), widget=a)
    win.open_widget(b, "B")
    win.set_inspection(inspect_widget(b), widget=b)
    assert pane_a._current.family == "QWidget"
    assert win.active_pane()._current.family == "QWidget"
    assert win.active_pane().widget is b
    assert pane_a.widget is a


def test_pane_created_signal_fires_per_tab(qapp):
    from PySide6.QtWidgets import QWidget

    win = InspectorWindow()
    created: list[object] = []
    win.pane_created.connect(created.append)
    win.open_widget(QWidget(), "A")
    win.open_widget(QWidget(), "B")
    assert len(created) == 2


def test_close_tab_removes_pane_and_cleans_dedupe(qapp):
    from PySide6.QtWidgets import QWidget

    win = InspectorWindow()
    a = QWidget()
    b = QWidget()
    pane_a = win.open_widget(a, "A")
    win.open_widget(b, "B")
    assert win.tabs.count() == 2
    win._close_tab(win.tabs.indexOf(pane_a))
    qapp.processEvents()
    assert win.tabs.count() == 1
    # dedupe entry dropped: re-opening the same widget creates a NEW tab
    pane_a2 = win.open_widget(a, "A")
    assert win.tabs.count() == 2
    assert pane_a2 is not pane_a


def test_close_tab_preserves_cached_layout_tree(qapp):
    from PySide6.QtWidgets import QWidget

    win = InspectorWindow()
    host = QWidget()
    node = QWidget(host)
    pane1 = win.open_widget(node, "A")
    win.set_layout_nodes((("QWidget", node, 0),))
    win.open_widget(QWidget(host), "B")
    pane2 = win.active_pane()
    tree = next(iter(win._layout_tree_cache.values()))
    assert tree.parentWidget() is pane2.pages["Layout"].content_widget
    win._close_tab(win.tabs.indexOf(pane2))
    qapp.processEvents()
    # the shared tree survived the pane deletion and moved to the next tab
    assert tree.parentWidget() is pane1.pages["Layout"].content_widget
    assert win.tabs.count() == 1
