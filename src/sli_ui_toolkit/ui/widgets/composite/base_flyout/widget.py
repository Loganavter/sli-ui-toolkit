"""BaseFlyout — the in-window flyout shell (thin facade).

The class keeps only construction, Qt-required event names, and the
inspection spec; the concerns live in sibling mixin modules (buttons/
style_api.py + events.py is the same pattern):

- ``style.py``      — ``_FlyoutStyleApi``      panel fill / border / shadow + paint
- ``builder.py``    — ``_FlyoutBuilderApi``    add_section / add_row / add_radio_row
- ``animation.py``  — ``_FlyoutFadeMixin``     snapshot fade pipeline + hide fade
- ``placement.py``  — ``_FlyoutPlacementApi``  show_aligned / reposition
- ``lifecycle.py``  — ``_FlyoutLifecycleApi``  hide / show / raise_ / focus restore
- ``contract.py``   — ``_FlyoutManagerApi``    hit-testing surface for FlyoutManager
- ``geometry.py``   — pure placement math (no widget state)
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    QParallelAnimationGroup,
    QPropertyAnimation,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import QBrush, QColor, QPixmap
from PySide6.QtWidgets import QApplication, QRhiWidget, QWidget

from sli_ui_toolkit.managers import FlyoutManager
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.in_window_surface import (
    attach_in_window_widget,
    create_shadow_surface,
)
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField
from sli_ui_toolkit.ui.widgets.composite.gpu_fill.widget import FlyoutGpuFillWidget
from sli_ui_toolkit.ui.widgets.helpers.rounded_clip import RoundedClipEffect

from .animation import FlyoutFadeController
from .builder import _FlyoutBuilderApi
from .contract import _FlyoutManagerApi
from .lifecycle import _FlyoutLifecycleApi
from .placement import _FlyoutPlacementApi
from .style import _FlyoutStyleApi


class BaseFlyout(
    _FlyoutStyleApi,
    _FlyoutBuilderApi,
    _FlyoutPlacementApi,
    _FlyoutLifecycleApi,
    _FlyoutManagerApi,
    QWidget,
):
    """In-window flyout shell. Mixins precede ``QWidget`` so their overrides
    (``show``/``hide``/``raise_``/``paintEvent``) win the MRO; ``super()``
    inside them still resolves to QWidget's own methods."""

    SHADOW_RADIUS = 8
    CONTENT_RADIUS = 8

    def __init__(
        self,
        parent=None,
        *,
        attach_overlay: bool = True,
        pinned: bool = False,
        gpu_fill: bool = False,
        gpu_fill_api: "QRhiWidget.Api | None" = None,
    ):
        if parent is None:
            raise ValueError("BaseFlyout requires an in-window parent widget")
        super().__init__(parent)

        # Pinned flyouts (persistent HUDs, e.g. a zoom-percent or info chip
        # anchored to a canvas) opt out of FlyoutManager's passive-dismiss
        # paths: outside click, outside wheel, app/window deactivate, and
        # anchor move/resize no longer hide them (see FlyoutManager._dismiss_passive
        # / _close_flyouts_with_moved_anchors). An explicit close_all() still
        # closes them. Callers are expected to keep them positioned via
        # reposition() (e.g. from the host's resize/move handlers) since the
        # manager will not do it for them.
        self.pinned = pinned

        # Fade-in/fade-out state. Must exist before attach_in_window_widget()
        # below: the overlay attach can call self.hide() during __init__ (host
        # overlays re-parent and hide the widget), and hide() reads these.
        self._show_animation: (
            QParallelAnimationGroup | QPropertyAnimation | QVariantAnimation | None
        ) = None
        self._hide_animation = None
        # Current fade opacity (1.0 = fully opaque). Fade is implemented
        # without a QGraphicsEffect: a one-shot snapshot of the flyout is
        # captured outside paintEvent (see _capture_fade_cache) and paintEvent
        # composites it with this opacity. A graphics effect on the shell would
        # conflict with the container's RoundedClipEffect (nested effects) and
        # with this widget's own QPainter(self) paintEvent, which shows up as
        # "A paint device can only be painted by one painter at a time" /
        # "Unbalanced save/restore" warnings on real composited windows.
        # In-window flyouts are plain child widgets (not toplevels), so
        # windowOpacity() would not work either.
        # All fade state (snapshot cache, opacity, hide-fade animation,
        # flags) lives in the controller; the widget only references it.
        self._fade = FlyoutFadeController()

        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Non-window child widgets are visible by default in Qt as soon as
        # their ancestor window is shown. Flyouts must stay hidden until an
        # explicit show()/show_aligned() call, otherwise every flyout ever
        # constructed (e.g. via eager tab creation at startup) flashes on
        # screen the moment the main window becomes visible. Use the base
        # QWidget.hide() here (not self.hide()) to avoid the overridden
        # hide()'s activateWindow()/setFocus() side effects during __init__.
        QWidget.hide(self)
        self.overlay_layer = (
            attach_in_window_widget(self, parent) if attach_overlay else None
        )
        self._anchor_widget: QWidget | None = None

        self._main_layout, self.container, self.content_layout = create_shadow_surface(
            self,
            shadow_radius=self.SHADOW_RADIUS,
            container_object_name="FlyoutContainer",
        )
        # Background + border are painted on the flyout shell; children are clipped
        # to the same corner radius so row hovers/ripples do not bleed past corners.
        self.container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._container_clip = RoundedClipEffect(self.CONTENT_RADIUS, self.container)
        self.container.setGraphicsEffect(self._container_clip)

        # Host-overridable surface style (background/border/shadow) — see
        # set_background_brush / set_border_color / set_shadow_color below.
        # None means "use the theme token", matching Button's
        # override_bg/border_color/hover_color convention in style_api.py.
        self._background_brush: QBrush | None = None
        self._border_color_override: QColor | None = None
        self._shadow_color: QColor | None = None

        # Opt-in second rendering path for the panel fill: a QRhiWidget child
        # sitting behind content_layout's widgets, painting via a GPU shader
        # instead of paintEvent's QBrush fill. Off by default -- the QPainter
        # path above stays the only path unless a caller asks for gpu_fill.
        # Currently solid-color only (see gpu_fill/widget.py); a brush that
        # isn't a flat QColor falls back to the QPainter fill even with
        # gpu_fill=True.
        self._gpu_fill: FlyoutGpuFillWidget | None = None
        if gpu_fill:
            self._gpu_fill = FlyoutGpuFillWidget(self.container, api=gpu_fill_api)
            self._gpu_fill.lower()
            self._gpu_fill.setGeometry(self.container.rect())
            # Starts hidden: only a *solid-color* set_background_brush() call
            # turns it on (see there). Until then the theme-token default /
            # a gradient / texture brush still goes through paintEvent's
            # QPainter fill below, same as gpu_fill=False.
            self._gpu_fill.setVisible(False)
            self.container.installEventFilter(self)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_base_style)
        self._apply_base_style()

        self.flyout_manager = FlyoutManager.get_instance()
        if attach_overlay:
            self.flyout_manager.register_flyout(self)
            self.destroyed.connect(lambda: self.flyout_manager.unregister_flyout(self))

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        if key in (
            Qt.Key.Key_Up, Qt.Key.Key_Down,
            Qt.Key.Key_Left, Qt.Key.Key_Right,
        ):
            if self._navigate_focusable(key):
                event.accept()
                return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focused = QApplication.focusWidget()
            if focused is not None and focused is not self:
                from PySide6.QtWidgets import QAbstractButton
                if isinstance(focused, QAbstractButton):
                    focused.click()
                    event.accept()
                    return
        super().keyPressEvent(event)

    def _navigate_focusable(self, key: int) -> bool:
        """Move focus to the next/previous StrongFocus child.

        Returns ``True`` if focus was moved, ``False`` to yield.
        """
        children = [
            c for c in self.findChildren(QWidget)
            if (
                c.focusPolicy() == Qt.FocusPolicy.StrongFocus
                and c.isVisible()
                and c.isEnabled()
            )
        ]
        if not children:
            return False
        focused = QApplication.focusWidget()
        idx = next((i for i, c in enumerate(children) if c is focused), None)
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            target = children[(idx + 1) % len(children)] if idx is not None else children[0]
        else:
            target = children[(idx - 1) % len(children)] if idx is not None else children[-1]
        target.setFocus(Qt.FocusReason.MouseFocusReason)
        return True

    def eventFilter(self, obj, event):  # noqa: N802 — Qt API
        if (
            self._gpu_fill is not None
            and obj is self.container
            and event.type() == QEvent.Type.Resize
        ):
            self._gpu_fill.setGeometry(self.container.rect())
        return super().eventFilter(obj, event)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def _fade_opacity_proxy(self) -> float:
        return self._fade.opacity


BaseFlyout.inspect_spec = InspectSpec(  # type: ignore[attr-defined]
    family="BaseFlyout",
    state=(
        SpecField("pinned", "pinned"),
        SpecField("flyout_group", "flyout_group"),
        SpecField("anchor", "_anchor_widget", private=True),
        SpecField("fade_opacity", "_fade_opacity_proxy", private=True),
        SpecField("visible", "isVisible"),
    ),
    token_family=("flyout.background", "flyout.border", "shadow.color", "separator.color"),
    docs='docs/user/FLYOUT_SYSTEM.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

BaseFlyout.widget_descriptor = WidgetDescriptor(
    family=BaseFlyout.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(BaseFlyout.inspect_spec, 'config', ()),
        state=BaseFlyout.inspect_spec.state,
        token_family=getattr(BaseFlyout.inspect_spec, 'token_family', ()),
        regions=getattr(BaseFlyout.inspect_spec, 'regions', False),
        layers=getattr(BaseFlyout.inspect_spec, 'layers', False),
        docs=getattr(BaseFlyout.inspect_spec, 'docs', ''),
        preview_seed=getattr(BaseFlyout.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(BaseFlyout.inspect_spec, 'apply_config_refresh', None),
    ),
)