"""MetricsContainer template order = derived -> children -> updateGeometry/update.

The metrics analogue of ``ThemedContainer``: subclasses split the refresh into
two ordered steps and the base schedules the layout/repaint last, so children
are re-driven only after the parent's derived geometry is fresh.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets import MetricsContainer


def test_template_order(qapp):
    events: list[str] = []

    class _Probe(MetricsContainer, QWidget):
        def on_metrics_derived(self) -> None:
            events.append("derived")

        def on_metrics_children(self) -> None:
            events.append("children")

        def updateGeometry(self) -> None:
            events.append("updateGeometry")
            super().updateGeometry()

        def update(self, *args) -> None:  # type: ignore[override]
            events.append("update")
            super().update(*args)

    probe = _Probe()
    events.clear()
    probe.on_ui_metrics_changed()
    assert events == ["derived", "children", "updateGeometry", "update"]


def test_default_steps_are_noops(qapp):
    class _Bare(MetricsContainer, QWidget):
        pass

    bare = _Bare()
    bare.on_metrics_derived()
    bare.on_metrics_children()
    bare.on_ui_metrics_changed()  # must not raise
