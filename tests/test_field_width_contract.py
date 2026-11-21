"""A field's width must follow the HOST, not the widget's own guess.

Two measured defects (2026-11-22, a host migrating its pages off a compatibility layer):
- `ComboBox` sized itself once, while the items were empty, and never re-measured after `setItemText` - the host's
  retranslate() fills empty items, so the field stayed at the 100 px floor and elided "sudo_scene_detect".
- `DoubleSpinBox` re-pinned its own content width on every `setRange`, replacing the host's `setMinimumSize(75, 30)`,
  so a 75 px field rendered at 57 px.
"""
from __future__ import annotations

from PySide6.QtCore import QSize

from sli_ui_toolkit.widgets import ComboBox, DoubleSpinBox


def test_combo_width_follows_item_text_set_later(qapp):
    combo = ComboBox()
    for _ in range(4):
        combo.addItem("")
    empty_width = combo.sizeHint().width()
    for index, text in enumerate(["mean", "mean_segmented", "sudo_scene_detect", "pyscenedetect"]):
        combo.setItemText(index, text)
    assert combo.sizeHint().width() > empty_width


def test_an_explicit_minimum_survives_set_range(qapp):
    field = DoubleSpinBox()
    field.setMinimumSize(QSize(75, 30))
    field.setRange(1.0, 10.0)
    assert field.minimumWidth() >= 75
    field.setValue(3.5)
    assert field.minimumWidth() >= 75


def test_without_an_explicit_minimum_the_control_still_sizes_itself(qapp):
    field = DoubleSpinBox()
    field.setRange(1.0, 100000.0)
    assert field.minimumWidth() >= 44
