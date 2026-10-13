"""Text variant registry.

Shares ``Label``'s registry for now (one preset table for both widgets until
``Label`` is retired in P3), so a variant registered for either applies to both.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.atomic.text_labels import (
    LabelVariantSpec,
    get_label_variant,
    register_label_variant,
)

TextVariantSpec = LabelVariantSpec


def register_text_variant(spec: TextVariantSpec) -> None:
    register_label_variant(spec)


def get_text_variant(name: str | None) -> TextVariantSpec:
    return get_label_variant(name)
