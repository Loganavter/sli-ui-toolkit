import copy
import logging
import os
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

theme_logger = logging.getLogger("ThemeManager")


def _ripple_remaining_ms(widget: QWidget) -> int:
    """Duck-typed peek at toolkit button ripple state (avoids import cycles)."""
    best = 0
    candidates: list[object] = []
    ripple = getattr(widget, "_ripple", None)
    if ripple is not None:
        candidates.append(ripple)
    region = getattr(widget, "_region_ripple", None)
    if isinstance(region, dict):
        candidates.extend(region.values())
    for effect in candidates:
        if effect is None:
            continue
        remaining = getattr(effect, "remaining_ms", None)
        if callable(remaining):
            best = max(best, int(remaining()))
            continue
        if not callable(getattr(effect, "is_active", None)):
            continue
        if not effect.is_active():
            continue
        elapsed = int(getattr(effect, "_elapsed", 0) or 0)
        duration = int(getattr(effect, "DURATION_MS", 280) or 280)
        best = max(best, max(0, duration - elapsed))
    return best


def _tree_ripple_remaining_ms(root: QWidget, *, limit: int = 8000) -> int:
    best = 0
    stack: list[QWidget] = [root]
    seen = 0
    while stack and seen < limit:
        widget = stack.pop()
        seen += 1
        best = max(best, _ripple_remaining_ms(widget))
        if best > 0 and seen > 64:
            # Once any active ripple is found, remaining ms is enough for delay.
            # Keep scanning siblings of the same top-level only lightly.
            pass
        for child in widget.children():
            if isinstance(child, QWidget):
                stack.append(child)
    return best


def max_active_ripple_remaining_ms(app: QApplication | None = None) -> int:
    """Longest remaining button-ripple duration across top-level windows."""
    app = app or QApplication.instance()
    if app is None:
        return 0
    try:
        from sli_ui_toolkit.ui.widgets.buttons.feedback import get_ripple_duration_ms

        cap = get_ripple_duration_ms()
    except Exception:
        cap = 280
    best = 0
    for top in app.topLevelWidgets():
        best = max(best, _tree_ripple_remaining_ms(top))
        if best >= cap:
            return best
    return best


def _tree_has_active_ripple(root: QWidget) -> bool:
    return _tree_ripple_remaining_ms(root) > 0


