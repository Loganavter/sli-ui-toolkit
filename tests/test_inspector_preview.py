"""Inspector tests — preview panel."""

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

def test_code_section_preview_builds_widget_from_edited_class(qapp, monkeypatch, tmp_path_factory):
    """Preview compiles the edited class and constructs a live instance
    with the current config values as constructor kwargs."""
    win = InspectorWindow()
    pane, _source_file, _written = _open_probe(
        win,
        "from PySide6.QtWidgets import QWidget\n\nclass Probe(QWidget):\n"
        "    def __init__(self, parent=None, text=''):\n"
        "        super().__init__(parent)\n"
        "        self.probe_text = text\n",
        tmp_path_factory,
        monkeypatch,
        source_start=3,
        config=(InspectField(name="text", value="live"),),
    )
    # the preview builds from the CURRENT (unedited) class first
    pane._code_section._preview_btn.click()
    assert pane._code_section._preview_widget is not None
    assert pane._code_section._preview_widget.probe_text == "live"
    assert not pane._code_section._preview_error.isVisible()

    # edit the class region: append an override statement to the END of the
    # __init__ body (so it runs after the original assignment)
    page = pane.pages["Code"]
    buttons = {
        str(getattr(b, "_text", "")): b
        for b in page.content_widget.findChildren(Button)
    }
    buttons["Edit"].click()
    editor = pane._code_view.editor()
    class_start = (
        pane._code_section._config_display_lines
        + pane._code_section._gap_a_display_lines
    )
    probe_line = class_start + 3  # 0=class, 1=def, 2=super().__init__, 3=self.probe_text
    probe_col = len(editor._lines[probe_line])
    editor._cursor = (probe_line, probe_col)
    # append a second statement after the original assignment (; separator)
    editor.insert_text("; self.probe_text = 'edited-live'")
    # the live preview re-builds on change (debounced)
    _spin_event_loop(qapp)
    assert pane._code_section._preview_widget.probe_text == "edited-live"
    # and reverting restores the original preview
    buttons["Revert"].click()
    _spin_event_loop(qapp)
    assert pane._code_section._preview_widget.probe_text == "live"


def test_code_section_preview_shows_error_for_broken_edit(qapp, monkeypatch, tmp_path_factory):
    win = InspectorWindow()
    pane, _source_file, _written = _open_probe(
        win,
        "from PySide6.QtWidgets import QWidget\n\nclass Probe(QWidget):\n"
        "    def __init__(self, parent=None, text=''):\n"
        "        super().__init__(parent)\n"
        "        self.probe_text = text\n",
        tmp_path_factory,
        monkeypatch,
        source_start=3,
        config=(InspectField(name="text", value="live"),),
    )
    pane._code_section._preview_btn.click()
    page = pane.pages["Code"]
    buttons = {
        str(getattr(b, "_text", "")): b
        for b in page.content_widget.findChildren(Button)
    }
    buttons["Edit"].click()
    editor = pane._code_view.editor()
    editor._cursor = (pane._code_section._config_display_lines + 1, 0)
    editor.insert_text("    def broken(:\n")
    _spin_event_loop(qapp)
    assert not pane._code_section._preview_error.isHidden()
    assert "Compile failed" in pane._code_section._preview_error.text()
    assert pane._code_section._preview_widget is None


def test_code_section_preview_fills_missing_required_kwargs(qapp, monkeypatch, tmp_path_factory):
    """Preview is best-effort: required constructor args the snippet cannot
    carry (not stored as attributes) are filled with None — like
    AdaptiveTabStrip's add_icon/close_icon."""
    win = InspectorWindow()
    pane, _source_file, _written = _open_probe(
        win,
        "from PySide6.QtWidgets import QWidget\n\nclass Probe(QWidget):\n"
        "    def __init__(self, parent=None, text='', *, required_thing):\n"
        "        super().__init__(parent)\n"
        "        self.thing = required_thing\n",
        tmp_path_factory,
        monkeypatch,
        source_start=3,
        config=(InspectField(name="text", value="x"),),
    )
    pane._code_section._preview_btn.click()
    assert pane._code_section._preview_widget is not None
    assert pane._code_section._preview_widget.thing is None
    assert pane._code_section._preview_error.isHidden()


def test_code_section_preview_fills_required_kwargs_hidden_behind_forwarding_subclass(qapp):
    """A subclass whose __init__ forwards *args/**kwargs hides the required
    args from the snippet — the preview must resolve the real signature
    through the MRO and still build."""
    import types

    from PySide6.QtWidgets import QWidget as QWidgetBase

    from sli_ui_toolkit.ui.inspector.code import CodeSectionEditor
    from sli_ui_toolkit.ui.inspector.fields import _config_snippet

    src = (
        "from PySide6.QtWidgets import QWidget\n\n"
        "class Probe(QWidget):\n"
        "    def __init__(self, parent=None, text='', *, required_thing):\n"
        "        super().__init__(parent)\n"
        "        self.thing = required_thing\n"
        "class Forwarder(Probe):\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        super().__init__(*args, **kwargs)\n"
    )
    module = types.ModuleType("preview_probe_module")
    module.__dict__["QWidget"] = QWidgetBase
    exec(src, module.__dict__)  # noqa: S102 — test fixture
    editor = CodeSectionEditor()
    editor.set_source(
        path="/virtual/probe.py",
        source_text=(
            "class Forwarder(Probe):\n"
            "    def __init__(self, *args, **kwargs):\n"
            "        super().__init__(*args, **kwargs)\n"
        ),
        source_start=7,
        config_text=_config_snippet(
            "Forwarder", (InspectField(name="text", value="x"),)
        ),
        module_vars=module.__dict__,
    )
    editor._preview_btn.click()
    assert editor._preview_widget is not None
    assert editor._preview_widget.thing is None
    assert editor._preview_error.isHidden()


