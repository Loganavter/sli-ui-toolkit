import copy
import logging
import os
import re
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.ui_scale import UiScale

theme_logger = logging.getLogger("ThemeManager")

# Alias table for theme token de-duplication (plan_theme_token_unification.md Phase 4).
# Canonical surface.* → many whites/grays previously duplicated across 20 keys.
# Keep old keys working for one breaking window via indirection, so themes.json can drop them.
# Public ALIAS dict — callers/tests may inspect it; _THEME_ALIASES kept for backward compat.
ALIAS: dict[str, str] = {
    # #ffffff cluster → surface.background
    "Window": "surface.background",
    "Base": "surface.background",
    "ToolTipBase": "surface.background",
    "HighlightedText": "surface.background",
    "button.dialog.default.background": "surface.background",
    "button.primary.background": "surface.background",
    "flyout.background": "surface.background",
    "dialog.background": "surface.background",
    "dialog.input.background": "surface.background",
    "label.image.background": "surface.background",
    "help.nav.selected.text": "surface.background",
    "toast.background": "surface.background",
    "slider.thumb.outer": "surface.background",
    "switch.knob.on": "surface.background",
    "tooltip.background": "surface.background",
    "color_dialog.input.background": "surface.background",
    # #f0f0f0 cluster → surface.list (backgrounds only — never text tokens:
    # list_item.text.normal was wrongly clustered here by hex proximity
    # (dark text #f0f0f0 == light surface #f0f0f0 in different themes),
    # which made row text resolve to a background color, i.e. always
    # near-white and unreadable; the token is defined directly in every
    # shipped palette and app themes.json, so no alias is needed).
    "help.nav.background": "surface.list",
    "button.toggle.background.normal": "surface.list",
    "color_dialog.background": "surface.list",
    # #e1e1e1 cluster → surface.button
    "AlternateBase": "surface.button",
    "Button": "surface.button",
    "dialog.button.background": "surface.button",
}

# Backward-compat private name — one-version window keeps old import path working.
_THEME_ALIASES: dict[str, str] = ALIAS

# Derive expression: lighten(token, 10%) / darken(token, 8%) / alpha(token, 60%)
_DERIVE_RE = re.compile(
    r"^\s*(lighten|darken|alpha)\s*\(\s*([^,]+?)\s*,\s*([^)]+?)\s*\)\s*$",
    re.IGNORECASE,
)


def _resolve_alias(key: str, *, _seen: set[str] | None = None) -> str:
    """Follow ALIAS chain (e.g. dialog.background -> surface.background).

    Cycle-safe; depth limited to len(ALIAS) to avoid infinite loop on bad table.
    """
    seen: set[str] = set() if _seen is None else _seen
    cur = key
    for _ in range(len(ALIAS) + 1):
        nxt = ALIAS.get(cur)
        if nxt is None or nxt in seen:
            break
        seen.add(cur)
        cur = nxt
    return cur


def _parse_amount(amount_str: str, *, for_alpha: bool = False) -> float | None:
    s = amount_str.strip()
    try:
        if s.endswith("%"):
            return float(s[:-1].strip()) / 100.0 if for_alpha else float(s[:-1].strip())
        # plain number: 0.6 (fraction) or 10 / 60  (percent without %)
        v = float(s)
        return v
    except ValueError:
        return None


def _apply_derive(base: QColor, func: str, amount_str: str) -> QColor | None:
    c = QColor(base)
    if not c.isValid():
        return None
    func_l = func.lower()
    if func_l == "lighten":
        pct = _parse_amount(amount_str, for_alpha=False)
        if pct is None:
            return None
        # 0.1 -> 10%, 10 -> 10%
        if 0 < pct < 1:
            pct *= 100.0
        # QColor.lighter(110) = 10% lighter
        factor = int(round(100 + pct))
        factor = max(100, factor)
        return c.lighter(factor)
    if func_l == "darken":
        pct = _parse_amount(amount_str, for_alpha=False)
        if pct is None:
            return None
        if 0 < pct < 1:
            pct *= 100.0
        factor = int(round(100 + pct))
        factor = max(100, factor)
        return c.darker(factor)
    if func_l == "alpha":
        raw = amount_str.strip()
        # percent case: "60%"
        if raw.endswith("%"):
            pct = _parse_amount(raw, for_alpha=True)
            if pct is None:
                return None
            a = int(round(255 * pct))
        else:
            try:
                v = float(raw)
            except ValueError:
                return None
            if 0 <= v <= 1:
                # 0.6 -> 60% opacity
                a = int(round(255 * v))
            elif 1 < v <= 100:
                # 60 -> 60% (common derive syntax without %); 128 would be >100 so raw alpha
                a = int(round(255 * (v / 100.0)))
            elif 100 < v <= 255:
                # raw 0-255 alpha
                a = int(round(v))
            else:
                return None
        a = max(0, min(255, a))
        c.setAlpha(a)
        return c
    return None


