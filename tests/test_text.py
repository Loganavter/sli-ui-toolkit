"""Text (P1 plain mode): Label parity, config, modes, selection, elide, marquee."""

from __future__ import annotations

import inspect

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QKeyEvent, QMouseEvent, QPalette
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.ui.widgets.atomic.label_context_menu import build_label_menu
from sli_ui_toolkit.ui.widgets.atomic.text_labels import (
    LabelVariantSpec,
    get_label_variant,
    register_label_variant,
)
from sli_ui_toolkit.widgets import Label, Text, TextConfig
from sli_ui_toolkit.ui.widgets.text.variants import (
    get_text_variant,
    register_text_variant,
)

_WHITE = QColor(255, 255, 255)


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


def _mouse(kind, pos: QPointF, buttons=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(
        kind,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        buttons,
        mods,
    )


def _press(widget, x: float, y: float = 10) -> None:
    QApplication.sendEvent(
        widget, _mouse(QEvent.Type.MouseButtonPress, QPointF(x, y))
    )


def _drag(widget, x: float, y: float = 10) -> None:
    QApplication.sendEvent(
        widget,
        _mouse(QEvent.Type.MouseMove, QPointF(x, y)),
    )


def _release(widget, x: float, y: float = 10) -> None:
    QApplication.sendEvent(
        widget,
        _mouse(QEvent.Type.MouseButtonRelease, QPointF(x, y)),
    )


def _key(widget, key: Qt.Key, mods=Qt.KeyboardModifier.NoModifier) -> None:
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, mods))


@pytest.mark.parametrize(
    ("text", "kwargs"),
    [
        ("Hello world", {}),
        ("A&B mnemonic", {}),
        ("two\nlines", {}),
        ("caption", {"variant": "caption", "bold": True}),
        ("right", {"alignment": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter}),
        ("long text wraps here for sure", {"word_wrap": True}),
        ("compact elided label text is long", {"variant": "compact"}),
        ("italic underline", {"italic": True, "underline": True, "pixel_size": 18}),
    ],
)
def test_plain_text_pixels_match_label(qapp, text, kwargs):
    width, height = 220, 60
    label = Label(text, **kwargs)
    label.resize(width, height)
    label.show()
    widget = Text(text, mode="plain", **kwargs)
    widget.resize(width, height)
    widget.show()
    QApplication.processEvents()
    assert _pixel_diff(_grab(label), _grab(widget)) == 0
    label.close()
    widget.close()


@pytest.mark.parametrize(
    ("text", "kwargs", "width"),
    [
        ("Hello world", {}, 220),
        ("long text wraps here for sure", {"word_wrap": True}, 200),
        ("long text wraps here for sure", {"word_wrap": True}, 60),
        ("a b", {"word_wrap": True}, 40),
        ("compact elided label text is long", {"variant": "compact"}, 120),
    ],
)
def test_size_metrics_match_label(qapp, text, kwargs, width):
    label = Label(text, **kwargs)
    widget = Text(text, **kwargs)
    assert widget.minimumSizeHint().toTuple() == label.minimumSizeHint().toTuple()
    assert widget.hasHeightForWidth() == label.hasHeightForWidth()
    assert widget.heightForWidth(width) == label.heightForWidth(width)
    if not kwargs.get("word_wrap"):
        assert widget.sizeHint().toTuple() == label.sizeHint().toTuple()


def test_typography_and_policy_match_label(qapp):
    kwargs = {"variant": "group-title", "pixel_size": 15, "italic": True}
    label = Label("Typography", **kwargs)
    widget = Text("Typography", **kwargs)
    assert widget.font().pixelSize() == label.font().pixelSize() == 15
    assert widget.font().bold() == label.font().bold()
    assert widget.font().italic() is True
    assert widget.sizePolicy().horizontalPolicy() == label.sizePolicy().horizontalPolicy()
    assert widget.sizePolicy().verticalPolicy() == label.sizePolicy().verticalPolicy()
    assert widget.palette().color(widget.foregroundRole()) == label.palette().color(
        label.foregroundRole()
    )


def test_explicit_color_applies_like_label(qapp):
    color = QColor(12, 200, 90)
    label = Label("Color", color=color)
    widget = Text("Color", color=color)
    assert widget.palette().color(widget.foregroundRole()) == color
    assert label.palette().color(label.foregroundRole()) == color