def test_code_section_preview_builds_widget_with_required_parent(qapp):
    """GlassHUD-style constructors (`__init__(self, parent)`, required)
    must not get `parent` auto-filled with None on top of the explicit
    host argument — that raised "multiple values for keyword argument
    'parent'" and left the well empty (InfoHUD/ZoomIndicator)."""
    import types

    from PySide6.QtWidgets import QWidget as QWidgetBase

    from sli_ui_toolkit.ui.inspector.code import CodeSectionEditor

    src = (
        "from PySide6.QtWidgets import QWidget\n\n"
        "class Probe(QWidget):\n"
        "    def __init__(self, parent):\n"
        "        super().__init__(parent)\n"
    )
    module = types.ModuleType("required_parent_probe_module")
    module.__dict__["QWidget"] = QWidgetBase
    exec(src, module.__dict__)  # noqa: S102 — test fixture
    editor = CodeSectionEditor()
    editor.set_source(
        path="/virtual/probe.py",
        source_text=src,
        source_start=3,
        config_text=None,
        module_vars=module.__dict__,
    )
    editor._preview_btn.click()
    assert editor._preview_widget is not None
    assert editor._preview_error.isHidden()
    assert editor._preview_widget.parentWidget() is editor._preview_host


def test_code_section_preview_gives_min_height_to_widget_without_sizehint(qapp):
    """A plain QWidget (no sizeHint) collapses to zero height in the well
    and renders nothing — the preview must still show a visible strip."""
    import types

    from PySide6.QtWidgets import QWidget as QWidgetBase

    from sli_ui_toolkit.ui.inspector.code import CodeSectionEditor

    src = (
        "from PySide6.QtWidgets import QWidget\n\n"
        "class Probe(QWidget):\n"
        "    def __init__(self, parent=None):\n"
        "        super().__init__(parent)\n"
    )
    module = types.ModuleType("flat_probe_module")
    module.__dict__["QWidget"] = QWidgetBase
    exec(src, module.__dict__)  # noqa: S102 — test fixture
    editor = CodeSectionEditor()
    editor.set_source(
        path="/virtual/probe.py",
        source_text=src,
        source_start=3,
        config_text=None,
        module_vars=module.__dict__,
    )
    editor._preview_btn.click()
    assert editor._preview_widget is not None
    assert editor._preview_widget.size().height() >= 48


def test_code_section_preview_seeds_live_state_via_spec(qapp):
    """The preview copies the live widget's runtime state through the
    spec's preview_seed hook — without it, stateful composites (a tab
    strip) preview as an empty shell and the well looks like nothing but
    the backdrop."""
    import types

    from PySide6.QtWidgets import QWidget as QWidgetBase

    from sli_ui_toolkit.ui.inspector.code import CodeSectionEditor
    from sli_ui_toolkit.ui.inspector.spec import InspectSpec

    src = (
        "from PySide6.QtWidgets import QWidget\n\n"
        "class Probe(QWidget):\n"
        "    def __init__(self, parent=None):\n"
        "        super().__init__(parent)\n"
        "        self.items = []\n"
        "    def add_item(self, text):\n"
        "        self.items.append(text)\n"
    )

    def seed(preview, live):
        for text in live.items:
            preview.add_item(text)

    module = types.ModuleType("seed_probe_module")
    module.__dict__["QWidget"] = QWidgetBase
    exec(src, module.__dict__)  # noqa: S102 — test fixture
    module.Probe.inspect_spec = InspectSpec(family="Probe", preview_seed=seed)
    live = module.Probe()
    live.add_item("alpha")
    live.add_item("beta")

    editor = CodeSectionEditor()
    editor.set_source(
        path="/virtual/probe.py",
        source_text=src,
        source_start=3,
        config_text=None,
        module_vars=module.__dict__,
        target_class=module.Probe,
        target_instance=live,
    )
    editor._preview_btn.click()
    assert editor._preview_widget is not None
    assert editor._preview_widget.items == ["alpha", "beta"]
    assert editor._preview_error.isHidden()


def test_code_section_preview_resolves_enum_not_in_widget_module(qapp):
    """Enum members from the live config resolve in the preview even when
    the widget module does not import their class (the app's AppIcon):
    the snippet's ``Type.MEMBER`` literal must not be skipped."""
    import types
    from enum import Enum

    from sli_ui_toolkit.ui.inspector.code.config import _config_kwargs
    from sli_ui_toolkit.ui.inspector.fields import _config_snippet

    class _ProbeIcon(Enum):
        STAR = "star"
        MOON = "moon"

    # the widget module deliberately does NOT know _ProbeIcon
    module = types.ModuleType("probe_enum_module")
    exec(
        "from PySide6.QtWidgets import QWidget\n\n"
        "class Probe(QWidget):\n"
        "    def __init__(self, parent=None, icon=None):\n"
        "        super().__init__(parent)\n"
        "        self._icon = icon\n",
        module.__dict__,
    )
    snippet = _config_snippet(
        "Probe", (InspectField(name="icon", value=_ProbeIcon.MOON),)
    )
    assert "ProbeIcon.MOON" in snippet
    kwargs, skipped = _config_kwargs(snippet, module.__dict__)
    assert kwargs == {"icon": _ProbeIcon.MOON}
    assert skipped == []

