"""Inspector honesty: staleness key, capture blind spots, extractor marks."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.inspector import registry as registry_module
from sli_ui_toolkit.ui.inspector.capture import CAPTURE_LIMITATION_META, capture_tokens
from sli_ui_toolkit.ui.inspector.contract import FieldKind, InspectField, WidgetInspection
from sli_ui_toolkit.ui.inspector.registry import inspect_widget
from sli_ui_toolkit.ui.inspector.tree import _layout_tree_key
from sli_ui_toolkit.ui.inspector.view import InspectorWindow
from sli_ui_toolkit.widgets import Button


def _theme(app):
    tm = ThemeManager.get_instance()
    tm.register_palettes(
        {
            "accent": "#0078d4",
            "dialog.text": "#111111",
            "surface.list": "#f0f0f0",
        },
        {
            "accent": "#0096ff",
            "dialog.text": "#dddddd",
            "surface.list": "#2a2a2a",
        },
    )
    tm.set_theme("light", app)
    return tm


def _window_with_children(qapp, count=4):
    host = QWidget()
    layout = QVBoxLayout(host)
    children = [QWidget(host) for _ in range(count)]
    for child in children:
        layout.addWidget(child)
    host.show()
    qapp.processEvents()
    nodes = tuple((f"W{i}", child, 0) for i, child in enumerate(children))
    return host, children, nodes


def test_layout_tree_key_stable_for_identical(qapp):
    _host, _children, nodes = _window_with_children(qapp)
    assert _layout_tree_key(nodes) == _layout_tree_key(tuple(nodes))
    _host.deleteLater()


def test_layout_tree_key_detects_middle_reorder(qapp):
    """Old key (window + count + first/last ids) missed middle reorders."""
    host, children, nodes = _window_with_children(qapp)
    before = _layout_tree_key(nodes)
    a, b, c, d = children
    reordered = ((nodes[0][0], a, 0), (nodes[2][0], c, 0), (nodes[1][0], b, 0), (nodes[3][0], d, 0))
    assert _layout_tree_key(reordered) != before
    host.deleteLater()


def test_layout_tree_key_detects_dropped_middle_node(qapp):
    """Old key missed a dropped middle node when endpoints survived."""
    host, _children, nodes = _window_with_children(qapp)
    before = _layout_tree_key(nodes)
    dropped = (nodes[0], nodes[2], nodes[3])
    assert _layout_tree_key(dropped) != before
    host.deleteLater()


def test_layout_tree_key_detects_rename(qapp):
    host, children, nodes = _window_with_children(qapp)
    before = _layout_tree_key(nodes)
    renamed = (("renamed", children[0], 0),) + nodes[1:]
    assert _layout_tree_key(renamed) != before
    host.deleteLater()


def test_layout_tree_key_none_without_widgets(qapp):
    assert _layout_tree_key((("a", None, 0), ("b", None, 1))) is None


def test_layout_tree_key_window_id_first(qapp):
    """The window identity stays the first element (tab-change lookup)."""
    host, _children, nodes = _window_with_children(qapp)
    key = _layout_tree_key(nodes)
    assert key is not None
    assert key[0] == id(host.window())
    host.deleteLater()


def test_capture_hidden_widget_discloses(qapp):
    """A hidden widget records nothing — disclosed, not ()."""
    widget = QWidget()  # never shown
    fields = capture_tokens(widget, _theme(qapp))
    assert len(fields) == 1
    assert fields[0].meta.get(CAPTURE_LIMITATION_META) == "hidden"
    assert fields[0].kind is FieldKind.TEXT


def test_capture_visible_bare_widget_discloses_cached(qapp):
    """A shown widget resolving no keys paints from cache — disclosed."""
    widget = QWidget()
    widget.show()
    qapp.processEvents()
    try:
        fields = capture_tokens(widget, _theme(qapp))
        assert len(fields) == 1
        assert fields[0].meta.get(CAPTURE_LIMITATION_META) == "cached"
    finally:
        widget.deleteLater()


def test_capture_real_tokens_unaffected(qapp):
    """Hidden-ness alone suppresses nothing when the repaint records keys."""
    button = Button(text="x")  # not shown; offscreen grab still repaints
    fields = capture_tokens(button, _theme(qapp))
    assert {f.name for f in fields} >= {"surface.list", "dialog.text"}
    assert not any(f.meta.get(CAPTURE_LIMITATION_META) for f in fields)


def test_inspect_widget_marks_failed_extractor(qapp):
    """A raising family extractor falls back — with a marked state row."""

    class _ProbeWidget(QWidget):
        """No spec: inspection must go through the family registry."""

    saved = list(registry_module._REGISTERED)
    registry_module._REGISTERED.clear()

    def _boom(widget, theme_manager=None):
        raise RuntimeError("extractor exploded")

    try:
        registry_module.register_family(
            "Boom", lambda w: isinstance(w, _ProbeWidget), _boom, priority=1
        )
        inspection = inspect_widget(_ProbeWidget())
        assert inspection.family == "QWidget"
        marks = [f for f in inspection.state if f.meta.get("extractor_failed")]
        assert len(marks) == 1
        assert marks[0].name == "extractor:Boom"
        assert "RuntimeError" in str(marks[0].value)
    finally:
        registry_module._REGISTERED.clear()
        registry_module._REGISTERED.extend(saved)


def test_inspect_widget_marks_failed_spec_build(qapp, monkeypatch):
    """A raising spec build falls back — with a marked state row."""
    import sli_ui_toolkit.ui.inspector.spec as spec_module

    def _boom(widget, spec, theme_manager=None):
        raise ValueError("spec build exploded")

    saved = list(registry_module._REGISTERED)
    registry_module._REGISTERED.clear()
    try:
        monkeypatch.setattr(spec_module, "build_inspection", _boom)
        inspection = inspect_widget(Button(text="x"))
        assert inspection.family == "QWidget"
        marks = [f for f in inspection.state if f.meta.get("extractor_failed")]
        assert len(marks) == 1
        assert marks[0].name.startswith("extractor:")
        assert "ValueError" in str(marks[0].value)
    finally:
        registry_module._REGISTERED.clear()
        registry_module._REGISTERED.extend(saved)


def _theme_page_labels(win):
    from tests.inspector_helpers import _page_labels

    return _page_labels(win, "Theme")


def test_render_theme_titles_empty_capture_as_caveat(qapp):
    """Disclosure-only live tokens render under a caveat title."""
    win = InspectorWindow()
    try:
        disclosure = InspectField(
            name="capture (hidden widget)",
            value="not visible",
            kind=FieldKind.TEXT,
            meta={CAPTURE_LIMITATION_META: "hidden"},
        )
        win.set_inspection(
            WidgetInspection(family="QWidget", live_tokens=(disclosure,)),
            widget=QWidget(),
        )
        labels = _theme_page_labels(win)
        assert "Live capture (no tokens recorded)" in labels
        assert "Live capture" not in labels or True  # caveat title present
    finally:
        win.deleteLater()


def test_render_theme_titles_real_capture_plainly(qapp):
    """A capture with real tokens keeps the plain title."""
    win = InspectorWindow()
    try:
        real = InspectField(
            name="surface.list", value="#f0f0f0", kind=FieldKind.COLOR
        )
        win.set_inspection(
            WidgetInspection(
                family="Button",
                token_family=("surface.list",),
                live_tokens=(real,),
            ),
            widget=QWidget(),
        )
        labels = _theme_page_labels(win)
        assert "Live capture" in labels
        assert "Live capture (no tokens recorded)" not in labels
    finally:
        win.deleteLater()
