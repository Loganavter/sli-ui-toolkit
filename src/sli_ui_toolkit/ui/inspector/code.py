"""Code section of the inspector — one unified, collapsible editor widget.

Instead of separate config/class fields, ``CodeSectionEditor`` shows ONE
text view: the live-config snippet, the widget's class source, and — when
the source file has other code around the class — the rest of the file.
Code that is not currently interesting is collapsed into a single gap row
(``·····``, VS Code-style boundary numbers in the gutter); clicking the
row expands that region inline. The **Full/Compact** toggle button
(top-left, session-picker style) expands everything at once and flips its
own label. **Preview** compiles the edited class and constructs a live
instance (with the current config as constructor kwargs) in a preview
panel that re-builds on every edit, so the effect of a change can be seen
before saving — or reverted. Save reconstructs the whole file with the
edited class region.

The surface is styled like the app's recent-projects shelf: a rounded
"well" fill behind the text and a ``variant="default"`` toggle button.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label
from sli_ui_toolkit.ui.widgets.buttons.button import Button
from sli_ui_toolkit.ui.widgets.composite.text_view import TextView

#: names available when evaluating the config snippet's literal values
#: (enum members render as ``Type.MEMBER`` in the snippet)
_PREVIEW_NAMESPACE = {
    "Qt": Qt,
    "AlignmentFlag": Qt.AlignmentFlag,
    "QColor": QColor,
    "QSize": QSize,
    "QRect": QRect,
    "QRectF": QRectF,
    "QIcon": QIcon,
    "QFont": QFont,
    "QBrush": QBrush,
    "QPen": QPen,
    "QPixmap": QPixmap,
}

_SKIP = object()

#: class attributes not copied when hot-patching the live class
_CLASS_BOOKKEEPING = frozenset(
    {"__dict__", "__weakref__", "__module__", "__qualname__", "__slots__"}
)

#: Collapsed gap row — plain ellipsis; the hidden block's boundary line
#: numbers live in the gutter (VS Code-style: "12" then immediately "17").
_MARKER_TEXT = "·····"
_MARKER_RE = re.compile(r"^·····$")


def _panel_color(theme_manager) -> QColor:
    """The recent-projects shelf well: Window, slightly darker (light) or
    lighter (dark) so the surface reads as a raised panel."""
    base = QColor(theme_manager.get_color("Window"))
    base.setAlpha(255)
    if base.lightness() > 140:
        return base.darker(106)
    return base.lighter(118)


class _PanelWell(QWidget):
    """Rounded shelf-well container (the preview host): opaque fill clipped
    to the corner radius, re-applied on resize."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fill = QColor(255, 255, 255)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def set_fill_color(self, color: QColor) -> None:
        self._fill = QColor(color)
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 8, 8)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(event.rect(), self._fill)
        painter.end()


def _preview_init_signature(cls) -> "inspect.Signature | None":
    """Constructor signature for the preview's best-effort fill.

    Walks the MRO like the inspector's own extractor: a subclass whose
    ``__init__`` forwards ``*args, **kwargs`` would otherwise hide the real
    required parameters (e.g. AdaptiveTabStrip's ``add_icon``) from the
    auto-fill, and the preview would fail to construct."""

    for klass in cls.__mro__:
        try:
            sig = inspect.signature(klass.__init__)  # type: ignore[misc]
        except (TypeError, ValueError):
            continue
        usable = [
            param
            for name, param in sig.parameters.items()
            if name != "self"
            and param.kind
            not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
        ]
        if usable:
            return sig
    return None


def _class_name_from_region(region: list[str]) -> str | None:
    """The class name declared by the first ``class X`` line of the region."""
    for line in region:
        match = re.match(r"\s*class\s+(\w+)", line)
        if match:
            return match.group(1)
    return None


