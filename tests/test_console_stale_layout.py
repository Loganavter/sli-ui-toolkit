"""ConsoleView — a pane laid out while it was hidden must describe the width it actually has.

Owner report (2026-11-28, the Logs tab): the restored log came up with a wrap and a scroll range built for a viewport it
did not have — the thumb implied far more text than existed, wrapped rows were chopped, and the scrollbar sat at its
default rect over the first rows — and ONE appended line fixed all of it at once. Both holes were a layout that nothing
but an append re-validated: a width that moved with no resize event reaching the widget, and a show that never
re-requested the bar's position.

The expectation in every test below is stated against a FRESH view built at the final size: that is what "the same
view, laid out where it really is" means, without hard-coding row counts that depend on the platform font.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QTabWidget, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.composite.console_view import ConsoleView

_BODY = "\n".join(
    [
        "2026-11-28 10:11:12 [INFO] engine: /models/tensorrt/rtdetr-l_opt-b4_tiling-dev16.engine loaded ok",
        "2026-11-28 10:11:13 [INFO] warmup pass done, 42 frames, mean 18.3 ms per frame across the whole batch",
        "2026-11-28 10:11:14 [WARN] fallback to cudaMallocAsync pool because the stream allocator was unavailable",
    ]
    * 8
)


def _fresh_view(qtbot, width: int, height: int) -> ConsoleView:
    """A view built at the final size — the reference the stale one has to match."""
    fresh = ConsoleView()
    qtbot.addWidget(fresh)
    fresh.resize(width, height)
    fresh.setPlainText(_BODY)
    return fresh


def _rows(view: ConsoleView) -> list[str]:
    return [visual.text for visual in view.visual_lines()]


def _expected_bar_rect(view: ConsoleView) -> tuple[int, int, int, int]:
    return (
        view.width() - view._scroll_reserve,
        view._pad,
        view._scroll_reserve,
        max(1, view.height() - 2 * view._pad),
    )


def test_tab_switch_rewraps_at_the_real_width_and_places_the_bar(qtbot):
    """The reported shape: the console lives on a non-current tab while the log arrives."""
    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    view = ConsoleView()
    layout.addWidget(view)
    tabs.addTab(QWidget(), "other")
    tabs.addTab(page, "Logs")
    tabs.setCurrentIndex(0)
    tabs.resize(420, 210)

    view.setPlainText(_BODY)
    built_width = view._content_width()
    tabs.show()
    QApplication.processEvents()

    tabs.resize(320, 210)
    QApplication.processEvents()
    tabs.setCurrentIndex(1)
    QApplication.processEvents()

    assert view._content_width() != built_width, "the tab switch must actually change the wrap width"
    fresh = _fresh_view(qtbot, view.width(), view.height())

    # The wrap is the one the real width asks for, not the one the hidden page kept.
    assert _rows(view) == _rows(fresh)
    assert len(view.visual_lines()) == len(fresh.visual_lines())
    # The range describes the content that is on screen: it overflows, and by exactly the painted height surplus.
    assert view._vbar.maximum() > 0
    assert view._vbar.maximum() == view._content_height() - view.height()
    assert view._vbar.maximum() == fresh._vbar.maximum()
    # The bar is where the console draws it - not at its construction-time default rect over the first rows.
    assert tuple(view._vbar.geometry().getRect()) == _expected_bar_rect(view)


def test_hidden_console_describes_the_real_width_before_and_after_it_is_shown(qtbot):
    """No tab host: a pane resized while hidden is asked for its range before it is shown (restore + pin to bottom)."""
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 220)
    view = ConsoleView(host)
    view.setPlainText(_BODY)
    built_width = view._content_width()

    view.resize(380, 220)
    assert view._content_width() != built_width, "the resize must actually change the wrap width"
    fresh = _fresh_view(qtbot, view.width(), view.height())

    # Read BEFORE the show: this is the state a host pins to the bottom from, and the layout must already be current.
    assert _rows(view) == _rows(fresh)
    assert view._vbar.maximum() == fresh._vbar.maximum()
    assert view.verticalScrollBar().maximum() == view._content_height() - view.height()

    host.show()
    view.show()
    QApplication.processEvents()

    assert _rows(view) == _rows(fresh)
    assert view._vbar.maximum() == view._content_height() - view.height()
    assert tuple(view._vbar.geometry().getRect()) == _expected_bar_rect(view)
