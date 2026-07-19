"""Unit tests for UnifiedFlyout multi-index move helpers."""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.composite.unified_flyout.multi_move import (
    move_many,
    normalize_indices,
    payload_indices,
    reorder_many,
)


def test_normalize_and_payload_indices():
    assert normalize_indices([3, 1, 1, -1, "x"]) == [1, 3]
    assert payload_indices({"indices": [2, 0]}) == [0, 2]
    assert payload_indices({"index": 4}) == [4]
    assert payload_indices({}) == []


def test_reorder_many_preserves_relative_order():
    items = ["a", "b", "c", "d", "e"]
    assert reorder_many(items, [1, 3], 0) == ["b", "d", "a", "c", "e"]
    assert reorder_many(items, [0, 1], 5) == ["c", "d", "e", "a", "b"]
    assert reorder_many(items, [], 2) == items


def test_move_many_between_lists():
    src = ["a", "b", "c", "d"]
    dst = ["x", "y"]
    new_src, new_dst = move_many(src, dst, [1, 3], 1)
    assert new_src == ["a", "c"]
    assert new_dst == ["x", "b", "d", "y"]
