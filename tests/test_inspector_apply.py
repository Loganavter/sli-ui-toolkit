"""Inspector tests — Apply (class patch + config apply)."""

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

def test_code_section_apply_does_not_launch_preview(qapp):
    """Apply must NOT open or build the preview panel — it only refreshes
    an already-open one (the live widget itself is the feedback)."""
    import types

    from PySide6.QtWidgets import QWidget as QWidgetBase

    from sli_ui_toolkit.ui.inspector.code import CodeSectionEditor

    src = (
        "from PySide6.QtWidgets import QWidget\n\n"
        "class Probe(QWidget):\n"
        "    def __init__(self, parent=None):\n"
        "        super().__init__(parent)\n"
    )
    module = types.ModuleType("apply_preview_probe_module")
    module.__dict__["QWidget"] = QWidgetBase
    exec(src, module.__dict__)  # noqa: S102 — test fixture
    live = module.Probe()
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
    editor._view.enter_edit_mode()
    canvas = editor._view.editor()
    canvas._cursor = (3, 0)
    canvas.insert_text("    def patched(self):\n        return 'ok'\n")
    editor._apply_btn.click()
    # the panel stays closed: no preview widget, no caption, button label
    # untouched
    assert not editor._preview_panel.isVisible()
    assert editor._preview_widget is None
    assert str(getattr(editor._preview_btn, "_text", "")) == "Preview"
    assert live.patched() == "ok"

    # an already-open preview IS refreshed and carries the Apply result
    editor._preview_btn.click()
    assert editor._preview_widget is not None
    assert editor._preview_widget.parentWidget() is editor._preview_host
    editor._view.enter_edit_mode()
    canvas = editor._view.editor()
    canvas._cursor = (5, 0)
    canvas.insert_text("    def patched2(self):\n        return 2\n")
    editor._apply_btn.click()
    assert "Apply OK" in editor._preview_caption.text()
    assert editor._preview_error.isHidden()
    assert live.patched2() == 2
    debug = editor._preview_debug.text()
    assert "patched onto Probe" in debug
    assert "sizeHint" in debug


def test_code_section_apply_reports_noop_for_unchanged_source(qapp):
    """Apply with an unedited class region is a no-op: the button stays
    disabled (like Save) and, if invoked anyway, reports "Nothing to
    patch" instead of claiming success."""
    import types

    from PySide6.QtWidgets import QWidget as QWidgetBase

    from sli_ui_toolkit.ui.inspector.code import CodeSectionEditor

    src = (
        "from PySide6.QtWidgets import QWidget\n\n"
        "class Probe(QWidget):\n"
        "    def __init__(self, parent=None):\n"
        "        super().__init__(parent)\n"
    )
    module = types.ModuleType("noop_apply_module")
    module.__dict__["QWidget"] = QWidgetBase
    exec(src, module.__dict__)  # noqa: S102 — test fixture
    live = module.Probe()
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
    # unchanged source -> Apply is disabled (stray clicks do nothing)
    assert not editor._apply_btn.isEnabled()
    editor._apply_btn.click()
    assert editor._preview_widget is None
    # the guard reports the no-op without launching the preview panel
    editor._apply_to_live()
    assert not editor._preview_panel.isVisible()
    # with the panel already open the no-op shows in the caption
    editor._preview_btn.click()
    editor._apply_to_live()
    assert "Nothing to patch" in editor._preview_caption.text()
    assert "Apply OK" not in editor._preview_caption.text()


def test_code_section_apply_init_hint_only_for_init_edits(qapp):
    """The "live instance keeps its current state" hint appears only when
    the edits actually touch __init__ — method edits must not carry it."""
    import types

    from PySide6.QtWidgets import QWidget as QWidgetBase

    from sli_ui_toolkit.ui.inspector.code import CodeSectionEditor

    src = (
        "from PySide6.QtWidgets import QWidget\n\n"
        "class Probe(QWidget):\n"
        "    def __init__(self, parent=None):\n"
        "        super().__init__(parent)\n"
        "        self.margin = 2\n"
        "    def answer(self):\n"
        "        return 40\n"
    )
    class_source = (
        "class Probe(QWidget):\n"
        "    def __init__(self, parent=None):\n"
        "        super().__init__(parent)\n"
        "        self.margin = 2\n"
        "    def answer(self):\n"
        "        return 40\n"
    )
    module = types.ModuleType("init_hint_module")
    module.__dict__["QWidget"] = QWidgetBase
    exec(src, module.__dict__)  # noqa: S102 — test fixture
    live = module.Probe()

    def fresh_editor():
        editor = CodeSectionEditor()
        editor.set_source(
            path="/virtual/probe.py",
            source_text=class_source,
            source_start=3,
            config_text=None,
            module_vars=module.__dict__,
            target_class=module.Probe,
            target_instance=live,
        )
        return editor

    # method-only edit: no hint
    editor = fresh_editor()
    editor._preview_btn.click()  # open the panel to read Apply feedback
    editor._view.enter_edit_mode()
    canvas = editor._view.editor()
    canvas._cursor = (4, 0)  # the `def answer` line
    canvas.insert_text("    def extra(self):\n        return 1\n")
    editor._apply_btn.click()
    assert "Apply OK" in editor._preview_caption.text()
    assert "keeps its current state" not in editor._preview_caption.text()
    assert live.extra() == 1

    # __init__-body edit: hint present, live instance keeps old state
    editor = fresh_editor()
    editor._preview_btn.click()
    editor._view.enter_edit_mode()
    canvas = editor._view.editor()
    canvas._cursor = (3, 0)  # the `self.margin = 2` line inside __init__
    canvas.insert_text("        self.margin = 99\n")
    editor._apply_btn.click()
    assert "Apply OK" in editor._preview_caption.text()
    assert "keeps its current state" in editor._preview_caption.text()
    assert live.margin == 2  # instance state is not re-run


