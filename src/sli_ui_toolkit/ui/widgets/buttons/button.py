"""Universal composable Button widget.

Заменяет набор узкоспециализированных кнопок (Icon/Toggle/LongPress/...).
Конфигурируется kwargs'ами или `ButtonConfig`. Архитектура декомпозирована:

- `style_api._ButtonStyleApi` — публичные set/get визуальных атрибутов и
  обработка динамических Qt-properties.
- `events._ButtonEvents` — обработчики mouse/key/wheel/focus + click flow.
- `capabilities/` — composable behaviour (LongPress/...). Приложения
  могут добавлять свои capabilities через `attach_capability()` — Button не
  завязан на конкретные типы (см. `ButtonCapability.handle_wheel_event` для
  примера того, как накрафтить собственный scroll-counter на app-уровне).
- `painter.Painter` + `layers/` — рендер pipeline.

Сам класс Button содержит только: signals, state-properties, __init__,
capability API, state/value API и paint plumbing.
"""

from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

import dataclasses
import logging
import time
from collections.abc import Sequence
from typing import Any, ClassVar, TYPE_CHECKING, cast

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
import shiboken6 as sip

logger = logging.getLogger(__name__)
_last_button_paint_error_ts: float = 0.0
_BUTTON_PAINT_ERROR_THROTTLE_S = 5.0
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import UiFont
from sli_ui_toolkit.deprecations import (
    BUTTON_PRIMARY_VARIANT,
    BUTTON_SET_CHECKED_EMIT_SIGNAL,
    warn_deprecated,
)
from sli_ui_toolkit.i18n import get_current_language, translator_for
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.helpers import WheelScrollPolicyMixin, register_hover_widget

from .capabilities import (
    ButtonCapability,
    LongPressCapability,
)
from .content import (
    ButtonRow,
    build_button_content,
    build_region_content,
    draw_marquee_paints,
)
from sli_ui_toolkit.ui.widgets.helpers.marquee_text import ensure_marquee_driver
from .controller import ButtonController
from .context import DrawContext
from .events import _ButtonEvents
from .layers._base import Layer
from .layers.focus import FocusLayer
from .layers.overlay import OverlayPainterCallback, OverlayPainterLayer
from .layers.ripple import RippleEffect
from .feedback import (
    coerce_defer_click_ms,
    get_default_defer_click,
)
from . import painter as _painter_module
from .painter import Painter, default_layers
from .regions import ButtonRegion, Divider, RegionHandle, SingleRegionSplit, SplitLayout
from .specs import ButtonConfig, ButtonSpec, ShapeSpec, _to_corner_radii
from .state import ButtonState
from .style_api import (
    _ButtonStyleApi,
    _normalize_underline_thickness,
    normalize_content_padding,
)

if TYPE_CHECKING:
    # Runtime import lives at module bottom (after the class body) to
    # avoid a heavier import cycle; annotations stay lazy via __future__.
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor


#: States a ``group=`` mirrors across its regions. Re-asserted after a
#: region rebuild so a region created while the group is already in that state
#: does not start idle (see ``Button._reassert_group_states``).
_GROUP_MIRRORED_STATES = (
    ButtonState.HOVERED,
    ButtonState.PRESSED,
    ButtonState.CHECKED,
)


def _state_property(state: ButtonState):
    """Property-обёртка: bool геттер/сеттер, мутирующий StateSet и вызывающий update()."""

    def getter(self) -> bool:
        return state in self._region_states.get("_main", self._states)

    def setter(self, value: bool) -> None:
        states = self._region_states.get("_main", self._states)
        if value:
            states.add(state)
        else:
            states.discard(state)
        self.update()

    return property(getter, setter)


