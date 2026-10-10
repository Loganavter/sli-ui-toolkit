"""MarkdownHelpDialog on the painted TextView (no QTextBrowser).

The dialog renders each help section through ``TextView.set_markdown``
(document mode) instead of a ``markdown``-to-HTML ``QTextBrowser``:
headings/anchors resolve in-page, external links open, and the page TOC is
generated (markdown) for pages with ≥2 ``###`` headings.
"""

from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser

from sli_ui_toolkit.ui.widgets.composite.markdown_help_dialog import (
    MarkdownHelpDialog,
    MarkdownHelpPageView,
    MarkdownHelpSection,
    build_toc_markdown,
    inject_heading_anchors,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.widget import TextView


def _page(dialog: MarkdownHelpDialog) -> MarkdownHelpPageView:
    page = dialog.scroll_area.widget()
    assert isinstance(page, MarkdownHelpPageView)
    return page


def _dialog_with(*bodies: str) -> MarkdownHelpDialog:
    sections = [
        MarkdownHelpSection(
            order=index + 1,
            slug=f"section-{index + 1}",
            title=f"Section {index + 1}",
            body_md=body,
        )
        for index, body in enumerate(bodies)
    ]
    return MarkdownHelpDialog(sections=sections)


def test_inject_heading_anchors_slugifies_and_dedupes():
    md = "# Title\n\n### Alpha Beta\n\n### Alpha  Beta\n\n#### Explicit {#kept}\n"
    out = inject_heading_anchors(md, fallback_prefix="page")
    assert "### Alpha Beta {#alpha-beta}" in out
    assert "### Alpha  Beta {#alpha-beta-2}" in out
    assert "#### Explicit {#kept}" in out


def test_build_toc_markdown_threshold():
    two = "### One {#one}\n\n### Two {#two}\n\nBody.\n"
    assert build_toc_markdown(two, title="On this page")
    one = "### One {#one}\n\nBody.\n"
    assert build_toc_markdown(one, title="On this page") == ""


def test_dialog_page_is_painted_text_view(qapp):
    dialog = _dialog_with("## Intro\n\nBody text.\n")
    dialog.resize(900, 600)
    dialog.show()
    qapp.processEvents()

    page = _page(dialog)
    assert isinstance(page, TextView)
    assert not isinstance(page, QTextBrowser)
    assert page.is_document()

    # Heading content renders (plain text carries the heading + body).
    plain = page.plain_text()
    assert "Intro" in plain
    assert "Body text." in plain


def test_internal_anchor_resolves_and_missing_is_none(qapp):
    dialog = _dialog_with(
        "## Intro\n\n### First Heading {#first}\n\n### Second Heading {#second}\n\nBody.\n"
    )
    dialog.resize(900, 600)
    dialog.show()
    qapp.processEvents()

    page = _page(dialog)
    assert page.anchor_y("first") is not None
    assert page.anchor_y("second") is not None
    assert page.anchor_y("does-not-exist") is None
    assert page.scroll_to_anchor("first") is True
    assert page.scroll_to_anchor("does-not-exist") is False

    # The old accessor is reproduced through the new one.
    assert page.anchor_vertical_offset("first") == page.anchor_y("first")


def test_toc_present_for_two_h3_sections(qapp):
    dialog = _dialog_with(
        "### One {#one}\n\n### Two {#two}\n\nBody under the second heading.\n"
    )
    dialog.resize(900, 600)
    dialog.show()
    qapp.processEvents()

    page = _page(dialog)
    plain = page.plain_text()
    assert "On this page" in plain
    assert "One" in plain and "Two" in plain


def test_external_link_opens_via_desktop_services(qapp, monkeypatch):
    from sli_ui_toolkit.ui.widgets.composite import markdown_help_dialog as mod

    opened: list[str] = []
    monkeypatch.setattr(
        mod.QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )

    dialog = _dialog_with("See [docs](https://example.com/help).\n")
    dialog.resize(900, 600)
    dialog.show()
    qapp.processEvents()

    dialog._on_link_activated("https://example.com/help")
    assert opened == ["https://example.com/help"]


def test_internal_link_scrolls_current_page(qapp, monkeypatch):
    dialog = _dialog_with(
        "## Intro\n\n"
        + "\n\n".join(f"Paragraph line {i}." for i in range(40))
        + "\n\n### Deep Target {#deep}\n\nAfter.\n"
    )
    dialog.resize(900, 300)
    dialog.show()
    qapp.processEvents()

    page = _page(dialog)
    y = page.anchor_y("deep")
    assert y is not None and y > 0

    dialog._on_link_activated("#deep")
    qapp.processEvents()
    assert dialog.scroll_area.verticalScrollBar().value() > 0
