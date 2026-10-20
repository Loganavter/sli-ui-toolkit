"""Text variant spec and registry.

This module owns the variant spec: ``atomic/text_labels.py`` imports it back
(``LabelVariantSpec`` is an alias of :class:`TextVariantSpec`, the registry
functions delegate here) so ``Label``'s pending retirement will not take the
spec or the shared preset table with it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextVariantSpec:
    name: str
    pixel_size: int | None = None
    bold: bool = False
    color_token: str = "dialog.text"
    minimum_width: int = 0
    expanding: bool = False
    elide: bool = False


_DEFAULT_VARIANTS: list[TextVariantSpec] = [
    TextVariantSpec("body", pixel_size=12, color_token="dialog.text"),
    TextVariantSpec("caption", pixel_size=11, color_token="dialog.text"),
    TextVariantSpec(
        "compact",
        pixel_size=10,
        color_token="dialog.text",
        minimum_width=80,
        expanding=True,
        elide=True,
    ),
    TextVariantSpec(
        "group-title",
        pixel_size=13,
        bold=True,
        color_token="dialog.text",
        elide=True,
    ),
    TextVariantSpec(
        "adaptive",
        pixel_size=12,
        color_token="dialog.text",
        minimum_width=50,
        expanding=True,
        elide=True,
    ),
]

_VARIANTS: dict[str, TextVariantSpec] = {
    variant.name: variant for variant in _DEFAULT_VARIANTS
}

# Public handle on the canonical table (one dict object; mutating it, e.g.
# popping a test variant, affects every lookup on both widget paths).
TEXT_VARIANTS = _VARIANTS


def register_text_variant(spec: TextVariantSpec) -> None:
    _VARIANTS[spec.name] = spec


def get_text_variant(name: str | None) -> TextVariantSpec:
    return _VARIANTS.get((name or "body").lower(), _VARIANTS["body"])
