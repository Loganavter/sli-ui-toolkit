"""Apply — hot class patch + config apply to the live widget.

Functions taking the ``CodeSectionEditor`` owner as their first argument
(thin-owner pattern): the editor keeps the instance state and Qt-required
method names; the patch/apply mechanics live here.
"""

from __future__ import annotations

import difflib
import logging

from PySide6.QtGui import QColor

from .config import _class_name_from_region, _config_kwargs
from .preview import fail_with_debug, set_debug, show_status
from sli_ui_toolkit.ui.inspector.spec import apply_config_refresh_for

logger = logging.getLogger("sli_ui_toolkit.inspector")

#: class attributes not copied when hot-patching the live class
_CLASS_BOOKKEEPING = frozenset(
    {
        "__dict__",
        "__weakref__",
        "__module__",
        "__qualname__",
        "__slots__",
        # Python 3.13+/3.14 class bookkeeping (no runtime behavior)
        "__firstlineno__",
        "__static_attributes__",
        # PySide meta-object machinery: the compiled preview class's own
        # QMetaObject must never replace the live class's — signal dispatch
        # is wired through it
        "staticMetaObject",
    }
)


def _init_edited(region: list[str], source_lines: list[str]) -> bool:
    """Whether the edits between the current class region and the loaded
    source touch the ``__init__`` method's body.

    ``__init__`` is re-copied onto the live class on EVERY apply (it is
    part of the region), so "``__init__`` was patched" alone says nothing.
    The live instance is not reconstructed, though — only edits that land
    inside the init body (or the def line itself) warrant the
    "init-time changes apply to new widgets" hint."""
    if not region or region == source_lines:
        return False
    matcher = difflib.SequenceMatcher(a=source_lines, b=region, autojunk=False)
    changed_in_region = {
        i
        for _tag, _i1, _i2, j1, j2 in matcher.get_opcodes()
        if _tag != "equal"
        for i in range(j1, j2)
    }
    if not changed_in_region:
        return False
    start = next(
        (i for i, line in enumerate(region) if line.lstrip().startswith("def __init__")),
        None,
    )
    if start is None:
        return False
    indent = len(region[start]) - len(region[start].lstrip())
    end = len(region)
    for i in range(start + 1, len(region)):
        if region[i].strip() and (len(region[i]) - len(region[i].lstrip())) <= indent:
            end = i
            break
    return any(i in changed_in_region for i in range(start, end))


