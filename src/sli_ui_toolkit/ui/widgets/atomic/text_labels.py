from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QFontMetrics
from PySide6.QtWidgets import QLabel, QSizePolicy

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import UiFont, apply_text_color, ui_font


@dataclass(frozen=True)
class LabelVariantSpec:
    name: str
    pixel_size: int | None = None
    bold: bool = False
    color_token: str = "dialog.text"
    minimum_width: int = 0
    expanding: bool = False
    elide: bool = False


@dataclass
class LabelConfig:
    text: str = ""
    variant: str = "body"
    family: str | None = None
    pixel_size: int | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strike_out: bool | None = None
    color: QColor | None = None
    color_token: str | None = None
    alignment: Qt.AlignmentFlag = (
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
    )
    elide: bool | None = None
    minimum_width: int | None = None
    expanding: bool | None = None
    word_wrap: bool | None = None
    selectable: bool = False


_DEFAULT_VARIANTS: list[LabelVariantSpec] = [
    LabelVariantSpec("body", pixel_size=12, color_token="dialog.text"),
    LabelVariantSpec("caption", pixel_size=11, color_token="dialog.text"),
    LabelVariantSpec(
        "compact",
        pixel_size=10,
        color_token="dialog.text",
        minimum_width=80,
        expanding=True,
        elide=True,
    ),
    LabelVariantSpec(
        "group-title",
        pixel_size=13,
        bold=True,
        color_token="dialog.text",
        elide=True,
    ),
    LabelVariantSpec(
        "adaptive",
        pixel_size=12,
        color_token="dialog.text",
        minimum_width=50,
        expanding=True,
        elide=True,
    ),
]

LABEL_VARIANTS: dict[str, LabelVariantSpec] = {
    variant.name: variant for variant in _DEFAULT_VARIANTS
}


def register_label_variant(spec: LabelVariantSpec) -> None:
    LABEL_VARIANTS[spec.name] = spec


def get_label_variant(name: str | None) -> LabelVariantSpec:
    return LABEL_VARIANTS.get((name or "body").lower(), LABEL_VARIANTS["body"])


