"""QSS scanning: candidate rules + dead-selector analysis."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from sli_ui_toolkit.ui.inspector.qss_scan import QssIndex

_TEXT = """
/* comment */
QPushButton#okButton { color: red; }
QWidget[class="icon-button"] { background: blue; }
#CustomTitleBar, QLabel#ratingLabel { height: 36px; }
QLineEdit[custom-line-edit="true"]:focus { border: 0; }
"""


def test_from_text_splits_selectors_and_strips_comments():
    index = QssIndex.from_text(_TEXT)
    selectors = {rule.selector for rule in index.rules}
    assert selectors == {
        "QPushButton#okButton",
        'QWidget[class="icon-button"]',
        "#CustomTitleBar",
        "QLabel#ratingLabel",
        'QLineEdit[custom-line-edit="true"]:focus',
    }


def test_candidates_match_object_name_class_and_properties(qapp):
    index = QssIndex.from_text(_TEXT)

    title = QWidget()
    title.setObjectName("CustomTitleBar")
    assert {r.selector for r in index.candidates_for(title)} == {
        "#CustomTitleBar"
    }

    label = QLabel("x")
    label.setObjectName("ratingLabel")
    assert {r.selector for r in index.candidates_for(label)} == {
        "QLabel#ratingLabel"
    }

    wrong = QWidget()
    wrong.setObjectName("other")
    assert index.candidates_for(wrong) == ()


def test_candidates_require_property_value(qapp):
    index = QssIndex.from_text(_TEXT)
    line_edit = QLabel("x")
    line_edit.setProperty("custom-line-edit", "true")
    # leaf type QLabel != QLineEdit → excluded despite the property
    assert index.candidates_for(line_edit) == ()
    from PySide6.QtWidgets import QLineEdit

    le = QLineEdit()
    le.setProperty("custom-line-edit", "true")
    assert {r.selector for r in index.candidates_for(le)} == {
        'QLineEdit[custom-line-edit="true"]:focus'
    }


def test_dead_selectors_flags_unmatched_rules(qapp):
    index = QssIndex.from_text(_TEXT)
    widget = QWidget()
    widget.setObjectName("CustomTitleBar")
    flags = {r.selector: m for r, m in index.dead_selectors([widget])}
    assert flags["#CustomTitleBar"] is True
    assert flags["QPushButton#okButton"] is False
    assert flags['QWidget[class="icon-button"]'] is False
    assert flags["QLabel#ratingLabel"] is False


def test_candidates_match_ancestor_class_selectors(qapp):
    from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import (
        AdaptiveTabStrip,
    )

    index = QssIndex.from_text(
        "AdaptiveTabStrip { border: 1px solid red; }\n"
        "QWidget#WorkspaceTabsBar { background: blue; }\n"
        "QPushButton { color: green; }\n"
    )

    class WorkspaceTabStrip(AdaptiveTabStrip):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

    strip = WorkspaceTabStrip(add_icon="+", close_icon="x")
    strip.setObjectName("WorkspaceTabsBar")
    # Qt type selectors match subclasses: the base-class rule applies to the
    # subclass instance even though the leaf __init__ hides the constructor.
    assert {r.selector for r in index.candidates_for(strip)} == {
        "AdaptiveTabStrip",
        "QWidget#WorkspaceTabsBar",
    }


def test_rules_carry_line_numbers():
    index = QssIndex.from_text("QPushButton { color: red; }\nQLabel { x: y; }\n")
    assert {r.selector: r.line for r in index.rules} == {
        "QPushButton": 1,
        "QLabel": 2,
    }