def test_shared_variant_registry_resolves_for_both_widgets(qapp):
    name = "text-p1-shared"
    register_text_variant(LabelVariantSpec(name, pixel_size=21, bold=True, minimum_width=33))
    try:
        assert get_text_variant(name) == get_label_variant(name)
        widget = Text("shared", variant=name)
        label = Label("shared", variant=name)
        assert widget.font().pixelSize() == label.font().pixelSize() == 21
        assert widget.minimumSizeHint().width() == 33
    finally:
        from sli_ui_toolkit.ui.widgets.atomic import text_labels

        text_labels.LABEL_VARIANTS.pop(name, None)


def test_register_label_variant_is_visible_to_text(qapp):
    name = "text-p1-from-label"
    register_label_variant(LabelVariantSpec(name, pixel_size=27))
    try:
        assert Text("x", variant=name).font().pixelSize() == 27
    finally:
        from sli_ui_toolkit.ui.widgets.atomic import text_labels

        text_labels.LABEL_VARIANTS.pop(name, None)


def test_config_is_equivalent_to_kwargs(qapp):
    config = TextConfig(
        text="from config",
        variant="caption",
        pixel_size=17,
        bold=True,
        word_wrap=True,
        selectable=True,
    )
    via_config = Text(config=config)
    via_kwargs = Text(
        "from config",
        variant="caption",
        pixel_size=17,
        bold=True,
        word_wrap=True,
        selectable=True,
    )
    assert via_config.text() == via_kwargs.text() == "from config"
    assert via_config.font() == via_kwargs.font()
    assert via_config.wordWrap() and via_kwargs.wordWrap()
    assert via_config.isSelectable() and via_kwargs.isSelectable()


def test_config_to_kwargs_covers_constructor_signature():
    params = set(inspect.signature(Text.__init__).parameters) - {"self", "parent", "config"}
    assert set(TextConfig().to_kwargs()) == params


def test_config_is_frozen():
    config = TextConfig(text="x")
    with pytest.raises(AttributeError):
        config.text = "y"  # type: ignore[misc]


@pytest.mark.parametrize("mode", ["document", "code"])
def test_document_and_code_modes_are_p2_stubs(qapp, mode):
    with pytest.raises(NotImplementedError, match="P2"):
        Text("body", mode=mode)
    with pytest.raises(NotImplementedError, match="P2"):
        Text(config=TextConfig(text="body", mode=mode))


def test_unknown_mode_is_rejected(qapp):
    with pytest.raises(ValueError, match="unknown Text mode"):
        Text("body", mode="rich")


def test_text_is_exported_from_widgets_package():
    import sli_ui_toolkit.widgets as widgets

    assert widgets.Text is Text
    assert widgets.TextConfig is TextConfig
    assert {"Text", "TextConfig"} <= set(widgets.__all__)


def test_elide_truncates_display_but_keeps_original(qapp):
    text = "a fairly long caption that cannot fit"
    widget = Text(text, elide=True)
    widget.resize(90, 24)
    widget.show()
    QApplication.processEvents()
    assert widget.text() != text
    assert widget.text().endswith("…")
    assert widget.get_original_text() == text
    assert widget.selectedText() == ""


def test_no_elide_keeps_full_text(qapp):
    text = "a fairly long caption that cannot fit"
    widget = Text(text)
    widget.resize(90, 24)
    widget.show()
    QApplication.processEvents()
    assert widget.text() == text


def test_marquee_keeps_full_text_and_drives_a_timer(qapp):
    text = "marquee text that overflows the box"
    widget = Text(text, marquee=True)
    widget.resize(80, 24)
    widget.show()
    QApplication.processEvents()
    assert widget.marquee() is True
    assert widget.text() == text
    driver = getattr(widget, "_marquee_driver", None)
    assert driver is not None
    widget.hide()


def test_marquee_off_has_no_driver(qapp):
    widget = Text("marquee text that overflows the box")
    widget.resize(80, 24)
    widget.show()
    QApplication.processEvents()
    assert widget.marquee() is False
    assert getattr(widget, "_marquee_driver", None) is None


