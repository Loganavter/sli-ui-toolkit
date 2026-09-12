"""Config-snippet parsing shared by the preview and apply paths.

The Code section shows a synthetic constructor call (the live config
values) above the class source. ``_config_kwargs`` turns the CURRENT
snippet text into constructor kwargs for the preview and into attribute
values for the live instance's config apply — the two consumers must
agree on how names resolve, so the parsing lives here rather than in
either consumer.

Names resolve against a small Qt namespace, the widget module's own
globals, and enum classes the inspector has seen in live config values
(see ``fields.preview_enum_classes``).
"""

from __future__ import annotations

import ast
import logging
import re

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap

logger = logging.getLogger("sli_ui_toolkit.inspector")

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

    from sli_ui_toolkit.ui.inspector.fields import preview_enum_classes

    lookup = dict(_PREVIEW_NAMESPACE)
    if namespace:
        lookup.update(namespace)
    lookup.update(preview_enum_classes())

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
