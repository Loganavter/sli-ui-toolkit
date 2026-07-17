"""Pluggable show/dismiss policies for ``FlyoutManager``.

The toolkit default is exclusive: showing any flyout hides every other
registered flyout. Hosts install a custom policy (typically
``GroupShowPolicy``) to keep some overlays open together — e.g. a context
menu over ``UnifiedFlyout`` — without patching widget classes.
"""

from __future__ import annotations

from typing import Callable, Iterable, Protocol

# Sentinel: dismiss every other visible flyout (legacy exclusive behavior).
DISMISS_ALL = object()

# Unconfigured / missing group name.
DEFAULT_FLYOUT_GROUP = "default"


def flyout_group_of(flyout: object) -> str:
    group = getattr(flyout, "flyout_group", None)
    if isinstance(group, str) and group:
        return group
    return DEFAULT_FLYOUT_GROUP


class FlyoutShowPolicy(Protocol):
    """Decides what happens when one flyout requests to show."""

    def should_dismiss(self, showing: object, other: object) -> bool:
        """Return True if ``other`` must hide when ``showing`` opens."""

    def should_claim_active(
        self, showing: object, current_active: object | None
    ) -> bool:
        """Return True if ``showing`` becomes the manager's active flyout."""


class ExclusiveShowPolicy:
    """Classic single-active behavior: hide everyone else, claim active."""

    def should_dismiss(self, showing: object, other: object) -> bool:
        return True

    def should_claim_active(
        self, showing: object, current_active: object | None
    ) -> bool:
        return True


class CallableShowPolicy:
    """Adapt a ``should_dismiss(showing, other)`` callable into a full policy."""

    def __init__(
        self,
        should_dismiss: Callable[[object, object], bool],
        *,
        should_claim_active: Callable[[object, object | None], bool] | None = None,
    ):
        self._should_dismiss = should_dismiss
        self._should_claim_active = should_claim_active

    def should_dismiss(self, showing: object, other: object) -> bool:
        return bool(self._should_dismiss(showing, other))

    def should_claim_active(
        self, showing: object, current_active: object | None
    ) -> bool:
        if self._should_claim_active is None:
            return True
        return bool(self._should_claim_active(showing, current_active))


class GroupShowPolicy:
    """Dismiss / active rules keyed by ``flyout.flyout_group`` (or per instance).

    Example::

        policy = GroupShowPolicy()
        policy.configure_group(
            "context_menu",
            dismisses=(),          # open over other flyouts
            claim_active=False,    # leave UnifiedFlyout as active
        )
        # Unconfigured groups keep exclusive defaults (dismiss all, claim active).
        FlyoutManager.get_instance().set_show_policy(policy)

    Per-flyout overrides win over group rules::

        policy.configure_flyout(
            special,
            dismisses=("unified_list",),
            claim_active=True,
        )
    """

    def __init__(self, *, fallback: FlyoutShowPolicy | None = None):
        self._fallback = fallback or ExclusiveShowPolicy()
        # None value => DISMISS_ALL; frozenset => only those groups.
        self._group_dismisses: dict[str, frozenset[str] | None] = {}
        self._group_claim_active: dict[str, bool] = {}
        self._flyout_dismisses: dict[int, frozenset[str] | None] = {}
        self._flyout_claim_active: dict[int, bool] = {}

    def configure_group(
        self,
        group: str,
        *,
        dismisses: object | Iterable[str] = DISMISS_ALL,
        claim_active: bool = True,
    ) -> GroupShowPolicy:
        self._group_dismisses[group] = self._normalize_dismisses(dismisses)
        self._group_claim_active[group] = bool(claim_active)
        return self

    def configure_flyout(
        self,
        flyout: object,
        *,
        dismisses: object | Iterable[str] = DISMISS_ALL,
        claim_active: bool = True,
    ) -> GroupShowPolicy:
        key = id(flyout)
        self._flyout_dismisses[key] = self._normalize_dismisses(dismisses)
        self._flyout_claim_active[key] = bool(claim_active)
        return self

    def clear_flyout(self, flyout: object) -> None:
        key = id(flyout)
        self._flyout_dismisses.pop(key, None)
        self._flyout_claim_active.pop(key, None)

    def should_dismiss(self, showing: object, other: object) -> bool:
        targets = self._dismiss_targets(showing)
        if targets is None:
            return True
        return flyout_group_of(other) in targets

    def should_claim_active(
        self, showing: object, current_active: object | None
    ) -> bool:
        key = id(showing)
        if key in self._flyout_claim_active:
            return self._flyout_claim_active[key]
        group = flyout_group_of(showing)
        if group in self._group_claim_active:
            return self._group_claim_active[group]
        return self._fallback.should_claim_active(showing, current_active)

    def _dismiss_targets(self, showing: object) -> frozenset[str] | None:
        key = id(showing)
        if key in self._flyout_dismisses:
            return self._flyout_dismisses[key]
        group = flyout_group_of(showing)
        if group in self._group_dismisses:
            return self._group_dismisses[group]
        # Fallback exclusive: dismiss all.
        if self._fallback.should_dismiss(showing, showing):
            return None
        return frozenset()

    @staticmethod
    def _normalize_dismisses(
        dismisses: object | Iterable[str],
    ) -> frozenset[str] | None:
        if dismisses is DISMISS_ALL:
            return None
        if isinstance(dismisses, str):
            if dismisses == "*":
                return None
            return frozenset((dismisses,))
        return frozenset(dismisses)