def _config_kwargs(
    config_text: str | None, namespace: dict | None = None
) -> tuple[dict, list[str]]:
    """Constructor kwargs + the list of skipped values from the config
    snippet (``({}, [])`` when there is no snippet). Values that cannot be
    reconstructed (REF placeholders, unknown names) are skipped — the
    preview is best-effort; the skipped names are reported in the debug
    output. ``namespace`` (the widget module's vars) resolves module-level
    names like ``CloseButtonPolicy.ALL_WHEN_FIT_ELSE_CURRENT``."""

    if not config_text:
        return {}, []
    try:
        tree = ast.parse(config_text)
        first = tree.body[0]
        if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Call):
            return {}, []
        call = first.value
    except (SyntaxError, IndexError, AttributeError):
        return {}, []

    lookup = dict(_PREVIEW_NAMESPACE)
    if namespace:
        lookup.update(namespace)

    def resolve(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.Tuple, ast.List)):
            items = [resolve(item) for item in node.elts]
            if any(item is _SKIP for item in items):
                return _SKIP
            return tuple(items) if isinstance(node, ast.Tuple) else items
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = resolve(node.operand)
            if value is _SKIP:
                return _SKIP
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.Attribute):
            parts = []
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                parts.append(node.id)
                obj = lookup.get(node.id, _SKIP)
                if obj is _SKIP:
                    return _SKIP
                for part in reversed(parts[:-1]):
                    try:
                        obj = getattr(obj, part)
                    except AttributeError:
                        return _SKIP
                return obj
            return _SKIP
        return _SKIP

    kwargs = {}
    skipped: list[str] = []
    for keyword in call.keywords:
        if keyword.arg is None:
            continue
        value = resolve(keyword.value)
        if value is not _SKIP:
            kwargs[keyword.arg] = value
        else:
            skipped.append(keyword.arg)
    return kwargs, skipped


