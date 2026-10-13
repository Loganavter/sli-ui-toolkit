"""Inline markdown scanner: recursive bold/italic, non-nesting code, links.

These pin the hand-written scanner that replaced the single alternation
regex (``_INLINE_TOKEN_RE``) and the ``InlineKind.KBD`` key wordlist. Every
assertion here fails against the pre-rewrite base commit.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QFont

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.text.engine.layout.text_layout import (
    build_text_layout,
    styles_from_spans,
)
from sli_ui_toolkit.ui.widgets.text.engine.markdown import (
    InlineKind,
    parse_help_blocks,
    parse_inline,
    spans_to_plain,
)
from sli_ui_toolkit.ui.widgets.text.engine.text_index import build_text_index


def _one(text: str, kind: InlineKind):
    spans = [s for s in parse_inline(text) if s.kind == kind]
    assert spans, f"no {kind} span in {text!r}: {parse_inline(text)!r}"
    return spans[0]


def test_bold_code_span_is_not_raw_backticks():
    spans = parse_inline("**`Ctrl+S`**")
    assert len(spans) == 1
    span = spans[0]
    assert span.kind == InlineKind.CODE
    assert span.text == "Ctrl+S"
    assert span.bold is True
    assert "`" not in spans_to_plain(spans)


def test_bold_mixed_text_and_code():
    spans = parse_inline("**a `b` c**")
    assert [(s.kind, s.text, s.bold) for s in spans] == [
        (InlineKind.TEXT, "a ", True),
        (InlineKind.CODE, "b", True),
        (InlineKind.TEXT, " c", True),
    ]
    assert spans_to_plain(spans) == "a b c"


def test_bold_inside_link():
    span = _one("[**x**](u)", InlineKind.BOLD)
    assert span.text == "x"
    assert span.href == "u"
    assert span.bold is True


def test_link_inside_bold():
    span = _one("**[a](u)**", InlineKind.LINK)
    assert span.text == "a"
    assert span.href == "u"
    assert span.bold is True


def test_interior_star_stays_in_bold():
    span = _one("**a*b**", InlineKind.BOLD)
    assert span.text == "a*b"
    assert span.bold is True
    assert spans_to_plain(parse_inline("**a*b**")) == "a*b"


def test_unterminated_delimiters_are_literal():
    for text in ("**unterminated", "`unterminated", "[unterminated", "*unterminated", "**a*"):
        spans = parse_inline(text)
        assert spans_to_plain(spans) == text
        assert all(s.kind == InlineKind.TEXT for s in spans)


def test_inline_code_is_always_code_no_kbd_wordlist():
    spans = parse_inline("`F13` `Page Up` `a+b`")
    codes = [s for s in spans if s.kind == InlineKind.CODE]
    assert [s.text for s in codes] == ["F13", "Page Up", "a+b"]
    assert all(s.bold is False for s in codes)
    assert not hasattr(InlineKind, "KBD")


def test_nested_bold_code_gets_bold_font_weight(qapp):
    spans = parse_inline("**a `b` c**")
    plain = spans_to_plain(spans)
    styles, roles = styles_from_spans(spans)
    layout, _ = build_text_layout(
        plain,
        styles,
        roles,
        base_font=QFont(),
        theme=ThemeManager.get_instance(),
        color_token="dialog.text",
        width=200.0,
    )
    code_index = plain.index("b")
    assert styles[code_index].kind == InlineKind.CODE
    assert styles[code_index].bold is True
    for fr in layout.formats():
        if fr.start <= code_index < fr.start + fr.length:
            assert fr.format.fontWeight() == QFont.Weight.Bold
            break
    else:  # pragma: no cover - the layout always formats every char
        pytest.fail("no format range covered the nested code character")


def test_selection_index_carries_nested_bold():
    blocks = parse_help_blocks("**a `b` c**\n")
    index = build_text_index(blocks)
    assert index.text == "a b c"
    offset = index.text.index("b")
    assert index.styles[offset].kind == InlineKind.CODE
    assert index.styles[offset].bold is True
