"""A swept consumer re-derives cached font geometry from the metrics bus.

Wave T2b of ``plan-ui-metrics-systemic`` replaced raw
``UiScale.scale_changed`` / ``UiFont.font_changed`` subscriptions in the
contract's offender list with :func:`connect_ui_metrics`. ``TopTabBar`` is
the reference consumer for the sweep: out of ``expand_tabs`` mode it caches
each tab's width from ``TopTabButton.sizeHint()`` (painted text metrics), so
a UI font that lands after construction must re-fit the strip — the exact
stale-geometry class the old single-signal wiring missed.

Falsification: remove the ``connect_ui_metrics`` call in
``top_tab_bar/bar.py`` and the re-fit assertion below stays stale (the
button keeps its construction-time ``setFixedWidth``). Restore it and the
fixed width matches the freshly resolved hint.
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.managers import UiFont
from sli_ui_toolkit.widgets import TopTabBar

_TITLE = "A reasonably long tab title"


def _let_bus_settle(qapp) -> None:
    """Run the coalescing zero-timer and the emission it schedules.

    ``emit_appearance`` schedules one flush on the next event-loop turn; the
    ``changed`` emission that flush performs lands on the turn after.
    """
    qapp.processEvents()
    qapp.processEvents()


def test_top_tab_bar_refits_cached_width_on_font_change(qapp, qtbot):
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    manager = UiFont.get_instance()
    previous_app = QFont(app.font())
    previous_override = manager._family_override
    try:
        # Small UI font at construction: the tab button caches this width as
        # a fixed-width constraint (``setFixedWidth(sizeHint().width())``).
        app.setFont(QFont(previous_app.family(), 10))
        manager.sync_from_application()
        _let_bus_settle(qapp)

        bar = TopTabBar()
        qtbot.addWidget(bar)
        bar.add_item(_TITLE)
        button = bar._tabs[0].button
        stale = button.maximumWidth()
        assert stale == button.sizeHint().width()

        # The host corrects the app font a beat later (startup font landing).
        app.setFont(QFont(previous_app.family(), 24))
        manager.sync_from_application()
        _let_bus_settle(qapp)

        refit = button.sizeHint().width()
        assert refit > stale, "the larger font must widen the size hint"
        assert button.maximumWidth() == refit, (
            "the tab width must be re-stamped from the larger font metrics; "
            f"stayed at {button.maximumWidth()} (fresh hint {refit})"
        )
    finally:
        manager._family_override = previous_override
        app.setFont(previous_app)
        manager.sync_from_application()
        _let_bus_settle(qapp)
