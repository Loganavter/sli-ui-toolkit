from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

I18N_STATE_DOC = "docs/user/API_CATALOG.md#i18n--configuration"


class I18nStateError(RuntimeError):
    """Raised when caller tries to mutate translation state through unsafe APIs."""


class _GuardedSignal:
    """Public signal facade: subscriptions are allowed, manual emit is not."""

    def __init__(self, signal, *, name: str):
        self._signal = signal
        self._name = name

    def connect(self, *args, **kwargs):
        return self._signal.connect(*args, **kwargs)

    def disconnect(self, *args, **kwargs):
        return self._signal.disconnect(*args, **kwargs)

    def emit(self, *_args, **_kwargs) -> None:
        raise I18nStateError(
            f"{self._name}.emit(...) is blocked because it desynchronizes "
            f"translation state. Use emit_language_changed(lang) for global "
            f"language changes or tr(key, language=...) for passive lookups. "
            f"See {I18N_STATE_DOC}."
        )


class ToolkitTranslationEvents(QObject):
    _language_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._language_changed_public = _GuardedSignal(
            self._language_changed,
            name="translation_events().language_changed",
        )

    @property
    def language_changed(self) -> _GuardedSignal:
        return self._language_changed_public

    def _emit_language_changed(self, lang_code: str) -> None:
        self._language_changed.emit(lang_code)

def _deep_merge(
    base: dict[str, Any],
    incoming: dict[str, Any],
    source: str,
    *,
    warn_on_override: bool,
) -> None:
    for key, value in incoming.items():
        if key not in base:
            base[key] = value
            continue

        if isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value, source, warn_on_override=warn_on_override)
            continue

        if warn_on_override:
            logger.warning("Translation key override for '%s' from %s", key, source)
        base[key] = value

def _resolve_dotted_key(data: dict[str, Any], dotted_key: str) -> str:
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return dotted_key
        current = current[part]

    return current if isinstance(current, str) else dotted_key

