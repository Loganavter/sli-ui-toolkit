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


def _is_toolkit_source(path: str | None, widget: QWidget | None = None) -> bool:
    """Whether ``path`` (or the widget's module) lives inside the toolkit
    package — its source must not be exposed as an editable file in the
    inspector (the inspector should show app-side configuration instead)."""
    if widget is not None:
        try:
            mod = type(widget).__module__ or ""
            if mod == "sli_ui_toolkit" or mod.startswith("sli_ui_toolkit."):
                return True
        except Exception:
            pass
    if not path:
        return False
    try:
        import sli_ui_toolkit
        from pathlib import Path

        pkg = Path(sli_ui_toolkit.__file__).resolve().parent
        target = Path(path).resolve()
        try:
            return target.is_relative_to(pkg)  # Python 3.9+
        except AttributeError:
            t = str(target)
            p = str(pkg)
            return t == p or t.startswith(p + "/")
    except Exception:
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
    config = owner._current.config if owner._current is not None else ()
    config_text = (
        _config_snippet(type(widget).__name__, config) if config else None
    )
    # Enrich Button-like configs: the visible text lives in regions/rows,
    # not in ``text``/``rows`` — without it GallerySeriesHeader shows
    # ``Button(text='', rows=[])`` which is not informative.
    config_text = _maybe_add_region_info(config_text, widget, owner._current)
    qss_text = _qss_snippet(getattr(owner, "_qss_rows", None))
    if _is_toolkit_source(source, widget):
        _build_toolkit_config_only(owner, page, config_text, qss_text)
        return None
    owner._add_title(page, "Code")

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


def _find_app_ancestor(widget: QWidget | None) -> QWidget | None:
    """Nearest *meaningful* app parent for a toolkit primitive.

    The old version returned the immediate ``parentWidget()`` even when
    it was a plain ``QWidget`` container (``GallerySeriesHeader_…`` is a
    generic ``QWidget``) or a generic host (``OpaqueFillHost``).  For
    ``GallerySeriesHeader_ungrouped_btn`` that made ``Show parent code``
    jump to the top-level window instead of ``GalleryGridView``.
    """
    if widget is None:
        return None
    import inspect as _inspect

    obj_name = ""
    try:
        obj_name = widget.objectName() or ""
    except Exception:
        pass

    candidates: list[QWidget] = []
    cur = widget.parentWidget()
    while cur is not None:
        try:
            t = type(cur)
            mod = t.__module__ or ""
            is_toolkit = mod == "sli_ui_toolkit" or mod.startswith("sli_ui_toolkit.")
            is_qt = mod.startswith("PySide6.") or mod.startswith("PyQt")
            if is_toolkit or is_qt:
                cur = cur.parentWidget()
                continue
            # Generic ``QWidget`` containers (GallerySeriesHeader_… is a
            # plain QWidget) have no app source — skip them.
            if t is QWidget:
                cur = cur.parentWidget()
                continue
            src = _inspect.getsourcefile(t)
            if src is None or _is_toolkit_source(src, cur):
                cur = cur.parentWidget()
                continue
            # Prefer the ancestor whose file actually defines the button's
            # objectName (grid_view.py contains GallerySeriesHeader_…).
            if obj_name:
                try:
                    txt = open(src, encoding="utf-8", errors="ignore").read()
                    if obj_name in txt:
                        return cur
                except Exception:
                    pass
            candidates.append(cur)
        except Exception:
            pass
        cur = cur.parentWidget()

    # No objectName match — prefer the closest app view whose file
    # actually creates buttons (grid_view.py does, shelf.py/host does not).
    for cand in candidates:
        try:
            if cand.isWindow():
                continue
            src = _inspect.getsourcefile(type(cand))
            if src:
                try:
                    txt = open(src, encoding="utf-8", errors="ignore").read()
                    if "Button(" in txt or "ButtonRegion" in txt:
                        return cand
                except Exception:
                    pass
        except Exception:
            pass
    for cand in candidates:
        try:
            if cand.isWindow():
                continue
        except Exception:
            pass
        return cand
    return candidates[0] if candidates else None


def _maybe_add_region_info(config_text: str | None, widget, inspection) -> str | None:
    """Append region display text to the synthetic snippet.

    For ``Button`` with ``regions=[ButtonRegion(rows=[ButtonRow(...)])]``
    the ``text``/``rows`` config is empty — the real visible string lives
    in ``InspectRegion.rows[].text``. Without it the Code tab shows
    ``Button(text='', rows=[])`` for e.g. ``GallerySeriesHeader_ungrouped_btn``.
    """
    try:
        regions = getattr(inspection, "regions", None) if inspection else None
        if not regions:
            return config_text
        row_texts: list[str] = []
        for reg in regions:
            for row in getattr(reg, "rows", ()) or ():
                txt = getattr(row, "text", None)
                if isinstance(txt, str) and txt.strip():
                    row_texts.append(txt.strip())
        if not row_texts:
            return config_text
        display_comment = "display: " + " | ".join(repr(t) for t in row_texts)
        if config_text:
            stripped = config_text.rstrip()
            if stripped.endswith(")"):
                inner = stripped[:-1].rstrip()
                return inner + f"\n    # {display_comment}\n)"
            return config_text + f"\n# {display_comment}"
        return f"# {display_comment}"
    except Exception:
        return config_text


