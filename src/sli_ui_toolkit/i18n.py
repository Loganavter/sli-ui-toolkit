from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QTimer, Signal

logger = logging.getLogger(__name__)

I18N_STATE_DOC = "docs/user/API_CATALOG.md#i18n--configuration"

#: Canonical translator signature: ``(key, language) -> text`` — the same
#: ``(key, lang)`` convention ``translatable_*`` widgets already use. A
#: translator returns ``key`` unchanged on a miss so a translation gap is
#: visible on screen (never silent English).
Translator = Callable[[str, str], str]


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
    _translations: dict[str, Any]
    _cache: dict[str, dict[str, Any]]
    _current_lang: str
    _events: ToolkitTranslationEvents
    _i18n_root: Path | None
    _extra_roots: list[Path]
    _custom_translator: Callable[[str, str | None], str] | None
    _language_provider: Callable[[], str] | None

    def __new__(cls) -> TranslationManager:
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._translations = {}
            instance._cache = {}
            instance._current_lang = "en"
            instance._events = ToolkitTranslationEvents()
            instance._i18n_root = None
            instance._extra_roots = []
            instance._custom_translator = None
            instance._language_provider = None
            cls._instance = instance
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
    if translator is not None:
        # A custom backend replaces the built-in JSON lookup for ``tr`` /
        # ``translator_for`` (``None`` leaves the current backend untouched).
        _manager._custom_translator = translator
    if language_provider is not None:
        # Source the current language from app state instead of the toolkit's
        # own tracked ``_current_lang``.
        _manager._language_provider = language_provider
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
    provider = getattr(_manager, "_language_provider", None)
    if provider is not None:
        try:
            resolved = provider()
        except Exception:
            logger.exception("language_provider() raised; falling back to tracked language")
            resolved = None
        if resolved:
            return str(resolved)
    return getattr(_manager, "_current_lang", default) or default

def tr(key: str, language: str | None = None, default: str | None = None, *args: Any, **kwargs: Any) -> str:
    """Pure translation lookup. When ``language`` is given, the pack is loaded
    into the cache **without** mutating the global current language or emitting
    ``language_changed``. Use ``emit_language_changed(lang)`` for that.

    Always resolve an explicit ``language`` from that pack — do not assume the
    live ``_translations`` buffer matches ``_current_lang`` (tests and hosts
    may restore one without the other).

    When a custom backend was registered via ``configure_i18n(translator=...)``
    it owns the lookup for every call; otherwise the built-in JSON pack is
    used. Either way a miss returns ``key`` (or ``default`` when given).
    """
    custom = getattr(_manager, "_custom_translator", None)
    if custom is not None:
        lang = language if language is not None else get_current_language()
        try:
            result = custom(key, lang)
        except Exception:
            logger.exception("custom translator failed for key %r", key)
            result = key
        if result == key:
            return default if default is not None else key
        if args or kwargs:
            try:
                return result.format(*args, **kwargs)
            except Exception:
                return result
        return result
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
    events: ToolkitTranslationEvents | None = None,
) -> None:
    """Apply ``callback`` immediately and re-apply on ``language_changed``.

    Auto-disconnects when the widget is destroyed, so callers don't need
    to manage lifetimes.

    When *defer_when_hidden* is true and the widget is not currently visible
    (e.g. a workspace page buried in ``QStackedWidget``), the language update
    is held until the next ``Show`` event — keeps language Apply cheap while
    off-screen tabs are stacked away.

    Pass *events* to subscribe to a tab-owned bus instead of the global
    singleton (per-subtree isolation for ``install_translator``).
    """
    events = events if events is not None else translation_events()

    _shiboken: Any = None
    try:
        import shiboken6 as _shiboken
    except Exception:
        pass

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


# ---------------------------------------------------------------------------
# Subtree-scoped translators + declarative keys
# ---------------------------------------------------------------------------

try:  # pragma: no cover - shiboken6 ships with PySide6, the guard is defensive
    import shiboken6 as _shiboken
except Exception:  # pragma: no cover
    _shiboken = None  # type: ignore[assignment]


def _object_alive(obj: Any) -> bool:
    """True while *obj* still has a live C++ side (mirrors ``_bind_widget``)."""
    if _shiboken is None or obj is None:
        return obj is not None
    try:
        return bool(_shiboken.isValid(obj))  # type: ignore[attr-defined]
    except Exception:
        return False


def translator_for(widget: QObject) -> Translator:
    """Return the translator governing *widget*.

    Walks the ``parent()`` chain for the nearest object bound with
    ``bind_translator`` / ``install_translator``; falls back to the global
    ``tr`` (which honours a custom backend from ``configure_i18n``).
    """
    node: Any = widget
    while node is not None:
        bound = getattr(node, "_sli_translator", None)
        if callable(bound):
            return bound  # type: ignore[no-any-return]
        try:
            node = node.parent()
        except (RuntimeError, SystemError):
            break
    return tr


def _apply_widget_translator(widget: Any, tr_func: Translator, *, defer_when_hidden: bool) -> None:
    setter = getattr(widget, "set_translator", None)
    if not callable(setter):
        return
    try:
        setter(tr_func, defer_when_hidden=defer_when_hidden)
    except TypeError:
        # Duck-typed widget with a positional-only set_translator.
        setter(tr_func)


def _widget_implements_protocol(widget: Any) -> bool:
    return callable(getattr(widget, "retranslate", None)) or callable(
        getattr(widget, "set_translator", None)
    )


