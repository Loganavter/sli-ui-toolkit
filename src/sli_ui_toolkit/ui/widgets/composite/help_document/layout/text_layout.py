"""QTextLayout construction and inline style formatting."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import (
    QColor,
    QFont,
    QTextCharFormat,
    QTextLayout,
    QTextOption,
)

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.composite.help_document.blocks import InlineKind, InlineSpan
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.types import LinkHitBox
from sli_ui_toolkit.ui.widgets.composite.help_document.text_index import (
    CharStyle,
    TextRole,
    TextRoleKind,
)


def styles_from_spans(
    spans: tuple[InlineSpan, ...],
) -> tuple[tuple[CharStyle, ...], tuple[TextRole, ...]]:
    styles: list[CharStyle] = []
    roles: list[TextRole] = []
    for span in spans:
        style = CharStyle(span.kind, span.href)
        role = TextRole(TextRoleKind.BODY)
        for _ch in span.text:
            styles.append(style)
            roles.append(role)
    return tuple(styles), tuple(roles)


def text_layout_height(layout: QTextLayout) -> float:
    """Total painted height of a laid-out ``QTextLayout``."""
    height = layout.boundingRect().height()
    if layout.lineCount() == 0:
        return max(0.0, height)
    last = layout.lineAt(layout.lineCount() - 1)
    if not last.isValid():
        return max(0.0, height)
    positioned = last.y() + last.height()
    return max(height, positioned)


def build_text_layout(
    text: str,
    styles: tuple[CharStyle, ...],
    roles: tuple,
    *,
    base_font: QFont,
    theme: ThemeManager,
    color_token: str,
    width: float,
) -> tuple[QTextLayout, tuple[LinkHitBox, ...]]:
    cursor = QTextCharFormat()
    text_color = theme.try_get_color(color_token) or theme.try_get_color("dialog.text")
    if text_color is not None and text_color.isValid():
        cursor.setForeground(text_color)

    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WordWrap)

    layout = QTextLayout(text, base_font)
    layout.setTextOption(option)

    format_ranges: list[QTextLayout.FormatRange] = []
    link_ranges: list[tuple[int, int, str]] = []
    i = 0
    while i < len(text):
        style = styles[i]
        role = roles[i]
        j = i + 1
        while j < len(text) and styles[j] == style and roles[j] == role:
            j += 1
        fmt = QTextCharFormat(cursor)
        fmt.setFont(base_font)
        if role.kind == TextRoleKind.HEADING:
            fmt.setFontWeight(QFont.Weight.Bold)
        if style.kind == InlineKind.BOLD:
            fmt.setFontWeight(QFont.Weight.Bold)
        elif style.kind == InlineKind.ITALIC:
            fmt.setFontItalic(True)
        elif style.kind == InlineKind.CODE:
            fmt.setFontFamilies(["monospace"])
        elif style.kind == InlineKind.KBD:
            _apply_kbd_format(fmt, theme, text_color)
        elif style.kind == InlineKind.LINK and style.href:
            accent = theme.try_get_color("accent")
            if accent is not None and accent.isValid():
                fmt.setForeground(accent)
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.NoUnderline)
            link_ranges.append((i, j, style.href))
        fr = QTextLayout.FormatRange()
        fr.start = i
        fr.length = j - i
        fr.format = fmt
        format_ranges.append(fr)
        i = j

    layout.setFormats(format_ranges)
    layout.beginLayout()
    line_y = 0.0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        line.setPosition(QPointF(0.0, line_y))
        line_y += line.height()
    layout.endLayout()

    links: list[LinkHitBox] = []
    for start, end, href in link_ranges:
        for li in range(layout.lineCount()):
            line = layout.lineAt(li)
            if not line.isValid():
                continue
            line_start = line.textStart()
            line_end = line_start + line.textLength()
            overlap_start = max(start, line_start)
            overlap_end = min(end, line_end)
            if overlap_start >= overlap_end:
                continue
            x1 = line.cursorToX(overlap_start)[0]
            x2 = line.cursorToX(overlap_end)[0]
            top = line.y()
            links.append(
                LinkHitBox(
                    rect=QRectF(
                        min(x1, x2),
                        top,
                        abs(x2 - x1),
                        line.height(),
                    ),
                    href=href,
                )
            )

    return layout, tuple(links)


def _apply_kbd_format(
    fmt: QTextCharFormat,
    theme: ThemeManager,
    text_color: QColor | None,
) -> None:
    border = theme.try_get_color("dialog.border")
    bg = theme.try_get_color("dialog.input.background")
    if text_color is not None and text_color.isValid():
        fmt.setForeground(text_color)
    if bg is not None and bg.isValid():
        fmt.setBackground(bg)
    if border is not None and border.isValid():
        fmt.setProperty(QTextCharFormat.Property.UserProperty + 1, border.name())
