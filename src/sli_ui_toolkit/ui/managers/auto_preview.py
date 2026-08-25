"""Auto-preview wiring for anchor→flyout.

One-line replacement for the 5× show_aligned boilerplate in every
ColorSettingsButton / PanelVisibility / _ScrollValueFlyout anchor:

    bind_auto_preview(btn, flyout, side="above")

Handles:
- Enter/Leave → preview (grab=False, register=False) + cancel/schedule auto_hide
- FocusIn(kbd) → preview
- MouseButtonPress/Enter → interactive (grab=True)
- Escape → hide
- FocusOut → hide if not inside flyout

Breaking API allowed — this is new, no compat needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AutoPreviewConfig:
    """Plain data object for auto-preview hide delay (host-agnostic).

    Hosts inject behaviour via this config or via
    ``sli_ui_toolkit.config.FlyoutTimingConfig`` instead of host fallback
    imports (AGENTS.md: inject via plain data objects / config hooks).
    """

    auto_hide_delay_ms: int | None = None


_SIDE_POINTS = {
    "above": ("top-center", "bottom-center"),
    "below": ("bottom-center", "top-center"),
    "left": ("center-left", "center-right"),
    "right": ("center-right", "center-left"),
}


class _AutoPreviewController(QObject):
    def __init__(
        self,
        anchor: QWidget,
        flyout: QWidget,
        side: str = "below",
        *,
        auto_hide_delay_ms: int | None = None,
        config: AutoPreviewConfig | None = None,
    ):
        super().__init__(anchor)
        self._anchor = anchor
        self._flyout = flyout
        self._side = side
        self._anchor_points = _SIDE_POINTS.get(side, _SIDE_POINTS["below"])
        # Injected delay: explicit arg > config object > toolkit FlyoutTimingConfig
        if auto_hide_delay_ms is not None:
            self._auto_hide_delay_ms: int | None = int(auto_hide_delay_ms)
        elif config is not None and config.auto_hide_delay_ms is not None:
            self._auto_hide_delay_ms = int(config.auto_hide_delay_ms)
        else:
            self._auto_hide_delay_ms = None
        anchor.installEventFilter(self)
        # Also filter flyout to keep hover zone alive if needed? No, flyout has its own auto_hide.

    def _has_visible(self) -> bool:
        try:
            if hasattr(self._flyout, "has_visible_actions"):
                return bool(self._flyout.has_visible_actions())
            return True
        except Exception:
            return True

    def _update_state(self):
        try:
            if hasattr(self._flyout, "update_state"):
                self._flyout.update_state()
        except Exception:
            pass

    def _show_preview(self):
        self._update_state()
        if not self._has_visible():
            return
        try:
            self._flyout.show_aligned(
                self._anchor,
                self._anchor_points[0],
                self._anchor_points[1],
                toggle=False,
                grab_focus=False,
                register_nav_section=False,
                animation="none",
            )
            if hasattr(self._flyout, "cancel_auto_hide"):
                self._flyout.cancel_auto_hide()
        except Exception:
            pass

    def _show_interactive(self):
        self._update_state()
        if not self._has_visible():
            return
        try:
            self._flyout.show_aligned(
                self._anchor,
                self._anchor_points[0],
                self._anchor_points[1],
                toggle=False,
                animation="none",
            )
            if hasattr(self._flyout, "cancel_auto_hide"):
                self._flyout.cancel_auto_hide()
        except Exception:
            pass

    def _schedule_hide(self):
        try:
            if hasattr(self._flyout, "schedule_auto_hide"):
                if self._auto_hide_delay_ms is not None:
                    delay = self._auto_hide_delay_ms
                else:
                    try:
                        from sli_ui_toolkit.config import get_flyout_timings

                        delay = get_flyout_timings().transient_auto_hide_delay_ms
                    except Exception:
                        logger.warning(
                            "auto_preview: could not resolve hide delay, using 400ms fallback",
                            exc_info=True,
                        )
                        delay = 400
                self._flyout.schedule_auto_hide(delay)
        except Exception:
            logger.warning("auto_preview: schedule_auto_hide failed", exc_info=True)

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is not self._anchor:
            return False
        t = event.type()
        # Hover preview
        if t == QEvent.Type.Enter:
            # Anchor's own enterEvent will still run (return False)
            # We show preview without stealing focus
            try:
                # Emit elementHovered if anchor has it? No, keep anchor's own signal.
                self._show_preview()
            except Exception:
                pass
        elif t == QEvent.Type.Leave:
            self._schedule_hide()
        elif t == QEvent.Type.FocusIn:
            try:
                reason = event.reason() if hasattr(event, "reason") else Qt.FocusReason.OtherFocusReason
                is_kbd = reason not in (Qt.FocusReason.MouseFocusReason, Qt.FocusReason.MenuBarFocusReason)
                # Also check NavigationManager last_input style
                try:
                    from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

                    if not is_kbd and NavigationManager.get_instance().last_input_was_keyboard():
                        is_kbd = True
                except Exception:
                    pass
                kbd_flag = getattr(self._anchor, "_keyboard_focus", False)
                if is_kbd and kbd_flag:
                    self._show_preview()
            except Exception:
                pass
        elif t == QEvent.Type.MouseButtonPress:
            try:
                # Left click → interactive
                if hasattr(event, "button") and event.button() == Qt.MouseButton.LeftButton:
                    self._show_interactive()
            except Exception:
                pass
        elif t == QEvent.Type.KeyPress:
            try:
                key = event.key()
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._show_interactive()
                    event.accept()
                    return True
                if key == Qt.Key.Key_Escape and self._flyout.isVisible():
                    self._flyout.hide()
                    event.accept()
                    return True
            except Exception:
                pass
        elif t == QEvent.Type.FocusOut:
            try:
                from PySide6.QtWidgets import QApplication

                new_focus = QApplication.focusWidget()
                if new_focus is not None and self._flyout.isAncestorOf(new_focus):
                    return False
                self._schedule_hide()
            except Exception:
                pass
        return False


def bind_auto_preview(
    anchor: QWidget,
    flyout: QWidget,
    side: str = "below",
    *,
    auto_hide_delay_ms: int | None = None,
    config: AutoPreviewConfig | None = None,
) -> _AutoPreviewController:
    """One-line anchor→flyout auto-preview wiring.

    Replaces 5 handlers (enter/leave/focusIn/mousePress/keyPress/focusOut) in
    every ColorSettingsButton-like anchor. Also calls NavigationManager.bind_flyout
    for Up/Down/Left/Right routing.

    side: "above"|"below"|"left"|"right" — Up/Down/Left/Right entry.
    ``auto_hide_delay_ms`` / ``config`` inject the hide delay host-agnostically
    (plain data object per AGENTS.md); falls back to
    ``get_flyout_timings().transient_auto_hide_delay_ms``.
    """
    try:
        from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

        NavigationManager.get_instance().bind_flyout(anchor, flyout, side=side, mode="preview")
    except Exception:
        logger.warning("bind_auto_preview: NavigationManager bind failed", exc_info=True)
    # Store controller on anchor to keep alive (parented to anchor, but also ref)
    controller = _AutoPreviewController(
        anchor, flyout, side=side, auto_hide_delay_ms=auto_hide_delay_ms, config=config
    )
    # Keep reference to avoid GC (QObject parent keeps it, but also anchor attr)
    try:
        if not hasattr(anchor, "_auto_preview_controllers"):
            anchor._auto_preview_controllers = []  # type: ignore[attr-defined]
        anchor._auto_preview_controllers.append(controller)  # type: ignore[attr-defined]
    except Exception:
        pass
    return controller
