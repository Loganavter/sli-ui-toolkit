"""Project-wide widget substitution policy (proxy-style enforcement).

Opt-in construction (``OverlayScrollArea(...)`` at each call site) does not
scale: every new stock ``QScrollArea`` silently reintroduces the native
look. This module is the enforcement half — a ``QProxyStyle`` that sees
every widget at polish time and runs the registered substitution handlers,
plus ``install_scrollbar_policy()`` wiring it into the application.

Built-in policy (scrollbars): every ``QAbstractScrollArea`` that is not an
``OverlayScrollArea`` and whose bars are not already ``MinimalistScrollBar``
gets its native bars replaced via ``setVerticalScrollBar`` /
``setHorizontalScrollBar``. Overlay areas keep their hidden mirrored native
bars (swapping them would break the mirror wiring).

Extension point for future widgets: ``register_widget_policy(cls, handler)``
— ``handler(widget)`` runs once per matching widget. Handlers must be
idempotent and never raise (every call is guarded).
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QProxyStyle, QWidget

# (key, widget class, handler). Keyed so a widget polished before a late
# registration still gets the new handler on the next sweep, and handlers
# never run twice on the same widget.
_POLICY_HANDLERS: list[tuple[str, type, Callable[[QWidget], None]]] = []
_POLICY_MARK = "_sli_widget_policy_done"

# Module-global ref: the installed proxy must outlive the install call —
# PySide may garbage-collect the Python wrapper otherwise, deleting the
# C++ object out from under QApplication::style().
_STYLE_REF: QProxyStyle | None = None


def _applied_keys(widget: QWidget) -> set[str]:
    try:
        raw = widget.property(_POLICY_MARK)
    except Exception:
        return set()
    if not raw:
        return set()
    try:
        return {k for k in str(raw).split(";") if k}
    except Exception:
        return set()


def _mark_applied(widget: QWidget, key: str) -> None:
    try:
        keys = _applied_keys(widget)
        keys.add(key)
        widget.setProperty(_POLICY_MARK, ";".join(sorted(keys)))
    except Exception:
        pass


def _apply_policies(widget: QWidget) -> None:
    try:
        done = _applied_keys(widget)
    except Exception:
        return
    for key, cls, handler in list(_POLICY_HANDLERS):
        if key in done:
            continue
        try:
            match = isinstance(widget, cls)
        except Exception:
            continue
        if not match:
            continue
        try:
            handler(widget)
        except Exception:
            pass
        _mark_applied(widget, key)


def register_widget_policy(
    cls: type, handler: Callable[[QWidget], None], *, key: str | None = None
) -> str:
    """Register a substitution handler for a widget class (and subclasses).

    Returns the handler key. Immediately sweeps already-existing widgets so
    late registrations still apply. Never raises.
    """
    try:
        name = key or getattr(handler, "__name__", None) or cls.__name__
        entry_key = f"{getattr(cls, '__name__', 'widget')}:{name}"
        for existing_key, existing_cls, existing_fn in _POLICY_HANDLERS:
            if existing_key == entry_key:
                return existing_key
        _POLICY_HANDLERS.append((entry_key, cls, handler))
        widgets: list[Any] = []
        try:
            from PySide6.QtWidgets import QApplication as _QA

            the_app: Any = _QA.instance()
            if the_app is not None:
                widgets = list(the_app.allWidgets())
        except Exception:
            pass
        for w in list(widgets):
            try:
                if not isinstance(w, cls):
                    continue
                # isinstance against a dynamic `type` narrows to object for
                # mypy — a fresh Any alias keeps the handler calls clean.
                target: Any = w
                if entry_key not in _applied_keys(target):
                    try:
                        handler(target)
                    except Exception:
                        pass
                    _mark_applied(target, entry_key)
            except Exception:
                continue
        return entry_key
    except Exception:
        return key or "unknown"


def _enforce_scrollbar_policy(area: Any) -> None:
    """Replace native bars with MinimalistScrollBar (built-in policy)."""
    try:
        from PySide6.QtCore import Qt as _Qt

        from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import (
            MinimalistScrollBar,
            OverlayScrollArea,
        )
    except Exception:
        return
    try:
        if isinstance(area, OverlayScrollArea):
            return
        for orientation, getter_name, setter_name in (
            (_Qt.Orientation.Vertical, "verticalScrollBar", "setVerticalScrollBar"),
            (_Qt.Orientation.Horizontal, "horizontalScrollBar", "setHorizontalScrollBar"),
        ):
            try:
                getter = getattr(area, getter_name, None)
                setter = getattr(area, setter_name, None)
                if not callable(getter) or not callable(setter):
                    continue
                if isinstance(getter(), MinimalistScrollBar):
                    continue
                setter(MinimalistScrollBar(orientation, area))
            except Exception:
                continue
    except Exception:
        pass


def _register_builtin_policies() -> None:
    try:
        from PySide6.QtWidgets import QAbstractScrollArea as _ASA

        register_widget_policy(_ASA, _enforce_scrollbar_policy, key="scrollbars")
    except Exception:
        pass


# The built-in scrollbar rule is registered at import (key-deduped, so
# re-registration is a no-op): using WidgetPolicyProxyStyle directly works
# without calling install_scrollbar_policy() first.
_register_builtin_policies()


class WidgetPolicyProxyStyle(QProxyStyle):
    """QProxyStyle that enforces the registered widget policies.

    ``polish(QWidget)`` runs every registered handler whose class matches
    (once per widget — re-polishes are cheap no-ops). All other style
    behavior delegates to the base style untouched.

    Ownership note: construct WITHOUT a base style (``WidgetPolicyProxyStyle()``)
    whenever the proxy may die before the application — ``QProxyStyle(base)``
    takes ownership of ``base``, so wrapping ``app.style()`` in a short-lived
    proxy deletes the live application style on garbage collection (proven
    segfault). ``install_scrollbar_policy()`` uses the null-base form, which
    delegates dynamically and steals nothing.
    """

    # Narrowed on purpose: only the QWidget polish carries substitutions;
    # QApplication/QPalette polishes delegate straight to the base style.
    def polish(self, widget: QWidget) -> None:  # type: ignore[override] # noqa: N802
        try:
            super().polish(widget)
        except Exception:
            pass
        try:
            if isinstance(widget, QWidget):
                _apply_policies(widget)
        except Exception:
            pass


def install_scrollbar_policy(app: Any = None) -> bool:
    """Install project-wide widget substitution (idempotent).

    Sets a null-base ``WidgetPolicyProxyStyle`` on the application (dynamic
    delegation — steals no ownership), sweeps already-existing widgets, and
    registers the built-in scrollbar rule. Everything created afterwards is
    covered at polish time, so host apps call this once at startup. Returns
    True when installed (or already installed); False when there is no
    application. Never raises.

    Note: Qt deletes the previous style inside ``setStyle`` — the old style
    object is gone after install, so there is deliberately no uninstall.
    """
    global _STYLE_REF
    try:
        if app is None:
            try:
                from PySide6.QtWidgets import QApplication as _QA

                app = _QA.instance()
            except Exception:
                app = None
        if app is None:
            return False
        try:
            current = app.style()
        except Exception:
            current = None
        if isinstance(current, WidgetPolicyProxyStyle):
            try:
                for w in list(app.allWidgets()):
                    _apply_policies(w)
            except Exception:
                pass
            return True
        _register_builtin_policies()
        try:
            proxy = WidgetPolicyProxyStyle()
        except Exception:
            return False
        try:
            _STYLE_REF = proxy
            app.setStyle(proxy)
        except Exception:
            return False
        try:
            for w in list(app.allWidgets()):
                _apply_policies(w)
        except Exception:
            pass
        return True
    except Exception:
        return False


__all__ = [
    "WidgetPolicyProxyStyle",
    "install_scrollbar_policy",
    "register_widget_policy",
]
