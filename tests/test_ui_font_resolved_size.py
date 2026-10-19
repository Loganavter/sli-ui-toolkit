"""``UiFont`` must pin the size it resolves, never inherit a stale ancestor's.

Falsification (pre-fix, measured live on Improve-ImgSLI startup): the host
applies its face as ``QApplication.setFont(QFont(family))`` — a font whose size
is the platform default and is **not** in its resolve mask. Every widget that
resolves the UI face copies that font (``UiFont.base_font``), and
``QWidget.setFont`` fills unresolved attributes from the widget's *inherited*
font, i.e. the ancestor chain. A widget whose ancestors were built before the
host applied its face therefore kept the ancestor's size — the workspace tab
bar sized its tab at 178x37 (11 pt) instead of 186x38 (12 pt) and jumped when
the shown window re-resolved the chain ("first tab wrong for a couple of
frames, then resizes"). Pre-fix, the two bars below disagree; the fix pins the
resolved size into the mask, so both agree.
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.ui_font import UiFont, apply_ui_font
from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip.tab_bar import (
    _AdaptiveTabBar,
)

TAB_TEXT = "Новая вкладка"


def test_apply_ui_font_pins_the_resolved_size_not_the_ancestors(qapp, qtbot) -> None:
    """``apply_ui_font`` yields the app font's size, not the ancestor's."""
    original = QFont(qapp.font())
    try:
        family = original.family()
        # An ancestor chain created while a 30 pt face is active.
        stale = QFont(family)
        stale.setPointSizeF(30.0)
        qapp.setFont(stale)
        root = QWidget()
        qtbot.addWidget(root)
        child = QWidget(root)
        qtbot.addWidget(child)

        # The host's real face: family only, size unresolved (platform default).
        host = QFont(family)
        qapp.setFont(host)
        assert qapp.font().pointSizeF() != 30.0, "precondition: sizes must differ"
        UiFont.get_instance().set_family(family)

        apply_ui_font(child)

        assert child.font().family() == family
        assert child.font().pointSizeF() == qapp.font().pointSizeF()
        assert QFontMetrics(child.font()).height() == QFontMetrics(qapp.font()).height()
    finally:
        qapp.setFont(original)
        UiFont.get_instance().set_family(None)


def test_tab_width_is_stable_across_the_hosts_startup_face_change(qapp, qtbot) -> None:
    """A bar on a pre-apply ancestor chain sizes tabs like a settled one."""
    original = QFont(qapp.font())
    try:
        family = original.family()
        stale = QFont(family)
        stale.setPointSizeF(30.0)
        qapp.setFont(stale)
        stale_root = QWidget()
        qtbot.addWidget(stale_root)
        stale_bar = _AdaptiveTabBar(close_button_design_width=20, parent=stale_root)

        # The host applies its face (family only — the Improve-ImgSLI shape).
        host = QFont(family)
        qapp.setFont(host)
        UiFont.get_instance().set_family(family)
        apply_ui_font(stale_bar)
        stale_bar.addTab(TAB_TEXT)

        settled_root = QWidget()
        qtbot.addWidget(settled_root)
        settled_bar = _AdaptiveTabBar(close_button_design_width=20, parent=settled_root)
        apply_ui_font(settled_bar)
        settled_bar.addTab(TAB_TEXT)

        assert stale_bar.sizeHint().width() == settled_bar.sizeHint().width()
        assert stale_bar.sizeHint().height() == settled_bar.sizeHint().height()
    finally:
        qapp.setFont(original)
        UiFont.get_instance().set_family(None)
