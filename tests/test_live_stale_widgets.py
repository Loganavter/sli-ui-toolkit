"""Red-before/green-after: live-stale cached geometry in toolkit widgets.

``plan-live-appearance-fixes-2026-10-19``. Each widget below cached derived
geometry from its construction-time ``UiScale`` factor (or never re-derived
it at all), so a live Settings → OK appearance change left it at design px
until a rebuild. Each is exercised at factor 1.0 and then 1.5 **live**
(build, ``set_factor``, let the appearance bus coalesce through its
zero-timer) and the cached value is asserted to equal ``scaled_px(design)``
— not merely "it changed". Every assertion fails against the pre-change
source: that is the point of committing the tests first.

The retired ``HelpDocumentView`` cases (root padding, TOC frame inner
padding) are gone with the widget: the document engine's own re-layout on a
live scale is pinned by
``tests/test_help_document_scale.py::test_help_document_reflows_and_grows_with_ui_scale``,
and the TOC frame was host chrome the toolkit no longer ships.

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