class ThemeManager(QObject):
    theme_changed = Signal()

    _instance: Optional["ThemeManager"] = None

    def __init__(self):
        super().__init__()
        self._current_theme = "light"
        self._light_palette = {}
        self._dark_palette = {}
        self._qss_template = ""
        self._qss_paths = []
        self._update_suspend_depth = 0
        self._update_suspend_state: List[Tuple[QWidget, bool]] = []
        self._pending_theme: str | None = None
        self._theme_flush_scheduled = False
        self._theme_flush_app: QApplication | None = None

    @classmethod
    def get_instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_palettes(self, light_palette: Dict, dark_palette: Dict = None):
        self._light_palette = copy.deepcopy(light_palette)
        if dark_palette:
            self._dark_palette = copy.deepcopy(dark_palette)
        else:
            self._dark_palette = copy.deepcopy(light_palette)

    def register_qss_path(self, qss_path: str):
        if os.path.exists(qss_path):
            self._qss_paths.append(qss_path)
            self._load_qss_template()
        else:
            theme_logger.warning("QSS file not found: %s", qss_path)

    def get_color(self, color_key: str) -> QColor:
        palette = self._dark_palette if self.is_dark() else self._light_palette
        value = palette.get(color_key)

        if isinstance(value, QColor):
            return QColor(value)
        if isinstance(value, str):
            return QColor(value)
        return QColor("#000000")

    def try_get_color(self, color_key: str) -> QColor | None:
        """Return the color for *color_key*, or ``None`` if the key is absent."""
        palette = self._dark_palette if self.is_dark() else self._light_palette
        value = palette.get(color_key)
        if value is None:
            return None
        if isinstance(value, QColor):
            return QColor(value)
        if isinstance(value, str):
            return QColor(value)
        return None

    def set_color(self, color_key: str, color: QColor):
        color_to_store = (
            QColor(color) if isinstance(color, QColor) else QColor(str(color))
        )
        if self.is_dark():
            self._dark_palette[color_key] = color_to_store
        else:
            self._light_palette[color_key] = color_to_store
        app = QApplication.instance()
        with self.suspend_widget_updates(app):
            self._apply_theme()
            self.theme_changed.emit()

    def get_current_theme(self) -> str:
        return self._current_theme

    def is_dark(self) -> bool:
        return self._current_theme == "dark"

    @contextmanager
    def suspend_widget_updates(self, app: QApplication | None = None):
        """Freeze top-level widget paints for one atomic theme apply + emit.

        Nest-safe. Without this, ``setStyleSheet`` + hundreds of
        ``theme_changed`` → ``update()`` slots paint frame-by-frame
        ("theme fills in gradually") and extend the UI freeze.

        Top-levels that currently host an active button ripple keep updates
        enabled so a finishing wave is not frozen mid-frame (QSS itself still
        blocks the GUI thread — prefer ``await_ripples`` / ``defer_click``).
        """
        app = app or QApplication.instance()
        if app is None:
            yield
            return

        if self._update_suspend_depth == 0:
            state: List[Tuple[QWidget, bool]] = []
            for widget in app.topLevelWidgets():
                try:
                    if _tree_has_active_ripple(widget):
                        continue
                    state.append((widget, widget.updatesEnabled()))
                    widget.setUpdatesEnabled(False)
                except RuntimeError:
                    continue
            self._update_suspend_state = state
        self._update_suspend_depth += 1
        try:
            yield
        finally:
            self._update_suspend_depth = max(0, self._update_suspend_depth - 1)
            if self._update_suspend_depth == 0:
                state = self._update_suspend_state
                self._update_suspend_state = []
                for widget, enabled in state:
                    try:
                        widget.setUpdatesEnabled(enabled)
                        if enabled:
                            widget.update()
                    except RuntimeError:
                        continue

    def set_theme(
        self,
        theme_name: str,
        app=None,
        *,
        await_ripples: bool = True,
    ):
        """Apply *theme_name* to the application.

        When *await_ripples* is true (default), a live button ripple delays the
        blocking QSS/polish work until the wave finishes. That keeps the press
        animation on the GUI thread instead of freezing it mid-flight — QSS
        cannot run off-thread, so waiting is the reliable mitigation.
        """
        new_theme = "dark" if theme_name == "dark" else "light"
        app = app or QApplication.instance()

        if self._current_theme == new_theme and self._pending_theme is None:
            if app is not None and not app.styleSheet():
                self.apply_theme_to_app(app)
            return

        self._pending_theme = new_theme
        self._theme_flush_app = app
        delay = 0
        if await_ripples and app is not None:
            delay = max_active_ripple_remaining_ms(app)
        if delay > 0:
            if not self._theme_flush_scheduled:
                self._theme_flush_scheduled = True
                QTimer.singleShot(delay, self._flush_pending_theme)
            return
        self._flush_pending_theme()

    def _flush_pending_theme(self) -> None:
        self._theme_flush_scheduled = False
        pending = self._pending_theme
        self._pending_theme = None
        app = self._theme_flush_app or QApplication.instance()
        self._theme_flush_app = None
        if pending is None:
            return
        if self._current_theme == pending:
            return
        self._current_theme = pending
        # Hold paints across QSS apply *and* theme_changed fan-out.
        with self.suspend_widget_updates(app):
            if app and self._qss_template:
                self.apply_theme_to_app(app)
            else:
                self._apply_theme()
            self.theme_changed.emit()

    def _load_qss_template(self):
        templates = []
        for qss_path in self._qss_paths:
            if os.path.exists(qss_path):
                try:
                    with open(qss_path, "r", encoding="utf-8") as f:
                        templates.append(f.read())
                    theme_logger.info("Loaded QSS part from: %s", qss_path)
                except Exception as exc:
                    theme_logger.error("Error loading QSS %s: %s", qss_path, exc)

        self._qss_template = "\n/* --- NEW FILE --- */\n".join(templates)
        if templates:
            theme_logger.info("Loaded %d QSS file(s)", len(templates))
        else:
            theme_logger.warning("Could not find any registered QSS file")

    def apply_theme_to_app(self, app):
        with self.suspend_widget_updates(app):
            self._apply_theme_to_app_unlocked(app)

    def _apply_theme_to_app_unlocked(self, app):
        palette_data = self._dark_palette if self.is_dark() else self._light_palette

        if not palette_data:
            theme_logger.warning("No palettes registered, skipping theme application")
            return

        q_palette = QPalette()
        color_roles = {
            "Window": QPalette.ColorRole.Window,
            "WindowText": QPalette.ColorRole.WindowText,
            "Base": QPalette.ColorRole.Base,
            "AlternateBase": QPalette.ColorRole.AlternateBase,
            "ToolTipBase": QPalette.ColorRole.ToolTipBase,
            "ToolTipText": QPalette.ColorRole.ToolTipText,
            "Text": QPalette.ColorRole.Text,
            "Button": QPalette.ColorRole.Button,
            "ButtonText": QPalette.ColorRole.ButtonText,
            "BrightText": QPalette.ColorRole.BrightText,
            "Highlight": QPalette.ColorRole.Highlight,
            "HighlightedText": QPalette.ColorRole.HighlightedText,
        }

        for name, role in color_roles.items():
            if name in palette_data:
                color = QColor(palette_data[name])
                q_palette.setColor(role, color)

        app.setPalette(q_palette)

        processed_palette = palette_data.copy()
        if "accent" in processed_palette:
            accent_color = QColor(processed_palette["accent"])
            hover_color = (
                accent_color.lighter(115)
                if self.is_dark()
                else accent_color.darker(115)
            )
            processed_palette["accent.hover"] = hover_color

        current_qss = self._qss_template
        sorted_keys = sorted(processed_palette.keys(), key=len, reverse=True)

        for key in sorted_keys:
            color = processed_palette[key]
            if isinstance(color, QColor):
                placeholder = f"@{key}"
                if placeholder in current_qss:
                    current_qss = current_qss.replace(
                        placeholder, color.name(QColor.NameFormat.HexArgb)
                    )

        # Clear then set in one go — do *not* processEvents between them.
        # A mid-apply flush paints a half-themed tree and lengthens the freeze.
        app.setStyleSheet("")
        app.setStyleSheet(current_qss)

        main_window = app.activeWindow()
        if main_window:
            main_window.style().unpolish(main_window)
            main_window.style().polish(main_window)
            main_window.update()

    def _apply_theme(self):
        app = QApplication.instance()
        if app is None:
            return

        self.apply_theme_to_app(app)

    def apply_theme_to_dialog(self, dialog):
        palette_data = self._dark_palette if self.is_dark() else self._light_palette

        if not palette_data:
            theme_logger.warning(
                "No palettes registered, skipping dialog theme application"
            )
            return

        color_roles = {
            "Window": QPalette.ColorRole.Window,
            "WindowText": QPalette.ColorRole.WindowText,
            "Base": QPalette.ColorRole.Base,
            "AlternateBase": QPalette.ColorRole.AlternateBase,
            "ToolTipBase": QPalette.ColorRole.ToolTipBase,
            "ToolTipText": QPalette.ColorRole.ToolTipText,
            "Text": QPalette.ColorRole.Text,
            "Button": QPalette.ColorRole.Button,
            "ButtonText": QPalette.ColorRole.ButtonText,
            "BrightText": QPalette.ColorRole.BrightText,
            "Highlight": QPalette.ColorRole.Highlight,
            "HighlightedText": QPalette.ColorRole.HighlightedText,
        }

        # Re-polish QSS first. unpolish/polish after setPalette() resets the
        # widget palette back to the pre-theme colors when an application
        # stylesheet is active (plain QLabel / dialog text then stay light).
        dialog.style().unpolish(dialog)
        dialog.style().polish(dialog)

        app = QApplication.instance()
        q_palette = QPalette(app.palette()) if app is not None else QPalette()
        for name, role in color_roles.items():
            if name in palette_data:
                color = QColor(palette_data[name])
                q_palette.setColor(role, color)

        dialog.setPalette(q_palette)
        dialog.updateGeometry()
        dialog.update()