class CodeSectionEditor(QWidget):
    """Unified class-source editor with collapsible file context.

    ``set_source`` loads a fresh inspection: the widget class source
    (gutter numbered from the actual file lines) plus the live-config
    snippet on top; any other code in the source file (before the class or
    after it) is collapsed into clickable gap rows. The Full/Compact button
    expands/collapses all gaps. Save writes the whole file back with the
    edited class region.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: str | None = None
        self._config_text: str | None = None
        self._source_lines: list[str] = []
        self._source_start = 1
        self._file_before: list[str] = []
        self._file_after: list[str] = []
        self._expanded: set[str] = set()
        #: display-line counts of the config block and the two gaps — the
        #: structural anchors used to locate the class region on save.
        self._config_display_lines = 0
        self._gap_a_display_lines = 0
        self._gap_b_display_lines = 0
        self._module_vars: dict | None = None
        self._preview_widget: QWidget | None = None
        self._preview_timer: QTimer | None = None
        self._target_class: type | None = None
        self._target_instance: QWidget | None = None
        self._applied = False
        self._patched_names: set[str] = set()
        self._original_class_dict: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._view = TextView("")
        self._view.changed.connect(self._on_changed)
        self._canvas = self._view.canvas()
        self._canvas.installEventFilter(self)
        root.addWidget(self._view)

        self._preview_panel = QWidget(self)
        self._preview_panel.setVisible(False)
        preview_layout = QVBoxLayout(self._preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(4)
        self._preview_caption = Label(
            "Preview (live) — rebuilt from the edited class on every change",
            pixel_size=11,
            color_token="dialog.text",
        )
        preview_layout.addWidget(self._preview_caption)
        self._preview_host = _PanelWell(self._preview_panel)
        self._preview_host.setMaximumHeight(260)
        self._preview_host.set_fill_color(_panel_color(ThemeManager.get_instance()))
        self._preview_host_layout = QVBoxLayout(self._preview_host)
        self._preview_host_layout.setContentsMargins(8, 8, 8, 8)
        self._preview_host_layout.setSpacing(0)
        preview_layout.addWidget(self._preview_host)
        self._preview_error = Label("", pixel_size=11, word_wrap=True)
        self._preview_error.setVisible(False)
        preview_layout.addWidget(self._preview_error)
        self._preview_debug = Label("", pixel_size=11, word_wrap=True)
        self._preview_debug.setVisible(False)
        preview_layout.addWidget(self._preview_debug)
        root.addWidget(self._preview_panel)

        self._toggle_btn = Button(
            text="Full",
            variant="default",
            size=(0, 26),
            corner_radius=8,
        )
        self._toggle_btn.setToolTip(
            "Expand/collapse all hidden code between the config and the class"
        )
        self._toggle_btn.clicked.connect(self._toggle_expansion)
        self._preview_btn = Button(
            text="Preview",
            variant="default",
            size=(0, 26),
            corner_radius=8,
        )
        self._preview_btn.setToolTip(
            "Compile the edited class and show a live instance built from it"
        )
        self._preview_btn.clicked.connect(self._toggle_preview)
        self._apply_btn = Button(
            text="Apply",
            variant="default",
            size=(0, 26),
            corner_radius=8,
        )
        self._apply_btn.setToolTip(
            "Hot-patch the LIVE widget class in place (the real widget "
            "updates; all instances of this class are affected). Revert "
            "restores the original class"
        )
        self._apply_btn.clicked.connect(self._apply_to_live)
        self._edit_btn = Button(text="Edit", variant="surface", size=(0, 26))
        self._edit_btn.setToolTip("Toggle editing of this widget's source file")
        self._edit_btn.clicked.connect(self._toggle_editing)
        self._revert_btn = Button(text="Revert", variant="surface", size=(0, 26))
        self._revert_btn.setToolTip("Discard edits, restore the loaded source")
        self._revert_btn.clicked.connect(self._revert)
        self._save_btn = Button(text="Save", variant="surface", size=(0, 26))
        self._save_btn.setToolTip("Write the edited class source back to the file")
        self._save_btn.clicked.connect(self._save)
        self._save_btn.setEnabled(False)

        buttons_row = QWidget()
        buttons = QHBoxLayout(buttons_row)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(6)
        buttons.addWidget(self._toggle_btn)
        buttons.addWidget(self._apply_btn)
        buttons.addWidget(self._preview_btn)
        buttons.addWidget(self._edit_btn)
        buttons.addWidget(self._revert_btn)
        buttons.addWidget(self._save_btn)
        buttons.addStretch(1)
        root.addWidget(buttons_row)

        self._view.set_panel_fill(_panel_color(ThemeManager.get_instance()))
        try:
            ThemeManager.get_instance().theme_changed.connect(
                self._on_theme_changed
            )
        except Exception:
            pass

    def _on_theme_changed(self, *_args) -> None:
        """Re-tint the code well after a theme switch. Bound method, so the
        connection dies with the editor (a lambda would survive the widget
        and raise on the deleted C++ view)."""
        try:
            color = _panel_color(ThemeManager.get_instance())
            self._view.set_panel_fill(color)
            self._preview_host.set_fill_color(color)
        except RuntimeError:
            pass

    # -- public surface -----------------------------------------------------

    def set_source(
        self,
        *,
        path: str | None,
        source_text: str,
        source_start: int,
        config_text: str | None,
        module_vars: dict | None = None,
        target_class: type | None = None,
        target_instance: QWidget | None = None,
    ) -> None:
        """Load a new inspection: class source + config snippet + the
        surrounding file code (collapsed into gap rows). ``module_vars`` is
        the widget module's namespace — the Preview compiles the edited
        class against it (base classes, imports). ``target_class`` /
        ``target_instance`` are the LIVE widget's class and instance —
        Apply hot-patches the class so the real widget changes in place
        (the snapshot below is what Revert restores)."""
        self._path = path
        self._config_text = config_text
        self._module_vars = dict(module_vars) if module_vars else None
        self._target_class = target_class
        self._target_instance = target_instance
        self._applied = False
        self._patched_names = set()
        self._original_class_dict = {}
        if target_class is not None:
            self._original_class_dict = {
                name: value
                for name, value in vars(target_class).items()
                if name not in _CLASS_BOOKKEEPING
            }
        self._source_lines = source_text.split("\n")
        self._source_start = max(1, int(source_start))
        self._file_before = []
        self._file_after = []
        if path:
            try:
                full = Path(path).read_text(encoding="utf-8").split("\n")
            except OSError:
                full = []
            if full:
                lo = self._source_start - 1
                hi = lo + len(self._source_lines)
                self._file_before = full[:lo] if lo > 0 else []
                self._file_after = full[hi:] if hi < len(full) else []
        self._expanded = set()
        self._rebuild()
        self._update_toggle_visibility()
        self._edit_btn.setText("Edit")
        self._save_btn.setEnabled(False)
        self._view.exit_edit_mode()
        self._close_preview()

    # -- editing state (for the inspector tests / app hooks) ----------------

    @property
    def view(self) -> TextView:
        """The unified code TextView."""
        return self._view

    @property
    def config_view(self) -> None:
        """Compatibility: the config snippet now lives in the unified view."""
        return None

    def is_dirty(self) -> bool:
        return self._class_region() != self._source_lines

    # -- apply to the live widget (hot class patch) --------------------------

    def _apply_to_live(self) -> None:
        """Hot-patch the REAL widget class: the edited class region's
        methods/attributes are copied onto ``target_class``, so the widget
        changes in place (same instance, wiring intact). Revert restores
        the snapshot taken at ``set_source``."""
        if self._target_class is None:
            self._show_preview_error("Apply failed: the live widget class is not available")
            return
        if self._view.is_editing():
            self._view.exit_edit_mode()
        region = self._class_region()
        text = "\n".join(region)
        namespace = dict(self._module_vars or {})
        namespace["__name__"] = "imgsli_inspector_preview"
        try:
            exec(compile(text, self._path or "<apply>", "exec"), namespace)  # noqa: S102
        except Exception as exc:
            self._fail_with_debug(
                f"Apply failed (compile): {type(exc).__name__}: {exc}", text
            )
            return
        class_name = _class_name_from_region(region)
        new_class = namespace.get(class_name or "", None) if class_name else None
        if new_class is None or not isinstance(new_class, type):
            self._fail_with_debug(
                f"Apply failed: class {class_name!r} not found in the compiled "
                f"source\ncompiled region:\n{text}",
                text,
            )
            return
        patched: list[str] = []
        try:
            for name, value in vars(new_class).items():
                if name in _CLASS_BOOKKEEPING:
                    continue
                setattr(self._target_class, name, value)
                self._patched_names.add(name)
                patched.append(name)
        except Exception as exc:
            self._fail_with_debug(
                f"Apply failed (patch): {type(exc).__name__}: {exc}", text
            )
            return
        self._applied = True
        if self._target_instance is not None:
            try:
                self._target_instance.update()
                self._target_instance.repaint()
            except RuntimeError:
                pass
        kwargs, skipped = _config_kwargs(self._config_text, self._module_vars)
        self._set_preview_debug(
            f"patched onto {self._target_class.__name__}: "
            f"{', '.join(patched) or '(no members)'}\n"
            f"kwargs used: {kwargs}\n"
            f"skipped: {', '.join(skipped) or 'none'}"
        )
        self._show_preview_status(
            f"Apply OK — patched {len(patched)} member(s) onto "
            f"{self._target_class.__name__}; the widget was repainted"
        )

    def _fail_with_debug(self, message: str, text: str | None = None) -> None:
        """Error + the attempted region/state in the debug line."""
        debug = message
        if text is not None:
            debug += f"\ncompiled region:\n{text}"
        try:
            kwargs, skipped = _config_kwargs(self._config_text, self._module_vars)
            debug += (
                f"\nkwargs: {kwargs}"
                f"\nskipped: {', '.join(skipped) or 'none'}"
            )
        except Exception:
            pass
        self._set_preview_debug(debug)
        self._show_preview_error(message)

    def _revert_class_patch(self) -> None:
        """Restore the snapshot of the live class taken at ``set_source``."""
        target = self._target_class
        if target is None or not self._applied:
            return
        try:
            for name, value in self._original_class_dict.items():
                setattr(target, name, value)
            for name in list(self._patched_names):
                if name not in self._original_class_dict:
                    delattr(target, name)
        except Exception:
            pass
        self._patched_names.clear()
        self._applied = False
        if self._target_instance is not None:
            try:
                self._target_instance.update()
            except RuntimeError:
                pass
        self._show_preview_status(
            f"Reverted — {target.__name__} restored to the original class"
        )

    # -- preview ------------------------------------------------------------

    def _toggle_preview(self) -> None:
        if self._preview_panel.isVisible():
            self._close_preview()
        else:
            self._preview_panel.setVisible(True)
            self._preview_btn.setText("Hide preview")
            self._rebuild_preview()

    def _close_preview(self) -> None:
        self._preview_panel.setVisible(False)
        self._preview_btn.setText("Preview")
        self._clear_preview_host()
        if self._preview_timer is not None:
            self._preview_timer.stop()
            self._preview_timer = None

    def _clear_preview_host(self) -> None:
        self._preview_widget = None
        self._set_preview_debug("")
        while self._preview_host_layout.count():
            item = self._preview_host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._preview_error.setVisible(False)

    def _rebuild_preview(self) -> None:
        """Compile the edited class region and construct a live instance
        (current config values as kwargs) inside the preview host."""
        if self._preview_panel.isHidden():
            return
        self._clear_preview_host()
        region = self._class_region()
        text = "\n".join(region)
        try:
            compiled = compile(text, self._path or "<preview>", "exec")
        except (SyntaxError, ValueError) as exc:
            self._show_preview_error(f"Compile failed: {exc}")
            return
        namespace = dict(self._module_vars or {})
        namespace["__name__"] = "imgsli_inspector_preview"
        try:
            exec(compiled, namespace)  # noqa: S102 — diagnostic tool, dev-only
        except Exception as exc:
            self._show_preview_error(f"Compile failed: {exc}")
            return
        class_name = _class_name_from_region(region)
        cls = namespace.get(class_name or "", None) if class_name else None
        if cls is None or not isinstance(cls, type):
            self._show_preview_error(
                f"Class {class_name!r} not found after compiling the edited source"
            )
            return
        kwargs, skipped = _config_kwargs(self._config_text, self._module_vars)
        signature = _preview_init_signature(cls)
        parent_param = signature.parameters.get("parent") if signature else None
        if signature is not None:
            # Best-effort: the config snippet only carries values the widget
            # self-describes, so REQUIRED args it does not store as
            # attributes (e.g. AdaptiveTabStrip's add_icon) are missing —
            # fill them with None so the preview still builds.
            for name, param in signature.parameters.items():
                if name == "self" or name in kwargs:
                    continue
                if param.kind not in (
                    inspect.Parameter.KEYWORD_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                ):
                    continue
                if param.default is inspect.Parameter.empty:
                    kwargs[name] = None
        try:
            if parent_param is not None and parent_param.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
                preview = cls(parent=self._preview_host, **kwargs)
            else:
                try:
                    preview = cls(self._preview_host, **kwargs)
                except TypeError:
                    preview = cls(**kwargs)
        except Exception as exc:
            self._fail_with_debug(
                f"Construct failed: {type(exc).__name__}: {exc}", text
            )
            return
        self._preview_widget = preview
        self._preview_host_layout.addWidget(preview)
        self._preview_caption.setText(
            "Preview (live) — " + (class_name or "class") + " rebuilt from the edited class"
        )
        self._preview_error.setVisible(False)
        self._set_preview_debug(
            f"class={class_name} signature={signature}\n"
            f"kwargs={kwargs}\n"
            f"skipped={skipped or 'none'}"
        )

    def _show_preview_error(self, message: str) -> None:
        """Show an error — auto-opens the panel so a failed Apply/Preview is
        never silent (the user's "Apply does nothing" case)."""
        self._preview_panel.setVisible(True)
        self._preview_btn.setText("Hide preview")
        self._preview_error.setText(message)
        self._preview_error.setVisible(True)
        self._preview_caption.setText("Preview — build failed")

    def _show_preview_status(self, message: str) -> None:
        """Success feedback for Apply — auto-opens the panel."""
        self._preview_panel.setVisible(True)
        self._preview_btn.setText("Hide preview")
        self._preview_caption.setText(message)
        self._preview_error.setVisible(False)

    def _set_preview_debug(self, text: str) -> None:
        """Diagnostic detail for the last preview/apply operation."""
        self._preview_debug.setText(text)
        self._preview_debug.setVisible(bool(text))

    def _schedule_preview_rebuild(self) -> None:
        if self._preview_panel.isHidden():
            return
        if self._preview_timer is None:
            self._preview_timer = QTimer(self)
            self._preview_timer.setSingleShot(True)
            self._preview_timer.setInterval(300)
            self._preview_timer.timeout.connect(self._rebuild_preview)
        self._preview_timer.start()

    # -- collapse / expand --------------------------------------------------

    def _rebuild(self) -> None:
        """Compose the unified buffer: config + gap + class + gap."""
        lines: list[str] = []
        gutter: dict[int, str] = {}

        if self._config_text:
            for line in self._config_text.split("\n"):
                lines.append(line)
                # the snippet is synthetic — a dot, never a file line number
                # (otherwise the counter would restart at 1 below it)
                gutter[len(lines) - 1] = "·"
        self._config_display_lines = len(lines)

        if self._file_before:
            if "before" in self._expanded:
                for i, line in enumerate(self._file_before):
                    lines.append(line)
                    gutter[len(lines) - 1] = str(i + 1)
                self._gap_a_display_lines = len(self._file_before)
            else:
                lines.append(_MARKER_TEXT)
                # the hidden block's last line — the next visible row (the
                # class statement) shows its real number right after
                gutter[len(lines) - 1] = str(self._source_start - 1)
                self._gap_a_display_lines = 1
        else:
            self._gap_a_display_lines = 0

        for i, line in enumerate(self._source_lines):
            lines.append(line)
            gutter[len(lines) - 1] = str(self._source_start + i)

        if self._file_after:
            off = self._source_start + len(self._source_lines)
            last = off + len(self._file_after) - 1
            if "after" in self._expanded:
                for i, line in enumerate(self._file_after):
                    lines.append(line)
                    gutter[len(lines) - 1] = str(off + i)
                self._gap_b_display_lines = len(self._file_after)
            else:
                lines.append(_MARKER_TEXT)
                # the hidden block's last line (the file's end here)
                gutter[len(lines) - 1] = str(last)
                self._gap_b_display_lines = 1
        else:
            self._gap_b_display_lines = 0

        self._view.set_text("\n".join(lines))
        self._view.set_line_number_start(1)
        self._canvas.set_line_number_map(gutter)
        # collapsed gap rows carry a disclosure arrow in the gutter; folding
        # stays enabled (reserving the constant arrow offset) while any gap
        # can exist, so the text never shifts between states
        fold_lines = set()
        if self._gap_a_display_lines == 1:
            fold_lines.add(self._config_display_lines)
        if self._gap_b_display_lines == 1:
            fold_lines.add(len(lines) - 1)
        if self._file_before or self._file_after:
            self._canvas.set_fold_lines(fold_lines)
        else:
            self._canvas.set_fold_lines(None)
        self._on_changed()  # re-sync save state + live preview
        self._update_toggle_label()

    def _current_text(self) -> str:
        return "\n".join(
            (self._config_text.split("\n") if self._config_text else [])
            + self._file_before
            + self._source_lines
            + self._file_after
        )

    def _class_region(self) -> list[str]:
        """The class region of the LIVE buffer — what a save writes back.

        Starts after the config + collapsed/expanded before-gap and ends at
        the after-gap. The collapsed gap rows are located by their ellipsis
        text (not by index) so edits above the class that shift the rows
        cannot push a marker into the saved region."""
        current = self._view.text().split("\n")
        lo = self._config_display_lines + self._gap_a_display_lines
        hi = max(lo, len(current) - self._gap_b_display_lines)
        markers = [i for i, line in enumerate(current) if _MARKER_RE.match(line)]
        if markers:
            # the first ellipsis row is the before-gap, the last one the
            # after-gap (they coincide when only one gap exists)
            if self._file_before and (len(markers) >= 2 or not self._file_after):
                lo = max(lo, markers[0] + 1)
            if self._file_after and (len(markers) >= 2 or not self._file_before):
                hi = min(hi, markers[-1])
        return current[lo:hi]

    def _marker_at(self, line_index: int) -> str | None:
        """The gap id ("before"/"after") whose collapsed row sits at the
        display line, or ``None``. Reads the live buffer so edits that
        destroy a marker just stop matching."""
        lines = self._view.text().split("\n")
        if not (0 <= line_index < len(lines)):
            return None
        if _MARKER_RE.match(lines[line_index]) is None:
            return None
        markers = [i for i, line in enumerate(lines) if _MARKER_RE.match(line)]
        if not markers:
            return None
        first, last = markers[0], markers[-1]
        if self._file_before and line_index == first:
            return "before"
        if self._file_after and line_index == last and last != first:
            return "after"
        if self._file_after and not self._file_before and line_index == first:
            return "after"
        return None

    def _toggle_gap(self, gap: str) -> None:
        if gap in self._expanded:
            self._expanded.discard(gap)
        else:
            self._expanded.add(gap)
        self._rebuild()

    def _toggle_expansion(self) -> None:
        if self._all_expanded():
            self._expanded.clear()
        else:
            self._expanded = {"before", "after"}
        self._rebuild()

    def _all_expanded(self) -> bool:
        return ("before" in self._expanded or not self._file_before) and (
            "after" in self._expanded or not self._file_after
        )

    def _update_toggle_label(self) -> None:
        self._toggle_btn.setText("Compact" if self._all_expanded() else "Full")

    def _update_toggle_visibility(self) -> None:
        self._toggle_btn.setVisible(bool(self._file_before or self._file_after))

    # -- editing ------------------------------------------------------------

    def _on_changed(self) -> None:
        self._save_btn.setEnabled(self.is_dirty())
        self._schedule_preview_rebuild()

    def _toggle_editing(self) -> None:
        if not self._view.is_editing():
            self._view.enter_edit_mode()
            self._edit_btn.setText("Stop editing")
        else:
            self._view.exit_edit_mode()
            self._edit_btn.setText("Edit")
            self._on_changed()

    def _revert(self) -> None:
        self._view.exit_edit_mode()
        self._revert_class_patch()
        self._rebuild()
        self._edit_btn.setText("Edit")
        self._save_btn.setEnabled(False)

    def _save(self) -> None:
        if not self._path:
            return
        # The class region sits between the (config + gap-before) block and
        # the gap-after block; edits above/below it (markers, config) are
        # not file content and are dropped on save.
        class_lines = self._class_region()
        try:
            Path(self._path).write_text(
                "\n".join(self._file_before + class_lines + self._file_after),
                encoding="utf-8",
            )
        except OSError:
            return
        self._source_lines = class_lines
        self._save_btn.setEnabled(False)

    # -- marker click handling ----------------------------------------------

    def eventFilter(self, watched, event):  # noqa: N802
        if (
            watched is self._canvas
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            line = self._canvas.line_at(int(event.position().toPoint().y()))
            gap = self._marker_at(line)
            if gap is not None:
                self._toggle_gap(gap)
                return True
        return super().eventFilter(watched, event)
