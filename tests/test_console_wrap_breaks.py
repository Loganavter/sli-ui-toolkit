"""ConsoleView — where a row breaks: on a natural point, never mid-token when a natural point exists.

Owner report (2026-11-28): a TensorRT engine name arrived as one token and the hand-rolled painter chopped it into
``..._opt-:`` / ``tiling-...`` / ``...dev16.e`` / ``gine.``.

The painter is gone: the rows now come from the text engine (`QTextLayout` with `WordWrap`), so this file pins the
BEHAVIOUR the owner asked for instead of our own span arithmetic - every break lands right after a space or after one
of ``- / \\ . : , ;``, the rows cover the source exactly, and no row is empty. Measured on the engine at 140/200/300/462
px (see the module's history): ``/models/tensorrt/`` | ``rtdetr-l_opt-`` | ``b4_tiling-`` | ``dev16.engine  the `` - the
breaks fall on `/` and `-`, which is what a reader expects from a path.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication
import pytest

from sli_ui_toolkit.ui.widgets.composite.console_view import ConsoleView

_ENGINE = "/models/tensorrt/rtdetr-l_opt-b4_tiling-dev16.engine"
_SENTENCE = "the quick brown fox jumps over the lazy dog again and again"

#: The characters a break may follow when a row has no space to break at.
_SOFT = set("-_/\\.,:;")


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _rows(qapp, text: str, width: int) -> list[str]:
    """The rows the real widget produces for `text` at `width` px."""
    view = ConsoleView()
    view.resize(width, 420)
    view.show()
    for _ in range(3):
        qapp.processEvents()
    view.setPlainText(text)
    for _ in range(3):
        qapp.processEvents()
    rows = [line.text for line in view.visual_lines()]
    view.deleteLater()
    qapp.processEvents()
    return rows


def _assert_natural_breaks(text: str, rows: list[str]) -> None:
    """Every break follows a space or a soft point; the rows rebuild the source."""
    assert rows, "a line always yields at least one row"
    assert "".join(rows) == text, "the rows must cover the source exactly"
    for row, following in zip(rows, rows[1:]):
        assert row, "no row may be empty"
        assert row[-1] in _SOFT or row[-1] == " ", (
            f"the row broke after {row[-1]!r} (…{row[-12:]!r} | {following[:12]!r}…): a break belongs after a space or "
            f"one of {''.join(sorted(_SOFT))}")


@pytest.mark.parametrize("width", [140, 200, 300])
def test_an_engine_path_breaks_on_its_own_separators(qapp, width):
    """The widths where the path does not fit; at 462 it fits on one row, which proves nothing about breaks."""
    rows = _rows(qapp, _ENGINE, width)
    _assert_natural_breaks(_ENGINE, rows)
    assert len(rows) > 1, f"the path must not fit at {width} px - the test would prove nothing"


@pytest.mark.parametrize("width", [140, 200, 300])
def test_a_sentence_breaks_only_at_its_spaces(qapp, width):
    rows = _rows(qapp, _SENTENCE, width)
    assert "".join(rows) == _SENTENCE
    for row, following in zip(rows, rows[1:]):
        assert row.endswith(" "), f"{row!r} | {following!r}: a sentence breaks at a space, not inside a word"


def test_a_path_and_a_sentence_together_still_cover_the_source(qapp):
    text = f"{_ENGINE}  {_SENTENCE}"
    rows = _rows(qapp, text, 200)
    _assert_natural_breaks(text, rows)


def test_a_token_without_any_separator_is_still_cut_and_covered(qapp):
    """A wall of one character has no natural point - the engine still has to emit it, in order, without loss."""
    text = "x" * 400
    rows = _rows(qapp, text, 200)
    assert "".join(rows) == text
    assert all(rows), "no empty row"
    assert len(rows) > 1
