"""Text document surface: the retired document host's accessors, on ``Text``.

Closes the document-surface gaps recorded in ``docs/dev/TEXT_UNIFICATION.md``
("Document gaps for P2"): ``scroll_to_anchor``, ``source_markdown``,
``plain_text``, ``set_asset_resolver``, ``set_panel_fill``/``panel_fill``,
``size_hint_from_content``, ``set_wheel_edge_forwarding`` — plus the
already-present ``imageActivated`` / ``textContextMenuRequested`` wiring.

Parity numbers below were measured before the change with an offscreen probe
(that host's canvas vs ``Text(mode="document")``, width 640, default theme) and
are pinned here so the surface cannot drift silently:

    doc        Text.sizeHint  size_hint_from_content  anchors
    headings   0x312          640x312                 one=144, two=239
    figure     0x583          640x583                 deep=510
    long       0x727          640x727                 —

    plain text identical to the host's ``plain_text()`` in all three
    (231 / 67 / 1062 chars); pixel diff vs the painted ``TextCanvas``
    document path 0/307200, 0/373120, 0/465280; ``scroll_to_text("needle")``
    on the long doc = 689.

Each behaviour has a falsification note: what the pre-change ``Text`` does
instead (AttributeError for a missing accessor, painted-through corner for
the panel fill, swallowed/accepted wheel for the edge policy).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QImage,
    QMouseEvent,
    QPixmap,
    QRegion,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QMenu, QScrollArea, QWidget

from sli_ui_toolkit.palettes import FLUENT_DARK, FLUENT_LIGHT
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.text.engine.canvas import TextCanvasCore as TextCanvas
from sli_ui_toolkit.ui.widgets.text.engine.markdown import (
    blocks_to_plain_text,
    parse_help_blocks,
)
from sli_ui_toolkit.ui.widgets.text.engine.constants import PAD
from sli_ui_toolkit.widgets import Text

_W = 640
_H = 480

DOC_HEADINGS = """# Title

Intro paragraph with words that wrap across the measure so the layout has to
break lines in a deterministic place.

## Section

### One {#one}

