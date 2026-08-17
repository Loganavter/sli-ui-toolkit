"""Preview panel of the Code section — functions taking the editor owner.

The preview lives in ``CodeSectionEditor``'s state (``_preview_panel``,
``_preview_host``, ``_preview_widget``, ...); per the thin-owner pattern
the building/toggling logic sits here as plain functions taking the
editor as their first argument, so the owner only wires construction and
delegates by the same method names.
"""

from __future__ import annotations

import inspect
import logging

from PySide6.QtCore import QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRegion
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from .config import _class_name_from_region, _config_kwargs
from sli_ui_toolkit.ui.inspector.spec import preview_seed_for
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label

logger = logging.getLogger("sli_ui_toolkit.inspector")


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


def toggle(editor) -> None:
    if not editor._preview_panel.isHidden() and editor._preview_widget is not None:
        close(editor)
    else:
        # a panel open with only status text (e.g. an Apply error)
        # counts as closed — the click builds the preview instead
        editor._preview_panel.setVisible(True)
        editor._preview_btn.setText("Hide preview")
        rebuild(editor)


def close(editor) -> None:
    editor._preview_panel.setVisible(False)
    editor._preview_btn.setText("Preview")
    clear_host(editor)
    if editor._preview_timer is not None:
        editor._preview_timer.stop()
        editor._preview_timer = None


def clear_host(editor) -> None:
    editor._preview_widget = None
    set_debug(editor, "")
    while editor._preview_host_layout.count():
        item = editor._preview_host_layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
    editor._preview_error.setVisible(False)


