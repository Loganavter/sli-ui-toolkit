"""Inspector-pane integration/wiring for the Code section: constructing the
``CodeSectionEditor``, wiring the Docs button, QSS-rule string formatting,
and clamping the editor to the page height. Split out of ``editor.py`` to
keep that module scoped to the editor widget's own construction and
document model, mirroring the thin-owner split already used for
``apply.py``/``preview.py``/``config.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

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
        source = None
        source_lines = None
        source_start = 1
    # Plain QWidget containers (e.g. gallery_toolbar_view_switch_container) are
    # created as ``QWidget`` in app code — ``type(widget) is QWidget`` has no
    # app file, so fall back to the nearest app ancestor that defines its
    # objectName (toolbar.py). Without this the Code tab stays empty.
    use_creation_site = False
    site_ancestor: QWidget | None = None
    try:
        is_plain = False
        try:
            # Bare QWidget containers (e.g. ScrollableDialogPage.content_widget)
            # are plain QWidget instances with no app file. Previously this
            # required a truthy objectName, so anonymous layout containers
            # like the Settings page content widget (QWidget, no name, 978x819)
            # never fell back to the owning app ancestor and the Code tab stayed
            # empty. Treat any exact QWidget as plain when its type has no
            # app source — the objectName helps _find_app_ancestor pick the
            # right file when present, but is not required for the fallback.
            is_plain = type(widget) is QWidget
        except Exception:
            pass
        if is_plain and (source is None or _is_toolkit_source(source, widget) is False):
            # Own type is Qt's QWidget — not app code. Check if its module is Qt.
            mod = getattr(type(widget), "__module__", "") or ""
            is_qt = mod.startswith("PySide6") or mod.startswith("PyQt")
            if is_qt or source is None:
                anc = _find_app_ancestor(widget)
                if anc is not None:
                    # Prefer the widget's OWN creation site — the enclosing
                    # function of the line that creates/configures it (matched
                    # by objectName or attribute reference). Without this the
                    # whole ancestor class (the entire SettingsDialog) would be
                    # shown for one anonymous container QWidget.
                    site = _creation_site_region(widget, anc)
                    if site is not None:
                        site_src, site_lines, site_start = site
                        if not _is_toolkit_source(site_src, anc):
                            source = site_src
                            source_lines = site_lines
                            source_start = site_start
                            use_creation_site = True
                            site_ancestor = anc
                    if not use_creation_site:
                        try:
                            anc_src = _inspect.getsourcefile(type(anc))
                            if anc_src and not _is_toolkit_source(anc_src, anc):
                                anc_lines, anc_start = _inspect.getsourcelines(type(anc))
                                source = anc_src
                                source_lines = anc_lines
                                source_start = anc_start
                        except (OSError, TypeError):
                            pass
    except Exception:
        pass
    if source is None or source_lines is None:
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
    # For a creation-site region (a function, not a class) Apply cannot
    # hot-patch anything — target_class=None makes the editor keep Apply
    # disabled; module_vars come from the ancestor's module so the
    # preview/apply error paths see the real app namespace.
    if use_creation_site and site_ancestor is not None:
        module = sys.modules.get(type(site_ancestor).__module__)
        target_class = None
    else:
        module = sys.modules.get(type(widget).__module__)
        target_class = type(widget)
    editor.set_source(
        path=source,
        source_text="".join(source_lines),
        source_start=source_start,
        config_text=config_text,
        qss_text=qss_text,
        module_vars=vars(module) if module is not None else None,
        target_class=target_class,
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


def _creation_markers(widget: QWidget, ancestor: QWidget) -> list[tuple[str, str]]:
    """Names that identify ``widget`` in source code, for locating its
    creation site inside an app file.

    Two kinds, in priority order:
    - ``("object_name", name)`` — a Qt objectName; app code usually
      assigns it right at the creation site (``setObjectName(...)``);
    - ``("attr", name)`` — an instance attribute on any widget in the
      parent chain that points at the selected widget itself
      (``page.content_widget`` — a ``vars()`` identity match), which
      lets anonymous containers be located even without an objectName.
    """
    markers: list[tuple[str, str]] = []
    try:
        obj_name = widget.objectName()
        if obj_name:
            markers.append(("object_name", obj_name))
    except Exception:
        pass
    node: QWidget | None = widget
    while node is not None:
        try:
            for name, value in vars(node).items():
                if value is widget:
                    markers.append(("attr", name))
        except Exception:
            pass
        if node is ancestor:
            break
        node = node.parentWidget()
    return markers


def _line_references(line: str, marker: tuple[str, str]) -> bool:
    """Whether a source line references the creation marker (objectName
    assignment, or an attribute access/assignment/call on the name)."""
    kind, name = marker
    if kind == "object_name":
        # the Qt method is ``setObjectName`` (capital O)
        if "ObjectName" not in line:
            return False
        return f'"{name}"' in line or f"'{name}'" in line
    return bool(
        re.search(
            rf"\.{re.escape(name)}\b|{re.escape(name)}\s*=|{re.escape(name)}\(",
            line,
        )
    )


def _enclosing_def(full: list[str], idx: int) -> int | None:
    """Index of the ``def``/``async def`` line enclosing the marker line
    ``idx`` — the nearest function start above it with strictly shallower
    indentation. ``None`` when the marker sits outside any function
    (class/module level) — then the caller keeps the whole-class fallback.
    """
    marker_indent = len(full[idx]) - len(full[idx].lstrip())
    for i in range(idx, -1, -1):
        line = full[i]
        if not line.strip() or not line.lstrip().startswith(("def ", "async def ")):
            continue
        if (len(line) - len(line.lstrip())) < marker_indent:
            return i
    return None


def _candidate_files(ancestor: QWidget) -> list[str]:
    """App-side source files worth searching for the widget's creation
    site: the ancestor's own file, plus the files of the app-side
    functions/classes its module imports (the settings pattern creates
    pages in imported builder modules, e.g. ``create_scrollable_page``).
    Toolkit files are never candidates — their source stays hidden."""
    import inspect as _inspect
    import sys

    files: list[str] = []
    try:
        src = _inspect.getsourcefile(type(ancestor))
        if src and not _is_toolkit_source(src, ancestor):
            files.append(src)
    except (OSError, TypeError):
        pass
    module = sys.modules.get(type(ancestor).__module__)
    if module is not None:
        for value in vars(module).values():
            if not (_inspect.isfunction(value) or _inspect.isclass(value)):
                continue
            try:
                f = _inspect.getsourcefile(value)
            except (OSError, TypeError):
                continue
            if f and not _is_toolkit_source(f) and f not in files:
                files.append(f)
    return files


def _creation_site_region(
    widget: QWidget, ancestor: QWidget
) -> tuple[str, list[str], int] | None:
    """The slice of app source that CREATES ``widget`` — the enclosing
    function of the first creation-marker hit — as ``(file, lines,
    start_line)``.

    Without this the fallback would show the whole ancestor class (e.g.
    the entire SettingsDialog) for one anonymous container QWidget. The
    markers (objectName / attribute identity) are matched against the
    ancestor's file and the files its module imports; the first hit wins.
    Returns ``None`` when nothing matches (e.g. the widget is built purely
    by toolkit code and app code only holds a local reference) — the
    caller then falls back to the whole ancestor class."""
    hits: list[tuple[str, int]] = []
    for candidate in _candidate_files(ancestor):
        try:
            full = Path(candidate).read_text(encoding="utf-8").split("\n")
        except OSError:
            continue
        for marker in _creation_markers(widget, ancestor):
            for i, line in enumerate(full):
                if not _line_references(line, marker):
                    continue
                if line.lstrip().startswith(("def ", "async def ", "class ")):
                    # a marker hit on a def/class line itself (e.g. the
                    # ``content(`` pattern matching ``def create_content``)
                    # is not a creation reference — keep looking
                    continue
                hits.append((candidate, i))
                break
    for candidate, idx in hits:
        try:
            full = Path(candidate).read_text(encoding="utf-8").split("\n")
        except OSError:
            continue
        lo = _enclosing_def(full, idx)
        if lo is None:
            continue
        indent = len(full[lo]) - len(full[lo].lstrip())
        hi = len(full)
        for i in range(lo + 1, len(full)):
            line = full[i]
            if not line.strip():
                continue
            if (len(line) - len(line.lstrip())) <= indent and line.lstrip().startswith(
                ("def ", "async def ", "class ", "@")
            ):
                hi = i
                break
        return candidate, full[lo:hi], lo + 1
    return None


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