def test_mouse_drag_selects_the_dragged_range(qapp):
    widget = Text("hello world", selectable=True)
    widget.resize(260, 30)
    widget.show()
    QApplication.processEvents()
    x0 = widget.contentsRect().x() + 2
    layout = widget._layout(widget.contentsRect().width())
    end_x = layout.lineAt(0).cursorToX(6)[0]
    _press(widget, x0)
    _drag(widget, end_x)
    _release(widget, end_x)
    assert widget.selectedText() == "hello "


def test_click_without_drag_selects_nothing(qapp):
    widget = Text("hello world", selectable=True)
    widget.resize(260, 30)
    widget.show()
    QApplication.processEvents()
    _press(widget, 40)
    _release(widget, 40)
    assert widget.hasSelectedText() is False
    assert widget.selectedText() == ""


def test_double_click_selects_word(qapp):
    widget = Text("hello world", selectable=True)
    widget.resize(260, 30)
    widget.show()
    QApplication.processEvents()
    layout = widget._layout(widget.contentsRect().width())
    inside_world = layout.lineAt(0).cursorToX(8)[0]
    QApplication.sendEvent(
        widget,
        _mouse(QEvent.Type.MouseButtonDblClick, QPointF(inside_world, 10)),
    )
    assert widget.selectedText() == "world"


def test_select_all_and_copy_shortcuts(qapp):
    widget = Text("copy me", selectable=True)
    widget.resize(200, 30)
    widget.show()
    QApplication.processEvents()
    QGuiApplication.clipboard().setText("")
    _key(widget, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert widget.selectedText() == "copy me"
    _key(widget, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QGuiApplication.clipboard().text() == "copy me"


def test_non_selectable_ignores_mouse_selection(qapp):
    widget = Text("hello world")
    widget.resize(260, 30)
    widget.show()
    QApplication.processEvents()
    _press(widget, 5)
    _drag(widget, 80)
    _release(widget, 80)
    assert widget.hasSelectedText() is False


def test_selection_is_painted_and_changes_pixels(qapp):
    widget = Text("highlight this", selectable=True)
    widget.resize(260, 30)
    widget.show()
    QApplication.processEvents()
    plain = _grab(widget)
    widget.selectAll()
    selected = _grab(widget)
    assert _pixel_diff(plain, selected) > 0
    highlight = widget.palette().color(QPalette.ColorRole.Highlight)
    assert any(
        selected.pixelColor(x, y) == highlight
        for x in range(selected.width())
        for y in range(selected.height())
    )


def test_selection_changed_signal_fires_only_on_change(qapp):
    widget = Text("signal", selectable=True)
    emitted: list[bool] = []
    widget.selectionChanged.connect(lambda: emitted.append(True))
    widget.selectAll()
    widget.selectAll()
    assert len(emitted) == 1


def test_set_selection_matches_qlabel_semantics(qapp):
    label = Label("set selection", selectable=True)
    widget = Text("set selection", selectable=True)
    for target in (label, widget):
        target.setSelection(4, 9)
    assert widget.selectedText() == label.selectedText() == "selection"
    widget.setSelection(-1, 3)
    assert widget.hasSelectedText() is False


def test_selection_feeds_build_label_menu(qapp):
    widget = Text("copy menu", selectable=True)
    entries, _callback = build_label_menu(widget)  # type: ignore[arg-type]
    copy_entry = entries[0]
    assert copy_entry.enabled is False
    widget.selectAll()
    entries, _callback = build_label_menu(widget)  # type: ignore[arg-type]
    assert entries[0].enabled is True


def test_set_text_clears_selection(qapp):
    widget = Text("before", selectable=True)
    widget.selectAll()
    widget.setText("after")
    assert widget.hasSelectedText() is False
    assert widget.text() == "after"


def test_context_menu_opens_only_for_selectable_text(qapp, monkeypatch):
    from PySide6.QtGui import QContextMenuEvent

    from sli_ui_toolkit.ui.widgets.text import text as text_module

    opened: list[object] = []
    monkeypatch.setattr(
        text_module,
        "open_label_context_menu",
        lambda widget, pos: opened.append(widget),
    )
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPointF(5, 5).toPoint())

    selectable = Text("menu me", selectable=True)
    QApplication.sendEvent(selectable, event)
    assert opened == [selectable]

    plain = Text("menu me")
    QApplication.sendEvent(plain, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPointF(5, 5).toPoint()))
    assert opened == [selectable]