def apply_config_to_instance(
    editor, kwargs: dict
) -> tuple[list[str], list[str]]:
    """Best-effort write of config-snippet kwargs onto the LIVE instance:
    each field's attribute (``name`` / ``_name`` / ``_name_override``, the
    inspector's read convention) is set directly (Qt methods are never
    overwritten), then the spec's ``apply_config_refresh`` hook re-runs
    the layout passes that ``__init__`` normally performs so the values
    actually take effect. Every write is logged with its before/after
    value."""
    target = editor._target_instance
    applied: list[str] = []
    failed: list[str] = []
    if target is None:
        return applied, failed
    for name, value in kwargs.items():
        attr = None
        for candidate in (name, f"_{name}", f"_{name}_override"):
            try:
                current = getattr(target, candidate)
            except Exception:
                continue
            if callable(current) and not isinstance(current, QColor):
                # Qt methods (width(), update(), ...) must never be
                # overwritten by a config value — keep looking for the
                # stored attribute (``_width`` etc.)
                continue
            attr = candidate
            break
        if attr is None:
            logger.warning(
                "[inspector-preview] config apply: no attribute for "
                "%s on %s (tried %r)",
                name,
                type(target).__name__,
                (name, f"_{name}", f"_{name}_override"),
            )
            failed.append(name)
            continue
        try:
            old = getattr(target, attr)
        except Exception:
            old = "<unreadable>"
        try:
            setattr(target, attr, value)
            applied.append(name)
            logger.warning(
                "[inspector-preview] config apply: %s.%s: %r -> %r",
                type(target).__name__,
                attr,
                old,
                value,
            )
        except Exception as exc:
            logger.warning(
                "[inspector-preview] config apply failed for %s: %s: %s",
                name,
                type(exc).__name__,
                exc,
            )
            failed.append(name)
    refresh = apply_config_refresh_for(target)
    if refresh is not None:
        try:
            refresh(target, tuple(applied))
            logger.warning(
                "[inspector-preview] config refresh hook ran for %s "
                "(applied=%s)",
                type(target).__name__,
                ", ".join(applied) or "(none)",
            )
        except Exception as exc:
            logger.warning(
                "[inspector-preview] config refresh hook failed for "
                "%s: %s: %s",
                type(target).__name__,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
    else:
        logger.warning(
            "[inspector-preview] config refresh: NO refresh hook for "
            "%s — layout-affected values (margins, sizes) may not "
            "show without one; only attribute writes + repaint",
            type(target).__name__,
        )
    try:
        target.updateGeometry()
        target.update()
        target.repaint()
    except RuntimeError:
        pass
    return applied, failed


def apply_to_live(editor) -> None:
    """Make the LIVE widget reflect the current editor state.

    Two independent effects:
    - edited CLASS region  → hot-patch the real widget class (methods/
      attributes copied onto ``target_class``; the live instance picks
      method changes up immediately; ``__init__``-body edits affect
      only widgets created after the patch). Revert restores the
      snapshot taken at ``set_source``.
    - edited CONFIG snippet → best-effort write of the snippet's
      kwargs onto the live instance's config attributes + repaint.
    """
    if editor._target_class is None:
        logger.warning(
            "[inspector-preview] apply refused: no target_class "
            "(path=%s)",
            editor._path,
        )
        from .preview import show_error

        show_error(editor, "Apply failed: the live widget class is not available")
        return
    class_dirty = editor.is_dirty()
    snippet_dirty = editor.snippet_dirty()
    if not class_dirty and not snippet_dirty:
        # nothing changed: re-copying reports "Apply OK" while nothing
        # changes — that reads as "Apply is broken". Say so instead
        # (without launching the preview panel).
        logger.warning(
            "[inspector-preview] apply skipped: class region and "
            "config snippet both identical to the loaded state"
        )
        if not editor._preview_panel.isHidden():
            show_status(
                editor,
                "Nothing to patch — edit the class source or the "
                "config snippet first (Preview shows the current state)",
            )
        return
    if editor._view.is_editing():
        editor._view.exit_edit_mode()

    region: list[str] = []
    text = ""
    patched: list[str] = []
    init_edited = False
    if class_dirty:
        region = editor._class_region()
        text = "\n".join(region)
        namespace = dict(editor._module_vars or {})
        namespace["__name__"] = "imgsli_inspector_preview"
        logger.warning(
            "[inspector-preview] apply begin: region=%d lines "
            "target=%s instance=%s",
            len(region),
            editor._target_class.__name__,
            editor._target_instance is not None,
        )
        try:
            exec(compile(text, editor._path or "<apply>", "exec"), namespace)  # noqa: S102
        except Exception as exc:
            logger.warning(
                "[inspector-preview] apply compile failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            fail_with_debug(
                editor,
                f"Apply failed (compile): {type(exc).__name__}: {exc}",
                text,
            )
            return
        class_name = _class_name_from_region(region)
        new_class = namespace.get(class_name or "", None) if class_name else None
        if new_class is None or not isinstance(new_class, type):
            logger.warning(
                "[inspector-preview] apply failed: class %r not found "
                "in the compiled source",
                class_name,
            )
            fail_with_debug(
                editor,
                f"Apply failed: class {class_name!r} not found in the compiled "
                f"source\ncompiled region:\n{text}",
                text,
            )
            return
        skipped_bookkeeping: list[str] = []
        try:
            for name, value in vars(new_class).items():
                if name in _CLASS_BOOKKEEPING:
                    skipped_bookkeeping.append(name)
                    continue
                old = vars(editor._target_class).get(name)
                setattr(editor._target_class, name, value)
                editor._patched_names.add(name)
                patched.append(name)
                logger.warning(
                    "[inspector-preview] apply member %s: %s -> %s "
                    "(identical=%s)",
                    name,
                    type(old).__name__ if old is not None else "absent",
                    type(value).__name__,
                    old is value,
                )
        except Exception as exc:
            logger.warning(
                "[inspector-preview] apply patch failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            fail_with_debug(
                editor, f"Apply failed (patch): {type(exc).__name__}: {exc}", text
            )
            return
        logger.warning(
            "[inspector-preview] apply patch done: patched=%d (%s) "
            "bookkeeping-skipped=%d (%s)",
            len(patched),
            ", ".join(patched) or "(none)",
            len(skipped_bookkeeping),
            ", ".join(skipped_bookkeeping) or "(none)",
        )
        init_edited = _init_edited(region, editor._source_lines)
        if init_edited:
            logger.warning(
                "[inspector-preview] __init__ body edited: the live "
                "instance is NOT rebuilt — init-time visual changes "
                "apply only to widgets created AFTER the patch"
            )
    editor._applied = bool(patched)
    if editor._target_instance is not None:
        try:
            editor._target_instance.update()
            editor._target_instance.repaint()
        except RuntimeError:
            pass

    # config snippet → live instance config attributes
    config_kwargs: dict = {}
    config_applied: list[str] = []
    config_failed: list[str] = []
    if snippet_dirty:
        config_kwargs, config_skipped = _config_kwargs(
            editor._snippet_text(), editor._module_vars
        )
        config_applied, config_failed = apply_config_to_instance(
            editor, config_kwargs
        )
        config_failed += config_skipped
        logger.warning(
            "[inspector-preview] config applied to instance: %s "
            "(failed/skipped: %s) kwargs=%s",
            ", ".join(config_applied) or "none",
            ", ".join(config_failed) or "none",
            config_kwargs,
        )
    inst = editor._target_instance
    if inst is not None:
        try:
            logger.warning(
                "[inspector-preview] live widget after apply: "
                "size=%dx%d geometry=%s visible=%s",
                inst.size().width(),
                inst.size().height(),
                inst.geometry(),
                inst.isVisible(),
            )
        except RuntimeError:
            pass

    parts = []
    if patched:
        parts.append(
            f"patched {len(patched)} member(s) onto "
            f"{editor._target_class.__name__}"
        )
        if init_edited:
            parts.append(
                "note: the live instance keeps its current state, "
                "__init__-level changes apply to widgets created "
                "after the patch"
            )
    if config_applied:
        parts.append(
            f"config applied to instance: {', '.join(config_applied)}"
        )
    if config_failed:
        parts.append(f"config skipped: {', '.join(config_failed)}")
    apply_status = "Apply OK — " + "; ".join(parts)
    debug_parts = []
    if patched:
        debug_parts.append(
            f"patched onto {editor._target_class.__name__}: "
            f"{', '.join(patched) or '(no members)'}"
        )
    if snippet_dirty:
        debug_parts.append(f"config kwargs: {config_kwargs}")
        debug_parts.append(
            f"config applied: {', '.join(config_applied) or 'none'} "
            f"failed: {', '.join(config_failed) or 'none'}"
        )
    # Apply never LAUNCHES the preview panel: it only refreshes an
    # already-open one, so the patched/config'd widget stays truthful
    # (the caption carries the Apply result there). With the panel
    # closed, feedback is the live widget itself + the log lines.
    from .preview import rebuild, show_status as _status

    if not editor._preview_panel.isHidden():
        rebuild(editor)
        if editor._preview_error.isVisible():
            logger.warning(
                "[inspector-preview] apply ok but preview rebuild "
                "failed: %s",
                editor._preview_error.text(),
            )
        else:
            pw = editor._preview_widget
            logger.warning(
                "[inspector-preview] apply ok: patched=%d members=%s "
                "config_applied=%s preview_widget=%s size=%dx%d",
                len(patched),
                ", ".join(patched) or "(none)",
                ", ".join(config_applied) or "(none)",
                pw is not None,
                pw.size().width() if pw is not None else 0,
                pw.size().height() if pw is not None else 0,
            )
            _status(editor, apply_status)
        set_debug(
            editor,
            "\n".join(debug_parts + [editor._preview_debug.text()]),
        )


def revert_class_patch(editor) -> None:
    """Restore the snapshot of the live class taken at ``set_source``."""
    target = editor._target_class
    if target is None or not editor._applied:
        return
    try:
        for name, value in editor._original_class_dict.items():
            setattr(target, name, value)
        for name in list(editor._patched_names):
            if name not in editor._original_class_dict:
                delattr(target, name)
    except Exception:
        pass
    editor._patched_names.clear()
    editor._applied = False
    if editor._target_instance is not None:
        try:
            editor._target_instance.update()
        except RuntimeError:
            pass
    show_status(
        editor,
        f"Reverted — {target.__name__} restored to the original class",
    )