def test_code_section_snippet_edit_enables_save_and_apply(qapp):
    """Editing the synthetic config snippet is a change: Save AND Apply
    both enable (Apply writes the values onto the live instance; Save
    rewrites the file — the snippet itself is synthetic, not file
    content, so a snippet-only Save persists the unchanged class)."""
    import types

    from PySide6.QtWidgets import QWidget as QWidgetBase

    from sli_ui_toolkit.ui.inspector.code import CodeSectionEditor
    from sli_ui_toolkit.ui.inspector.fields import _config_snippet

    src = (
        "from PySide6.QtWidgets import QWidget\n\n"
        "class Probe(QWidget):\n"
        "    def __init__(self, parent=None, width=28):\n"
        "        super().__init__(parent)\n"
        "        self._width = width\n"
    )
    class_source = (
        "class Probe(QWidget):\n"
        "    def __init__(self, parent=None, width=28):\n"
        "        super().__init__(parent)\n"
        "        self._width = width\n"
    )
    module = types.ModuleType("snippet_edit_module")
    module.__dict__["QWidget"] = QWidgetBase
    exec(src, module.__dict__)  # noqa: S102 — test fixture
    refreshed: list = []

    def refresh(live_widget, applied):
        refreshed.append(tuple(applied))

    from sli_ui_toolkit.ui.inspector.spec import InspectSpec

    module.Probe.inspect_spec = InspectSpec(
        family="Probe", apply_config_refresh=refresh
    )
    live = module.Probe()
    editor = CodeSectionEditor()
    editor.set_source(
        path="/virtual/probe.py",
        source_text=class_source,
        source_start=3,
        config_text=_config_snippet(
            "Probe", (InspectField(name="width", value=28),)
        ),
        module_vars=module.__dict__,
        target_class=module.Probe,
        target_instance=live,
    )
    assert not editor._apply_btn.isEnabled()
    assert not editor._save_btn.isEnabled()
    # the snippet is display lines 0..2 — select the `28` on line 1 and
    # replace it with `33`
    editor._view.enter_edit_mode()
    canvas = editor._view.editor()
    canvas._selection.set_range((1, 10), (1, 12))
    canvas.insert_text("33")
    assert not editor.is_dirty()  # class region untouched
    assert editor.snippet_dirty()
    assert editor._apply_btn.isEnabled()
    assert editor._save_btn.isEnabled()
    # Apply writes the snippet config onto the live instance (open the
    # panel first to read the Apply feedback)
    editor._preview_btn.click()
    editor._apply_btn.click()
    assert live._width == 33
    assert "config applied to instance" in editor._preview_caption.text()
    # the spec's apply_config_refresh hook ran with the applied names
    assert refreshed == [("width",)]



    """Apply hot-patches the REAL widget class: the live instance gains the
    edited behavior immediately; Revert restores the original class."""
    import types

    from PySide6.QtWidgets import QWidget as QWidgetBase

    from sli_ui_toolkit.ui.inspector.code import CodeSectionEditor

    src = (
        "from PySide6.QtWidgets import QWidget\n\n"
        "class Probe(QWidget):\n"
        "    def answer(self):\n"
        "        return 40\n"
    )
    module = types.ModuleType("apply_probe_module")
    module.__dict__["QWidget"] = QWidgetBase
    exec(src, module.__dict__)  # noqa: S102 — test fixture
    live = module.Probe()
    assert live.answer() == 40

    editor = CodeSectionEditor()
    editor.set_source(
        path="/virtual/probe.py",
        source_text="class Probe(QWidget):\n    def answer(self):\n        return 40\n",
        source_start=3,
        config_text=None,
        module_vars=module.__dict__,
        target_class=module.Probe,
        target_instance=live,
    )
    # edit the class: append a new method + change the existing one
    editor._preview_btn.click()  # open the panel to read Apply feedback
    editor._view.enter_edit_mode()
    canvas = editor._view.editor()
    canvas._cursor = (3, 0)  # after the existing `return 40` line
    canvas.insert_text("    def patched(self):\n        return 'patched-ok'\n")
    assert str(getattr(editor._apply_btn, "_text", "")) == "Apply"
    editor._apply_btn.click()

    # the LIVE instance changed in place (same object, new behavior)
    assert live is editor._target_instance
    assert live.answer() == 40  # untouched method
    assert live.patched() == "patched-ok"
    # the button label never flips; the panel shows the apply feedback
    assert str(getattr(editor._apply_btn, "_text", "")) == "Apply"
    assert "Apply OK" in editor._preview_caption.text()
    assert "patched" in editor._preview_debug.text()
    assert editor._preview_error.isHidden()  # success -> no error label

    # Revert restores the original class
    editor._revert()
    assert not hasattr(live, "patched")
