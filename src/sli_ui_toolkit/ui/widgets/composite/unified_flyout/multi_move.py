"""Pure helpers for multi-index reorder / cross-list move."""

from __future__ import annotations


def normalize_indices(indices) -> list[int]:
    out = sorted({int(i) for i in indices if isinstance(i, int) and i >= 0})
    return out


def adjust_dest_after_removals(dest_index: int, source_indices: list[int]) -> int:
    """Lower ``dest_index`` by one for each removed index strictly below it."""
    dest = int(dest_index)
    for index in source_indices:
        if index < dest_index:
            dest -= 1
    return max(0, dest)


def reorder_many(items: list, source_indices, dest_index: int) -> list:
    """Return a new list with ``source_indices`` moved to ``dest_index`` (stable order)."""
    indices = normalize_indices(source_indices)
    if not indices:
        return list(items)
    working = list(items)
    extracted = [working[i] for i in indices if i < len(working)]
    if not extracted:
        return working
    for i in reversed(indices):
        if i < len(working):
            working.pop(i)
    dest = adjust_dest_after_removals(dest_index, indices)
    dest = max(0, min(dest, len(working)))
    for offset, item in enumerate(extracted):
        working.insert(dest + offset, item)
    return working


def move_many(
    source: list,
    dest: list,
    source_indices,
    dest_index: int,
) -> tuple[list, list]:
    """Move entries from ``source`` into ``dest`` at ``dest_index`` (stable order)."""
    indices = normalize_indices(source_indices)
    if not indices:
        return list(source), list(dest)
    src = list(source)
    dst = list(dest)
    extracted = [src[i] for i in indices if i < len(src)]
    if not extracted:
        return src, dst
    for i in reversed(indices):
        if i < len(src):
            src.pop(i)
    insert_at = max(0, min(int(dest_index), len(dst)))
    for offset, item in enumerate(extracted):
        dst.insert(insert_at + offset, item)
    return src, dst


def payload_indices(payload: dict | None) -> list[int]:
    """Prefer ``indices``; fall back to single ``index``."""
    if not isinstance(payload, dict):
        return []
    raw = payload.get("indices")
    if isinstance(raw, (list, tuple)) and raw:
        return normalize_indices(raw)
    index = payload.get("index")
    if isinstance(index, int) and index >= 0:
        return [index]
    return []
