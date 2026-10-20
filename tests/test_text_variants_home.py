"""The variant spec lives in ``text/variants.py``; ``Label``'s names alias it.

Wave C step 1: one class object and one preset table, so deleting ``Label``
later cannot take the spec or the registry with it.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.atomic import text_labels
from sli_ui_toolkit.ui.widgets.atomic.text_labels import (
    LabelVariantSpec,
    get_label_variant,
    register_label_variant,
)
from sli_ui_toolkit.ui.widgets.text import variants as text_variants
from sli_ui_toolkit.ui.widgets.text.variants import (
    TextVariantSpec,
    get_text_variant,
    register_text_variant,
)
from sli_ui_toolkit.widgets import Label


def test_label_spec_name_is_the_same_class_object():
    assert LabelVariantSpec is TextVariantSpec
    assert text_labels.LabelVariantSpec is text_variants.TextVariantSpec


def test_one_preset_table_shared_by_both_names():
    assert text_labels.LABEL_VARIANTS is text_variants.TEXT_VARIANTS
    name = "text-home-shared-table"
    try:
        register_label_variant(LabelVariantSpec(name, pixel_size=19, bold=True))
        assert get_text_variant(name).pixel_size == 19
        assert get_label_variant(name) is get_text_variant(name)
        # ... and the other direction, same table.
        register_text_variant(TextVariantSpec(name, pixel_size=23))
        assert get_label_variant(name).pixel_size == 23
        assert text_labels.LABEL_VARIANTS[name].pixel_size == 23
    finally:
        text_labels.LABEL_VARIANTS.pop(name, None)


def test_positional_construction_still_works():
    spec = TextVariantSpec("x", 13, True)
    assert (spec.name, spec.pixel_size, spec.bold) == ("x", 13, True)
    assert spec.color_token == "dialog.text"
    assert spec.minimum_width == 0
    assert spec.expanding is False
    assert spec.elide is False


def test_label_variant_path_unchanged(qapp):
    name = "text-home-label-path"
    register_text_variant(TextVariantSpec(name, pixel_size=21, minimum_width=33))
    try:
        label = Label("patched", variant=name)
        try:
            assert label.font().pixelSize() == 21
            assert label.minimumSizeHint().width() == 33
        finally:
            label.deleteLater()
    finally:
        text_labels.LABEL_VARIANTS.pop(name, None)
