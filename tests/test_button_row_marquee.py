"""Shared marquee helper + ButtonRow/Label wiring."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QImage, QPainter

from sli_ui_toolkit.ui.widgets.atomic import Label
from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonRegion, ButtonRow, VerticalSplit
from sli_ui_toolkit.ui.widgets.helpers.marquee_text import (
    apply_marquee,
    draw_marquee_text,
    text_overflows,
)


def _render(widget, size=(120, 48)) -> QImage:
    widget.resize(*size)
    widget.show()
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image, QPoint(0, 0))
    return image


def test_text_overflows_helper(qapp):
    from PySide6.QtGui import QFontMetrics

    fm = QFontMetrics(QFont())
    assert not text_overflows(fm, "ok", 400)
    assert text_overflows(fm, "x" * 200, 40)


def test_draw_marquee_text_does_not_raise(qapp):
    image = QImage(80, 24, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setFont(QFont())
    draw_marquee_text(
        painter,
        QRect(0, 0, 80, 24),
        "a long label that will not fit in eighty pixels easily",
        phase=12.0,
    )
    painter.end()


def test_button_row_marquee_uses_shared_driver(qapp):
    long_text = "Сравнение изображений " * 4
    btn = Button(
        regions=[
            ButtonRegion(
                id="text",
                rows=[
                    ButtonRow(text="2m ago", size=11, h_align=Qt.AlignmentFlag.AlignLeft),
                    ButtonRow(
                        text=long_text,
                        size=11,
                        h_align=Qt.AlignmentFlag.AlignLeft,
                        marquee=True,
                    ),
                ],
            )
        ],
        split=VerticalSplit(),
        size=(100, 56),
        content_padding=(8, 4, 8, 4),
    )
    btn._rows_compact = True
    _render(btn, size=(100, 56))
    qapp.processEvents()
    driver = btn._marquee_driver
    assert driver._timer.isActive()
    phase0 = driver.phase
    driver._tick()
    assert driver.phase > phase0
    btn.hide()
    assert not driver._timer.isActive()
    btn.deleteLater()


def test_label_marquee_flag(qapp):
    label = Label("A" * 80, marquee=True, pixel_size=12)
    label.resize(60, 24)
    label.show()
    qapp.processEvents()
    _render(label, size=(60, 24))
    qapp.processEvents()
    assert label.marquee() is True
    assert label._marquee_driver._timer.isActive()
    label.setMarquee(False)
    assert not label._marquee_driver._timer.isActive()
    label.deleteLater()


def test_apply_marquee_on_plain_label(qapp):
    from PySide6.QtWidgets import QLabel

    label = QLabel("B" * 80)
    apply_marquee(label)
    label.resize(50, 20)
    label.show()
    qapp.processEvents()
    _render(label, size=(50, 20))
    qapp.processEvents()
    assert label._marquee_driver._timer.isActive()
    label.deleteLater()
