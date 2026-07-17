"""CSD rounded masks must be HiDPI-safe and dense enough not to staircase."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QBitmap, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.windows.rounded_body import (
    apply_rounded_window_mask,
    apply_top_trailing_rounded_mask,
    rounded_window_path,
)


def test_rounded_window_mask_excludes_corners():
    app = QApplication.instance() or QApplication([])
    widget = QWidget()
    widget.resize(400, 300)
    widget.show()
    app.processEvents()

    apply_rounded_window_mask(widget, radius=10.0, squared=False)
    mask = widget.mask()
    assert not mask.isEmpty()
    assert isinstance(mask, (QRegion, QBitmap)) or mask is not None

    # Corner outside the rounded silhouette must be excluded.
    assert not mask.contains(widget.rect().topLeft())
    assert mask.contains(widget.rect().center())


def test_rounded_window_mask_clears_when_squared():
    app = QApplication.instance() or QApplication([])
    widget = QWidget()
    widget.resize(400, 300)
    widget.show()
    app.processEvents()

    apply_rounded_window_mask(widget, radius=10.0, squared=False)
    assert not widget.mask().isEmpty()
    apply_rounded_window_mask(widget, radius=10.0, squared=True)
    assert widget.mask().isEmpty()


def test_top_trailing_mask_keeps_top_left_of_controls():
    app = QApplication.instance() or QApplication([])
    widget = QWidget()
    widget.resize(138, 36)
    widget.show()
    app.processEvents()

    apply_top_trailing_rounded_mask(widget, radius=10.0, squared=False)
    mask = widget.mask()
    assert not mask.isEmpty()
    # Top-left of the control cluster is interior to the window curve.
    assert mask.contains(widget.rect().topLeft())
    # Top-right outside the arc is excluded.
    assert not mask.contains(widget.rect().topRight())


def test_rounded_path_has_curves():
    path = rounded_window_path(QRectF(0, 0, 400, 300), radius=10.0, squared=False)
    assert not path.isEmpty()
    assert path.elementCount() > 4