def _retranslate_widget(widget: Any, lang: str) -> None:
    retranslate = getattr(widget, "retranslate", None)
    if callable(retranslate):
        retranslate(lang)


def bind_translator(
    widget: QObject,
    tr_func: Translator,
    *,
    events: ToolkitTranslationEvents | None = None,
    defer_when_hidden: bool = False,
) -> None:
    """Bind *tr_func* to a single *widget* and remap on ``language_changed``.

    The widget is driven through the duck-typed protocol
    ``set_translator(tr_func, *, defer_when_hidden=False)`` /
    ``retranslate(lang)`` (declarative-key widgets implement both) and the
    binding is stored on the widget so ``translator_for`` resolves it for
    descendants. Auto-detaches when the widget is destroyed.

    For a whole subtree — current **and** future descendants — use
    ``install_translator``; ``bind_translator`` touches only this widget.
    """
    bus = events if events is not None else translation_events()
    setattr(widget, "_sli_translator", tr_func)
    _apply_widget_translator(widget, tr_func, defer_when_hidden=defer_when_hidden)
    _bind_widget(
        widget,
        lambda lang: _retranslate_widget(widget, lang),
        defer_when_hidden=defer_when_hidden,
        events=bus,
    )


def install_translator(
    root: QObject,
    tr_func: Translator,
    *,
    events: ToolkitTranslationEvents | None = None,
    defer_when_hidden: bool = False,
) -> None:
    """Bind *tr_func* to *root* and every current/future descendant.

    Only descendants that implement the duck-typed protocol
    ``set_translator(tr_func, *, defer_when_hidden=False)`` / ``retranslate(lang)``
    are driven. A single ``language_changed`` subscription (on *events*, or the
    global ``translation_events()`` by default) fans out ``retranslate(lang)``
    to the whole subtree, and the current language is applied immediately on
    install (mirrors ``_bind_widget``). Future descendants are picked up through
    a ``QEvent.Type.ChildAdded`` watcher installed as a dedicated event-filter
    object on EVERY covered node (never ``installEventFilter(self)``) — watching
    only ``root`` would miss a widget added later to an existing descendant.
    The subscription auto-detaches when *root* is destroyed; dead C++ children
    are dropped defensively.
    """
    bus = events if events is not None else translation_events()
    setattr(root, "_sli_translator", tr_func)
    covered: list[Any] = []

    def _watch(obj: Any) -> None:
        """Install the ``ChildAdded`` watcher on *obj* (once).

        The watcher must live on EVERY covered node, not only ``root``:
        ``QEvent.ChildAdded`` is delivered to the new child's DIRECT parent, so
        watching only ``root`` misses a widget added later to an EXISTING
        descendant (a popup/chip parented to a card that predates the install).
        """
        if getattr(obj, "_sli_i18n_watched", False):
            return
        try:
            obj.installEventFilter(filter_obj)
        except (RuntimeError, SystemError, AttributeError):
            return
        try:
            setattr(obj, "_sli_i18n_watched", True)
        except Exception:
            pass

    def _covered(obj: Any) -> bool:
        return any(existing is obj for existing in covered)

    def _cover(obj: Any) -> None:
        if obj is None or not _object_alive(obj):
            return
        _watch(obj)
        if callable(getattr(obj, "set_translator", None)):
            try:
                _apply_widget_translator(obj, tr_func, defer_when_hidden=defer_when_hidden)
            except (RuntimeError, SystemError):
                return
        if not _widget_implements_protocol(obj) or _covered(obj):
            return
        covered.append(obj)

    def _walk(obj: Any) -> None:
        _cover(obj)
        try:
            children = obj.findChildren(QObject)
        except (RuntimeError, SystemError):
            return
        for child in children:
            _cover(child)

    def _fan(lang: str) -> None:
        alive: list[Any] = []
        for obj in covered:
            if not _object_alive(obj):
                continue
            try:
                _retranslate_widget(obj, lang)
            except (RuntimeError, SystemError):
                # Dead C++ child (deleted between the liveness check and the
                # call) — drop it from the fan-out list.
                continue
            alive.append(obj)
        covered[:] = alive

    def _late_cover(*_args: Any) -> None:
        """Register + first-retranslate the subtree once construction settles.

        ``QEvent.ChildAdded`` fires inside ``QWidget.__init__`` (via
        ``setParent``) while ``shiboken6`` still reports the child as a bare
        ``QWidget`` wrapper (its Python subclass is not bound yet) and its ctor
        kwargs/keys are not assigned. Deferring one loop turn fixes both, so we
        re-walk from *root* (findChildren then returns correctly-typed
        wrappers) instead of trusting ``event.child()``.
        """
        if not _object_alive(root):
            return
        try:
            _walk(root)
        except (RuntimeError, SystemError):
            return
        _fan(get_current_language())

    class _ChildAddedFilter(QObject):
        def eventFilter(self, obj, event):  # noqa: N802 - Qt API
            if event.type() == QEvent.Type.ChildAdded:
                QTimer.singleShot(0, _late_cover)
            return False

    # Keep the filter alive for the lifetime of ``root`` and install it there.
    filter_obj = _ChildAddedFilter(root)
    setattr(root, "_sli_i18n_child_filter", filter_obj)
    root.installEventFilter(filter_obj)

    _walk(root)
    _bind_widget(
        root,
        _fan,
        defer_when_hidden=defer_when_hidden,
        events=bus,
    )
