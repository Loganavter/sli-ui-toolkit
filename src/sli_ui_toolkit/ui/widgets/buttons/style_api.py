"""Button visual style API — mixin со всеми setX/getX визуальных атрибутов.

Включает: badge, underline, цвета (foreground/accent/border/background), content
(icon/text/rows), variant/density/corner radius/icon size, size hints,
flyout/footer/popup, а также dispatcher динамических Qt-properties.

Сам по себе класс не наследует QWidget — он подмешивается в Button и опирается
на инстансные атрибуты Button (self._foo) и базовые методы QWidget (update,
setProperty, setFixedSize…).
"""

from __future__ import annotations

from typing import Any
import warnings

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QColor, QCursor

from sli_ui_toolkit.deprecations import BUTTON_PRIMARY_VARIANT, warn_deprecated
from sli_ui_toolkit.ui.widgets.style_bridge import update_widget_style


_MAX_UNDERLINE_THICKNESS = 3.0


def normalize_content_padding(
    padding: float | tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """CSS-margin-style normalization: single float applies to all four sides;
    a 4-tuple gives independent (left, top, right, bottom) insets — needed to
    e.g. reserve space only below content (icon/text) without moving it,
    which a uniform inset cannot do for already-centered content.
    """
    if isinstance(padding, (tuple, list)):
        if len(padding) != 4:
            raise ValueError(
                f"content_padding tuple must have 4 elements (left, top, right, bottom), got {len(padding)}"
            )
        return tuple(max(0.0, float(v)) for v in padding)
    value = max(0.0, float(padding))
    return (value, value, value, value)


def _normalize_underline_thickness(thickness: float | None) -> float | None:
    if thickness is None:
        return None
    normalized = max(0.0, float(thickness))
    if normalized > _MAX_UNDERLINE_THICKNESS:
        warnings.warn(
            (
                "Button underline thickness is capped at "
                f"{_MAX_UNDERLINE_THICKNESS:.1f}px; got {normalized:.1f}px."
            ),
            RuntimeWarning,
            stacklevel=3,
        )
        return _MAX_UNDERLINE_THICKNESS
    return normalized


class _ButtonStyleApi:
    """Mixin: визуальные атрибуты + dynamic Qt-property dispatch."""

    # -------- badge --------

    def setBadge(self, num: int | None):
        self._badge = num
        self.update()

    set_display_number = setBadge

    def setBadgeStyle(
        self,
        *,
        filled: bool | None = None,
        bordered: bool | None = None,
        background_color: QColor | None = None,
        border_color: QColor | None = None,
        text_color: QColor | None = None,
    ):
        if filled is not None:
            self.setProperty("badgeFilled", bool(filled))
        if bordered is not None:
            self.setProperty("badgeBordered", bool(bordered))
        if background_color is not None:
            self.setProperty("badgeBackgroundColor", background_color)
        if border_color is not None:
            self.setProperty("badgeBorderColor", border_color)
        if text_color is not None:
            self.setProperty("badgeTextColor", text_color)
        self.update()

    set_badge_style = setBadgeStyle

    # -------- underline --------

    def setUnderlineColor(self, color: QColor | list | None):
        self._underline_config_color = color
        if isinstance(color, QColor):
            self.setProperty("underlineColor", color)
        elif isinstance(color, list):
            self.setProperty("underlineColor", color)
        elif color is None:
            self.setProperty("underlineColor", None)
        self.update()

    set_underline_color = setUnderlineColor

    def setUnderlineThickness(self, thickness: float | None):
        self._underline_thickness = _normalize_underline_thickness(thickness)
        self.setProperty("underlineThicknessPx", self._underline_thickness)
        self.update()

    set_underline_thickness = setUnderlineThickness

    def setShowUnderline(self, show: bool):
        if self._show_underline != show:
            self._show_underline = show
            self.setProperty("showUnderline", show)
            self.update()

    set_show_underline = setShowUnderline

    # -------- background / border / decoration colors --------

    def set_override_bg_color(self, color: QColor | None):
        """Set an exact base fill color (pixel-accurate normal layer).

        Unlike historically, this no longer freezes hover/pressed — set
        ``bg_locked=True`` when interaction overlays must be suppressed.
        """
        self._override_bg_color = color
        self.update()

    def set_bg_locked(self, locked: bool) -> None:
        """When True, paint base only (no hover/pressed/hover_color overlays)."""
        self._bg_locked = bool(locked)
        self.update()

    def is_bg_locked(self) -> bool:
        return bool(getattr(self, "_bg_locked", False))

    def set_hover_color(self, color: QColor | None) -> None:
        """Widget-level hover overlay color (feeds ``_main`` / context default).

        For multi-region buttons prefer per-region ``hover_color=`` or
        ``update_region(...);`` this setter also writes ``_main`` when present.
        """
        self._hover_color = QColor(color) if color is not None else None
        if self._region_by_id("_main") is not None:
            self.update_region("_main", hover_color=self._hover_color)
        else:
            self.update()

    def hover_color(self) -> QColor | None:
        return getattr(self, "_hover_color", None)

    def set_hover_compose(self, compose: str) -> None:
        """``replace`` (default) or ``stack`` — applied to every current region."""
        normalized = compose if compose in ("replace", "stack") else "replace"
        self._hover_compose = normalized
        for region in list(self._controller.regions):
            self.update_region(region.id, hover_compose=normalized)

    def hover_compose(self) -> str:
        return getattr(self, "_hover_compose", "replace")

    def set_background_color(self, color: QColor | None):
        self._custom_bg_color = color
        self.update()

    def getBackgroundColor(self) -> QColor | None:
        return self._custom_bg_color

    def setBorderColor(self, color: QColor | None) -> None:
        self._border_color_override = color
        self.update()

    set_border_color = setBorderColor

    def borderColor(self) -> QColor | None:
        return self._border_color_override

    def set_show_strike_through(self, enabled: bool):
        self._show_strike_through = enabled
        self.update()

    # -------- ripple gradient --------

    def setRippleColors(
        self,
        color_from: QColor | None,
        color_to: QColor | None,
    ) -> None:
        """Включить градиент-режим ripple: волна от `color_from` к `color_to`.

        Если оба None — возврат к дефолтному overlay-ripple.
        """
        if color_from is None or color_to is None:
            self._ripple_color_from = None
            self._ripple_color_to = None
        else:
            self._ripple_color_from = QColor(color_from)
            self._ripple_color_to = QColor(color_to)

    set_ripple_colors = setRippleColors

    def clearRippleColors(self) -> None:
        self._ripple_color_from = None
        self._ripple_color_to = None

    clear_ripple_colors = clearRippleColors

    def _resolve_ripple_colors(self) -> tuple[QColor | None, QColor | None]:
        """Цвет волны на момент трига нажатия.

        Возвращает явно заданные `_ripple_color_from`/`_ripple_color_to`
        (через `setRippleColors`) либо `None, None` — дефолтный overlay-ripple.
        """
        from_color = getattr(self, "_ripple_color_from", None)
        to_color = getattr(self, "_ripple_color_to", None)
        if from_color is not None and to_color is not None:
            return from_color, to_color
        return None, None

    # -------- content (icon/text/rows) --------

    def setIcon(self, icon):
        if isinstance(icon, (tuple, list)) and len(icon) >= 2:
            self._icon_unchecked, self._icon_checked = icon[0], icon[1]
        else:
            self._icon_unchecked = self._icon_checked = icon
        self._sync_main_region(icon=icon)
        self.update()

    def setText(self, text: str):
        self._text = text
        self._sync_main_region(text=text)
        self._apply_text_geometry(bool(text))

    def setRows(self, rows, compact: bool = False):
        self._rows = rows or []
        self._rows_compact = compact
        self._sync_main_region(rows=self._rows)
        self._apply_text_geometry(bool(rows))

    _UNSET = object()

    def _sync_main_region(self, *, text=_UNSET, icon=_UNSET, rows=_UNSET) -> None:
        controller = getattr(self, "_controller", None)
        if controller is None:
            return
        for region in controller.regions:
            if region.id == "_main":
                if text is not self._UNSET:
                    region.text = text
                if icon is not self._UNSET:
                    region.icon = icon
                if rows is not self._UNSET:
                    region.rows = rows
                return

    def _apply_text_geometry(self, has_text: bool):
        had_text = self._has_text
        self._has_text = has_text
        if has_text and not had_text:
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            self.setMinimumHeight(max(32, self.minimumHeight()))
            self.setMaximumHeight(16777215)
            self._corner_radius_px = 2
            self.setProperty("cornerRadiusPx", 2)
        elif not has_text and had_text:
            self.setFixedSize(36, 36)
            self._corner_radius_px = 6
            self.setProperty("cornerRadiusPx", 6)
        self.updateGeometry()
        self.update()

    # -------- misc visual state --------

    def setFlyoutOpen(self, is_open: bool):
        self._flyout_open = is_open
        if not is_open:
            self._hovered = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def setIconSize(self, size: QSize):
        self._icon_size_px = max(1, size.width())
        self.update()

    def set_footer_mode(self, is_footer: bool):
        self._is_footer = is_footer
        self.update()

    def set_bottom_extension(self, factor: float):
        """Compat: no-op (handled inside paint if needed)."""
        pass

    # -------- size hints --------

    def sizeHint(self):
        if self._has_text:
            fm = self.fontMetrics()
            text_w = fm.horizontalAdvance(self._text) if self._text else 0
            icon_w = self._icon_size_px + self._gap_px if self._icon_unchecked else 0
            w = text_w + icon_w + 24
            h = max(32, fm.height() + 16)
            return QSize(w, h)
        return QSize(36, 36)

    def minimumSizeHint(self):
        return self.sizeHint()

    # -------- variant / density / corner radius / icon size --------

    def getVariant(self) -> str:
        return self._variant

    def setVariant(self, variant: str):
        self._variant = str(variant or "default")
        if self._variant == "primary":
            warn_deprecated(BUTTON_PRIMARY_VARIANT, stacklevel=2)
            self._variant = "surface"
        self.setProperty("variant", self._variant)
        update_widget_style(self)

    def getDensity(self) -> str:
        return self._density

    def setDensity(self, density: str):
        self._density = str(density or "normal")
        self.setProperty("density", self._density)
        update_widget_style(self, update_geometry=True)

    def getIconSizePx(self) -> int:
        return int(self._icon_size_px)

    def setIconSizePx(self, size_px: int):
        size_px = max(1, int(size_px))
        if self._icon_size_px != size_px:
            self._icon_size_px = size_px
            self.setProperty("iconSizePx", size_px)
            update_widget_style(self, update_geometry=True)

    def getGap(self) -> int:
        return int(self._gap_px)

    def setGap(self, gap: int):
        gap = max(0, int(gap))
        if self._gap_px != gap:
            self._gap_px = gap
            self.update()

    def getContentAlign(self) -> Qt.AlignmentFlag:
        return self._content_align

    def setContentAlign(self, align: Qt.AlignmentFlag):
        if self._content_align != align:
            self._content_align = align
            self.update()

    def getContentPadding(self) -> tuple[float, float, float, float]:
        return self._content_padding

    def setContentPadding(self, padding: float | tuple[float, float, float, float]):
        padding = normalize_content_padding(padding)
        if self._content_padding != padding:
            self._content_padding = padding
            self.update()

    def getCornerRadiusPx(self) -> int:
        return int(self._corner_radius_px)

    def setCornerRadiusPx(self, radius_px: int):
        radius_px = max(0, int(radius_px))
        if self._corner_radius_px != radius_px:
            self._corner_radius_px = radius_px
            self.setProperty("cornerRadiusPx", self._corner_radius_px)
            update_widget_style(self)

    def getForegroundColor(self):
        return self._foreground_color

    def setForegroundColor(self, color):
        self._foreground_color = color
        self.setProperty("foregroundColor", color)
        update_widget_style(self)

    def getAccentColor(self):
        return self._accent_color

    def setAccentColor(self, color):
        self._accent_color = color
        self.setProperty("accentColor", color)
        update_widget_style(self)

    # -------- Qt dynamic property dispatcher --------

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            name = event.propertyName().data().decode("utf-8", errors="ignore")
            self._handle_property_change(name)
        from PySide6.QtWidgets import QWidget
        return QWidget.event(self, event)

    def _handle_property_change(self, name: str):
        needs_geometry = False
        if name == "variant":
            self._variant = str(self.property("variant") or self._variant)
        elif name == "density":
            self._density = str(self.property("density") or self._density)
            needs_geometry = True
        elif name == "iconSizePx":
            self._icon_size_px = max(1, int(self.property("iconSizePx") or self._icon_size_px))
            needs_geometry = True
        elif name == "cornerRadiusPx":
            raw_radius = self.property("cornerRadiusPx")
            if raw_radius is not None:
                self._corner_radius_px = max(0, int(raw_radius))
        elif name in {"foregroundColor", "textColor"}:
            self._foreground_color = self.property(name) or self._foreground_color
        elif name == "backgroundColor":
            self._background_color = self.property("backgroundColor") or self._background_color
        elif name == "accentColor":
            self._accent_color = self.property("accentColor") or self._accent_color
        elif name == "underlineColor":
            self._underline_config_color = self.property("underlineColor")
        elif name == "showUnderline":
            self._show_underline = bool(self.property("showUnderline"))
        elif name == "underlineThicknessPx":
            value = self.property("underlineThicknessPx")
            self._underline_thickness = _normalize_underline_thickness(value)
        else:
            return
        update_widget_style(self, update_geometry=needs_geometry)

    def _is_strike_through(self) -> bool:
        return self._show_strike_through and self._checked
