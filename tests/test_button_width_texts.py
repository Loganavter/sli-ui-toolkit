"""Button width_texts: picker anchors size to the longest option, not the current text."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.composite.simple_options_flyout import SimpleOptionsFlyout
from sli_ui_toolkit.widgets import Button

OPTIONS = ["Sort: Rank ▾", "Sort: Name ▾", "Sort: Date ▾"]


def test_width_texts_round_trip(qtbot):
    btn = Button(text="Sort: Rank ▾", parent=None)
    qtbot.addWidget(btn)
    assert btn.width_texts() == ()
    btn.set_width_texts(OPTIONS)
    assert btn.width_texts() == tuple(OPTIONS)
    btn.set_width_texts(None)
    assert btn.width_texts() == ()


def test_hints_follow_widest_candidate_not_current_text(qtbot):
    short = Button(text="A ▾", parent=None)
    qtbot.addWidget(short)
    plain = short.sizeHint().width()

    short.set_width_texts(OPTIONS)
    fitted = short.sizeHint().width()
    assert fitted > plain
    assert short.minimumSizeHint().width() == fitted

    # Same candidates, different short current text — identical widths.
    other = Button(text="B ▾", parent=None)
    qtbot.addWidget(other)
    other.set_width_texts(OPTIONS)
    assert other.sizeHint().width() == fitted


def test_short_candidates_do_not_shrink_current_text(qtbot):
    btn = Button(text="A much longer current label ▾", parent=None)
    qtbot.addWidget(btn)
    plain = btn.sizeHint().width()
    btn.set_width_texts(["x"])
    assert btn.sizeHint().width() == plain


def test_constructor_kwarg(qtbot):
    btn = Button(text="Sort: Rank ▾", width_texts=OPTIONS, parent=None)
    qtbot.addWidget(btn)
    assert btn.width_texts() == tuple(OPTIONS)
    assert btn.sizeHint().width() > Button(text="Sort: Rank ▾", parent=None).sizeHint().width()


def test_flyout_content_width_hint_matches_container(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()

    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)
    labels = ["Sort: Rank", "Sort: Name", "Sort: Date"]
    flyout.populate(labels, current_index=0)

    longest_row = max(
        flyout._rows_layout.itemAt(i).widget().sizeHint().width()
        for i in range(len(labels))
    )
    margins = flyout.content_layout.contentsMargins()
    expected = longest_row + margins.left() + margins.right()

    assert flyout.content_width_hint() == expected
    assert flyout.content_width_hint() == flyout.container.width()