def _build_toolkit_config_only(owner, page, config_text: str | None, qss_text: str | None) -> None:
    """Toolkit widgets: show live configuration (app-side values) plus an
    editable parent-file editor.

    The toolkit's own class source is never exposed as editable (patching
    the installed package). Instead the page shows:

    * the synthetic ``QSS + Button(...)`` snippet for the *selected*
      toolkit primitive — editable, ``Apply`` writes the snippet's kwargs
      onto the live instance (``apply_config_to_instance``);
    * a ``Show parent code`` button that jumps to the nearest app-side
      ancestor (found via ``_find_app_ancestor``) — its file *is* editable
      and ``Save`` works there.

    This restores editing for the ``only config`` case and makes the
    parent location discoverable even though the Constructor tree already
    shows the hierarchy."""
    from PySide6.QtWidgets import QHBoxLayout, QWidget

    from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label
    from sli_ui_toolkit.ui.widgets.buttons.button import Button as _Btn
    from sli_ui_toolkit.ui.inspector.code.editor import CodeSectionEditor

    owner._add_title(page, "Code")
    info = Label(
        "Source is inside sli-ui-toolkit — showing live configuration "
        "(see Config / State sections for the full field list).",
        pixel_size=11,
        word_wrap=True,
        selectable=True,
    )
    page.content_layout.addWidget(info)
    if owner._current is not None and owner._current.docs:
        docs_btn = _Btn(text="Docs", variant="surface", size=(0, 26))
        docs_btn.setToolTip("Open the widget family's documentation section")
        docs_btn.clicked.connect(lambda: owner.show_section("Docs"))
        page.content_layout.addWidget(docs_btn)

    # Parent jump row — makes the app-side file discoverable.
    widget = getattr(owner, "widget", None)
    ancestor = _find_app_ancestor(widget)
    if ancestor is not None:
        import inspect as _inspect

        try:
            src = _inspect.getsourcefile(type(ancestor)) or ""
            line = _inspect.getsourcelines(type(ancestor))[1] if src else 0
            src_label = f"{src}:{line}" if src else type(ancestor).__name__
        except Exception:
            src_label = type(ancestor).__name__
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(Label(f"Parent: {type(ancestor).__name__}", pixel_size=11, bold=True, selectable=True))
        lay.addWidget(Label(src_label, pixel_size=11, elide=True, selectable=True))
        jump = _Btn(text="Show parent code", variant="surface", size=(0, 26))
        jump.setToolTip("Inspect the app-side parent that owns this toolkit widget")
        # capture ancestor via default arg (avoid late binding)
        jump.clicked.connect(lambda _c=False, anc=ancestor: owner.widget_activated.emit(anc))
        lay.addWidget(jump)
        lay.addStretch(1)
        page.content_layout.addWidget(row)
    else:
        # No app ancestor — hint where to find hierarchy.
        page.content_layout.addWidget(
            Label(
                "No app-side parent found — see Layout / Constructor tabs for the containing tree.",
                pixel_size=11,
                selectable=True,
                word_wrap=True,
            )
        )

    # Editable synthetic config for the *selected* toolkit widget.
    # Reuse CodeSectionEditor so the snippet is selectable, editable
    # and ``Apply`` works (writes kwargs onto the live primitive).
    # The editor's file part is empty / non-toolkit — ``Save`` is a
    # no-op for the primitive itself; the parent's file is edited after
    # the jump button above.
    if config_text or qss_text:
        import sys as _sys

        selected = widget
        # No toolkit file is exposed — the editor shows only the synthetic
        # config (now enriched with region display text).
        placeholder_src = ""
        module = _sys.modules.get(type(selected).__module__) if selected is not None else None
        editor = CodeSectionEditor()
        editor.set_source(
            path=None,
            source_text=placeholder_src,
            source_start=1,
            config_text=config_text,
            qss_text=qss_text,
            module_vars=vars(module) if module is not None else None,
            target_class=type(selected) if selected is not None else None,
            target_instance=selected,
        )
        # The placeholder source is not app code — never treat class
        # edits as dirty and never enable Save (path is None anyway).
        # Config snippet remains editable and Apply stays enabled.
        try:
            editor.is_dirty = lambda: False  # type: ignore[method-assign]
        except Exception:
            pass

        def _toolkit_on_changed() -> None:
            snippet_dirty = editor.snippet_dirty()
            try:
                editor._save_btn.setEnabled(False)
                editor._apply_btn.setEnabled(snippet_dirty)
            except Exception:
                pass
            # keep preview in sync when the snippet changes
            try:
                from sli_ui_toolkit.ui.inspector.code.preview import schedule_rebuild

                schedule_rebuild(editor)
            except Exception:
                pass

        try:
            editor._on_changed = _toolkit_on_changed  # type: ignore[method-assign]
            editor._on_changed()
        except Exception:
            try:
                editor._save_btn.setEnabled(False)
            except Exception:
                pass
        page.content_layout.addWidget(editor, 1)
        # Keep the editor alive under the same attribute the view expects,
        # so ``_code_view`` / ``is_dirty`` / ``snippet_dirty`` keep working.
        owner._code_section = editor
        return None

    page.content_layout.addWidget(
        Label(
            "No synthetic configuration to show for this widget.",
            pixel_size=11,
            selectable=True,
        )
    )
    page.content_layout.addStretch(1)
    owner._code_section = None
    return None


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
