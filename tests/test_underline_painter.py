"""Underline colour family — a field paints its own token, not a button's.

Regression (reported 2026-11-24): a disabled output-path field kept a bright
underline. ``draw_bottom_underline`` resolved the widget's ``class`` property
to ``button.primary``/``button.default`` and read ``.bottom.edge``, so a line
edit — a widget with no button class — always painted a BUTTON colour, and
its disabled state only dimmed that colour with alpha.

``token_prefix`` lets a caller name its own family; the line edit passes
``"input"`` and resolves ``input.underline`` / ``.focused`` / ``.disabled``.
Every token is optional until the palette phase ships them: without them the
painted pixels are the pre-token ones.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.helpers.underline_painter import (
    UnderlineConfig,
    draw_bottom_underline,
)
from sli_ui_toolkit.widgets import CustomLineEdit

THEMES = ("light", "dark")


def _opaque(color: QColor) -> QColor:
    color = QColor(color)
    color.setAlpha(255)
    return color


def _theme(theme: str) -> ThemeManager:
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme(theme)
    return tm


def _band_image(
    tm: ThemeManager,
    *,
    token_prefix: str | None = None,
    color: QColor | None = None,
    width: int = 120,
    height: int = 20,
) -> QImage:
    """One underline band at full alpha, so a pixel is the token itself."""
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        draw_bottom_underline(
            painter,
            QRect(0, 0, width, height),
            tm,
            UnderlineConfig(
                thickness=8.0,
                arc_radius=3.0,
                vertical_offset=0.0,
                alpha=255,
                color=color,
                fade=False,
            ),
            token_prefix=token_prefix,
        )
    finally:
        painter.end()
    return image


class _Probe(QWidget):
    """Widget that paints an underline through the real widget-device path.

    ``draw_bottom_underline`` reads ``painter.device()`` for the ``class``
    property, so the button branch is only reachable while painting a widget.
    """

    def __init__(self, tm: ThemeManager, token_prefix: str | None):
        super().__init__()
        self._tm = tm
        self._token_prefix = token_prefix
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event):  # noqa: N802 - Qt override
        painter = QPainter(self)
        try:
            draw_bottom_underline(
                painter,
                self.rect(),
                self._tm,
                UnderlineConfig(
                    thickness=8.0,
                    arc_radius=3.0,
                    vertical_offset=0.0,
                    alpha=255,
                ),
                token_prefix=self._token_prefix,
            )
        finally:
            painter.end()


def _render(widget: QWidget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image, QPoint(0, 0))
    return image


# -- painter contract -------------------------------------------------------


@pytest.mark.parametrize("theme", THEMES)
def test_family_token_wins_when_the_palette_defines_it(qapp, theme):
    tm = _theme(theme)
    tm.set_color("input.underline", QColor("#ff00aa"))

    image = _band_image(tm, token_prefix="input")

    assert image.pixelColor(60, 18) == QColor("#ff00aa")


@pytest.mark.parametrize("theme", THEMES)
def test_explicit_colour_beats_the_family_token(qapp, theme):
    tm = _theme(theme)
    tm.set_color("input.underline", QColor("#ff00aa"))

    image = _band_image(tm, token_prefix="input", color=QColor("#00ff00"))

    assert image.pixelColor(60, 18) == QColor("#00ff00")


@pytest.mark.parametrize("theme", THEMES)
def test_no_token_prefix_reads_the_button_token(qapp, theme):
    """The button layer's own rule is untouched (``class`` → bottom.edge)."""
    tm = _theme(theme)
    probe = _Probe(tm, None)
    probe.setProperty("class", "primary")
    probe.resize(120, 20)
    try:
        image = _render(probe)
    finally:
        probe.deleteLater()

    assert image.pixelColor(60, 18) == _opaque(tm.get_color("button.primary.bottom.edge"))


@pytest.mark.parametrize("theme", THEMES)
def test_absent_family_token_falls_back_to_the_button_pixel(qapp, theme):
    """A caller may adopt ``token_prefix`` before the palette ships it."""
    tm = _theme(theme)

    legacy = _Probe(tm, None)
    legacy.setProperty("class", "primary")
    legacy.resize(120, 20)

    family = _Probe(tm, "input")
    family.setProperty("class", "primary")
    family.resize(120, 20)

    try:
        legacy_image = _render(legacy)
        family_image = _render(family)
    finally:
        legacy.deleteLater()
        family.deleteLater()

    assert tm.try_get_color("input.underline") is None
    assert bytes(family_image.constBits()) == bytes(legacy_image.constBits())


def test_legacy_direct_call_pixel_is_unchanged(qapp):
    """No ``class`` property and no family token: button.default, as before."""
    tm = _theme("light")

    image = _band_image(tm)

    assert image.pixelColor(60, 18) == _opaque(tm.get_color("button.default.bottom.edge"))


# -- CustomLineEdit states --------------------------------------------------