- first list item
- second list item with a [help link](help://topic)

### Two {#two}

Closing paragraph after the list.
"""

DOC_FIGURE = """# Figure page

![shot](figure.png)

Caption under the figure.

### Deep {#deep}

Tail paragraph.
"""

DOC_LONG = "# Top\n\n" + "\n\n".join(
    f"Paragraph {i} filler text that wraps over the line." for i in range(20)
) + "\n\n### Deep\n\nThe Needle sits here.\n"

_IMG_DOC = "# Pic\n\n![alt text](figure.png)\n"


def _pixmap() -> QPixmap:
    pix = QPixmap(48, 32)
    pix.fill(QColor("#3366cc"))
    return pix


def _show(widget, width: int = _W, height: int = _H):
    widget.resize(width, height)
    widget.show()
    QApplication.processEvents()
    return widget


def _grab(widget, fill: QColor | None = None) -> QImage:
    """Render without the root window background, so an unpainted area keeps
    *fill* — that is how an absent panel fill is observed."""
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(fill or QColor(0, 0, 0, 0))
    widget.render(image, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawChildren)
    return image


def _pixel_diff(a: QImage, b: QImage) -> int:
    assert a.size() == b.size()
    fmt = QImage.Format.Format_ARGB32
    a = a.convertToFormat(fmt)
    b = b.convertToFormat(fmt)
    raw_a, raw_b = bytes(a.constBits()), bytes(b.constBits())
    stride = a.bytesPerLine()
    n = 0
    for y in range(a.height()):
        ra = raw_a[y * stride : (y + 1) * stride]
        rb = raw_b[y * stride : (y + 1) * stride]
        for x in range(a.width()):
            i = x * 4
            if ra[i : i + 4] != rb[i : i + 4]:
                n += 1
    return n


def _wheel(delta: int, phase=Qt.ScrollPhase.NoScrollPhase) -> QWheelEvent:
    pos = QPointF(10, 10)
    return QWheelEvent(
        pos,
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        phase,
        False,
    )


# -- shared metrics parity ---------------------------------------------------


@pytest.mark.parametrize(
    ("doc", "size_hint", "size_hint_from_content", "with_image"),
    [
        (DOC_HEADINGS, (0, 312), (640, 312), False),
        (DOC_FIGURE, (0, 583), (640, 583), True),
        (DOC_LONG, (0, 727), (640, 727), False),
    ],
)
def test_document_size_metrics_match_the_measured_host_parity(
    qapp, doc, size_hint, size_hint_from_content, with_image
):
    """Falsification: pre-change ``Text`` has no ``size_hint_from_content``
    (AttributeError); ``sizeHint`` itself already reports the engine height."""
    kwargs = {"resolve_asset": (lambda p: _pixmap())} if with_image else {}
    widget = _show(Text(doc, mode="document", **kwargs), width=_W, height=_H)
    assert (widget.sizeHint().width(), widget.sizeHint().height()) == size_hint
    hint = widget.size_hint_from_content()
    assert (hint.width(), hint.height()) == size_hint_from_content
    assert hint.height() == widget._engine.minimumHeight()
    # Document mode never declares height-for-width (the host sizes from
    # ``size_hint_from_content``); the plain-mode formula stays the only path,
    # so ``heightForWidth`` is not a document-contract number to pin (it
    # follows the ambient UI font). The probe recorded 272 / 170 / 782.
    assert widget.hasHeightForWidth() is False


def test_document_anchor_y_matches_the_measured_host_offsets(qapp):
    """Falsification: pre-change anchors exist but nothing pins their ids /
    widget-space y against the old host canvas."""
    widget = _show(Text(DOC_HEADINGS, mode="document"))
    assert widget.anchor_y("one") == 144
    assert widget.anchor_y("two") == 239
    assert widget.anchor_y("missing") is None
    figure = _show(Text(DOC_FIGURE, mode="document", resolve_asset=lambda p: _pixmap()))
    assert figure.anchor_y("deep") == 510


def test_document_plain_text_is_the_parsed_block_text(qapp):
    """Falsification: pre-change ``Text`` has no ``plain_text`` accessor.

    The oracle is the block parser (independent of the painted layout), so
    the measured 231-character parity the retired host pinned stays pinned."""
    widget = _show(Text(DOC_HEADINGS, mode="document"))
    assert widget.plain_text() == blocks_to_plain_text(parse_help_blocks(DOC_HEADINGS))
    assert len(widget.plain_text()) == 231
    assert widget.plain_text() == widget.text()


def test_document_render_is_pixel_identical_to_the_painted_document_path(qapp):
    """The engine hosting on ``Text`` must not repaint differently: parity
    against ``TextCanvas`` (the painted document path) is the pixel gate."""
    view = _show(Text(DOC_HEADINGS, mode="document"))
    reference = _show(TextCanvas(""))
    reference.set_document(DOC_HEADINGS)
    assert _pixel_diff(_grab(view), _grab(reference)) == 0


def test_document_scroll_to_text_target_matches_the_measured_offset(qapp):
    widget = _show(Text(DOC_LONG, mode="document", selectable=True), height=120)
    assert widget.scroll_to_text("needle") == 689


# -- scroll_to_anchor --------------------------------------------------------


def test_scroll_to_anchor_is_anchor_y_in_the_same_coordinate_space(qapp):
    """Falsification: pre-change ``Text`` has no ``scroll_to_anchor``
    (AttributeError); the old host returns a widget, not a y."""
    widget = _show(Text(DOC_HEADINGS, mode="document"))
    for anchor in ("one", "two"):
        y = widget.scroll_to_anchor(anchor)
        assert isinstance(y, int) and not isinstance(y, bool)
        assert y == widget.anchor_y(anchor)
    assert widget.scroll_to_anchor("missing") is None
    assert widget.scroll_to_anchor("") is None


def test_scroll_to_anchor_requires_document_mode(qapp):
    with pytest.raises(RuntimeError, match='mode="document"'):
        Text("caption").scroll_to_anchor("one")


# -- source_markdown / plain_text -------------------------------------------


def test_source_markdown_tracks_markdown_and_clears_on_blocks(qapp):
    """Falsification: pre-change ``Text`` has no ``source_markdown``."""
    widget = _show(Text(DOC_HEADINGS, mode="document"))
    assert widget.source_markdown() == DOC_HEADINGS
    widget.set_markdown(DOC_FIGURE)
    assert widget.source_markdown() == DOC_FIGURE
    widget.set_blocks(())
    assert widget.source_markdown() == ""
    widget.setText(DOC_LONG)
    assert widget.source_markdown() == DOC_LONG


def test_plain_text_reports_engine_text_in_every_mode(qapp):
    document = _show(Text(DOC_HEADINGS, mode="document"))
    assert "Intro paragraph" in document.plain_text()
    assert "# Title" not in document.plain_text()
    code = _show(Text("alpha\nbeta", mode="code"))
    assert code.plain_text() == "alpha\nbeta"
    plain = _show(Text("caption"))
    assert plain.plain_text() == "caption"


# -- asset resolver alias ----------------------------------------------------


def test_set_asset_resolver_feeds_the_same_resolver_path(qapp):
    """Falsification: pre-change ``Text`` has no ``set_asset_resolver``
    (AttributeError); the spelling is the old host's."""
    calls: list[str] = []
    widget = _show(Text(_IMG_DOC, mode="document", resolve_asset=lambda p: None))
    widget.set_asset_resolver(lambda path: calls.append(path))
    QApplication.processEvents()
    assert "figure.png" in calls
    assert widget._resolve_asset is not None


def test_set_resolve_asset_and_set_asset_resolver_share_one_field(qapp):
    def first(path):
        return None

    def second(path):
        return None

    widget = Text("", mode="document")
    widget.set_asset_resolver(first)
    assert widget._resolve_asset is first
    widget.set_resolve_asset(second)
    assert widget._resolve_asset is second


# -- imageActivated / textContextMenuRequested stay host-owned --------------


def test_image_click_emits_the_asset_reference_and_opens_no_popup(qapp):
    """Falsification: pre-change nothing emits from a document image click;
    the lightbox belongs to the host, so ``Text`` must create no window."""
    from sli_ui_toolkit.ui.widgets.text.engine.layout.hit_test import (
        hit_test_pixmap,
    )

    widget = _show(Text(_IMG_DOC, mode="document", resolve_asset=lambda p: _pixmap()))
    received: list[str] = []
    widget.imageActivated.connect(received.append)
    before = set(QApplication.topLevelWidgets())

    layout = widget._engine._document_layout
    fragment = layout.pixmaps[0]
    target = fragment.rect.center()
    assert hit_test_pixmap(layout, target) == "figure.png"
    # The engine's hit test subtracts the paint pad, so the click lands there.
    click = target + QPointF(PAD, PAD)

    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        QApplication.sendEvent(
            widget._engine,
            QMouseEvent(
                kind,
                click,
                click,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
    QApplication.processEvents()
    assert received == ["figure.png"]
    assert set(QApplication.topLevelWidgets()) - before == set()


def test_document_context_menu_is_requested_not_opened(qapp):
    """Falsification: nothing routes a document right-click to the host, so
    the signal never fires and the widget would have to own a menu."""
    widget = _show(Text(DOC_HEADINGS, mode="document"))
    received: list[QPoint] = []
    widget.textContextMenuRequested.connect(received.append)
    before = set(QApplication.topLevelWidgets())
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, QPoint(5, 5), QPoint(105, 205)
    )
    QApplication.sendEvent(widget._engine, event)
    QApplication.processEvents()
    assert received == [QPoint(105, 205)]
    assert [w for w in QApplication.topLevelWidgets() if isinstance(w, QMenu)] == []
    assert set(QApplication.topLevelWidgets()) - before == set()


def test_right_press_keeps_the_document_selection(qapp):
    """A right-button press must NOT collapse the selection.

    The host opens its context menu from that same press and enables its
    copy rows from the live selection, so a press that reset the selection
    left every copy row disabled (2026-10-21). The plain-mode ``Text`` and
    the legacy document core both ignore non-left buttons; this pins the
    unified document canvas to the same rule.
    """
    widget = _show(Text(DOC_HEADINGS, mode="document"))
    canvas = widget.canvas()

    canvas.select_all_text()
    QApplication.processEvents()
    selected = widget.selected_plain_text()
    assert selected, "select-all must produce a selection to preserve"

    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(30.0, 40.0),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, press)
    QApplication.processEvents()
    assert widget.selected_plain_text() == selected

    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(30.0, 40.0),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, release)
    QApplication.processEvents()
    assert widget.selected_plain_text() == selected