class Label(QLabel):
    """Unified themed text label.

    Use direct keyword arguments for one-off typography and behavior, or
    ``variant`` when a registered shared preset is useful.
    """

    def __init__(
        self,
        text: str = "",
        parent=None,
        *,
        variant: str = "body",
        family: str | None = None,
        pixel_size: int | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        strike_out: bool | None = None,
        color: QColor | None = None,
        color_token: str | None = None,
        alignment: Qt.AlignmentFlag = (
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        ),
        elide: bool | None = None,
        minimum_width: int | None = None,
        expanding: bool | None = None,
        word_wrap: bool | None = None,
        selectable: bool = False,
        config: LabelConfig | None = None,
    ):
        if config is not None:
            text = config.text
            variant = config.variant
            family = config.family
            pixel_size = config.pixel_size
            bold = config.bold
            italic = config.italic
            underline = config.underline
            strike_out = config.strike_out
            color = config.color
            color_token = config.color_token
            alignment = config.alignment
            elide = config.elide
            minimum_width = config.minimum_width
            expanding = config.expanding
            word_wrap = config.word_wrap
            selectable = config.selectable

        super().__init__(parent)
        self.theme_manager = ThemeManager.get_instance()
        self._variant_name = variant
        self._family_override = family
        self._pixel_size_override = pixel_size
        self._bold_override = bold
        self._italic_override = italic
        self._underline_override = underline
        self._strike_out_override = strike_out
        self._color_override = QColor(color) if color is not None else None
        self._color_token_override = color_token
        self._elide_override = elide
        self._minimum_width_override = minimum_width
        self._expanding_override = expanding
        self._word_wrap_override = word_wrap
        self._original_text = text
        self._preferred_width_cache: int | None = None

        self.setAlignment(alignment)
        self.setWordWrap(bool(word_wrap) if word_wrap is not None else False)
        if selectable:
            self.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
        QLabel.setText(self, text)
        self._applying_style = False
        self.theme_manager.theme_changed.connect(self._apply_style)
        UiFont.get_instance().font_changed.connect(self._apply_style)
        self._apply_style()

    def variant(self) -> str:
        return self._variant_name

    def setVariant(self, variant: str) -> None:
        self._variant_name = str(variant or "body")
        self._preferred_width_cache = None
        self._apply_style()

    def setTextColor(self, color: QColor | None) -> None:
        self._color_override = QColor(color) if color is not None else None
        self._apply_style()

    def setColorToken(self, token: str | None) -> None:
        self._color_token_override = token
        self._apply_style()

    def setPixelSize(self, size: int | None) -> None:
        self._pixel_size_override = max(1, int(size)) if size is not None else None
        self._preferred_width_cache = None
        self._apply_style()

    def setFamily(self, family: str | None) -> None:
        self._family_override = family
        self._preferred_width_cache = None
        self._apply_style()

    def setBold(self, enabled: bool | None) -> None:
        self._bold_override = enabled
        self._preferred_width_cache = None
        self._apply_style()

    def setItalic(self, enabled: bool | None) -> None:
        self._italic_override = enabled
        self._preferred_width_cache = None
        self._apply_style()

    def setUnderline(self, enabled: bool | None) -> None:
        self._underline_override = enabled
        self._preferred_width_cache = None
        self._apply_style()

    def setStrikeOut(self, enabled: bool | None) -> None:
        self._strike_out_override = enabled
        self._preferred_width_cache = None
        self._apply_style()

    def setSelectable(self, enabled: bool) -> None:
        flags = Qt.TextInteractionFlag.NoTextInteraction
        if enabled:
            flags = (
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
        self.setTextInteractionFlags(flags)

    def setMinimumWidth(self, width: int) -> None:
        self._minimum_width_override = max(0, int(width))
        super().setMinimumWidth(width)
        self._preferred_width_cache = None
        self.updateGeometry()

    def setText(self, text: str) -> None:
        self._original_text = text
        self._preferred_width_cache = None
        super().setText(text)
        self._update_elided_text()
        self.updateGeometry()

    def get_original_text(self) -> str:
        return self._original_text

    def invalidate_size_cache(self) -> None:
        self._preferred_width_cache = None
        self.updateGeometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elided_text()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        et = event.type()
        if et == QEvent.Type.ApplicationFontChange:
            self._preferred_width_cache = None
            self._apply_style()
            return
        # Reparent / style polish can wipe WA_SetPalette text colors.
        if et in (QEvent.Type.ParentChange, QEvent.Type.StyleChange):
            self._apply_style()

    def sizeHint(self):
        hint = super().sizeHint()
        if self._uses_elide():
            minimum_width = self._minimum_width()
            if self._preferred_width_cache is None:
                metrics = QFontMetrics(self.font())
                self._preferred_width_cache = (
                    metrics.horizontalAdvance(self._original_text) + 10
                )
            hint.setWidth(max(self._preferred_width_cache, minimum_width))
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        minimum_width = self._minimum_width()
        if minimum_width > 0:
            hint.setWidth(minimum_width)
        return hint

    def _apply_style(self) -> None:
        if self._applying_style:
            return
        self._applying_style = True
        try:
            spec = get_label_variant(self._variant_name)
            font = ui_font(
                family=self._family_override,
                pixel_size=(
                    self._pixel_size_override
                    if self._pixel_size_override is not None
                    else spec.pixel_size
                ),
                bold=(
                    spec.bold
                    if self._bold_override is None
                    else bool(self._bold_override)
                ),
                italic=bool(self._italic_override),
                underline=bool(self._underline_override),
                strike_out=bool(self._strike_out_override),
            )
            # Color via palette — never setStyleSheet("color:…") (Qt then ignores setFont).
            apply_text_color(self, self._resolve_color(spec))
            self.setFont(font)

            if self._expanding():
                self.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
            else:
                self.setSizePolicy(
                    QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
                )

            minimum_width = self._minimum_width()
            if minimum_width > 0:
                QLabel.setMinimumWidth(self, minimum_width)

            self._update_elided_text()
            self.updateGeometry()
            self.update()
        finally:
            self._applying_style = False

    def _resolve_color(self, spec: LabelVariantSpec) -> QColor | None:
        if self._color_override is not None:
            return QColor(self._color_override)

        token = self._color_token_override or spec.color_token
        color = self.theme_manager.try_get_color(token)
        if color is not None:
            return color

        fallback = self.theme_manager.try_get_color("WindowText")
        return fallback if fallback is not None else None

    def _minimum_width(self) -> int:
        if self._minimum_width_override is not None:
            return max(0, int(self._minimum_width_override))
        return max(0, get_label_variant(self._variant_name).minimum_width)

    def _expanding(self) -> bool:
        if self._expanding_override is not None:
            return bool(self._expanding_override)
        return get_label_variant(self._variant_name).expanding

    def _uses_elide(self) -> bool:
        if self._elide_override is not None:
            return bool(self._elide_override)
        return get_label_variant(self._variant_name).elide

    def _update_elided_text(self) -> None:
        if not self._uses_elide() or not self._original_text:
            if self.text() != self._original_text:
                super().setText(self._original_text)
            return

        available_width = self.width() - 10
        if available_width <= 0:
            return

        metrics = QFontMetrics(self.font())
        if metrics.horizontalAdvance(self._original_text) <= available_width:
            display_text = self._original_text
        else:
            display_text = metrics.elidedText(
                self._original_text,
                Qt.TextElideMode.ElideRight,
                available_width,
            )
        if self.text() != display_text:
            super().setText(display_text)