def _render_edit(
    qapp,
    *,
    theme: str,
    tokens: dict[str, str],
    enabled: bool = True,
    focused: bool = False,
) -> QColor:
    tm = _theme(theme)
    for name, value in tokens.items():
        tm.set_color(name, QColor(value))

    edit = CustomLineEdit()
    edit.setFixedSize(160, CustomLineEdit.HEIGHT)
    edit.set_underline_thickness(6.0)
    edit.setFocusedUnderlineThickness(6.0)
    edit.setEnabled(enabled)
    if focused:
        edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    else:
        # The offscreen platform hands focus to the first shown widget and
        # clearFocus() gets undone by the activation; NoFocus is deterministic.
        edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    edit.show()
    if focused:
        edit.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    try:
        image = _render(edit)
        return image.pixelColor(80, edit.height() - 3)
    finally:
        edit.deleteLater()


@pytest.mark.parametrize("theme", THEMES)
def test_disabled_line_edit_samples_the_disabled_token(qapp, theme):
    pixel = _render_edit(
        qapp,
        theme=theme,
        tokens={
            CustomLineEdit.UNDERLINE_TOKEN: "#00aa00",
            CustomLineEdit.UNDERLINE_FOCUSED_TOKEN: "#0000ff",
            CustomLineEdit.UNDERLINE_DISABLED_TOKEN: "#ff0000",
        },
        enabled=False,
    )

    assert pixel == QColor("#ff0000")


@pytest.mark.parametrize("theme", THEMES)
def test_enabled_line_edit_samples_the_family_token(qapp, theme):
    pixel = _render_edit(
        qapp,
        theme=theme,
        tokens={
            CustomLineEdit.UNDERLINE_TOKEN: "#00aa00",
            CustomLineEdit.UNDERLINE_FOCUSED_TOKEN: "#0000ff",
            CustomLineEdit.UNDERLINE_DISABLED_TOKEN: "#ff0000",
        },
    )

    assert pixel == QColor("#00aa00")


@pytest.mark.parametrize("theme", THEMES)
def test_focused_line_edit_samples_the_focused_token(qapp, theme):
    pixel = _render_edit(
        qapp,
        theme=theme,
        tokens={
            CustomLineEdit.UNDERLINE_TOKEN: "#00aa00",
            CustomLineEdit.UNDERLINE_FOCUSED_TOKEN: "#0000ff",
            CustomLineEdit.UNDERLINE_DISABLED_TOKEN: "#ff0000",
        },
        focused=True,
    )

    assert pixel == QColor("#0000ff")


@pytest.mark.parametrize("theme", THEMES)
def test_line_edit_without_tokens_keeps_its_previous_underline(qapp, theme):
    """The fallback path is the exact pre-token pixel: one button colour, dimmed.

    Before the tokens existed a disabled field drew the same colour as an
    enabled one (only the text was dimmed) — that identity is the fallback.
    """
    enabled_pixel = _render_edit(qapp, theme=theme, tokens={})
    disabled_pixel = _render_edit(qapp, theme=theme, tokens={}, enabled=False)

    assert disabled_pixel == enabled_pixel


def test_line_edit_explicit_underline_colour_still_wins(qapp):
    tm = _theme("light")
    tm.set_color(CustomLineEdit.UNDERLINE_TOKEN, QColor("#00aa00"))

    edit = CustomLineEdit(underline_color=QColor("#123456"))
    edit.setFixedSize(160, CustomLineEdit.HEIGHT)
    edit.set_underline_thickness(6.0)
    edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    edit.show()
    qapp.processEvents()
    try:
        image = _render(edit)
        pixel = image.pixelColor(80, edit.height() - 3)
    finally:
        edit.deleteLater()

    # Explicit override keeps its legacy alpha (the token never applies):
    # the painted pixel is the override blended exactly as before.
    assert pixel != QColor("#00aa00")
    assert pixel == _blended(image.pixelColor(80, 10), QColor("#123456"), 60)


def _blended(background: QColor, color: QColor, alpha: int) -> QColor:
    """Reference pixel: ``color`` at ``alpha`` over ``background`` (SourceOver)."""
    reference = QImage(1, 1, QImage.Format.Format_ARGB32)
    reference.fill(background)
    painter = QPainter(reference)
    try:
        blended = QColor(color)
        blended.setAlpha(alpha)
        painter.fillRect(QRect(0, 0, 1, 1), blended)
    finally:
        painter.end()
    return reference.pixelColor(0, 0)


def test_painter_uses_try_get_color_not_get_color_for_the_family(qapp):
    """An unknown token must not reach ``get_color`` (which warns + repaints
    the surface background)."""
    tm = _theme("light")
    with patch.object(tm, "get_color", wraps=tm.get_color) as spy:
        image = _band_image(tm, token_prefix="input")
        assert image.pixelColor(60, 18) == _opaque(tm.get_color("button.default.bottom.edge"))
    assert all(call.args[0] != "input.underline" for call in spy.call_args_list)
