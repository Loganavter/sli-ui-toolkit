"""Per-instance colour overrides — one widget's colour, without the whole theme.

A host had two ways to recolour a toolkit control: a one-off constructor
argument (``Text(color_token=)``, ``Button(background_color=)``,
``CustomLineEdit(underline_color=)``) or a global write
(``ThemeManager.set_color``), which repaints every widget painted with that
token. Saying "this one combo's hover is different" had no expression.

``TokenOverrideMixin`` is that expression. The mixin keeps a per-instance map
of ``palette key -> QColor``; ``resolve_token(widget, key)`` is the one lookup
the painters use, so an instance override wins over the family token with no
theme mutation:

    explicit constructor/setter colour > instance override > family token
    > neutral fallback

Values are ``QColor`` or a colour literal (``"#ff8800"``); a palette key is
*rejected* as a value — remapping one token for one widget is exactly what
this map is for, while remapping it for every widget is what
``ThemeManager.set_color`` does. A value the map cannot turn into a colour is
logged and dropped, never stored as an invalid ``QColor``.

The map is repaint-only: it never touches ``ThemeManager`` palettes, so two
instances of the same widget can differ (the overridden one samples the
override, its sibling the family token) and a theme switch keeps the override.

Adoption is per widget: ``Button`` (its ``background_color`` routes through the
map under ``BACKGROUND_TOKEN``), ``CustomLineEdit``, ``CheckBox``, ``Switch``
and ``Slider`` today; the other families adopt the mixin when they are touched.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager

_logger = logging.getLogger("TokenOverrides")

#: The colour a key that neither the widget nor the palette defines paints with:
#: a mid grey, legible on both themes. Deliberately not black — a silent black
#: reads as "the design says black" instead of "this token is missing".
NEUTRAL_TOKEN_FALLBACK = "#808080"

#: Keys the resolver has already reported. A missing token is a host wiring
#: error; repeating it on every paint frame would drown the log, so each key
#: warns once per process (``reset_miss_warning`` clears the memo for a test or
#: a host that re-registers palettes at runtime).
_MISS_WARNED: set[str] = set()


def reset_miss_warning(key: str | None = None) -> None:
    """Forget that *key* (or every key) was reported as missing."""
    if key is None:
        _MISS_WARNED.clear()
    else:
        _MISS_WARNED.discard(key)


def _as_colour(value: object) -> QColor | None:
    """``QColor``/colour-literal to a valid ``QColor``; anything else is ``None``.

    A palette *key* is not a colour: ``QColor("input.text")`` is invalid, which
    is how a key passed as a value is caught instead of being half-resolved.
    """
    if isinstance(value, QColor):
        return QColor(value) if value.isValid() else None
    if isinstance(value, str):
        colour = QColor(value)
        return colour if colour.isValid() else None
    return None


class TokenOverrideMixin:
    """Per-instance token overrides for a widget that paints from tokens.

    Mixed into a ``QWidget`` subclass; the map is created lazily so the mixin
    survives the toolkit's ``QWidget.__init__``-direct construction (a mixin
    ``__init__`` is not on that path). Every mutation repaints the widget and
    calls :meth:`_on_token_overrides_changed`, which subclasses use to keep
    their own resolved fields (Button's background) in step.
    """

    def _token_override_store(self) -> dict[str, QColor]:
        store = self.__dict__.get("_token_overrides")
        if store is None:
            store = {}
            self.__dict__["_token_overrides"] = store
        return store

    def token_overrides(self) -> Mapping[str, QColor]:
        """A read-only view of this widget's overrides (``key -> QColor``)."""
        return MappingProxyType(self._token_override_store())

    def set_token_overrides(self, mapping: Mapping[str, QColor | str]) -> None:
        """Merge *mapping* into this widget's overrides and repaint.

        ``QColor`` or a colour literal only (see the module docstring). An entry
        that is not a colour is logged and ignored; the rest still apply.
        """
        resolved: dict[str, QColor] = {}
        rejected: list[str] = []
        for key, value in mapping.items():
            colour = _as_colour(value)
            if colour is None:
                rejected.append(str(key))
            else:
                resolved[str(key)] = colour
        if rejected:
            _logger.warning(
                "%s: ignored non-colour token override(s): %s — a value must be "
                "a QColor or a colour literal, not a palette key",
                type(self).__name__,
                ", ".join(sorted(rejected)),
            )
        if not resolved:
            return
        self._token_override_store().update(resolved)
        self._on_token_overrides_changed()
        # The mixin never subclasses QWidget: the host widget supplies update().
        cast(QWidget, self).update()

    def clear_token_overrides(self, name: str | None = None) -> None:
        """Drop one override (``name``) or all of them, then repaint."""
        store = self._token_override_store()
        if name is None:
            if not store:
                return
            store.clear()
        elif store.pop(name, None) is None:
            return
        self._on_token_overrides_changed()
        # The mixin never subclasses QWidget: the host widget supplies update().
        cast(QWidget, self).update()

    def _token_override(self, key: str) -> QColor | None:
        """The override for *key*, or ``None``. Paint-time read; returns a copy."""
        colour = self._token_override_store().get(key)
        return QColor(colour) if colour is not None else None

    def _on_token_overrides_changed(self) -> None:
        """Hook after a mutation. The base map needs nothing; subclasses sync."""
        return None


def resolve_token(widget: QWidget, key: str) -> QColor:
    """Resolve *key* for *widget*: instance override, then palette, then neutral.

    The single lookup the toolkit painters use, so one instance can differ from
    its siblings without a theme write. Never raises and never returns an
    invalid colour: a key defined by neither the widget's overrides nor the
    active palette logs once per key and paints :data:`NEUTRAL_TOKEN_FALLBACK`.
    """
    if isinstance(widget, TokenOverrideMixin):
        override = widget._token_override(key)
        if override is not None:
            return override
    theme = getattr(widget, "theme_manager", None)
    if not isinstance(theme, ThemeManager):
        theme = ThemeManager.get_instance()
    colour = theme.try_get_color(key)
    if colour is not None:
        return colour
    if key not in _MISS_WARNED:
        _MISS_WARNED.add(key)
        _logger.warning(
            "unknown theme token %r read by %s — painting %s",
            key,
            type(widget).__name__,
            NEUTRAL_TOKEN_FALLBACK,
        )
    return QColor(NEUTRAL_TOKEN_FALLBACK)


__all__ = [
    "NEUTRAL_TOKEN_FALLBACK",
    "TokenOverrideMixin",
    "reset_miss_warning",
    "resolve_token",
]
