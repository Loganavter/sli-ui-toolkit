"""ConsoleView — wrap break points: a long token breaks at a natural point, never mid-word.

Owner report (2026-11-28): a TensorRT engine name arrived as one token and the hard cut chopped it into
``..._opt-:`` / ``tiling-...`` / ``...dev16.e`` / ``gine.``. A break is allowed after any of ``- _ / \\ . : , ;``
when no space fits earlier on the row; a token with no such point is still cut at the width, and every result keeps
the spans contiguous, non-overlapping, non-empty and covering the whole source string.
"""

from __future__ import annotations

from PySide6.QtGui import QFontMetrics

from sli_ui_toolkit.ui.widgets.composite.console_view import ConsoleView

_ENGINE = "/models/tensorrt/rtdetr-l_opt-b4_tiling-dev16.engine"
_SENTENCE = "the quick brown fox jumps over the lazy dog again and again"

#: The characters a break may follow when the row has no space to break at.
_SOFT = set("-_/\\.,:;")


def _view(qtbot) -> ConsoleView:
    view = ConsoleView()
    qtbot.addWidget(view)
    return view


def _wrap(view: ConsoleView, text: str, width: int) -> list[tuple[int, int]]:
    return view._wrap_line(text, QFontMetrics(view._font), width)


def _assert_covered(text: str, spans: list[tuple[int, int]]) -> None:
    """Contiguous, non-overlapping, non-empty spans that reconstruct the source exactly."""
    assert spans, "a line always yields at least one row"
    assert spans[0][0] == 0
    assert spans[-1][1] == len(text)
    for index, (start, end) in enumerate(spans):
        assert start < end, "no empty row"
        if index:
            assert spans[index - 1][1] == start, "spans must be contiguous"
    assert "".join(text[start:end] for start, end in spans) == text


def _segments(text: str, spans: list[tuple[int, int]]) -> list[str]:
    return [text[start:end] for start, end in spans]


def test_engine_name_breaks_after_a_soft_point_and_never_mid_token(qtbot):
    view = _view(qtbot)
    fm = QFontMetrics(view._font)
    width = fm.horizontalAdvance("rtdetr-l_opt-b4_tiling")

    spans = _wrap(view, _ENGINE, width)
    assert len(spans) > 1, "the engine name is longer than this row"
    _assert_covered(_ENGINE, spans)
    # No space in the name, so every interior break must sit right after a soft point - not at an arbitrary character.
    for start, end in spans[:-1]:
        assert _ENGINE[end - 1] in _SOFT, "break at %r not after a soft point" % _ENGINE[end - 1 : end + 6]


def test_break_prefers_a_space_over_a_later_soft_point(qtbot):
    view = _view(qtbot)
    fm = QFontMetrics(view._font)
    # "aaa bbb-" fits the row and a soft point sits right at its end; the next token starts beyond it, so the space at
    # index 3 is the one a reader expects the break after.
    text = "aaa bbb-ccc"
    width = fm.horizontalAdvance("aaa bbb-")

    spans = _wrap(view, text, width)
    _assert_covered(text, spans)
    assert len(spans) > 1
    assert spans[0] == (0, 4), "a fitting space outranks a soft point further right"


def test_token_without_a_soft_point_is_hard_cut_and_fully_covered(qtbot):
    view = _view(qtbot)
    fm = QFontMetrics(view._font)
    token = "x" * 300
    width = fm.horizontalAdvance("x" * 10)

    spans = _wrap(view, token, width)
    assert len(spans) > 1
    _assert_covered(token, spans)
    for segment in _segments(token, spans):
        assert sum(fm.horizontalAdvance(char) for char in segment) <= width or len(segment) == 1


def test_a_normal_sentence_still_breaks_only_at_spaces(qtbot):
    view = _view(qtbot)
    fm = QFontMetrics(view._font)
    width = fm.horizontalAdvance("the quick brown fox jumps")

    spans = _wrap(view, _SENTENCE, width)
    assert len(spans) > 1
    _assert_covered(_SENTENCE, spans)
    for start, end in spans[:-1]:
        assert _SENTENCE[end - 1] == " ", "a plain sentence must not be broken at a soft point"
    # A line that fits stays one row.
    assert _wrap(view, "short line", width) == [(0, len("short line"))]


_SAMPLES = [
    "/models/tensorrt/rtdetr-l_opt-b4_tiling-dev16.engine",
    "C:\\Users\\dev\\AppData\\Local\\Temp\\render-cache\\frame-000123.tif",
    "https://example.com/a/very/long/path?query=1&other=2#fragment",
    "1234567890123456789012345678901234567890123456789012345678901234567890",
    "Съешь же ещё этих мягких французских булок, да выпей чаю — длинная строка без разрывов",
    "mixed_Текст-path.with:many,soft;breaks/and\\backslashes",
    "one",
    "",
]


def test_every_sample_is_fully_covered_at_every_width(qtbot):
    view = _view(qtbot)
    fm = QFontMetrics(view._font)
    for width in (12, 40, 90, 150, 400):
        for text in _SAMPLES:
            spans = _wrap(view, text, width)
            if not text:
                # An empty source line still needs one row to paint; there is nothing to cover.
                assert spans == [(0, 0)]
                continue
            _assert_covered(text, spans)
            for segment in _segments(text, spans):
                assert sum(fm.horizontalAdvance(char) for char in segment) <= width or len(segment) == 1
