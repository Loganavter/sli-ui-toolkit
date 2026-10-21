"""Label word-wrap vertical policy + heightForWidth flag sync.

Regression: ``_apply_style`` rebuilt the size policy from scratch, wiping
the ``heightForWidth`` flag ``setWordWrap()`` maintains while forcing
vertical ``Fixed`` — layouts then honored the stale multi-line ``sizeHint``
height instead of ``heightForWidth`` and wrapped labels floated in dead
space (settings backend hint: 40px for a 20px line).
"""

from __future__ import annotations

from PySide6.QtWidgets import QSizePolicy

from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label  # internal: documented Label exception (queue task-text-unification-retirement-2026-10-21)



def test_plain_label_is_vertically_fixed(qapp):
    label = Label("one line")
    assert label.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
    assert not label.sizePolicy().hasHeightForWidth()


def test_wrapped_label_uses_height_for_width(qapp):
    label = Label("wrapping text", word_wrap=True)
    assert label.wordWrap()
    assert label.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Preferred
    assert label.sizePolicy().hasHeightForWidth()
    assert label.hasHeightForWidth()


def test_word_wrap_toggle_resyncs_policy(qapp):
    label = Label("toggle me")
    label.setWordWrap(True)
    assert label.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Preferred
    assert label.sizePolicy().hasHeightForWidth()
    label.setWordWrap(False)
    assert label.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
    assert not label.sizePolicy().hasHeightForWidth()


def test_style_reapplication_keeps_wrapped_policy(qapp):
    label = Label("wrapped", word_wrap=True)
    label.setPixelSize(20)
    assert label.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Preferred
    assert label.sizePolicy().hasHeightForWidth()
    assert label.hasHeightForWidth()
