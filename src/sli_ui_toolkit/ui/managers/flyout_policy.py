"""Pluggable show/dismiss policies for ``FlyoutManager``.

The toolkit default is exclusive: showing any flyout hides every other
registered flyout. Hosts install a custom policy (typically
``GroupShowPolicy``) to keep some overlays open together — e.g. a context
menu over ``UnifiedFlyout`` — without patching widget classes.
"""

from __future__ import annotations

from typing import Callable, Iterable, Protocol, Sequence, cast

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


class ChainShowPolicy:
    """Combine several policies into one, in priority order.

    ``should_dismiss`` is AND-combined: ``other`` is only dismissed if
    *every* policy in the chain agrees to dismiss it. This means any single
    policy can protect a pair from being dismissed (return ``False``) and
    that protection wins regardless of what the rest of the chain says —
    the same way ``GroupShowPolicy.coexists_with`` already overrides a
    single policy's own dismiss-all default, generalized across multiple
    policy objects (e.g. a host-specific one-off rule layered on top of the
    toolkit's ``GroupShowPolicy``).

    ``should_claim_active`` is priority-order: the first policy's answer is
    used, since "who becomes active" is a single decision rather than a set
    of independent exceptions to combine. Put the policy whose claim-active
    rules should take precedence first in the list.

    Requires at least one policy.
    """

    def __init__(self, policies: Sequence[FlyoutShowPolicy]):
        self._policies = tuple(policies)
        if not self._policies:
            raise ValueError("ChainShowPolicy requires at least one policy")

    def should_dismiss(self, showing: object, other: object) -> bool:
        return all(p.should_dismiss(showing, other) for p in self._policies)

    def should_claim_active(
        self, showing: object, current_active: object | None
    ) -> bool:
        return self._policies[0].should_claim_active(showing, current_active)


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


_UNSET = object()


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

    Groups can inherit another group's rules via ``parent`` — a group with
    no rules of its own (dismiss set / claim_active) configured falls back
    to its parent's, recursively::

        policy.configure_group("context_menu", dismisses=(), claim_active=False)
        policy.define_group("submenu", parent="context_menu")  # inherits both

    ``coexists_with`` is symmetric sugar for "opening either of these two
    groups must never dismiss the other", independent of what each group's
    own ``dismisses`` set says. It also follows ``parent`` inheritance on
    both sides -- a group with no ``coexists_with`` edges of its own still
    inherits its ancestor's::

        policy.coexists_with("context_menu", "unified_list")
        policy.define_group("submenu", parent="context_menu")
        # submenu <-> unified_list also never dismiss each other, inherited
        # from context_menu, with no separate coexists_with call needed.
    """

    def __init__(self, *, fallback: FlyoutShowPolicy | None = None):
        self._fallback = fallback or ExclusiveShowPolicy()
        # None value => DISMISS_ALL; frozenset => only those groups.
        self._group_dismisses: dict[str, frozenset[str] | None] = {}
        self._group_claim_active: dict[str, bool] = {}
        self._group_parent: dict[str, str] = {}
        self._group_coexist: dict[str, set[str]] = {}
        self._flyout_dismisses: dict[int, frozenset[str] | None] = {}
        self._flyout_claim_active: dict[int, bool] = {}

    def configure_group(
        self,
        group: str,
        *,
        dismisses: object | Iterable[str] = _UNSET,
        claim_active: bool | object = _UNSET,
        parent: str | None | object = _UNSET,
    ) -> GroupShowPolicy:
        """Set this group's own rules and/or its parent.

        Any argument left as ``_UNSET`` (the default) is not written —
        so ``configure_group("submenu", parent="context_menu")`` only sets
        the parent link, leaving ``dismisses``/``claim_active`` to inherit
        from that parent (or the fallback, if no ancestor sets them).
        """
        if parent is not _UNSET:
            if parent is None:
                self._group_parent.pop(group, None)
            else:
                self._group_parent[group] = parent  # type: ignore[assignment]
        if dismisses is not _UNSET:
            self._group_dismisses[group] = self._normalize_dismisses(dismisses)
        if claim_active is not _UNSET:
            self._group_claim_active[group] = bool(claim_active)
        return self

    def define_group(self, group: str, *, parent: str) -> GroupShowPolicy:
        """Declare ``group`` as inheriting ``parent``'s rules, with no rules of its own."""
        return self.configure_group(group, parent=parent)

    def coexists_with(self, group_a: str, group_b: str) -> GroupShowPolicy:
        """Neither group dismisses the other, regardless of their own dismiss sets."""
        self._group_coexist.setdefault(group_a, set()).add(group_b)
        self._group_coexist.setdefault(group_b, set()).add(group_a)
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
        if self._coexist_chain_match(
            flyout_group_of(showing), flyout_group_of(other)
        ):
            return False
        targets = self._dismiss_targets(showing)
        if targets is None:
            return True
        return flyout_group_of(other) in targets

    def _coexist_chain_match(self, showing_group: str, other_group: str) -> bool:
        """``coexists_with`` follows ``parent`` inheritance on both sides.

        A group declared with ``define_group(child, parent=X)`` has no
        ``coexists_with`` edges of its own, so it must fall back to
        whatever its ancestors declared -- otherwise a group inheriting
        ``dismisses``/``claim_active`` from a parent would silently *not*
        inherit that parent's coexistence exceptions.
        """
        other_chain = tuple(self._group_chain(other_group))
        for candidate in self._group_chain(showing_group):
            coexist = self._group_coexist.get(candidate)
            if coexist and any(member in coexist for member in other_chain):
                return True
        return False

    def should_claim_active(
        self, showing: object, current_active: object | None
    ) -> bool:
        key = id(showing)
        if key in self._flyout_claim_active:
            return self._flyout_claim_active[key]
        for candidate in self._group_chain(flyout_group_of(showing)):
            if candidate in self._group_claim_active:
                return self._group_claim_active[candidate]
        return self._fallback.should_claim_active(showing, current_active)

    def _dismiss_targets(self, showing: object) -> frozenset[str] | None:
        key = id(showing)
        if key in self._flyout_dismisses:
            return self._flyout_dismisses[key]
        for candidate in self._group_chain(flyout_group_of(showing)):
            if candidate in self._group_dismisses:
                return self._group_dismisses[candidate]
        # Fallback exclusive: dismiss all.
        if self._fallback.should_dismiss(showing, showing):
            return None
        return frozenset()

    def _group_chain(self, group: str):
        seen: set[str] = set()
        current: str | None = group
        while current is not None and current not in seen:
            yield current
            seen.add(current)
            current = self._group_parent.get(current)

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
        return frozenset(cast(Iterable[str], dismisses))
