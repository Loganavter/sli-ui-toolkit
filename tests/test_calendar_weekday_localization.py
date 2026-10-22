"""Calendar weekday labels must come from the catalog, not English literals.

Same class as the switch state text (owner report 2026-10-22): the widget asked
for bare ``weekday_mon`` … keys that no catalog ever defined, so the labels were
always English. They now use ``common.calendar.weekday.<day>``, which the host
catalogs carry.
"""

from __future__ import annotations

import json

import pytest

from sli_ui_toolkit import TranslationManager, emit_language_changed
from sli_ui_toolkit.i18n import configure_i18n
from sli_ui_toolkit.widgets import CalendarWidget


@pytest.fixture(autouse=True)
def _restore_i18n_backend(qapp):
    mgr = TranslationManager()
    saved = (
        getattr(mgr, "_custom_translator", None),
        getattr(mgr, "_language_provider", None),
        mgr._current_lang,
    )
    yield
    mgr._custom_translator = saved[0]
    mgr._language_provider = saved[1]
    mgr._current_lang = saved[2]


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / "app"
    (root / "en").mkdir(parents=True)
    (root / "en" / "common.json").write_text(
        json.dumps({"common": {"calendar": {"weekday": {"mon": "Mon"}}}}), encoding="utf-8"
    )
    (root / "ru").mkdir(parents=True)
    (root / "ru" / "common.json").write_text(
        json.dumps(
            {
                "common": {
                    "calendar": {
                        "weekday": {
                            "mon": "Пн", "tue": "Вт", "wed": "Ср", "thu": "Чт",
                            "fri": "Пт", "sat": "Сб", "sun": "Вс",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    configure_i18n(i18n_root=root)
    emit_language_changed("ru")
    return root


def test_the_weekday_labels_are_localized(catalog, qtbot):
    widget = CalendarWidget()
    qtbot.addWidget(widget)

    assert list(widget._weekday_names) == ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"], (
        "weekday labels must resolve from common.calendar.weekday.*, not the English default"
    )
