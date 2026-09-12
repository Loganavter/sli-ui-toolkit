"""CustomTitleBar._hide_active_flyouts must honor pinned flyouts.

Regression: this Resize/Move sweep special-cased ``flyout_group ==
"context_menu"`` (to keep CSD File/Help menus open through a resize caused
by their own attach) but hid every *other* visible flyout unconditionally --
including ``pinned=True`` persistent HUDs, which every other auto-dismiss
path in ``FlyoutManager`` (``_close_flyouts_with_moved_anchors``,
``_dismiss_passive``) already exempts. A host whose window resizes when an
unrelated panel opens (or when a context menu attaches/detaches from the
overlay layer) would see its pinned HUDs vanish.
"""

from __future__ import annotations

from sli_ui_toolkit import CustomTitleBar
from sli_ui_toolkit.managers import FlyoutManager


class _FakeFlyout:
    def __init__(self, *, group: str | None = None, pinned: bool = False) -> None:
        self.flyout_group = group
        self.pinned = pinned
        self._visible = True

    def isVisible(self) -> bool:
        return self._visible

    def hide(self) -> None:
        self._visible = False


def test_hide_active_flyouts_skips_pinned(qapp):
    manager = FlyoutManager.get_instance()
    previous_registered = set(getattr(manager, "_registered_flyouts", ()))
    previous_active = getattr(manager, "_active_flyout", None)
    try:
        pinned = _FakeFlyout(group="hud", pinned=True)
        menu = _FakeFlyout(group="context_menu")
        ordinary = _FakeFlyout(group="options")
        manager._registered_flyouts = {pinned, menu, ordinary}
        manager._active_flyout = None

        CustomTitleBar()._hide_active_flyouts()

        assert pinned.isVisible()
        assert menu.isVisible()
        assert not ordinary.isVisible()
    finally:
        manager._registered_flyouts = previous_registered
        manager._active_flyout = previous_active