def test_right_release_does_not_activate_a_document_link(qapp):
    """A right-button release must not follow the link under the cursor.

    The link sits in the second paragraph; the legacy document core ignored
    non-left releases for the same reason.
    """
    widget = _show(Text(DOC_HEADINGS, mode="document"))
    canvas = widget.canvas()
    activated: list[str] = []
    canvas.linkActivated.connect(activated.append)

    # The link box lives in the "second paragraph" fragment; find its rect
    # through the layout instead of hard-coding a pixel.
    target = None
    for frag in canvas._document_layout.text_fragments:
        for link in frag.links:
            target = frag.rect.topLeft() + link.rect.center()
            break
        if target is not None:
            break
    assert target is not None, "the fixture document must contain a link"

    for kind in (
        QMouseEvent.Type.MouseButtonPress,
        QMouseEvent.Type.MouseButtonRelease,
    ):
        QApplication.sendEvent(
            canvas,
            QMouseEvent(
                kind,
                QPointF(target),
                Qt.MouseButton.RightButton,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
    QApplication.processEvents()
    assert activated == []


# -- panel fill --------------------------------------------------------------


@pytest.fixture
def light_palette(qapp):
    manager = ThemeManager.get_instance()
    manager.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    yield manager
    manager.register_palettes({}, {})


def test_panel_fill_paints_the_theme_surface_behind_the_document(qapp, light_palette):
    """Falsification: pre-change ``Text`` has no ``set_panel_fill``; the
    sentinel corner would survive the render."""
    sentinel = QColor("#ff00ff")
    surface = light_palette.get_color("surface.background")
    widget = _show(Text(DOC_HEADINGS, mode="document"))
    assert widget.panel_fill is False
    assert _grab(widget, sentinel).pixelColor(widget.width() - 1, widget.height() - 1) == sentinel

    widget.set_panel_fill(True)
    QApplication.processEvents()
    assert widget.panel_fill is True
    corner = _grab(widget, sentinel).pixelColor(widget.width() - 1, widget.height() - 1)
    assert corner == surface


def test_panel_fill_leaves_plain_mode_background_untouched(qapp, light_palette):
    widget = _show(Text("caption"))
    widget.set_panel_fill(True)
    sentinel = QColor("#ff00ff")
    corner = _grab(widget, sentinel).pixelColor(widget.width() - 1, widget.height() - 1)
    assert corner == sentinel


# -- wheel edge policy -------------------------------------------------------


def _document_in_scroll_area(doc: str = DOC_LONG):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.resize(300, 120)
    widget = Text(doc, mode="document")
    scroll.setWidget(widget)
    scroll.show()
    QApplication.processEvents()
    return scroll, widget


def test_wheel_at_host_edge_is_forwarded_by_default(qapp):
    """Falsification: pre-change there is no policy at all (no method, no
    filter), so this test cannot even build the second half."""
    scroll, widget = _document_in_scroll_area()
    bar = scroll.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    event = _wheel(-120)
    QApplication.sendEvent(widget._engine, event)
    assert event.isAccepted() is False
    scroll.close()


def test_wheel_edge_forwarding_false_keeps_the_edge_wheel(qapp):
    scroll, widget = _document_in_scroll_area()
    bar = scroll.verticalScrollBar()
    widget.set_wheel_edge_forwarding(False)
    bar.setValue(bar.maximum())
    QApplication.processEvents()
    held = _wheel(-120)
    QApplication.sendEvent(widget._engine, held)
    assert held.isAccepted() is True

    # Interior of the range: the host must still scroll, never swallowed.
    bar.setValue(0)
    QApplication.processEvents()
    interior = _wheel(-120)
    QApplication.sendEvent(widget._engine, interior)
    assert interior.isAccepted() is False

    # Top edge, upward wheel: held as well.
    top = _wheel(120)
    QApplication.sendEvent(widget._engine, top)
    assert top.isAccepted() is True
    scroll.close()


# -- explicit non-goals ------------------------------------------------------


@pytest.mark.parametrize("name", ["set_show_toc", "set_toc_title", "set_tab_stop_px"])
def test_toc_and_tab_stop_surface_stays_outside_text(qapp, name):
    """Documented decision (TEXT_UNIFICATION §4): TOC chrome and the
    host-measured tab column compose outside the widget."""
    widget = Text("", mode="document")
    assert not hasattr(widget, name)
