"""Python syntax highlighting for the text view.

One line-based tokenizer feeds the painted text surface (both read and edit
modes — the view paints itself, no stock Qt text widgets). The inspected
widgets are always Python classes, so a single hardcoded Python rule set is
enough — no language registry.

Kinds produced by :func:`python_line_spans`: ``comment``, ``string``,
``decorator``, ``keyword``, ``builtin``, ``number``, ``defclass`` (the name
after ``def``/``class``).
"""

from __future__ import annotations

import re

from PySide6.QtGui import QColor

PY_KEYWORDS = frozenset(
    """
    False None True and as assert async await break class continue def del
    elif else except finally for from global if import in is lambda
    nonlocal not or pass raise return try while with yield
    """.split()
)

PY_BUILTINS = frozenset(
    """
    abs all any ascii bin bool bytearray bytes callable chr classmethod
    compile complex delattr dict dir divmod enumerate eval exec filter
    float format frozenset getattr globals hasattr hash help hex id input
    int isinstance issubclass iter len list locals map max memoryview min
    next object oct open ord pow print property range repr reversed round
    set setattr slice sorted staticmethod str sum super tuple type vars zip
    Exception ValueError KeyError TypeError RuntimeError ImportError
    AttributeError NameError IndexError StopIteration NotImplementedError
    """.split()
)

_KEYWORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER_RE = re.compile(
    r"0[xX][0-9a-fA-F_]+|\d[\d_]*(\.\d+)?([eE][+-]?\d+)?"
)
_DECORATOR_RE = re.compile(r"@[A-Za-z_][A-Za-z0-9_.]*")
_TRIPLE_RE = re.compile(r"(\"\"\"|''')(?:\\.|[^\\])*?(\"\"\"|''')")
_QUOTE_RE = re.compile(r"(\"|')(?:\\.|[^\\\"'])*?(\"|')")
_DEF_NAME_RE = re.compile(r"\s+([A-Za-z_][A-Za-z0-9_]*)")


def python_line_spans(line: str) -> list[tuple[int, int, str]]:
    """``(start, end, kind)`` spans for one line (single-line constructs;
    triple-quoted strings are handled line-by-line: an opening triple
    without a same-line closer marks the rest of the line as string)."""
    spans: list[tuple[int, int, str]] = []
    index = 0
    length = len(line)
    while index < length:
        ch = line[index]
        if ch.isspace():
            index += 1
            continue
        if ch == "#":
            spans.append((index, length, "comment"))
            break
        if ch == "@":
            match = _DECORATOR_RE.match(line, index)
            if match is not None:
                spans.append((index, match.end(), "decorator"))
                index = match.end()
                continue
        if ch in "\"'":
            if line.startswith('"""', index) or line.startswith("'''", index):
                match = _TRIPLE_RE.match(line, index)
                if match is not None:
                    spans.append((index, match.end(), "string"))
                    index = match.end()
                    continue
                # opening triple without a same-line closer → multiline
                # string: the rest of the line is string content
                spans.append((index, length, "string"))
                break
            match = _QUOTE_RE.match(line, index)
            if match is not None:
                spans.append((index, match.end(), "string"))
                index = match.end()
                continue
            # unterminated single-quoted string → rest of the line
            spans.append((index, length, "string"))
            break
        if ch.isdigit() or (ch == "." and index + 1 < length and line[index + 1].isdigit()):
            match = _NUMBER_RE.match(line, index)
            if match is not None:
                spans.append((index, match.end(), "number"))
                index = match.end()
                continue
        if ch.isascii() and (ch.isalpha() or ch == "_"):
            match = _KEYWORD_RE.match(line, index)
            word = match.group(0)
            end = index + len(word)
            if word in PY_KEYWORDS:
                spans.append((index, end, "keyword"))
                if word in ("def", "class"):
                    name = _DEF_NAME_RE.match(line, end)
                    if name is not None:
                        name_start = name.start(1)
                        name_end = name.end(1)
                        if line[name_start:name_end] not in PY_KEYWORDS:
                            spans.append((name_start, name_end, "defclass"))
            elif word in PY_BUILTINS:
                spans.append((index, end, "builtin"))
            index = end
            continue
        index += 1
    return spans


def python_span_colors(theme_manager) -> dict[str, QColor]:
    """Theme-aware palette for the span kinds."""
    dark = bool(theme_manager.is_dark())
    accent = theme_manager.try_get_color("accent")
    if accent is None or not accent.isValid():
        accent = theme_manager.get_color("accent")
    return {
        "comment": QColor("#6a737d" if not dark else "#8b949e"),
        "string": QColor("#2e7d32" if not dark else "#7ee787"),
        "keyword": QColor(accent),
        "builtin": QColor("#005cc5" if not dark else "#79c0ff"),
        "number": QColor("#b31d28" if not dark else "#ff7b72"),
        "decorator": QColor("#795e26" if not dark else "#d2a8ff"),
        "defclass": QColor("#6f42c1" if not dark else "#d2a8ff"),
    }