class Button(QWidget, WheelScrollPolicyMixin, _ButtonStyleApi, _ButtonEvents):
    clicked = Signal()
    pressed = Signal()
    released = Signal()
    regionClicked = Signal(str)
    rightClicked = Signal()
    middleClicked = Signal()

    # Declared here, assigned at module bottom (deferred widget_descriptor
    # import — see below): the inspector spec and unified descriptor.
    inspect_spec: ClassVar[InspectSpec]
    widget_descriptor: ClassVar[WidgetDescriptor]

    def enterEvent(self, event):
        _ButtonEvents.enterEvent(self, event)

    def leaveEvent(self, event):
        _ButtonEvents.leaveEvent(self, event)

    def mouseMoveEvent(self, event):
        _ButtonEvents.mouseMoveEvent(self, event)

    def mousePressEvent(self, event):
        _ButtonEvents.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        _ButtonEvents.mouseReleaseEvent(self, event)

    def wheelEvent(self, event):
        _ButtonEvents.wheelEvent(self, event)

    def keyPressEvent(self, event):
        _ButtonEvents.keyPressEvent(self, event)

    def focusInEvent(self, event):
        _ButtonEvents.focusInEvent(self, event)

    def focusOutEvent(self, event):
        _ButtonEvents.focusOutEvent(self, event)

    def setEnabled(self, enabled: bool) -> None:
        """Propagate widget enablement into the paint-state set.

        QWidget.setEnabled would otherwise shadow the events-mixin override
        (QWidget precedes _ButtonEvents in the MRO), so the DISABLED state
        never reached the painter and disabled buttons rendered exactly
        like enabled ones. The mixin still calls QWidget.setEnabled."""
        _ButtonEvents.setEnabled(self, enabled)

    def event(self, event):
        return _ButtonStyleApi.event(self, event)

    def changeEvent(self, event):
        # setFont()/setPalette()/setStyle() repaint through Qt internals,
        # bypassing the update() override — retire the snapshot explicitly.
        if event.type() in (
            QEvent.Type.FontChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.StyleChange,
        ):
            self._invalidate_static_cache()
        super().changeEvent(event)

    def update(self, *args: Any) -> None:
        """Full-widget repaints retire the static layer; tick rects don't.

        Every painted-content mutator (text/icon/rows, colors, variant,
        padding, regions, theme/font/scale switches, state flips) funnels
        through a full ``update()`` — bumping ``_content_version`` here
        invalidates the snapshot without touching any of those call sites.
        Marquee ticks repaint only the driver dirty rect
        (``update(QRect)``), so the idle 60fps crawl keeps its cache.

        The ``isValid`` guard matters because this override is a Python
        callable held by long-lived singleton signals (``theme_changed``,
        ``font_changed``): unlike a direct C++ slot connection, those do
        not auto-disconnect when the C++ object dies, so a late theme
        switch would otherwise re-enter ``QWidget.update`` on a deleted
        object (``RuntimeError`` in the Qt event loop).
        """
        if not sip.isValid(self):  # type: ignore[attr-defined]
            return
        if not args:
            self._invalidate_static_cache()
        super().update(*args)

    def _on_toolkit_font_changed(self) -> None:
        self._invalidate_static_cache()
        self.update()

    def sizeHint(self):
        return _ButtonStyleApi.sizeHint(self)

    def minimumSizeHint(self):
        return _ButtonStyleApi.minimumSizeHint(self)

    def hasHeightForWidth(self):
        return _ButtonStyleApi.hasHeightForWidth(self)

    def heightForWidth(self, width: int):
        return _ButtonStyleApi.heightForWidth(self, width)

    @staticmethod
    def _drop_singleton_slots(pairs) -> None:
        """Drop app-lifetime singleton connections at C++ destruction.

        Static on purpose (see the destroyed-hook above): no ``self``.
        Every disconnect is best-effort — a subclass that disconnected
        earlier, or singletons already torn down at app exit, must not
        fail teardown.
        """
        # One disconnect() call removes a single matching connection, but
        # app code may connect the same slot twice (gallery series-header
        # buttons get an extra theme_changed.connect(btn.update) in
        # grid_view.py) — loop until no matching connection remains.
        # The cap is paranoia: disconnect either removes one (progress)
        # or raises (done), so the loop always terminates.
        for signal, slot in pairs:
            for _ in range(64):
                try:
                    signal.disconnect(slot)
                except Exception:
                    # Best-effort: RuntimeError (no such connection),
                    # TypeError, or SystemError depending on teardown
                    # order — none of them may fail destruction.
                    break

    toggled = Signal(bool)
    longPressed = Signal()
    shortClicked = Signal()
    regionPressed = Signal(str)
    regionReleased = Signal(str)
    regionToggled = Signal(str, bool)
    regionLongPressed = Signal(str)
    actionTriggered = Signal(str, object)

    # Имена-алиасы для подклассов (CalendarDayButton) и capabilities.
    _hovered = _state_property(ButtonState.HOVERED)
    _pressed = _state_property(ButtonState.PRESSED)
    _checked = _state_property(ButtonState.CHECKED)

    def __init__(
        self,
        icon: Any = None,
        *,
        text: str = "",
        rows: list[ButtonRow] | None = None,
        text_key: str | None = None,
        toggle: bool = False,
        long_press: bool = False,
        long_press_ms: int = 600,
        badge: int | str | None = None,
        badge_key: str | None = None,
        show_underline: bool = False,
        underline_color: Any = None,
        underline_thickness: float | None = None,
        underline_tongue_reach: float | None = None,
        underline_ring: bool = False,
        underline_fade: bool | None = None,
        size: tuple[int, int] = (36, 36),
        icon_size: int = 22,
        gap: int = 6,
        content_align: Qt.AlignmentFlag = (
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        ),
        content_padding: float | tuple[float, float, float, float] = 0.0,
        corner_radius: int | None = None,
        corner_radii: tuple[int, int, int, int] | None = None,
        border_color: QColor | None = None,
        variant: str = "default",
        density: str = "normal",
        wheel_requires_focus: bool = False,
        background_color: QColor | None = None,
        defer_click: bool | int | str | None = None,
        text_fit: bool = False,
        width_texts: Sequence[str] | None = None,
        regions: list[ButtonRegion] | None = None,
        split: SplitLayout | None = None,
        divider: Divider | None = None,
        spec: ButtonSpec | None = None,
        config: ButtonConfig | None = None,
        layers: list[Layer] | None = None,
        extra_layers: list[Layer] | None = None,
        overlay_painter: OverlayPainterCallback | None = None,
        parent: QWidget | None = None,
    ):
        # Call QWidget directly. Cooperative ``super()`` through the non-QObject
        # mixins (WheelScrollPolicyMixin / style / events) can return NULL from
        # the Shiboken ``__init__`` wrapper on Python 3.14+ (SystemError, then
        # segfault when a ContextMenuRow is built for a title-bar menu).
        QWidget.__init__(self, parent)

        # Static-layer cache state — first, before any update() can fire
        # (the update() override below bumps the version on full repaints).
        self._content_version = 0
        self._static_cache: QPixmap | None = None
        self._static_key: tuple[Any, ...] | None = None
        self._marquee_row_paints: list[Any] = []
        self._paint_skip_marquee = False
        # Custom layers / overlay painters paint through the same snapshotted
        # pipeline (Painter.paint with the final layer list, incl. the
        # OverlayPainterLayer adapter), so the snapshot reproduces their
        # output exactly — no overlay/layer code in the repo reads the
        # marquee phase, and any animated paint code must call update(),
        # which bumps _content_version and re-snapshots per frame (fail-safe:
        # animated overlays degrade to today's full-pipeline behavior, never
        # frozen). Ripples keep their own per-tick guard. Always cache.
        self._static_cache_allowed = True
        self._static_fast_hits = 0

        if config is not None:
            cfg = config.to_kwargs()
            icon = cfg["icon"]
            text = cfg["text"]
            rows = cfg["rows"]
            toggle = cfg["toggle"]
            long_press = cfg["long_press"]
            long_press_ms = cfg["long_press_ms"]
            badge = cfg["badge"]
            show_underline = cfg["show_underline"]
            underline_color = cfg["underline_color"]
            underline_thickness = cfg["underline_thickness"]
            underline_tongue_reach = cfg["underline_tongue_reach"]
            underline_ring = cfg["underline_ring"]
            underline_fade = cfg["underline_fade"]
            size = cfg["size"]
            icon_size = cfg["icon_size"]
            corner_radius = cfg["corner_radius"]
            corner_radii = cfg["corner_radii"]
            border_color = cfg["border_color"]
            variant = cfg["variant"]
            density = cfg["density"]
            wheel_requires_focus = cfg["wheel_requires_focus"]
            defer_click = cfg["defer_click"]
            text_fit = cfg["text_fit"]

        if spec is not None:
            regions = spec.to_regions()
            split = spec.split
            divider = spec.divider
            size = spec.shape.size
            icon_size = spec.shape.icon_size
            corner_radius = spec.shape.corner_radius
            corner_radii = spec.shape.corner_radii
            variant = spec.variant
            density = spec.density
            wheel_requires_focus = spec.wheel_requires_focus
            defer_click = spec.defer_click
            if regions and regions[0].id == "_main":
                main = regions[0]
                icon = main.icon
                text = main.text
                rows = main.rows
                toggle = main.toggle
                long_press = main.long_press
                long_press_ms = main.long_press_ms
                badge = main.badge
                show_underline = bool(main.show_underline)
                underline_color = main.underline_color
                underline_thickness = main.underline_thickness
                background_color = main.custom_bg_color
                border_color = main.override_border_color

        if variant == "primary":
            warn_deprecated(BUTTON_PRIMARY_VARIANT, stacklevel=2)
            variant = "surface"

        self.init_wheel_scroll_policy(wheel_requires_focus=wheel_requires_focus)
        self._states: set[ButtonState] = set()
        self._region_states: dict[str, set[ButtonState]] = {"_main": self._states}
        self._regions: list[ButtonRegion] = []
        self._split: SplitLayout = split or SingleRegionSplit()
        self._divider: Divider | None = divider
        self._region_rects: dict[str, QRectF] = {}
        self._region_paths: dict[str, QPainterPath] = {}
        # Memo for the region-rect pass: the last ``_region_rects_cache_key()``
        # that was actually computed, plus a version bumped whenever the region
        # list / split / divider is rebuilt (see ``_region_rects_cache_key``).
        # ``None`` = never computed, so the first pass always runs.
        self._region_rects_token: tuple[Any, ...] | None = None
        self._regions_version = 0
        self._region_ripple: dict[str, RippleEffect] = {}
        self._hovered_region: str | None = None
        self._pressed_region: str | None = None

        if isinstance(icon, (tuple, list)) and len(icon) >= 2:
            self._icon_unchecked, self._icon_checked = icon[0], icon[1]
        else:
            self._icon_unchecked = self._icon_checked = icon

        self._has_toggle = toggle
        self._has_text = bool(text)
        self._text = text
        self._rows = rows or []
        self._rows_compact = False
        self._text_fit = bool(text_fit)
        self._width_texts: tuple[str, ...] = (
            tuple(str(t) for t in width_texts) if width_texts else ()
        )

        self._variant = variant
        self._density = density
        self._icon_size_px = icon_size
        self._gap_px = max(0, int(gap))
        self._content_align = content_align
        self._content_padding = normalize_content_padding(content_padding)
        if corner_radius is None:
            corner_radius = 2 if self._has_text else 6
        self._corner_radius_px = corner_radius
        # Corner-radii tuples are design px; the scaled copy feeds hit-test
        # and paint paths consistently and is re-derived in on_scale_changed.
        self._design_corner_radii: tuple[int, int, int, int] | None = (
            _to_corner_radii(corner_radii) if corner_radii is not None else None
        )
        self._corner_radii_px = self._scaled_corner_radii()
        self._border_color_override: QColor | None = border_color

        self.setProperty("variant", variant)
        self.setProperty("density", density)
        self.setProperty("iconSizePx", icon_size)
        self.setProperty("cornerRadiusPx", corner_radius)

        self._foreground_color: QColor | None = None
        self._background_color: QColor | None = None
        self._custom_bg_color: QColor | None = background_color
        self._accent_color: QColor | None = None
        self._show_underline = show_underline
        self._underline_thickness = _normalize_underline_thickness(underline_thickness)
        self._underline_tongue_reach = (
            None if underline_tongue_reach is None else max(0.0, float(underline_tongue_reach))
        )
        self._underline_ring = bool(underline_ring)
        self._underline_fade = None if underline_fade is None else bool(underline_fade)
        self._show_strike_through = False
        self._is_footer = False
        self._underline_config_color: QColor | list | None = underline_color
        self._override_bg_color: QColor | None = None
        self._bg_locked = False
        self._hover_color: QColor | None = None
        self._hover_compose: str = "replace"
        self._badge = badge
        self._text_key: str | None = None
        self._badge_key: str | None = None
        self._flyout_open = False

        if underline_color is not None:
            self.setProperty("underlineColor", underline_color)
        if self._underline_thickness is not None:
            self.setProperty("underlineThicknessPx", self._underline_thickness)

        w, h = size
        # Design px — re-applied scaled in ``on_scale_changed`` so live
        # factor changes actually resize fixed-size buttons.
        self._design_fixed_size = (0, 0)
        self._design_min_height = None
        if self._has_text and w == 36 and h == 36:
            self._design_min_height = 32
            self.setMinimumHeight(scaled_px(32))
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        elif w > 0 and h > 0:
            self._design_fixed_size = (int(w), int(h))
            self.setFixedSize(scaled_px(w), scaled_px(h))
        elif h > 0:
            self._design_fixed_size = (0, int(h))
            self.setFixedHeight(scaled_px(h))
        elif w > 0:
            self._design_fixed_size = (int(w), 0)
            self.setFixedWidth(scaled_px(w))

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Hover host (HoverCoordinator contract): an embedded action button
        # inside a composite card sets it via setHoverHost() so the whole card
        # is one hover surface. None → normal per-widget hover.
        self.hover_host: QWidget | None = None
        register_hover_widget(self)
        self.theme_manager = ThemeManager.get_instance()
        theme_sig = self.theme_manager.theme_changed
        scale_sig = UiScale.get_instance().scale_changed
        font_sig = UiFont.get_instance().font_changed
        # Capture bound slots as locals: the destroyed-hook below must
        # never touch the dying wrapper (attribute access on an object
        # under C++ destruction is refused), so everything it needs is
        # closed over here while the object is alive.
        _update = self.update
        _on_scale = self.on_scale_changed
        _on_font = self._on_toolkit_font_changed
        theme_sig.connect(_update)
        scale_sig.connect(_on_scale)
        # ui_font() results feed every text row (including the cached marquee
        # descriptors), so an app-font change must retire the snapshot — the
        # same class of invalidation as a theme switch.
        font_sig.connect(_on_font)
        # Singleton signals hold bound methods past C++ destruction (no
        # auto-disconnect for Python callables): without this, every dead
        # Button keeps firing on theme/font/scale switches, and a wrapper
        # whose address was reused by a new C++ object passes the
        # sip.isValid guard and crashes in the Qt event loop
        # (gallery suite: stale slot firing as QSpacerItem).
        # The hook is a closure over locals — NOT a bound method — because
        # bound-method slots on the dying object never run. The closure
        # itself dies with the last destroyed-connection, so it leaks
        # nothing.
        self.destroyed.connect(
            lambda _obj=None: Button._drop_singleton_slots(
                ((theme_sig, _update), (scale_sig, _on_scale), (font_sig, _on_font))
            )
        )

        effective_extra: list[Layer] = []
        if extra_layers:
            effective_extra.extend(extra_layers)
        if overlay_painter is not None:
            effective_extra.append(OverlayPainterLayer(overlay_painter))

        if layers is not None:
            final_layers = list(layers) + effective_extra
        elif effective_extra:
            final_layers = default_layers() + effective_extra
        else:
            final_layers = None

        # FocusLayer is always required for keyboard focus ring rendering.
        # Append it automatically when not already present so subclasses
        # that pass custom layers don't lose focus ring behavior.
        if final_layers is not None and not any(
            isinstance(l, FocusLayer) for l in final_layers
        ):
            final_layers.append(FocusLayer())

        self._painter = Painter(self.theme_manager, layers=final_layers)
        self._ripple = RippleEffect(self)
        self._region_ripple["_main"] = self._ripple
        self._ripple_color_from = None
        self._ripple_color_to = None
        self.set_defer_click(
            get_default_defer_click() if defer_click is None else defer_click
        )

        self._capabilities: list[ButtonCapability] = []
        self._capability_map: dict[tuple[type, str], ButtonCapability] = {}
        self._controller = ButtonController(self)
        # Shared marquee phase/timer; activated by RowsContent when a row overflows.
        ensure_marquee_driver(self)

        if long_press:
            self.attach_capability(LongPressCapability(delay_ms=long_press_ms))

        if regions is None:
            regions = [
                ButtonRegion(
                    id="_main",
                    icon=icon,
                    text=text,
                    rows=rows,
                    toggle=toggle,
                    long_press=long_press,
                    long_press_ms=long_press_ms,
                    badge=badge,
                    badge_key=badge_key,
                    text_key=text_key,
                    variant=variant,
                    custom_bg_color=background_color,
                    show_underline=show_underline,
                    underline_color=underline_color,
                    underline_thickness=self._underline_thickness,
                    icon_size_px=icon_size,
                    override_border_color=border_color,
                )
            ]
        if spec is not None:
            self.set_spec(spec)
        else:
            self.set_regions(regions, split=split, divider=divider)
        self._sync_wrap_height_policy()
        self._text_key = text_key
        self._badge_key = badge_key
        if self._has_translation_keys():
            # Resolve declarative keys immediately (mirrors ``setTextKey``);
            # a miss paints the key so the gap is visible, never silent English.
            self.retranslate(get_current_language())

    def _has_translation_keys(self) -> bool:
        if self._text_key is not None or self._badge_key is not None:
            return True
        for region in self._controller.regions:
            if region.text_key is not None or region.badge_key is not None:
                return True
            if any(getattr(row, "text_key", None) for row in (region.rows or [])):
                return True
        return False

    # -------- public API: translation keys --------

    def setTextKey(self, key: str | None) -> None:
        """Attach (or clear) the declarative translation key for ``_main`` text.

        The key wins over the literal ``text`` on every retranslate; clearing it
        leaves the last resolved string in place.
        """
        self._text_key = key
        if key is not None:
            self.retranslate(get_current_language())

    def setBadgeKey(self, key: str | None) -> None:
        """Attach (or clear) the declarative translation key for the badge."""
        self._badge_key = key
        if key is not None:
            self.retranslate(get_current_language())

    def set_translator(self, tr_func, *, defer_when_hidden: bool = False) -> None:
        """Duck-typed protocol hook used by ``bind_translator``/``install_translator``."""
        self._sli_translator = tr_func
        self._sli_defer_when_hidden = defer_when_hidden

    def retranslate(self, lang: str) -> None:
        """Re-resolve every keyed text/badge from ``translator_for(self)`` at *lang*.

        ``translatable_text`` silently no-ops on a rows button (the painter
        reads ``_rows``, not ``setText``); this updates the actual rows.
        """
        tr_func = translator_for(self)
        main_text_key = self._text_key
        main_badge_key = self._badge_key

        for region in list(self._controller.regions):
            if region.id == "_main":
                if main_text_key is None:
                    main_text_key = region.text_key
                if main_badge_key is None:
                    main_badge_key = region.badge_key
                continue
            if region.text_key is not None:
                self.update_region(region.id, text=tr_func(region.text_key, lang))
            if region.badge_key is not None:
                self.update_region(region.id, badge=tr_func(region.badge_key, lang))

        if main_text_key is not None:
            self.setText(tr_func(main_text_key, lang))
        if main_badge_key is not None:
            self.setBadge(tr_func(main_badge_key, lang))

        self._retranslate_rows(tr_func, lang)

    def _retranslate_rows(self, tr_func, lang: str) -> None:
        main_rows = list(getattr(self, "_rows", None) or [])
        if main_rows:
            new_rows = self._rows_with_translations(main_rows, tr_func, lang)
            if new_rows is not main_rows:
                self.setRows(new_rows, compact=bool(getattr(self, "_rows_compact", False)))
        for region in list(self._controller.regions):
            if region.id == "_main" and main_rows:
                continue
            rows = list(region.rows or [])
            if not rows:
                continue
            new_rows = self._rows_with_translations(rows, tr_func, lang)
            if new_rows is not rows:
                self.update_region(region.id, rows=new_rows)

    @staticmethod
    def _rows_with_translations(rows: list[ButtonRow], tr_func, lang: str) -> list[ButtonRow]:
        """Return *rows* with every ``text_key`` row re-resolved, else *rows*.

        Identity is preserved when nothing has a key (or nothing changed), so
        callers can skip the ``setRows``/``update_region`` re-apply.
        """
        changed = False
        out: list[ButtonRow] = []
        for row in rows:
            key = getattr(row, "text_key", None)
            if key:
                text = tr_func(key, lang)
                if text != getattr(row, "text", None):
                    out.append(dataclasses.replace(row, text=text))
                    changed = True
                    continue
            out.append(row)
        return out if changed else rows

    def on_scale_changed(self, _factor: float) -> None:
        if self._design_min_height is not None:
            self.setMinimumHeight(scaled_px(self._design_min_height))
        w, h = self._design_fixed_size
        if w > 0 and h > 0:
            self.setFixedSize(scaled_px(w), scaled_px(h))
        elif h > 0:
            self.setFixedHeight(scaled_px(h))
        elif w > 0:
            self.setFixedWidth(scaled_px(w))
        self._sync_wrap_height_policy()
        self._corner_radii_px = self._scaled_corner_radii()
        self.updateGeometry()
        self.update()

    def _scaled_corner_radii(self) -> tuple[int, int, int, int] | None:
        design = self._design_corner_radii
        if design is None:
            return None
        # 0 (square corner) must stay 0 — scaled_px's min-1 clamp would turn
        # it into a 1px rounding at every factor. cast: design is always
        # exactly 4 elements (see _to_corner_radii / the attribute annotation).
        return cast(
            "tuple[int, int, int, int]",
            tuple(0 if v == 0 else scaled_px(v) for v in design),
        )

    @classmethod
    def from_spec(
        cls,
        spec: ButtonSpec,
        *,
        parent: QWidget | None = None,
        layers: list[Layer] | None = None,
    ) -> "Button":
        return cls(spec=spec, parent=parent, layers=layers)

    # -------- public API: capabilities --------

    def attach_capability(
        self,
        capability: ButtonCapability,
        region_id: str | None = None,
    ) -> None:
        key = (type(capability), region_id or "_main")
        if key in self._capability_map:
            self.detach_capability(type(capability), region_id=region_id)
        capability.attach(self, region_id=region_id or "_main")
        self._capabilities.append(capability)
        self._capability_map[key] = capability
        self._invalidate_static_cache()

    def detach_capability(
        self,
        capability_type: type[ButtonCapability],
        region_id: str | None = None,
    ) -> None:
        key = (capability_type, region_id or "_main")
        cap = self._capability_map.get(key)
        if cap:
            cap.detach(self)
            self._capabilities.remove(cap)
            del self._capability_map[key]
            self._invalidate_static_cache()

    def get_capability(
        self,
        capability_type: type[ButtonCapability],
        region_id: str | None = None,
    ) -> ButtonCapability | None:
        return self._capability_map.get((capability_type, region_id or "_main"))

    # -------- public API: regions --------

    def set_regions(
        self,
        regions: list[ButtonRegion],
        *,
        split: SplitLayout | None = None,
        divider: Divider | None = None,
    ) -> None:
        if not regions:
            regions = [ButtonRegion(id="_main")]
        seen: set[str] = set()
        normalized: list[ButtonRegion] = []
        for region in regions:
            if not region.id or region.id in seen:
                raise ValueError(f"duplicate or empty button region id: {region.id!r}")
            seen.add(region.id)
            normalized.append(region)
        effective_split = split if split is not None else (
            SingleRegionSplit() if len(normalized) == 1 else self._split
        )
        effective_divider = divider if (divider is not None or len(normalized) == 1) else self._divider
        self._controller.set_regions(
            normalized,
            split=effective_split,
            divider=effective_divider,
            shape=ShapeSpec(
                corner_radius=self._corner_radius_px,
                corner_radii=self._corner_radii_px,
                size=(self.width(), self.height()),
                icon_size=self._icon_size_px,
            ),
            variant=self._variant,
            density=self._density,
            defer_click=self._defer_click_ms is not None,
            wheel_requires_focus=getattr(self, "_wheel_requires_focus", False),
        )
        self._sync_region_aliases()
        self._detach_stale_region_capabilities(normalized)
        self._attach_region_capabilities(normalized)
        self._invalidate_region_rects_memo()
        self._recompute_region_rects()
        self._sync_wrap_height_policy()
        self._reassert_group_states()
        self.update()

    def _reassert_group_states(self) -> None:
        """Let regions added by :meth:`set_regions` inherit their group's state.

        ``set_regions`` creates fresh runtime state for every new region id, so
        a region introduced while its group is already hovered/pressed/checked
        started idle. A host that swaps its layout under the pointer (e.g. a
        toolbar control that grows a value half on enter and rebuilds on every
        value change) then painted that half with the idle background/text
        family — measured on ``ScrollValueButton``: the digit capsule resolved
        only the base colour (``#f0f0f0``) on a hovered body (``#e6e6e6``).
        State belongs to the control, not to the region id, so it is restored
        here instead of asking every host to re-assert it.
        """
        inherited: dict[str, set[ButtonState]] = {}
        for region in self._regions:
            group = getattr(region, "group", None)
            if not group:
                continue
            held = {
                state
                for state in self._controller.states(region.id)
                if state in _GROUP_MIRRORED_STATES
            }
            if held:
                inherited.setdefault(group, set()).update(held)
        if not inherited:
            return
        for region in self._regions:
            for state in inherited.get(getattr(region, "group", None), ()):
                if state not in self._controller.states(region.id):
                    self._controller.set_state(region.id, state, True)

    def set_spec(self, spec: ButtonSpec) -> None:
        self._apply_spec_widget_properties(spec)
        self._controller.set_spec(spec)
        self._sync_region_aliases()
        self._detach_stale_region_capabilities(self._regions)
        self._attach_region_capabilities(self._regions)
        self._invalidate_region_rects_memo()
        self._recompute_region_rects()
        self._sync_wrap_height_policy()
        self.update()

    def regions(self) -> list[ButtonRegion]:
        return list(self._regions)

    def region(self, region_id: str) -> RegionHandle:
        """Live read/write handle for a single region.

        Hides the split between static ``ButtonRegion`` fields (icon, text,
        colors, ...) and runtime state (checked, hovered, pressed): both are
        readable/writable as plain attributes, e.g.
        ``button.region("copy").checked = True``.
        """
        if self._region_by_id(region_id) is None:
            raise ValueError(f"unknown button region id: {region_id!r}")
        return RegionHandle(self, region_id)

    def region_rects(self) -> dict[str, QRectF]:
        """Live per-region rects in the button's own coordinates (read-only).

        Hosts that lay decorations/overlays over regions (or hit-test them)
        should not poke the private ``_region_rects``. Recomputed on demand
        when the button has not laid out yet; empty on any surprise.
        """
        try:
            if not self._region_rects:
                self._recompute_region_rects()
            return dict(self._region_rects)
        except Exception:
            return {}

    def region_rect(self, region_id: str) -> QRectF:
        """Live rect of a single region (button coordinates).

        Raises ``ValueError`` for an unknown region id (mirrors ``region()``).
        """
        rects = self.region_rects()
        if region_id not in rects:
            raise ValueError(f"unknown button region id: {region_id!r}")
        return QRectF(rects[region_id])

    def update_region(self, region_id: str, **changes: Any) -> None:
        """Replace one or more static ``ButtonRegion`` fields for ``region_id``.

        Other regions, and this region's runtime state (hover/ripple/checked),
        are preserved — ``set_regions`` reconciles by region id.
        """
        if not changes:
            return
        regions = list(self._controller.regions)
        for index, region in enumerate(regions):
            if region.id == region_id:
                regions[index] = dataclasses.replace(region, **changes)
                break
        else:
            raise ValueError(f"unknown button region id: {region_id!r}")
        self.set_regions(regions)

    def spec(self) -> ButtonSpec:
        return self._controller.spec

    def _sync_region_aliases(self) -> None:
        self._regions = self._controller.regions
        self._split = self._controller.split
        self._divider = self._controller.divider
        self._region_rects = self._controller.rects
        self._region_paths = self._controller.paths
        self._region_states = {
            region_id: runtime.states
            for region_id, runtime in self._controller.runtime.items()
        }
        self._region_ripple = {
            region_id: runtime.ripple
            for region_id, runtime in self._controller.runtime.items()
            if runtime.ripple is not None
        }
        self._states = self._region_states.setdefault("_main", self._states)
        self._ripple = self._region_ripple.get("_main", self._ripple)

    def _apply_spec_widget_properties(self, spec: ButtonSpec) -> None:
        self._variant = spec.variant
        self._density = spec.density
        self.set_defer_click(
            get_default_defer_click()
            if spec.defer_click is None
            else spec.defer_click
        )
        self.set_wheel_requires_focus(spec.wheel_requires_focus)
        self.setProperty("variant", self._variant)
        self.setProperty("density", self._density)
        self._icon_size_px = int(spec.shape.icon_size)
        self.setProperty("iconSizePx", self._icon_size_px)
        if spec.shape.corner_radius is not None:
            self._corner_radius_px = int(spec.shape.corner_radius)
            self.setProperty("cornerRadiusPx", self._corner_radius_px)
        if spec.shape.corner_radii is not None:
            self._design_corner_radii = _to_corner_radii(spec.shape.corner_radii)
            self._corner_radii_px = self._scaled_corner_radii()
        else:
            self._corner_radii_px = None
            self._design_corner_radii = None
        w, h = spec.shape.size
        self._design_min_height = None
        self._design_fixed_size = (0, 0)
        if w > 0 and h > 0:
            self._design_fixed_size = (int(w), int(h))
            self.setFixedSize(scaled_px(w), scaled_px(h))
        elif h > 0:
            self._design_fixed_size = (0, int(h))
            self.setFixedHeight(scaled_px(h))
        elif w > 0:
            self._design_fixed_size = (int(w), 0)
            self.setFixedWidth(scaled_px(w))

    def _detach_stale_region_capabilities(self, regions: list[ButtonRegion]) -> None:
        """Detach capabilities left over from regions that no longer exist.

        `set_regions`/`set_spec` are meant to be callable repeatedly as app
        state reshapes the button (e.g. 2 regions collapsing into 1).
        Capabilities are keyed by region id in `_capability_map`, so without
        this pass a region's capability (and its QTimer) would leak forever
        once that region id stops appearing in the new region set.
        """
        live_ids = {region.id for region in regions}
        for capability_type, region_id in list(self._capability_map.keys()):
            if region_id not in live_ids:
                self.detach_capability(capability_type, region_id=region_id)

    def _attach_region_capabilities(self, regions: list[ButtonRegion]) -> None:
        for region in regions:
            if region.long_press and self.get_capability(LongPressCapability, region.id) is None:
                self.attach_capability(
                    LongPressCapability(delay_ms=region.long_press_ms),
                    region_id=region.id,
                )

    # -------- public API: state/value --------

    def setChecked(self, checked: bool, emit: bool = True, emit_signal: bool | None = None):
        """emit_signal — backwards-compat alias for emit."""
        if emit_signal is not None:
            warn_deprecated(BUTTON_SET_CHECKED_EMIT_SIGNAL, stacklevel=2)
            emit = emit_signal
        if not self._has_toggle:
            return
        self.setRegionChecked("_main", checked, emit=emit)

    def isChecked(self) -> bool:
        return self._checked

    def setRegionChecked(self, region_id: str, checked: bool, *, emit: bool = True) -> None:
        """Programmatically set the CHECKED state of any region (not just `"_main"`).

        Generalizes `setChecked` — same effect a user click would have on a
        `toggle=True` region. When the region belongs to a ``group=``, CHECKED
        mirrors to every sibling in that group (same as HOVERED/PRESSED).
        """
        checked = bool(checked)
        linked = self._linked_region_ids(region_id)
        if all(
            (ButtonState.CHECKED in self._controller.states(rid)) == checked
            for rid in linked
        ):
            return
        self._set_region_state(region_id, ButtonState.CHECKED, checked)
        if "_main" in linked:
            self._checked = checked
        if emit:
            self.regionToggled.emit(region_id, checked)
            if region_id == "_main" or "_main" in linked:
                self.toggled.emit(checked)

    # -------- paint --------

    def _build_content(self):
        return build_button_content(self)

    def _build_region_content(self, region: ButtonRegion):
        return build_region_content(self, region)

    def _make_context(self, qpainter: QPainter) -> DrawContext:
        return _painter_module.make_draw_context(self, qpainter)

    def iter_regions(self, ctx: DrawContext):
        yield from _painter_module.iter_button_regions(self, ctx)

    def region_states(self, region_id: str) -> frozenset[ButtonState]:
        return frozenset(self._controller.states(region_id))

    def region_ripple(self, region_id: str) -> RippleEffect | None:
        return self._controller.ripple(region_id)

    # -------- static-layer cache (marquee fast path) --------

    def _invalidate_static_cache(self) -> None:
        """Retire the static snapshot (safe before attrs exist, via update())."""
        self._content_version = int(getattr(self, "_content_version", 0) or 0) + 1
        self._static_cache = None
        self._static_key = None
        self._marquee_row_paints = []

    def _static_key_now(self) -> tuple[Any, ...]:
        """Key for the snapshot: geometry + paint states + version + DPR.

        Mutators bump ``_content_version`` (via the ``update()`` override);
        hover/press/check/disable/focus flips ride in ``states`` (no bump
        needed); per-region hover targets ride along explicitly because
        ``_update_hover_region`` can move the highlight without a state
        change; resize/DPR changes fall out of the size/ratio terms.
        """
        states = frozenset(
            (region_id, state)
            for region_id, owned in self._region_states.items()
            for state in owned
        )
        size = self.size()
        return (
            size.width(),
            size.height(),
            states,
            self._hovered_region,
            self._pressed_region,
            self._content_version,
            float(self.devicePixelRatioF()),
        )

    def _ripple_active(self) -> bool:
        ripples = list(self._region_ripple.values())
        main = getattr(self, "_ripple", None)
        if main is not None and main not in ripples:
            ripples.append(main)
        return any(r is not None and r.is_active() for r in ripples)

    def _try_fast_marquee_paint(self, painter: QPainter, event: Any) -> bool:
        """Blit the static snapshot + replay marquee rows at tick phase.

        Zero context builds, zero region walks, zero background resolves,
        zero pixmap scaling, zero font metrics — the strip cache on the
        driver serves the row blits. Falls back (False) to the full
        pipeline on any doubt: missing/disabled cache, key mismatch,
        uncovered event rect, active ripple.
        """
        if not self._static_cache_allowed:
            return False
        cache = self._static_cache
        if cache is None or cache.isNull():
            return False
        paints = self._marquee_row_paints
        if not paints:
            return False
        driver = getattr(self, "_marquee_driver", None)
        if driver is None:
            return False
        dirty = driver.dirty_rect()
        if dirty is None or dirty.isEmpty():
            return False
        rect = event.rect()
        if rect.isEmpty() or not dirty.contains(rect, False):
            return False
        if self._static_key != self._static_key_now():
            return False
        if self._ripple_active():
            return False
        # The snapshot pixmap carries devicePixelRatio, so (0, 0) blits it
        # back onto exactly the widget rect it was rendered from.
        painter.drawPixmap(0, 0, cache)
        draw_marquee_paints(painter, paints, float(driver.phase), driver)
        self._static_fast_hits += 1
        return True

    def _maybe_snapshot_static(self, event: Any) -> None:
        """Re-render the static layer after a full paint with marquee live.

        One extra full render, amortized over hundreds of cheap ticks. Only
        from a paint that covered the whole widget — a row-clipped tick
        repaint must never bake a partial frame into the snapshot.
        """
        if not self._static_cache_allowed:
            return
        if not self._marquee_row_paints:
            return
        if self._ripple_active():
            return
        if not event.rect().contains(self.rect(), False):
            return
        key = self._static_key_now()
        if self._static_cache is not None and self._static_key == key:
            return
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        dpr = max(1.0, float(self.devicePixelRatioF() or 1.0))
        # Allocate in DEVICE px: a QPixmap(size) tagged with dpr gets a LOGICAL
        # canvas of size/dpr, so the full-widget render landed in the top-left
        # quadrant and every tick blitted that quadrant back (quarter-size
        # content at DPR>1). QPainter scales commands by the tagged ratio, so
        # the snapshot pipeline below keeps painting in logical px.
        pixmap = QPixmap(
            max(1, int(round(size.width() * dpr))),
            max(1, int(round(size.height() * dpr))),
        )
        if pixmap.isNull():
            return
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        snapshot = QPainter(pixmap)
        if not snapshot.isActive():
            return
        # ContentLayer calls RowsContent.draw(ctx, tm) without the skip
        # flag, so the flag travels on the widget for the snapshot render.
        self._paint_skip_marquee = True
        try:
            snapshot.save()
            try:
                self._painter.paint(self._make_context(snapshot))
            finally:
                snapshot.restore()
        finally:
            self._paint_skip_marquee = False
            snapshot.end()
        if pixmap.isNull():
            return
        self._static_cache = pixmap
        self._static_key = key

    def set_defer_click(self, value: bool | int | str) -> None:
        """Defer ``clicked`` / ``shortClicked`` relative to the press gesture.

        ``False`` — emit synchronously.
        ``True`` — next event-loop tick (one frame for the ripple to start).
        ``int`` — wait that many ms.
        ``"ripple"`` / ``DEFER_CLICK_AWAIT_RIPPLE`` — wait the process-wide
        ripple duration (``get_ripple_duration_ms()``).

        Construct with ``defer_click=None`` (default) to inherit
        ``get_default_defer_click()``.
        """
        self._defer_click_ms = coerce_defer_click_ms(value)

    def _dispatch_region_behavior(
        self,
        region_id: str | None,
        kind: str,
        data: Any = None,
    ) -> None:
        if region_id is None:
            return
        for behavior in self._controller.behaviors(region_id, kind):
            if behavior.action is None:
                continue
            payload = data if data is not None else behavior.data
            if behavior.callback is not None:
                behavior.callback(behavior.action, payload)
            self.actionTriggered.emit(behavior.action, payload)

    def _invalidate_region_rects_memo(self) -> None:
        """Force the next region-rect pass (the region *list* was rebuilt).

        ``recompute_rects`` reads per-region ``weight``/``rect_fn``/``path_fn``
        and groups, which a value key cannot compare (a closure keeps its
        identity while its captured state changes), so every rebuild of the
        list — ``set_regions`` / ``set_spec`` — invalidates the memo outright.
        """
        self._regions_version = int(getattr(self, "_regions_version", 0) or 0) + 1

    def _region_rects_cache_key(self) -> tuple[Any, ...]:
        """Inputs that feed ``ButtonController.recompute_rects``.

        Geometry (the widget rect) plus the shape/style values the controller
        reads through ``ButtonSpec``/``ShapeSpec``. When this key repeats, a
        recompute is guaranteed to reproduce the rects/paths already stored.
        The split/divider identities are a secondary signal only: a replaced
        layout always arrives with a rebuilt region list, which bumps
        ``_regions_version`` (an ``id()`` can be reused by a fresh object).
        """
        return (
            self.width(),
            self.height(),
            self._density,
            self._variant,
            self._corner_radius_px,
            self._corner_radii_px,
            self._icon_size_px,
            id(self._split),
            id(self._divider),
            int(getattr(self, "_regions_version", 0) or 0),
        )

    def _recompute_region_rects(self) -> bool:
        """Recompute region rects/paths unless their inputs are unchanged.

        ``ButtonController.recompute_rects`` walks every region twice and
        rebuilds its paths; a QLayout pass resizes buttons to the size they
        already have, and repeating that pass produced byte-identical rects at
        real cost (the app's session-mode sync blocked the GUI per toggle).
        The memo makes a no-change call free and keeps the controller the
        single source of rects.

        Returns True when a recompute actually ran — ``resizeEvent`` pairs the
        static-snapshot retirement with exactly that.
        """
        key = self._region_rects_cache_key()
        if key == self._region_rects_token and self._region_rects:
            return False
        self._region_rects_token = key
        self._controller.recompute_rects()
        self._region_rects = self._controller.rects
        self._region_paths = self._controller.paths
        return True

    def resizeEvent(self, event):
        # The snapshot bakes the region paths for the old geometry, so it
        # retires in the same breath as the rects — never on a resize to the
        # size the button already has (layout passes do that constantly).
        if self._recompute_region_rects():
            self._invalidate_static_cache()
        super().resizeEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._cancel_transient_effects()

    def _cancel_transient_effects(self) -> None:
        """A layout reflow can reposition this button out from under the
        cursor without Qt sending enter/leave events (those only fire on
        actual pointer movement). Left alone, hover glow and an in-flight
        ripple would keep animating at the button's new location even
        though the pointer never actually entered it there."""
        changed = False
        for ripple in list(self._region_ripple.values()):
            if ripple is not None and ripple.is_active():
                ripple.cancel()
                changed = True
        under_cursor = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        if not under_cursor:
            for states in list(self._region_states.values()):
                if ButtonState.HOVERED in states or ButtonState.PRESSED in states:
                    states.discard(ButtonState.HOVERED)
                    states.discard(ButtonState.PRESSED)
                    changed = True
        if changed:
            self.update()

    def hideEvent(self, event) -> None:  # noqa: N802
        driver = getattr(self, "_marquee_driver", None)
        if driver is not None:
            driver.set_active(False)
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        try:
            # Marquee tick fast path: blit the static snapshot + replay the
            # crawling rows. Qt still runs this whole handler per tick — the
            # win is skipping the pipeline inside it.
            if self._try_fast_marquee_paint(painter, event):
                painter.end()
                return
            self._marquee_row_paints = []
            painter.save()
            try:
                self._painter.paint(self._make_context(painter))
            finally:
                painter.restore()
                painter.end()
            self._maybe_snapshot_static(event)
        except Exception:
            global _last_button_paint_error_ts
            now = time.monotonic()
            if now - _last_button_paint_error_ts >= _BUTTON_PAINT_ERROR_THROTTLE_S:
                _last_button_paint_error_ts = now
                logger.exception("Button paint failed")
            else:
                logger.debug("Button paint failed (throttled)", exc_info=True)


