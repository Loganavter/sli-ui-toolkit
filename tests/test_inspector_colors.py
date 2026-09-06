"""Inspector Colors section: color-origin analysis helpers + page render.

The section must answer "why is this widget this color" from the pieces Qt
exposes: candidate QSS rules (background/color/border), the effective
palette roles + autoFillBackground, the ThemeManager tokens behind the
values, and custom painting.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.inspector.colors import (
    first_painting_ancestor,
    has_custom_paint,
    palette_background,
    qss_background_rows,
    qss_border_rows,
    qss_text_rows,
    resolve_qss_value,
    tokens_for_color,
    widget_flags,
)
from sli_ui_toolkit.ui.inspector.qss_scan import QssIndex
from sli_ui_toolkit.ui.inspector.contract import WidgetInspection
from sli_ui_toolkit.ui.inspector.view import InspectorWindow
from sli_ui_toolkit.widgets import Button

_LIGHT = {"Window": "#000000", "surface.background": "#222222", "Text": "#111111"}
_DARK = {"Window": "#000000", "surface.background": "#333333", "Text": "#dddddd"}


@pytest.fixture
def themed(qapp):
    from sli_ui_toolkit import ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(_LIGHT, _DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    yield tm
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]


def test_resolve_qss_value_hex_and_token(qapp, themed):
    assert resolve_qss_value("#123456", themed).name() == "#123456"
    assert resolve_qss_value("@dialog.background", themed).name() == "#222222"
    assert resolve_qss_value("transparent", themed) is None
    assert resolve_qss_value("bogus", themed) is None


def test_qss_property_rows_from_index(qapp, themed):
    index = QssIndex.from_text(
        "\n".join(
            [
                "QWidget#MyPanel {",
                "    background-color: @dialog.background;",
                "    color: #ffffff;",
                "    border: 1px solid #555555;",
                "    border-radius: 8px;",
                "}",
            ]
        ),
        source="/tmp/fake.qss",
    )
    widget = QWidget()
    widget.setObjectName("MyPanel")
    rows = qss_background_rows(index.candidates_for(widget), themed)
    assert len(rows) == 1
    assert rows[0].value == "@dialog.background"
    assert rows[0].color.name() == "#222222"
    assert "fake.qss" in rows[0].origin

    text_rows = qss_text_rows(index.candidates_for(widget), themed)
    assert len(text_rows) == 1
    assert text_rows[0].value == "#ffffff"

    border_rows = qss_border_rows(index.candidates_for(widget), themed)
    props = {row.label for row in border_rows}
    assert {"border", "border-radius"} <= props


def test_tokens_for_color_reverse_lookup(qapp, themed):
    tokens = tokens_for_color(themed, QColor("#222222"))
    assert "surface.background" in tokens
    assert "dialog.background" in tokens  # alias chain
    # ``Window`` aliases to surface.background — the resolver shadows an
    # explicit Window key, so #000000 (the raw Window value) matches no
    # token: this is exactly why stock widgets painted near-black in the
    # app (the app's Window #1e1e1e never wins over the alias).
    tokens = tokens_for_color(themed, QColor("#000000"))
    assert tokens == []


def test_palette_background_and_transparent_chain(qapp, themed):
    parent = QWidget()
    parent.setAutoFillBackground(True)
    child = QWidget(parent)
    role, color, auto_fill = palette_background(child)
    assert auto_fill is False  # plain QWidget without QSS
    assert role == "Window"
    assert first_painting_ancestor(child) is parent


def test_has_custom_paint(qapp):
    assert has_custom_paint(Button(text="x")) is True
    assert has_custom_paint(QWidget()) is False


def test_widget_flags_rows(qapp):
    flags = dict(widget_flags(QWidget()))
    assert flags["autoFillBackground"] == "off"
    assert "WA_StyledBackground" in flags


def _page_labels(window: InspectorWindow, section: str) -> list[str]:
    from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label
    from sli_ui_toolkit.widgets import Button

    page = window._pages[section]
    out: list[str] = []
    for label in page.content_widget.findChildren(Label):
        out.append(label.text())
    for button in page.content_widget.findChildren(Button):
        out.append(str(getattr(button, "_text", "") or ""))
        for row in getattr(button, "_rows", ()) or ():
            out.append(str(getattr(row, "text", "") or ""))
    return out


def test_colors_section_renders(qapp, themed):
    window = InspectorWindow()
    widget = QWidget()
    widget.setObjectName("Probe")
    pane = window._ensure_pane()
    pane.widget = widget
    window.set_inspection(
        WidgetInspection(family="QWidget", config=(), state=()),
        widget=widget,
        theme_manager=themed,
    )
    labels = _page_labels(window, "Colors")
    joined = "\n".join(labels)
    assert "Background" in joined
    assert "palette Window" in joined
    assert "autoFillBackground off" in joined
    assert "#000000" in joined
    # token trace of the palette Window color
    assert "= token" in joined
    assert "Window" in joined
    assert "Paint flags" in joined


def test_colors_section_reports_qss_background(qapp, themed):
    index = QssIndex.from_text(
        "QWidget#Probe { background-color: #336699; color: #ffffff; }",
        source="/tmp/fake.qss",
    )
    window = InspectorWindow()
    widget = QWidget()
    widget.setObjectName("Probe")
    pane = window._ensure_pane()
    pane.widget = widget
    window.set_inspection(
        WidgetInspection(family="QWidget", config=(), state=()),
        widget=widget,
        theme_manager=themed,
        qss_candidates=index.candidates_for(widget),
        token_sources={"surface.background": "themes.json:81"},
    )
    labels = _page_labels(window, "Colors")
    joined = "\n".join(labels)
    assert "#336699" in joined
    assert "QSS" in joined
    assert "fake.qss:1" in joined
    assert "#ffffff" in joined