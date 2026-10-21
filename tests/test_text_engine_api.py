"""Text engine-mode API (P2b): context menu, external links, scroll_to_text,
set_blocks, resolve_asset ctor+setter, selectionChanged, typography, and
content-height re-layout inside a real QScrollArea.

Falsification notes per test describe what the pre-change code does instead.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QContextMenuEvent, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication, QScrollArea

from sli_ui_toolkit.ui.widgets.text.engine.canvas import TextCanvasCore as TextCanvas
from sli_ui_toolkit.ui.widgets.text.engine.markdown import parse_help_blocks
from sli_ui_toolkit.ui.widgets.text import text as text_module
from sli_ui_toolkit.widgets import Text, TextConfig

_WHITE = QColor(255, 255, 255)
_DOC = "# Title\n\nSome **bold** words and a [link](help://x).\n"


def _grab(widget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(_WHITE)
    widget.render(image)
    return image


def _pixel_diff(a: QImage, b: QImage) -> int:
    assert a.size() == b.size()
    return sum(
        1
        for x in range(a.width())
        for y in range(a.height())
        if a.pixelColor(x, y) != b.pixelColor(x, y)
    )


def _mouse(kind, x: float, y: float) -> QMouseEvent:
    pos = QPointF(x, y)
    return QMouseEvent(kind, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def _show(widget, width=360, height=200):
    widget.resize(width, height)
    widget.show()
    QApplication.processEvents()
    return widget


class _FakeDesktopServices:
    def __init__(self) -> None:
        self.opened: list[str] = []

    def openUrl(self, url) -> bool:  # noqa: N802 - Qt API name
        self.opened.append(url.toString())
        return True


# -- context menu signal ----------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [{"mode": "plain"}, {"mode": "document"}, {"mode": "code"}],
)
def test_right_click_emits_text_context_menu_requested(qapp, kwargs):
    """Falsification: the pre-change Text has no ``textContextMenuRequested``
    signal (AttributeError), and an engine-mode right-click never reaches it."""
    widget = _show(Text("menu me" if kwargs["mode"] != "document" else _DOC, **kwargs))
    received: list[QPoint] = []
    widget.textContextMenuRequested.connect(received.append)
    target = widget._engine if widget._engine is not None else widget
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5), QPoint(105, 205))
    QApplication.sendEvent(target, event)
    assert received == [QPoint(105, 205)]


# -- open_external_links ----------------------------------------------------


def test_external_link_opens_by_default_and_emits(qapp, monkeypatch):
    """Falsification: pre-change nothing opens http(s) links from the engine."""
    fake = _FakeDesktopServices()
    monkeypatch.setattr(text_module, "QDesktopServices", fake)
    widget = _show(Text(_DOC, mode="document"))
    links: list[str] = []
    widget.linkActivated.connect(links.append)
    widget._engine.linkActivated.emit("https://example.com/a")
    widget._engine.linkActivated.emit("help://x")
    assert links == ["https://example.com/a", "help://x"]
    assert fake.opened == ["https://example.com/a"]


def test_open_external_links_false_emits_but_does_not_open(qapp, monkeypatch):
    fake = _FakeDesktopServices()
    monkeypatch.setattr(text_module, "QDesktopServices", fake)
    widget = _show(Text(_DOC, mode="document", open_external_links=False))
    links: list[str] = []
    widget.linkActivated.connect(links.append)
    widget._engine.linkActivated.emit("https://example.com/a")
    assert links == ["https://example.com/a"]
    assert fake.opened == []


def test_open_external_links_setter_and_config(qapp, monkeypatch):
    fake = _FakeDesktopServices()
    monkeypatch.setattr(text_module, "QDesktopServices", fake)
    widget = Text(_DOC, mode="document")
    widget.set_open_external_links(False)
    widget._engine.linkActivated.emit("https://a.test")
    assert fake.opened == []
    config_widget = Text(config=TextConfig(text=_DOC, mode="document", open_external_links=False))
    config_widget._engine.linkActivated.emit("https://b.test")
    assert fake.opened == []
    assert TextConfig().open_external_links is True


# -- scroll_to_text ---------------------------------------------------------

_LONG = "# Top\n\n" + "\n\n".join(f"Paragraph {i} filler text." for i in range(20)) + (
    "\n\n### Deep\n\nThe Needle sits here.\n"
)


def test_scroll_to_text_returns_y_and_highlights_match(qapp):
    """Falsification: pre-change Text has no ``scroll_to_text``."""
    widget = _show(Text(_LONG, mode="document", selectable=True), width=360, height=120)
    y = widget.scroll_to_text("needle")
    assert isinstance(y, int) and not isinstance(y, bool)
    assert y > 0
    assert "needle" in widget.selected_plain_text().lower()
    assert widget.hasSelectedText() is True
    top = widget.scroll_to_text("Top")
    assert top is not None and top < y


def test_scroll_to_text_absent_or_empty_clears_selection(qapp):
    widget = _show(Text(_LONG, mode="document", selectable=True), width=360, height=120)
    widget.scroll_to_text("needle")
    assert widget.scroll_to_text("no such phrase xyz") is None
    assert widget.hasSelectedText() is False
    widget.scroll_to_text("needle")
    assert widget.scroll_to_text("") is None
    assert widget.hasSelectedText() is False


def test_scroll_to_text_requires_document_mode(qapp):
    with pytest.raises(RuntimeError, match='mode="document"'):
        Text("plain").scroll_to_text("x")


# -- set_blocks -------------------------------------------------------------


def test_set_blocks_replaces_document_content(qapp):
    """Falsification: pre-change Text has no ``set_blocks``."""
    widget = _show(Text("", mode="document"))
    widget.set_blocks(parse_help_blocks("# Blocks\n\nfrom parsed blocks\n"))
    assert "from parsed blocks" in widget.text()
    widget.set_blocks(())
    assert widget.text() == ""


def test_set_blocks_matches_set_markdown_pixels(qapp):
    widget = _show(Text("", mode="document"))
    widget.set_blocks(parse_help_blocks(_DOC))
    reference = _show(TextCanvas(""))
    reference.set_document(_DOC)
    QApplication.processEvents()
    assert _pixel_diff(_grab(widget), _grab(reference)) == 0


# -- resolve_asset ctor + setter -------------------------------------------

_IMG_DOC = "# Pic\n\n![alt text](figure.png)\n"


def test_resolve_asset_ctor_kwarg_is_used_for_images(qapp):
    """Falsification: pre-change the resolver is only consulted per call, so
    the resolver passed to the constructor is not invoked by layout."""
    calls: list[str] = []

    def resolver(path):
        calls.append(path)
        return None

    _show(Text(_IMG_DOC, mode="document", resolve_asset=resolver))
    assert "figure.png" in calls


def test_resolve_asset_setter_relayouts_with_new_resolver(qapp):
    """Falsification: pre-change Text has no ``set_resolve_asset`` setter."""
    first: list[str] = []
    second: list[str] = []
    widget = _show(Text(_IMG_DOC, mode="document", resolve_asset=lambda p: first.append(p)))
    first.clear()
    widget.set_resolve_asset(lambda p: second.append(p))
    QApplication.processEvents()
    assert "figure.png" in second
    assert first == []


def test_resolve_asset_setter_exists_in_plain_mode(qapp):
    widget = Text("caption")
    widget.set_resolve_asset(lambda p: None)
    assert widget.text() == "caption"


# -- selectionChanged in engine modes --------------------------------------


def test_code_mode_selection_changed_fires_on_change_only(qapp):
    """Falsification: pre-change the engine's selection is not forwarded, so
    the count stays zero."""
    widget = _show(Text("alpha\nbeta", mode="code", editable=True))
    emitted: list[bool] = []
    widget.selectionChanged.connect(lambda: emitted.append(True))
    widget.selectAll()
    widget.selectAll()
    assert len(emitted) == 1
    widget.clear_selection()
    assert len(emitted) == 2
    widget.clear_selection()
    assert len(emitted) == 2


def test_code_mode_drag_emits_selection_changed(qapp):
    widget = _show(Text("hello world", mode="code", editable=True), width=260, height=60)
    emitted: list[bool] = []
    widget.selectionChanged.connect(lambda: emitted.append(True))
    engine = widget._engine
    x0 = 12
    y = 10
    x1 = 60
    QApplication.sendEvent(engine, _mouse(QEvent.Type.MouseButtonPress, x0, y))
    QApplication.sendEvent(engine, _mouse(QEvent.Type.MouseMove, x1, y))
    QApplication.sendEvent(engine, _mouse(QEvent.Type.MouseButtonRelease, x1, y))
    assert widget.hasSelectedText() is True
    assert len(emitted) >= 1


def test_document_select_all_and_scroll_emit_selection_changed(qapp):
    widget = _show(Text(_DOC, mode="document", selectable=True))
    emitted: list[bool] = []
    widget.selectionChanged.connect(lambda: emitted.append(True))
    widget.select_all_text()
    widget.select_all_text()
    assert len(emitted) == 1
    widget.scroll_to_text("bold")
    assert len(emitted) == 2
    widget.clear_selection()
    assert len(emitted) == 3


# -- typography in engine modes --------------------------------------------


def test_code_default_typography_is_unchanged_parity(qapp):
    """Default engine typography must not move: pixel parity with a bare
    TextCanvas for the same text and size (guards the new font plumbing)."""
    widget = _show(Text("print value", mode="code"), width=220, height=60)
    reference = _show(TextCanvas("print value"), width=220, height=60)
    QApplication.processEvents()
    assert _pixel_diff(_grab(widget), _grab(reference)) == 0


def test_code_pixel_size_bold_and_family_are_honored(qapp):
    """Falsification: pre-change the engine ignores pixel_size/bold/family
    (its font stays at the 12 px fixed default)."""
    plain = Text("xyz", mode="code")
    big = Text("xyz", mode="code", pixel_size=22, bold=True, family="Monospace")
    assert plain._engine._font.pixelSize() == 12
    assert big._engine._font.pixelSize() == 22
    assert big._engine._font.bold() is True
    assert big._engine._font.family() == "Monospace"


def test_code_variant_pixel_size_applies(qapp):
    assert Text("x", mode="code", variant="caption")._engine._font.pixelSize() == 11


def test_code_explicit_color_is_painted(qapp):
    """Falsification: pre-change the engine always paints the theme foreground,
    so no pixel of the requested color appears."""
    def magenta_pixels(image: QImage) -> int:
        return sum(
            1
            for x in range(image.width())
            for y in range(image.height())
            if (c := image.pixelColor(x, y)).red() - c.green() > 40
            and c.blue() - c.green() > 40
        )

    default = _show(Text("xxxx", mode="code"), width=200, height=40)
    tinted = _show(Text("xxxx", mode="code", color=QColor(200, 0, 200)), width=200, height=40)
    assert magenta_pixels(_grab(default)) == 0
    assert magenta_pixels(_grab(tinted)) > 0


def test_document_pixel_size_changes_body_layout(qapp):
    """Falsification: pre-change document mode ignores pixel_size, so the
    layout height is identical to the default."""
    default = _show(Text(_DOC, mode="document"), width=360, height=200)
    large = _show(Text(_DOC, mode="document", pixel_size=24), width=360, height=200)
    assert large._engine.minimumHeight() > default._engine.minimumHeight()


def test_document_family_override_reaches_layout(qapp):
    """Falsification: pre-change document mode ignores ``family``, so every
    installed family lays out at the default height."""
    from PySide6.QtGui import QFontDatabase

    body = "Some words in a body paragraph that wraps across the width. " * 6
    doc = "# Title\n\n" + body
    keep: list[Text] = []

    def height_for(**kwargs) -> int:
        widget = _show(Text(doc, mode="document", **kwargs), width=360, height=200)
        keep.append(widget)
        return widget._engine.minimumHeight()

    default_height = height_for()
    heights = {family: height_for(family=family) for family in QFontDatabase.families()[:8]}
    families = QFontDatabase.families()
    if len(families) < 2:
        pytest.skip("needs at least two installed font families")
    assert any(h != default_height for h in heights.values())


# -- content-height re-layout inside a real QScrollArea -----------------------


@pytest.mark.parametrize("mode", ["document", "code"])
def test_content_growth_relayouts_host_in_scroll_area(qapp, mode):
    """Falsification: pre-change the engine's new minimum height never reaches
    the host Text, so the host keeps the viewport height, the engine is clipped
    and the scroll range stays 0."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    widget = Text("" if mode == "document" else "short", mode=mode)
    scroll.setWidget(widget)
    scroll.resize(300, 150)
    scroll.show()
    QApplication.processEvents()
    if mode == "document":
        widget.set_markdown("\n\n".join(f"Paragraph {i} with words." for i in range(60)))
    else:
        widget.setText("\n".join(f"line {i}" for i in range(200)))
    QApplication.processEvents()
    assert widget.height() >= widget._engine.minimumHeight() > scroll.viewport().height()
    assert scroll.verticalScrollBar().maximum() > 0
    scroll.close()