# Backwards-compat: ButtonRow re-exported from button module.
__all__ = ["Button", "ButtonConfig", "ButtonRow"]

Button.inspect_spec = InspectSpec(
    family="Button",
    config=(
        SpecField("text"),
        SpecField("rows"),
        SpecField("toggle", "_has_toggle", private=True),
        SpecField("variant"),
        SpecField("density"),
        SpecField("content_align"),
        SpecField("content_padding"),
        SpecField("corner_radius", "_corner_radius_px", private=True),
        SpecField("corner_radii", "_corner_radii_px", private=True),
        SpecField("defer_click", "_defer_click", private=True),
    ),
    state=(
        SpecField("checked", "isChecked"),
        SpecField("hovered", "_hovered", private=True),
        SpecField("pressed", "_pressed", private=True),
        SpecField("hovered_region", "_hovered_region", private=True),
        SpecField("pressed_region", "_pressed_region", private=True),
        SpecField("icon_size_px", "iconSizePx"),
        SpecField("corner_radius_px", "cornerRadiusPx"),
    ),
    token_family=(
        "surface.list",
        "button.toggle.background.hover",
        "button.toggle.background.pressed",
        "button.toggle.background.checked",
        "button.toggle.background.checked.hover",
    ),
    regions=True,
    layers=True,
    docs="docs/user/BUTTON_API.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

Button.widget_descriptor = WidgetDescriptor(
    family="Button",
    inspect=InspectSection(
        config=Button.inspect_spec.config,
        state=Button.inspect_spec.state,
        token_family=Button.inspect_spec.token_family,
        regions=Button.inspect_spec.regions,
        layers=Button.inspect_spec.layers,
        docs=Button.inspect_spec.docs,
    ),
)
