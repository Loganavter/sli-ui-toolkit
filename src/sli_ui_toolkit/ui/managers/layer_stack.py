"""Named z-order layers for :class:`FlyoutManager` overlay stacking.

Replaces the single hardcoded "context_menu always on top" special case in
``FlyoutManager.ensure_overlay_stacking`` with a small ordered list of layer
names that a host can extend. Groups (``flyout.flyout_group``) are assigned
to a layer; flyouts in a higher layer are always raised above flyouts in a
lower layer, regardless of open order. Unassigned groups default to the
first (lowest) layer.

The default stack, installed automatically on :class:`FlyoutManager`, has
exactly two layers and pre-assigns ``"context_menu"`` to the top one — this
matches the toolkit's previous hardcoded behavior exactly, so hosts that
never touch layers see no change.
"""

from __future__ import annotations


class LayerStack:
    DEFAULT_ORDER: tuple[str, ...] = ("base", "context_menu")

    def __init__(self, order: tuple[str, ...] | list[str] | None = None):
        if order is None:
            self._order: tuple[str, ...] = self.DEFAULT_ORDER
            self._group_layer: dict[str, str] = {"context_menu": "context_menu"}
        else:
            self._order = tuple(order)
            if not self._order:
                raise ValueError("LayerStack requires at least one layer")
            self._group_layer = {}

    def assign_group(self, group: str, layer: str) -> "LayerStack":
        if layer not in self._order:
            raise ValueError(
                f"Unknown layer {layer!r}; declared layers are {self._order!r}"
            )
        self._group_layer[group] = layer
        return self

    def layer_of(self, group: str | None) -> str:
        if group is None:
            return self._order[0]
        return self._group_layer.get(group, self._order[0])

    def index_of(self, group: str | None) -> int:
        return self._order.index(self.layer_of(group))

    def order(self) -> tuple[str, ...]:
        return self._order
