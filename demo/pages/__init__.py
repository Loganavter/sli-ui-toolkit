"""Demo gallery pages."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


def build_pages() -> list[tuple[str, QWidget]]:
    """Construct all gallery pages in display order.

    Heavy imports are deferred so a single broken page doesn't crash the whole demo.
    """
    pages: list[tuple[str, QWidget]] = []

    def _add(label: str, factory):
        try:
            pages.append((label, factory()))
        except Exception as exc:  # pragma: no cover - dev-only safety net
            from sli_ui_toolkit.widgets import Label
            stub = Label(f"{label} page failed: {exc!r}", pixel_size=11)
            stub.setWordWrap(True)
            pages.append((label, stub))

    from demo.pages.home_page import HomePage
    from demo.pages.buttons_page import ButtonsPage
    from demo.pages.inputs_page import InputsPage
    from demo.pages.comboboxes_page import ComboBoxesPage
    from demo.pages.labels_page import LabelsPage
    from demo.pages.lists_page import ListsPage
    from demo.pages.composites_page import CompositesPage
    from demo.pages.flyouts_page import FlyoutsPage
    from demo.pages.dialogs_page import DialogsPage
    from demo.pages.feedback_page import FeedbackPage
    from demo.pages.charts_page import ChartsPage
    from demo.pages.console_page import ConsolePage
    from demo.pages.misc_page import MiscPage

    _add("Home", HomePage)
    _add("Buttons", ButtonsPage)
    _add("Basic Inputs", InputsPage)
    _add("ComboBoxes", ComboBoxesPage)
    _add("Labels & Text", LabelsPage)
    _add("Lists & Items", ListsPage)
    _add("Composites", CompositesPage)
    _add("Flyouts", FlyoutsPage)
    _add("Dialogs", DialogsPage)
    _add("Feedback", FeedbackPage)
    _add("Charts", ChartsPage)
    _add("Console", ConsolePage)
    _add("Misc", MiscPage)
    return pages