class TranslationManager:
    _instance: TranslationManager | None = None

    def __new__(cls) -> TranslationManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._translations: dict[str, Any] = {}
            cls._instance._cache: dict[str, dict[str, Any]] = {}
            cls._instance._current_lang = "en"
            cls._instance._events = ToolkitTranslationEvents()
            cls._instance._i18n_root: Path | None = None
            cls._instance._extra_roots: list[Path] = []
        return cls._instance

    def set_i18n_root(self, path: str | Path) -> None:
        self._i18n_root = Path(path)
        self._extra_roots = []
        self._cache.clear()
        self._translations = {}

    def add_i18n_root(self, path: str | Path) -> None:
        root = Path(path)
        if root in self._extra_roots:
            self._cache.clear()
        else:
            self._extra_roots.append(root)
            self._cache.clear()
        # ``tr(key)`` / ``tr(key, language=current)`` read ``_translations``,
        # not the cache. Rebuild the live pack so deferred plugin roots
        # (e.g. export.*) are visible immediately after registration.
        if self._current_lang:
            self._translations = self.ensure_loaded(self._current_lang)
        else:
            self._translations = {}

    def _load_tree(self, lang_dir: Path) -> dict[str, Any]:
        translations: dict[str, Any] = {}
        json_files = sorted(lang_dir.rglob("*.json"))

        if not json_files:
            logger.warning("No translation files found in %s", lang_dir)
            return translations

        for file_path in json_files:
            try:
                file_data = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("Failed to load translation file %s: %s", file_path, exc)
                continue

            if not isinstance(file_data, dict):
                logger.warning("Skipping non-object translation file: %s", file_path)
                continue

            _deep_merge(
                translations,
                file_data,
                file_path.relative_to(lang_dir).as_posix(),
                warn_on_override=True,
            )

        return translations

    def _build_language_pack(self, lang_code: str) -> dict[str, Any]:
        if self._i18n_root is None:
            logger.error("i18n root not configured — call configure_i18n(i18n_root=...)")
            return {}

        base_path = self._i18n_root
        fallback_dir = base_path / "en"
        requested_dir = base_path / lang_code

        if not fallback_dir.is_dir():
            logger.error("Fallback translation directory not found: %s", fallback_dir)
            return {}

        translations = self._load_tree(fallback_dir)

        if lang_code != "en":
            if not requested_dir.is_dir():
                logger.warning(
                    "Translation directory not found: %s. Falling back to EN.",
                    requested_dir,
                )
            else:
                _deep_merge(
                    translations,
                    self._load_tree(requested_dir),
                    requested_dir.relative_to(base_path).as_posix(),
                    warn_on_override=False,
                )

        for extra_root in self._extra_roots:
            fallback_dir = extra_root / "en"
            if fallback_dir.is_dir():
                _deep_merge(
                    translations,
                    self._load_tree(fallback_dir),
                    fallback_dir.relative_to(extra_root).as_posix(),
                    warn_on_override=False,
                )
            if lang_code != "en":
                lang_dir = extra_root / lang_code
                if lang_dir.is_dir():
                    _deep_merge(
                        translations,
                        self._load_tree(lang_dir),
                        lang_dir.relative_to(extra_root).as_posix(),
                        warn_on_override=False,
                    )

        return translations

    def ensure_loaded(self, lang_code: str) -> dict[str, Any]:
        """Build and cache the pack for ``lang_code`` without mutating
        ``_current_lang`` or emitting ``language_changed``. Safe to call from
        ad-hoc ``tr(key, language=…)`` lookups.
        """
        requested_lang = lang_code or "en"
        cached = self._cache.get(requested_lang)
        if cached is None:
            cached = self._build_language_pack(requested_lang)
            self._cache[requested_lang] = cached
        return cached

    def set_current_language(self, lang_code: str, *, force_emit: bool = False) -> None:
        """Switch the global current language. The only path that emits
        ``language_changed``. Call this from settings/init, never from passive
        translation lookups.
        """
        requested_lang = lang_code or "en"
        if requested_lang == self._current_lang and not force_emit:
            return
        if requested_lang != self._current_lang or not self._translations:
            self._translations = self.ensure_loaded(requested_lang)
        self._current_lang = requested_lang
        self._events._emit_language_changed(requested_lang)

    def load_language(self, lang_code: str) -> None:
        raise I18nStateError(
            "TranslationManager.load_language(...) is blocked because it was "
            "ambiguous: old callers used it for both passive pack loading and "
            "global language mutation. Use emit_language_changed(lang) to "
            "change global UI language, or ensure_loaded(lang) / "
            "tr(key, language=...) for passive lookups. "
            f"See {I18N_STATE_DOC}."
        )

    def get(self, text: str, *args: Any, **kwargs: Any) -> str:
        return self.get_from(self._translations, text, *args, **kwargs)

    def get_from(
        self,
        translations: dict[str, Any],
        text: str,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        translated = _resolve_dotted_key(translations, text)

        if args or kwargs:
            try:
                return translated.format(*args, **kwargs)
            except Exception:
                return translated
        return translated

_manager = TranslationManager()

def configure_i18n(
    *,
    i18n_root: str | Path | None = None,
    translator: Callable[[str, str | None], str] | None = None,
    language_provider: Callable[[], str] | None = None,
    events: ToolkitTranslationEvents | None = None,
) -> None:
    if i18n_root is not None:
        _manager.set_i18n_root(i18n_root)
    if events is not None:
        _manager._events = events

def translation_events() -> ToolkitTranslationEvents:
    return _manager._events

def emit_language_changed(lang_code: str) -> None:
    """Public, explicit way to switch the global current language and notify
    subscribers. The ONLY entry point that should emit ``language_changed``.
    """
    _manager.set_current_language(str(lang_code or "en"), force_emit=True)

def get_current_language(default: str = "en") -> str:
    return getattr(_manager, "_current_lang", default) or default

def tr(key: str, language: str | None = None, default: str | None = None, *args: Any, **kwargs: Any) -> str:
    """Pure translation lookup. When ``language`` is given, the pack is loaded
    into the cache **without** mutating the global current language or emitting
    ``language_changed``. Use ``emit_language_changed(lang)`` for that.

    Always resolve an explicit ``language`` from that pack — do not assume the
    live ``_translations`` buffer matches ``_current_lang`` (tests and hosts
    may restore one without the other).
    """
    if language is None:
        result = _manager.get(key, *args, **kwargs)
    else:
        pack = _manager.ensure_loaded(language)
        result = _manager.get_from(pack, key, *args, **kwargs)
    if result == key and default is not None:
        return default
    return result


def _bind_widget(
    widget,
    callback: Callable[[str], None],
    *,
    defer_when_hidden: bool = False,
) -> None:
    """Apply ``callback`` immediately and re-apply on ``language_changed``.

    Auto-disconnects when the widget is destroyed, so callers don't need
    to manage lifetimes.

    When *defer_when_hidden* is true and the widget is not currently visible
    (e.g. a workspace page buried in ``QStackedWidget``), the language update
    is held until the next ``Show`` event — keeps language Apply cheap while
    off-screen tabs are stacked away.
    """
    events = translation_events()

    try:
        import shiboken6 as _shiboken
    except Exception:
        _shiboken = None

    def _widget_alive() -> bool:
        if _shiboken is None:
            return True
        try:
            return bool(_shiboken.isValid(widget))
        except Exception:
            return False

    state: dict[str, str | None] = {"pending": None}

    def _apply(lang: str) -> None:
        try:
            callback(lang)
        except (RuntimeError, SystemError):
            # Widget already deleted on the C++ side, or one of its children
            # returned NULL from a Qt factory (typical when a parent QObject
            # was deleteLater'd but Python still holds a stale reference).
            try:
                events.language_changed.disconnect(_on_lang)
            except (TypeError, RuntimeError):
                pass

    def _on_lang(lang: str) -> None:
        if not _widget_alive():
            try:
                events.language_changed.disconnect(_on_lang)
            except (TypeError, RuntimeError):
                pass
            return
        if defer_when_hidden:
            try:
                visible = bool(widget.isVisible())
            except RuntimeError:
                return
            if not visible:
                state["pending"] = lang
                return
        state["pending"] = None
        _apply(lang)

    def _flush_pending() -> None:
        pending = state["pending"]
        if pending is None or not _widget_alive():
            return
        state["pending"] = None
        _apply(pending)

    callback(get_current_language())
    events.language_changed.connect(_on_lang)

    if defer_when_hidden:
        from PySide6.QtCore import QEvent, QObject

        class _ShowFlushFilter(QObject):
            def eventFilter(self, obj, event):  # noqa: N802
                if event.type() == QEvent.Type.Show and obj is widget:
                    _flush_pending()
                return False

        show_filter = _ShowFlushFilter(widget)
        widget.installEventFilter(show_filter)

    destroyed_signal = getattr(widget, "destroyed", None)
    if destroyed_signal is not None:
        def _cleanup(*_args) -> None:
            try:
                events.language_changed.disconnect(_on_lang)
            except (TypeError, RuntimeError):
                pass
        destroyed_signal.connect(_cleanup)


def translatable_text(
    widget,
    key: str,
    *,
    suffix: str = "",
    tr_func: Callable[..., str] | None = None,
    defer_when_hidden: bool = False,
) -> None:
    """Bind ``widget.setText`` to translation key ``key``."""
    tr_func = tr_func or tr
    _bind_widget(
        widget,
        lambda lang: widget.setText(tr_func(key, lang) + suffix),
        defer_when_hidden=defer_when_hidden,
    )


def translatable_tooltip(
    widget,
    key: str,
    *,
    tr_func: Callable[..., str] | None = None,
    defer_when_hidden: bool = False,
) -> None:
    """Bind ``widget.setToolTip`` to translation key ``key``."""
    tr_func = tr_func or tr
    _bind_widget(
        widget,
        lambda lang: widget.setToolTip(tr_func(key, lang)),
        defer_when_hidden=defer_when_hidden,
    )


def translatable_placeholder(
    widget,
    key: str,
    *,
    tr_func: Callable[..., str] | None = None,
    defer_when_hidden: bool = False,
) -> None:
    """Bind ``widget.setPlaceholderText`` to translation key ``key``."""
    tr_func = tr_func or tr
    _bind_widget(
        widget,
        lambda lang: widget.setPlaceholderText(tr_func(key, lang)),
        defer_when_hidden=defer_when_hidden,
    )


def translatable_callback(
    widget,
    callback: Callable[[str], None],
    *,
    defer_when_hidden: bool = False,
) -> None:
    """Bind an arbitrary ``callback(lang)`` for composite or conditional
    updates that don't fit a simple setter pattern. Lifetime is tied to
    ``widget`` — the connection is dropped on widget destruction.

    Pass ``defer_when_hidden=True`` for workspace-page chrome so language
    Apply skips pages that are not the current stacked widget.
    """
    _bind_widget(widget, callback, defer_when_hidden=defer_when_hidden)