def _resolve_palette_value(
    raw: object,
    palette: Dict[str, object],
    *,
    _seen_tokens: set[str] | None = None,
    _depth: int = 0,
) -> QColor | None:
    """Turn a palette entry (QColor | str derive | alias token) into QColor.

    Handles:
    - QColor pass-through
    - derive strings: lighten(surface.background, 10%) / alpha(accent, 0.6)
    - indirection strings that are themselves token names
    """
    if _depth > 10:
        return None
    if _seen_tokens is None:
        _seen_tokens = set()
    if isinstance(raw, QColor):
        return QColor(raw)
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    # derive?
    m = _DERIVE_RE.match(s)
    if m:
        func, base_token, amount = m.group(1), m.group(2).strip(), m.group(3).strip()
        base_token = base_token.strip().strip("'\"")
        base_color: QColor | None = None
        # base may be hex literal
        if base_token.startswith("#"):
            candidate = QColor(base_token)
            if candidate.isValid():
                base_color = candidate
        if base_color is None:
            # prevent cycle: token derives from itself
            if base_token in _seen_tokens:
                return None
            new_seen = set(_seen_tokens)
            new_seen.add(base_token)
            # resolve base token recursively via alias + palette lookup
            canonical = _resolve_alias(base_token)
            # try canonical first, then original
            candidates = (canonical, base_token) if canonical != base_token else (canonical,)
            for k in candidates:
                if k in palette:
                    val = palette.get(k)
                    # if base entry itself is a derive, recurse
                    resolved = _resolve_palette_value(val, palette, _seen_tokens=new_seen, _depth=_depth + 1)
                    if resolved is not None and resolved.isValid():
                        base_color = resolved
                        break
                    # fallback: if palette value is plain string color, try QColor
                    if isinstance(val, str) and QColor(val).isValid():
                        base_color = QColor(val)
                        break
                    if isinstance(val, QColor):
                        base_color = QColor(val)
                        break
            if base_color is None:
                # last resort: try interpreting base_token as literal color
                cand = QColor(base_token)
                if cand.isValid():
                    base_color = cand
        if base_color is None or not base_color.isValid():
            return None
        derived = _apply_derive(base_color, func, amount)
        return derived
    # plain color literal?
    cand = QColor(s)
    if cand.isValid():
        return cand
    # indirection: value is another token name (e.g. palette["dialog.background"] = "surface.background")
    if s in palette:
        if s in _seen_tokens:
            return None
        new_seen = set(_seen_tokens)
        new_seen.add(s)
        # resolve via alias mapping as well
        canonical = _resolve_alias(s)
        candidates = (canonical, s) if canonical != s else (canonical,)
        for k in candidates:
            if k in palette:
                v = palette.get(k)
                # avoid infinite recursion on self
                if v is s:
                    continue
                res = _resolve_palette_value(v, palette, _seen_tokens=new_seen, _depth=_depth + 1)
                if res is not None and res.isValid():
                    return res
        # fallback: try alias resolution without palette re-entry
        if canonical != s and canonical in palette:
            return _resolve_palette_value(palette.get(canonical), palette, _seen_tokens=new_seen, _depth=_depth + 1)
    return None


_QSS_PX_LITERAL = re.compile(r"(-?\d+(?:\.\d+)?)px")


def _scale_qss_px(qss: str) -> str:
    """Multiply ``Npx`` QSS literals by the current ``UiScale`` factor.

    ``1px`` (and sub-px) borders stay untouched — scaling hairlines either
    does nothing visible or thickens them unevenly; 2px and above scale so
    padding/radius/sizes follow the interface factor.
    """
    factor = UiScale.get_instance().factor()
    if factor == 1.0:
        return qss

    def _replace(match: "re.Match[str]") -> str:
        value = float(match.group(1))
        if abs(value) < 2:
            return match.group(0)
        return f"{int(round(value * factor))}px"

    return _QSS_PX_LITERAL.sub(_replace, qss)


