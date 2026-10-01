"""SimpleOptionsFlyout settles derived sizes synchronously (qt-selfsizing T1).

``geometry.update_size`` fixes the flyout + container from live row hints
while ``QLayout``s place the children. Without a synchronous settle the rows
keep stale geometry for one painted frame (growing exposes it, shrinking
hides it).

Note on scope: only *reused* rows can settle in the same call — widgets
freshly inserted into a shown layout are positioned by the event loop no
matter what (verified with probes in ``.agent/scratch/probe_bisect.py``:
manual ``invalidate()+activate()`` is a no-op for fresh insertions, on
plain layouts and in scroll areas alike). The tests below therefore mutate
a reused row's hint-affecting state and assert child geometry/hint
agreement in the same synchronous call — no ``processEvents()`` between
the mutation and the assertions.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.composite.simple_options_flyout import (
    SimpleOptionsFlyout,
)


def _visible_flyout(qtbot, labels: list[str]) -> SimpleOptionsFlyout:
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(500, 400)
    host.show()
    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)
    flyout.populate(labels)
    flyout.show()
    qtbot.wait(30)
    qtbot.wait(30)
    return flyout


def _assert_width_agreement(flyout: SimpleOptionsFlyout) -> None:
    """Rows fill the rows-container, which fills the container (same call)."""
    rows = list(flyout.rows())
    assert rows, "expected installed rows"
    margins = flyout.content_layout.contentsMargins()
    assert flyout._rows_container.width() == (
        flyout.container.width() - margins.left() - margins.right()
    ), (
        f"rows-container/container mismatch: {flyout._rows_container.width()} "
        f"vs container {flyout.container.width()}"
    )
    for row in rows:
        assert row.width() == flyout._rows_container.width(), (
            f"row/container mismatch: row={row.width()} "
            f"container={flyout._rows_container.width()}"
        )


def test_widen_settles_rows_same_call(qtbot):
    flyout = _visible_flyout(qtbot, ["Alpha", "Beta"])
    base_w = flyout.container.width()

    flyout.rows()[0].label.setText("A very long interpolation mode label here")
    flyout._update_size()
    # No processEvents() between the mutation and these assertions.
    assert flyout.container.width() > base_w
    _assert_width_agreement(flyout)


def test_narrow_settles_rows_same_call(qtbot):
    flyout = _visible_flyout(qtbot, ["Alpha", "Beta"])
    flyout.rows()[0].label.setText("A very long interpolation mode label here")
    flyout._update_size()
    qtbot.wait(30)
    grown_w = flyout.container.width()

    flyout.rows()[0].label.setText("A")
    flyout.rows()[1].label.setText("B")
    flyout._update_size()
    # No processEvents() between the mutation and these assertions.
    assert flyout.container.width() < grown_w
    _assert_width_agreement(flyout)