def rebuild(editor) -> None:
    """Compile the edited class region and construct a live instance
    (current config values as kwargs) inside the preview host."""
    if editor._preview_panel.isHidden():
        logger.warning("[inspector-preview] rebuild skipped: panel hidden")
        return
    clear_host(editor)
    region = editor._class_region()
    text = "\n".join(region)
    logger.warning(
        "[inspector-preview] rebuild begin: class region %d lines, "
        "config=%r, module_vars=%s, target=%s",
        len(region),
        (editor._snippet_text() or "")[:160],
        "yes" if editor._module_vars is not None else "no",
        editor._target_class.__name__ if editor._target_class is not None else None,
    )
    try:
        compiled = compile(text, editor._path or "<preview>", "exec")
    except (SyntaxError, ValueError) as exc:
        logger.warning(
            "[inspector-preview] compile failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        show_error(editor, f"Compile failed: {exc}")
        return
    namespace = dict(editor._module_vars or {})
    namespace["__name__"] = "imgsli_inspector_preview"
    try:
        exec(compiled, namespace)  # noqa: S102 — diagnostic tool, dev-only
    except Exception as exc:
        logger.warning(
            "[inspector-preview] exec of edited class failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        show_error(editor, f"Compile failed: {exc}")
        return
    class_name = _class_name_from_region(region)
    cls = namespace.get(class_name or "", None) if class_name else None
    if cls is None or not isinstance(cls, type):
        logger.warning(
            "[inspector-preview] class %r not found after exec "
            "(namespace keys: %s)",
            class_name,
            sorted(k for k in namespace if not k.startswith("__"))[:30],
        )
        show_error(
            editor,
            f"Class {class_name!r} not found after compiling the edited source",
        )
        return
    # the CURRENT buffer snippet, not the loaded one — the preview must
    # reflect config-snippet edits live (Apply writes the same values
    # to the live instance)
    kwargs, skipped = _config_kwargs(editor._snippet_text(), editor._module_vars)
    signature = _preview_init_signature(cls)
    parent_param = signature.parameters.get("parent") if signature else None
    logger.warning(
        "[inspector-preview] class=%s signature=%s parent_kind=%s",
        class_name,
        signature,
        parent_param.kind if parent_param is not None else None,
    )
    if signature is not None:
        # Best-effort: the config snippet only carries values the widget
        # self-describes, so REQUIRED args it does not store as
        # attributes (e.g. AdaptiveTabStrip's add_icon) are missing —
        # fill them with None so the preview still builds. ``parent`` is
        # skipped on purpose: it is passed explicitly below, and filling
        # it with None would make every widget with a required
        # ``parent`` fail with "multiple values for keyword argument
        # 'parent'" (the GlassHUD family's ``__init__(self, parent)``).
        for name, param in signature.parameters.items():
            if name == "self" or name in kwargs or name == "parent":
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
            logger.warning(
                "[inspector-preview] constructing with parent=host, "
                "kwargs=%s skipped=%s",
                kwargs,
                skipped,
            )
            preview = cls(parent=editor._preview_host, **kwargs)
        else:
            try:
                logger.warning(
                    "[inspector-preview] constructing with positional "
                    "host, kwargs=%s skipped=%s",
                    kwargs,
                    skipped,
                )
                preview = cls(editor._preview_host, **kwargs)
            except TypeError:
                logger.warning(
                    "[inspector-preview] positional host rejected, "
                    "retrying kwargs-only: kwargs=%s",
                    kwargs,
                    exc_info=True,
                )
                preview = cls(**kwargs)
    except Exception as exc:
        logger.warning(
            "[inspector-preview] construct failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        fail_with_debug(
            editor, f"Construct failed: {type(exc).__name__}: {exc}", text
        )
        return
    editor._preview_widget = preview
    editor._preview_host_layout.addWidget(preview)
    # a tall sizeHint must never inflate the well into a long fixed
    # strip — cap the preview at the well's budget (160 - margins)
    preview.setMaximumHeight(144)
    seeded = False
    if preview.sizeHint().height() <= 0:
        # a plain QWidget (or any custom-painted widget without a
        # sizeHint) gets zero height from the layout and renders
        # nothing — the well shows only its backdrop fill. Give it a
        # visible strip so the preview never looks empty.
        preview.setMinimumHeight(48)
    if editor._target_instance is not None:
        seed = preview_seed_for(editor._target_instance)
        if seed is not None:
            try:
                seed(preview, editor._target_instance)
                seeded = True
            except Exception as exc:
                logger.warning(
                    "[inspector-preview] preview seed failed for %s: "
                    "%s: %s",
                    type(editor._target_instance).__name__,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
    editor._preview_host_layout.activate()
    logger.warning(
        "[inspector-preview] built ok: widget=%s size=%dx%d "
        "sizeHint=%dx%d visible=%s panel_visible=%s seeded=%s",
        class_name,
        preview.size().width(),
        preview.size().height(),
        preview.sizeHint().width(),
        preview.sizeHint().height(),
        preview.isVisible(),
        editor._preview_panel.isVisible(),
        seeded,
    )
    editor._preview_caption.setText(
        "Preview (live) — " + (class_name or "class") + " rebuilt from the edited class"
    )
    editor._preview_error.setVisible(False)
    set_debug(
        editor,
        f"class={class_name} signature={signature}\n"
        f"kwargs={kwargs}\n"
        f"skipped={skipped or 'none'}\n"
        f"sizeHint={preview.sizeHint().width()}x{preview.sizeHint().height()}",
    )


def fail_with_debug(editor, message: str, text: str | None = None) -> None:
    """Error + the attempted region/state in the debug line (shared by the
    apply and preview paths)."""
    debug = message
    if text is not None:
        debug += f"\ncompiled region:\n{text}"
    try:
        kwargs, skipped = _config_kwargs(editor._config_text, editor._module_vars)
        debug += (
            f"\nkwargs: {kwargs}"
            f"\nskipped: {', '.join(skipped) or 'none'}"
        )
    except Exception:
        pass
    set_debug(editor, debug)
    show_error(editor, message)


def show_error(editor, message: str) -> None:
    """Show an error — auto-opens the panel so a failed Apply/Preview is
    never silent (the user's "Apply does nothing" case)."""
    editor._preview_panel.setVisible(True)
    editor._preview_btn.setText("Hide preview")
    editor._preview_error.setText(message)
    editor._preview_error.setVisible(True)
    editor._preview_caption.setText("Preview — build failed")


def show_status(editor, message: str) -> None:
    """Success feedback for Apply — auto-opens the panel."""
    editor._preview_panel.setVisible(True)
    editor._preview_btn.setText("Hide preview")
    editor._preview_caption.setText(message)
    editor._preview_error.setVisible(False)


def set_debug(editor, text: str) -> None:
    """Diagnostic detail for the last preview/apply operation."""
    editor._preview_debug.setText(text)
    editor._preview_debug.setVisible(bool(text))


def schedule_rebuild(editor) -> None:
    if editor._preview_panel.isHidden():
        return
    if editor._preview_timer is None:
        editor._preview_timer = QTimer(editor)
        editor._preview_timer.setSingleShot(True)
        editor._preview_timer.setInterval(300)
        editor._preview_timer.timeout.connect(editor._rebuild_preview)
    editor._preview_timer.start()
