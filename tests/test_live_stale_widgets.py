"""Red-before/green-after: live-stale cached geometry in four toolkit widgets.

``plan-live-appearance-fixes-2026-10-19``. Each widget below cached derived
geometry from its construction-time ``UiScale`` factor (or never re-derived
it at all), so a live Settings → OK appearance change left it at design px
until a rebuild. Each is exercised at factor 1.0 and then 1.5 **live**
(build, ``set_factor``, let the appearance bus coalesce through its
zero-timer) and the cached value is asserted to equal ``scaled_px(design)``
— not merely "it changed". Every assertion in the first four tests fails
against the pre-change source: that is the point of committing the tests
first.

Not in this file: ``CalendarDayButton`` — its floor/hints already re-derive
on the bus and are pinned by
``tests/test_px_ratchet_drain.py::test_calendar_day_button_geometry_re_derives_on_live_scale``.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.ui.managers.ui_metrics import UiMetrics
from sli_ui_toolkit.ui.widgets.atomic.custom_group_widget import CustomGroupWidget
from sli_ui_toolkit.ui.widgets.composite.help_document.view import HelpDocumentView
from sli_ui_toolkit.ui.widgets.composite.simple_options_flyout import (
    SimpleOptionsFlyout,
)
from sli_ui_toolkit.ui.widgets.composite.toast.notification import ToastNotification


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _to_factor(factor: float, qtbot) -> None:
    UiScale.get_instance().set_factor(factor)
    qtbot.wait(20)  # the appearance bus coalesces through a zero-timer


def _margins(layout) -> tuple[int, int, int, int]:
    m = layout.contentsMargins()
    return m.left(), m.top(), m.right(), m.bottom()


# --------------------------------------------------------------------------
# HelpDocumentView: root padding + cached TOC frame inner padding
# --------------------------------------------------------------------------


def test_help_document_view_root_margins_re_derive_on_live_scale(qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    root = view.layout()
    assert root is not None

    assert _margins(root) == (20, 16, 20, 24)
    assert root.spacing() == 10

    _to_factor(1.5, qtbot)

    assert _margins(root) == (30, 24, 30, 36)  # scaled_px((20,16,20,24))
    assert root.spacing() == 15  # scaled_px(10)


def test_help_document_view_toc_frame_margins_re_derive_on_live_scale(qtbot):
    view = HelpDocumentView(show_toc=True)
    qtbot.addWidget(view)
    view.resize(640, 480)
    view.set_markdown("### Alpha {#alpha}\n\ntext\n\n### Beta {#beta}\n\ntext\n")
    toc = view._toc
    assert toc is not None
    layout = toc.layout()
    assert layout is not None

    assert _margins(layout) == (12, 10, 12, 10)
    assert layout.spacing() == 4

    _to_factor(1.5, qtbot)

    toc = view._toc
    assert toc is not None
    layout = toc.layout()
    assert layout is not None
    assert _margins(layout) == (18, 15, 18, 15)  # scaled_px((12,10,12,10))
    assert layout.spacing() == 6  # scaled_px(4)


def test_help_document_view_is_scale_only(qtbot, monkeypatch):
    """The root padding derives from the factor only: a font-only change must
    not wake the handler (over-invalidation is the anti-pattern)."""
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    calls: list[object] = []
    monkeypatch.setattr(view, "_apply_root_metrics", lambda: calls.append(1))

    UiMetrics.get_instance().emit_appearance({"font"})
    qtbot.wait(20)
    assert calls == []

    UiMetrics.get_instance().emit_appearance({"scale"})
    qtbot.wait(20)
    assert calls == [1]


# --------------------------------------------------------------------------
# _SimpleRow (SimpleOptionsFlyout): row horizontal pad
# --------------------------------------------------------------------------


def test_simple_row_horizontal_pad_re_derives_on_live_scale(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(600, 500)
    host.show()
    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)
    flyout.populate(["One", "Two"], current_index=0)
    row = flyout.rows()[0]
    layout = row.layout()
    assert layout is not None

    assert _margins(layout) == (8, 0, 8, 0)

    _to_factor(1.5, qtbot)

    layout = row.layout()
    assert layout is not None
    assert _margins(layout) == (12, 0, 12, 0)  # scaled_px(8)


# --------------------------------------------------------------------------
# ToastNotification: content / progress / action-row design px
# --------------------------------------------------------------------------


def test_toast_margins_re_derive_on_live_scale(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(600, 400)
    toast = ToastNotification(parent=host)
    qtbot.addWidget(toast)
    toast.show_message("Hello", max_width=320)

    assert _margins(toast.main_layout) == (12, 10, 12, 6)
    assert toast.main_layout.spacing() == 0
    assert _margins(toast.progress_layout) == (12, 0, 12, 10)
    assert toast.action_row_layout.spacing() == 6

    _to_factor(1.5, qtbot)

    assert _margins(toast.main_layout) == (18, 15, 18, 9)  # scaled_px((12,10,12,6))
    assert _margins(toast.progress_layout) == (18, 0, 18, 15)
    assert toast.action_row_layout.spacing() == 9  # scaled_px(6)


# --------------------------------------------------------------------------
# CustomGroupWidget (top caption): content margins + spacing
# --------------------------------------------------------------------------


def test_custom_group_widget_top_caption_margins_re_derive_on_live_scale(qtbot):
    group = CustomGroupWidget("Title")
    qtbot.addWidget(group)
    layout = group._content_layout

    m = _margins(layout)
    assert (m[0], m[2], m[3]) == (12, 12, 12)
    assert layout.spacing() == 8

    _to_factor(1.5, qtbot)

    _, title_h = group._get_title_metrics()
    m = _margins(layout)
    assert (m[0], m[2], m[3]) == (18, 18, 18)  # scaled_px(12)
    assert layout.spacing() == 12  # scaled_px(8)
    assert m[1] == int(title_h * 0.8) + 18  # title-derived + scaled_px(12)
