"""Inspector-pane integration/wiring for the Code section: constructing the
``CodeSectionEditor``, wiring the Docs button, QSS-rule string formatting,
and clamping the editor to the page height. Split out of ``editor.py`` to
keep that module scoped to the editor widget's own construction and
document model, mirroring the thin-owner split already used for
``apply.py``/``preview.py``/``config.py``.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.inspector.code.editor import CodeSectionEditor
from sli_ui_toolkit.ui.widgets.buttons.button import Button


class _CodeEditorClamp(QObject):
    """Keep the Code editor's maximum height in lockstep with its page, so
    the code + preview panel always fit the window: the TextView (a scroll
    area) absorbs the leftover height and scrolls internally instead of
    the page growing into a long fixed strip."""

    def __init__(self, editor: CodeSectionEditor, page):
        super().__init__(editor)
        self._editor = editor
        self._page = page

    def _apply(self) -> None:
        self._editor.setMaximumHeight(max(160, self._page.height()))

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self._page and event.type() == QEvent.Type.Resize:
            self._apply()
        return False


def build_code_section(owner, widget: QWidget | None) -> CodeSectionEditor | None:
    """Construct + wire the Code section editor into the owner pane's Code
    page (thin-owner split: the pane's ``_render_code`` delegates here).
    Returns the editor, or ``None`` when the widget has no source file."""
    from sli_ui_toolkit.ui.inspector.fields import _config_snippet

    page = owner.pages["Code"]
    owner._clear(page)
    if widget is None:
        return None
    import inspect as _inspect
    import sys

    try:
        source = _inspect.getsourcefile(type(widget))
        source_lines, source_start = _inspect.getsourcelines(type(widget))
    except (OSError, TypeError):
        return None
    owner._add_title(page, "Code")
    config = owner._current.config if owner._current is not None else ()
    config_text = (
        _config_snippet(type(widget).__name__, config) if config else None
    )
    qss_text = _qss_snippet(getattr(owner, "_qss_rows", None))

    editor = CodeSectionEditor()
    docs_ref = (
        owner._current.docs if owner._current is not None else ""
    )
    if docs_ref:
        docs_btn = Button(
            text="Docs",
            variant="surface",
            size=(0, 26),
        )
        docs_btn.setToolTip(
            "Open the widget family's documentation section"
        )
        docs_btn.clicked.connect(lambda: owner.show_section("Docs"))
        editor.add_top_action(docs_btn)
    module = sys.modules.get(type(widget).__module__)
    editor.set_source(
        path=source,
        source_text="".join(source_lines),
        source_start=source_start,
        config_text=config_text,
        qss_text=qss_text,
        module_vars=vars(module) if module is not None else None,
        target_class=type(widget),
        target_instance=widget,
    )
    # The editor fills the page (stretch 1; no trailing spacer): the
    # TextView inside expands and scrolls internally. The clamp below caps
    # it at the page height, so the whole editor flexes with the window.
    page.content_layout.addWidget(editor, 1)
    # clamp the editor to the page height (the TextView scrolls
    # internally) so the preview panel never pushes the page into a
    # long fixed-height strip
    clamp = _CodeEditorClamp(editor, page)
    editor._editor_clamp = clamp  # type: ignore[attr-defined]  # keep alive
    page.installEventFilter(clamp)
    clamp._apply()
    owner._code_section = editor
    return editor


def _qss_snippet(qss_rows) -> str | None:
    """Assemble the candidate QSS rules into a code block (selector + body
    + closing brace per rule), rendered in the editor above the config
    snippet — synthetic, like the config: never written back to a file."""
    if not qss_rows:
        return None
    parts: list[str] = []
    for rule, _dead in qss_rows:
        selector = rule.selector.strip()
        if not selector:
            continue
        if not selector.endswith("{"):
            selector += " {"
        parts.append(selector)
        body = rule.body.strip()
        if body:
            for line in body.split("\n"):
                parts.append("    " + line)
        parts.append("}")
    return "\n".join(parts) if parts else None
