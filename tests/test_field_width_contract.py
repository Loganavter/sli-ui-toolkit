"""A field's width must follow the HOST, not the widget's own guess.

Two measured defects (2026-11-22, a host migrating its pages off a compatibility layer):
- `ComboBox` sized itself once, while the items were empty, and never re-measured after `setItemText` - the host's
  retranslate() fills empty items, so the field stayed at the 100 px floor and elided "sudo_scene_detect".
- `DoubleSpinBox` re-pinned its own content width on every `setRange`, replacing the host's `setMinimumSize(75, 30)`,
  so a 75 px field rendered at 57 px.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFontMetrics

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.widgets import ComboBox, DoubleSpinBox

#: The host's own item, measured live: `horizontalAdvance` 106 px, a 130 px
#: field, and the layer still painted "sudo_scene_dete…".
HOST_ITEM = "sudo_scene_detect"


def test_combo_width_follows_item_text_set_later(qapp):
    combo = ComboBox()
    for _ in range(4):
        combo.addItem("")
    empty_width = combo.sizeHint().width()
    for index, text in enumerate(["mean", "mean_segmented", HOST_ITEM, "pyscenedetect"]):
        combo.setItemText(index, text)
    assert combo.sizeHint().width() > empty_width


def test_a_combo_never_sizes_below_the_text_it_paints(qapp):
    """``sizeHint`` must cover the layer's own text rect, or the item elides.

    ``_ComboFieldContentLayer`` paints into ``width - 2·TEXT_HORIZONTAL_PADDING``
    with ``paint_font`` and ``QFontMetrics.elidedText``. A hint that only equals
    ``advance + 2·padding`` lands exactly ON that limit — and Qt elides at a
    limit equal to the advance (measured: limit 106 → "sudo_scene_dete…",
    107 → the whole string). So the hint has to carry the measured text width
    plus the same padding, with room for the elider.
    """
    combo = ComboBox()
    combo.addItem(HOST_ITEM)

    fm = QFontMetrics(paint_font(combo))
    pad = scaled_px(combo.TEXT_HORIZONTAL_PADDING)
    painted_text_width = fm.horizontalAdvance(HOST_ITEM)
    hint = combo.sizeHint().width()

    assert hint >= painted_text_width + 2 * pad, (
        f"sizeHint {hint} < painted {painted_text_width} + padding {2 * pad}"
    )
    text_rect_width = hint - 2 * pad
    assert fm.elidedText(HOST_ITEM, Qt.TextElideMode.ElideRight, text_rect_width) == HOST_ITEM, (
        f"the field would still elide {HOST_ITEM!r} at its own hint width {hint}"
    )
    assert combo.minimumSizeHint().width() >= painted_text_width + 2 * pad


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


def test_qt_range_halves_answer_on_both_variants(qapp):
    """The host's glue calls `setMaximum`/`setMinimum` (Qt's own names) on its spin fields."""
    from sli_ui_toolkit.widgets import Stepper

    for field in (DoubleSpinBox(), Stepper()):
        field.setRange(0, 4) if not isinstance(field, DoubleSpinBox) else field.setRange(0.0, 4.0)
        field.setMaximum(7)
        assert field.maximum() == 7
        field.setMinimum(2)
        assert field.minimum() == 2
        assert field.value() >= 2


def test_a_host_can_point_the_progress_track_at_its_own_token(qapp):
    """A page's render bar is not a toast: the trough token must be the host's."""
    from sli_ui_toolkit.ui.widgets.composite.toast.progress_bar import ToastProgressBar

    bar = ToastProgressBar(track_token="progress.track.background")
    assert bar._track_token == "progress.track.background"
    default = ToastProgressBar()
    assert default._track_token == "toast.progress.background"