def _qapp_instance() -> QApplication | None:
    instance = QApplication.instance()
    return instance if isinstance(instance, QApplication) else None


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
        is_active = getattr(effect, "is_active", None)
        if not callable(is_active):
            continue
        if not is_active():
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
    app = app or _qapp_instance()
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

    def register_palettes(self, light_palette: Dict, dark_palette: Dict | None = None):
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

    def _resolve_key(self, color_key: str) -> str:
        # Chain-aware alias indirection; canonical must exist in palette.
        # Kept for external callers; get_color/try_get_color use full resolver.
        return _resolve_alias(color_key)

    def _lookup_raw_with_alias(self, color_key: str, palette: Dict) -> object | None:
        """Find raw palette entry for *color_key* considering ALIAS both directions.

        One-version compat: alias -> canonical and canonical -> alias fallback.
        """
        canonical = _resolve_alias(color_key)
        # primary: canonical (if alias, this is the target)
        if canonical in palette:
            return palette[canonical]
        # migration window: alias present but canonical missing
        if canonical != color_key and color_key in palette:
            return palette[color_key]
        # reverse: canonical requested but only alias exists (old themes.json)
        if canonical == color_key:
            for alias, target in ALIAS.items():
                if target == canonical and alias in palette:
                    return palette[alias]
        return None

    def get_color(self, color_key: str) -> QColor:
        palette = self._dark_palette if self.is_dark() else self._light_palette
        # One-version deprecated alias warning (debug to avoid spam, but visible with -v)
        canonical = _resolve_alias(color_key)
        if canonical != color_key:
            theme_logger.debug("deprecated alias token %r -> %r (one-version compat)", color_key, canonical)
        raw = self._lookup_raw_with_alias(color_key, palette)
        if raw is not None:
            # _resolve_palette_value handles QColor, derive strings, indirection
            seen: set[str] = {color_key}
            if canonical != color_key:
                seen.add(canonical)
            resolved = _resolve_palette_value(raw, palette, _seen_tokens=seen)  # type: ignore[arg-type]
            if resolved is not None and resolved.isValid():
                return QColor(resolved)
            # raw was plain string color? _resolve already tried; fallback direct QColor
            if isinstance(raw, QColor) and raw.isValid():
                return QColor(raw)
            if isinstance(raw, str):
                cand = QColor(raw)
                if cand.isValid():
                    return cand
        # Derive fallback via try_get_color with alias-aware resolver
        fallback = self.try_get_color(color_key)
        if fallback is not None:
            return fallback
        # Unknown token — warn and fall back to palette default
        theme_logger.warning("unknown theme token: %s", color_key)
        for default_key in ("surface.background", "Window", "WindowText", "Base", "Text"):
            # also alias-aware for defaults
            raw_def = self._lookup_raw_with_alias(default_key, palette)
            if raw_def is not None:
                seen_def: set[str] = {default_key, _resolve_alias(default_key)}
                resolved_def = _resolve_palette_value(raw_def, palette, _seen_tokens=seen_def)  # type: ignore[arg-type]
                if resolved_def is not None and resolved_def.isValid():
                    return QColor(resolved_def)
                if isinstance(raw_def, QColor) and raw_def.isValid():
                    return QColor(raw_def)
                if isinstance(raw_def, str):
                    cand = QColor(raw_def)
                    if cand.isValid():
                        return cand
        return QColor("#000000")

    def try_get_color(self, color_key: str) -> QColor | None:
        """Return the color for *color_key*, or ``None`` if the key is absent.

        Alias-aware and derive-aware (lighten/alpha). Returns None for unknown
        tokens instead of black, preserving previous contract.
        """
        palette = self._dark_palette if self.is_dark() else self._light_palette
        raw = self._lookup_raw_with_alias(color_key, palette)
        if raw is None:
            return None
        canonical = _resolve_alias(color_key)
        seen: set[str] = {color_key}
        if canonical != color_key:
            seen.add(canonical)
        resolved = _resolve_palette_value(raw, palette, _seen_tokens=seen)  # type: ignore[arg-type]
        if resolved is not None and resolved.isValid():
            return QColor(resolved)
        if isinstance(raw, QColor) and raw.isValid():
            return QColor(raw)
        if isinstance(raw, str):
            cand = QColor(raw)
            if cand.isValid():
                return QColor(cand)
        return None

    def set_color(self, color_key: str, color: QColor):
        color_to_store = (
            QColor(color) if isinstance(color, QColor) else QColor(str(color))
        )
        if self.is_dark():
            self._dark_palette[color_key] = color_to_store
        else:
            self._light_palette[color_key] = color_to_store
        app = _qapp_instance()
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
        app = app or _qapp_instance()
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
        app = app or _qapp_instance()

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
        app = self._theme_flush_app or _qapp_instance()
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

        # Expand aliases so QSS @help.nav.background etc. still resolve to canonical surface.*
        # and QPalette roles Window/Base etc. resolve to surface.background if Window was dropped.
        # Keep backward compat for one version: expand both directions.
        expanded = palette_data.copy()
        for alias, canonical in ALIAS.items():
            if alias not in expanded and canonical in palette_data:
                expanded[alias] = palette_data[canonical]
            if canonical not in expanded and alias in palette_data:
                expanded[canonical] = palette_data[alias]
        # Resolve derive strings (lighten/alpha) and normalize all entries to QColor where possible
        resolved: dict[str, QColor] = {}
        for k, raw in expanded.items():
            if isinstance(raw, QColor):
                if raw.isValid():
                    resolved[k] = QColor(raw)
                continue
            if isinstance(raw, str):
                c = _resolve_palette_value(raw, expanded)
                if c is not None and c.isValid():
                    resolved[k] = c
                else:
                    # fallback: plain hex / named color
                    cand = QColor(raw)
                    if cand.isValid():
                        resolved[k] = cand
                continue
        # Merge resolved QColors back into palette_data for QPalette/QSS
        palette_data = {**expanded, **resolved}

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
                raw = palette_data[name]
                if isinstance(raw, QColor):
                    color = QColor(raw)
                elif isinstance(raw, str):
                    tmp = _resolve_palette_value(raw, palette_data)  # type: ignore[arg-type]
                    color = tmp if tmp is not None and tmp.isValid() else QColor(raw)
                else:
                    continue
                if color.isValid():
                    q_palette.setColor(role, color)

        app.setPalette(q_palette)

        processed_palette: dict[str, QColor] = {}
        for k, v in palette_data.items():
            if isinstance(v, QColor) and v.isValid():
                processed_palette[k] = QColor(v)
            elif isinstance(v, str):
                tmp = _resolve_palette_value(v, palette_data)  # type: ignore[arg-type]
                if tmp is not None and tmp.isValid():
                    processed_palette[k] = tmp
                else:
                    cand = QColor(v)
                    if cand.isValid():
                        processed_palette[k] = cand
        if "accent" in processed_palette and "accent.hover" not in processed_palette:
            accent_color = QColor(processed_palette["accent"])
            if accent_color.isValid():
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
            if isinstance(color, QColor) and color.isValid():
                placeholder = f"@{key}"
                if placeholder in current_qss:
                    current_qss = current_qss.replace(
                        placeholder, color.name(QColor.NameFormat.HexArgb)
                    )

        current_qss = _scale_qss_px(current_qss)

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
        app = _qapp_instance()
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

        # Alias + derive aware palette for dialog (one-version compat)
        expanded = palette_data.copy()
        for alias, canonical in ALIAS.items():
            if alias not in expanded and canonical in palette_data:
                expanded[alias] = palette_data[canonical]
            if canonical not in expanded and alias in palette_data:
                expanded[canonical] = palette_data[alias]
        palette_data = expanded

        app = _qapp_instance()
        q_palette = QPalette(app.palette()) if app is not None else QPalette()
        for name, role in color_roles.items():
            if name in palette_data:
                raw = palette_data[name]
                if isinstance(raw, QColor):
                    color = QColor(raw)
                elif isinstance(raw, str):
                    tmp = _resolve_palette_value(raw, palette_data)  # type: ignore[arg-type]
                    color = tmp if tmp is not None and tmp.isValid() else QColor(raw)
                else:
                    continue
                if color.isValid():
                    q_palette.setColor(role, color)

        dialog.setPalette(q_palette)
        dialog.updateGeometry()
        dialog.update()
