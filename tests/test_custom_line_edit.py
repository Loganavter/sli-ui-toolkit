"""CustomLineEdit geometry — no stacked QSS padding / no clipped descenders."""

from __future__ import annotations

from PySide6.QtGui import QFontMetrics

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.widgets import CustomLineEdit


def _register_palettes(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("dark", qapp)


def test_custom_line_edit_text_margins_are_horizontal_only(qapp):
    _register_palettes(qapp)
    edit = CustomLineEdit()
    margins = edit.textMargins()
    assert margins.left() == CustomLineEdit.H_PADDING
    assert margins.right() == CustomLineEdit.H_PADDING
    assert margins.top() == 0
    assert margins.bottom() == 0
    assert "padding: 0" in edit.styleSheet()
    edit.deleteLater()


def test_custom_line_edit_content_taller_than_font_with_descenders(qapp):
    """Fixed height minus text margins must fit fontMetrics().height()."""
    _register_palettes(qapp)
    edit = CustomLineEdit()
    margins = edit.textMargins()
    content_h = edit.height() - margins.top() - margins.bottom()
    assert content_h >= QFontMetrics(edit.font()).height()
    edit.deleteLater()
