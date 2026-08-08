import logging
from typing import Callable, Optional, Protocol, Set

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QTimer, Qt
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.flyout_policy import (
    CallableShowPolicy,
    ChainShowPolicy,
    ExclusiveShowPolicy,
    FlyoutShowPolicy,
)
from sli_ui_toolkit.ui.managers.layer_stack import LayerStack

logger = logging.getLogger(__name__)


class ManagedFlyout(Protocol):
    def isVisible(self) -> bool: ...
    def hide(self) -> None: ...


class FlyoutManager(QObject):
    _instance: Optional["FlyoutManager"] = None

    def __init__(self):
        super().__init__()
        self._active_flyout: Optional[ManagedFlyout] = None
        self._registered_flyouts: Set[ManagedFlyout] = set()
        self._anchor_snapshots: dict[ManagedFlyout, tuple[tuple[QWidget, QRect], ...]] = {}
        self._pending_anchor_snapshots: Set[int] = set()
        self._event_filter_installed = False
        self._show_policy: FlyoutShowPolicy = ExclusiveShowPolicy()
        self._layer_stack = LayerStack()
        self._links: dict[ManagedFlyout, Set[ManagedFlyout]] = {}
        self._link_parent_of: dict[ManagedFlyout, ManagedFlyout] = {}
        # ``_registered_flyouts`` is a set (no ordering); stacking order
        # within a layer needs registration order as a stable tie-break.
        self._registration_order: dict[ManagedFlyout, int] = {}
        self._registration_counter = 0

    @classmethod
    def get_instance(cls) -> "FlyoutManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_show_policy(
        self,
        policy: FlyoutShowPolicy
        | Callable[[object, object], bool]
        | list[FlyoutShowPolicy]
        | tuple[FlyoutShowPolicy, ...]
        | None,
    ) -> None:
        """Install the dismiss / active policy used by ``request_show``.

        Pass ``None`` to restore exclusive defaults. A bare
        ``(showing, other) -> bool`` callable is wrapped as dismiss-only
        (always claims active). A ``list``/``tuple`` of policies is wrapped
        in a ``ChainShowPolicy`` (see its docstring for how the policies are
        combined) — pass higher-priority policies first.
        """
        if policy is None:
            self._show_policy = ExclusiveShowPolicy()
            return
        if isinstance(policy, (list, tuple)):
            self._show_policy = ChainShowPolicy(policy)
            return
        if callable(policy) and not hasattr(policy, "should_dismiss"):
            self._show_policy = CallableShowPolicy(policy)
            return
        self._show_policy = policy  # type: ignore[assignment]

    def show_policy(self) -> FlyoutShowPolicy:
        return self._show_policy

    def set_layer_stack(self, layer_stack: LayerStack | None) -> None:
        """Install the z-order layer stack used by ``ensure_overlay_stacking``.

        Pass ``None`` to restore the default two-layer stack (``base`` /
        ``context_menu``, matching the toolkit's historical hardcoded
        behavior).
        """
        self._layer_stack = layer_stack if layer_stack is not None else LayerStack()

    def layer_stack(self) -> LayerStack:
        return self._layer_stack

    def link(self, parent: ManagedFlyout, child: ManagedFlyout) -> None:
        """Declare ``child`` as part of ``parent``'s family.

        Hiding ``parent`` (via any path — outside click, ``close_all``,
        group-policy dismiss, anchor movement) also hides ``child``,
        recursively. Showing ``parent`` again (e.g. a pinned HUD's
        ``reposition()``, which re-enters ``request_show``) also calls
        ``child.reposition()`` if the child has one and is visible. A child
        can have at most one parent; linking it again replaces the previous
        parent link.
        """
        previous_parent = self._link_parent_of.get(child)
        if previous_parent is not None and previous_parent is not parent:
            self.unlink(previous_parent, child)
        self._links.setdefault(parent, set()).add(child)
        self._link_parent_of[child] = parent

    def unlink(self, parent: ManagedFlyout, child: ManagedFlyout) -> None:
        children = self._links.get(parent)
        if children is not None:
            children.discard(child)
            if not children:
                self._links.pop(parent, None)
        if self._link_parent_of.get(child) is parent:
            self._link_parent_of.pop(child, None)

    def linked_children(self, parent: ManagedFlyout) -> tuple[ManagedFlyout, ...]:
        return tuple(self._links.get(parent, ()))

    def _hide_with_family(self, flyout: ManagedFlyout) -> None:
        try:
            if flyout.isVisible():
                flyout.hide()
        except RuntimeError:
            self._registered_flyouts.discard(flyout)
            return
        except Exception:
            return
        for child in list(self._links.get(flyout, ())):
            self._hide_with_family(child)

    def _reposition_children(self, parent: ManagedFlyout) -> None:
        for child in list(self._links.get(parent, ())):
            try:
                if not child.isVisible():
                    continue
                reposition = getattr(child, "reposition", None)
                if callable(reposition):
                    reposition()
            except RuntimeError:
                self._registered_flyouts.discard(child)
            except Exception:
                continue

    def register_flyout(self, flyout: ManagedFlyout):
        if flyout not in self._registered_flyouts:
            self._registered_flyouts.add(flyout)
            self._registration_counter += 1
            self._registration_order[flyout] = self._registration_counter

    def unregister_flyout(self, flyout: ManagedFlyout):
        self._registered_flyouts.discard(flyout)
        self._anchor_snapshots.pop(flyout, None)
        self._pending_anchor_snapshots.discard(id(flyout))
        self._registration_order.pop(flyout, None)
        if self._active_flyout is flyout:
            self._active_flyout = None
        for child in list(self._links.pop(flyout, ())):
            self._link_parent_of.pop(child, None)
        parent = self._link_parent_of.pop(flyout, None)
        if parent is not None:
            self.unlink(parent, flyout)

    def request_show(self, flyout: ManagedFlyout) -> bool:
        if flyout not in self._registered_flyouts:
            self.register_flyout(flyout)

        self._install_event_filter()

        if self._active_flyout is flyout and flyout.isVisible():
            self._schedule_anchor_snapshot(flyout)
            self.ensure_overlay_stacking(raised=flyout)
            self._reposition_children(flyout)
            return True

        # Pinned HUDs call show_aligned()/reposition() on every anchor move —
        # they must not dismiss unrelated open flyouts or steal "active" on
        # every one of those calls the way a real (user-triggered) flyout
        # opening should.
        if not self._is_pinned(flyout):
            policy = self._show_policy
            for registered in list(self._registered_flyouts):
                if registered is flyout:
                    continue
                try:
                    if not registered.isVisible():
                        continue
                    if policy.should_dismiss(flyout, registered):
                        self._hide_with_family(registered)
                except RuntimeError:
                    self._registered_flyouts.discard(registered)
                except Exception:
                    continue

            if policy.should_claim_active(flyout, self._active_flyout):
                self._active_flyout = flyout
            elif self._active_flyout is None or not self._active_flyout.isVisible():
                self._active_flyout = flyout

        self._schedule_anchor_snapshot(flyout)
        self.ensure_overlay_stacking(raised=flyout)
        self._reposition_children(flyout)
        return True

    def ensure_overlay_stacking(self, raised: ManagedFlyout | None = None) -> None:
        """Keep higher-layer flyouts above every lower-layer in-window flyout.

        Layer membership comes from ``self._layer_stack`` (see
        ``layer_stack.py``); by default only ``context_menu`` sits in a
        layer above ``base``. List open/refresh animations call
        ``raise_()`` on UnifiedFlyout; without this, a higher-layer flyout
        opened mid-animation would sink under a base-layer panel.
        """
        stack = self._layer_stack
        base_index = 0
        above_base: list[tuple[int, int, ManagedFlyout]] = []
        for registered in list(self._registered_flyouts):
            if registered is raised:
                continue
            try:
                if not registered.isVisible():
                    continue
            except RuntimeError:
                self._registered_flyouts.discard(registered)
                continue
            group = getattr(type(registered), "flyout_group", None)
            if group is None:
                group = getattr(registered, "flyout_group", None)
            index = stack.index_of(group)
            if index > base_index:
                # Registration order is the tie-break within a layer --
                # ``_registered_flyouts`` is a plain set, so its iteration
                # order alone is not stable across runs.
                order = self._registration_order.get(registered, 0)
                above_base.append((index, order, registered))
        above_base.sort(key=lambda triple: (triple[0], triple[1]))
        for _, _, item in above_base:
            try:
                raise_fn = getattr(item, "raise_", None)
                if callable(raise_fn):
                    # Use QWidget.raise_ to avoid re-entering ensure_overlay_stacking
                    # if the widget's raise_ is wrapped. ManagedFlyout is a
                    # structural Protocol (isVisible/hide only) so mypy can't
                    # see it's really QWidget-backed at runtime.
                    from PySide6.QtWidgets import QWidget

                    QWidget.raise_(item)  # type: ignore[arg-type]
            except RuntimeError:
                self._registered_flyouts.discard(item)
            except Exception:
                continue

    def request_hide(self, flyout: ManagedFlyout):
        self._anchor_snapshots.pop(flyout, None)
        if self._active_flyout is flyout:
            self._active_flyout = None
        for child in list(self._links.get(flyout, ())):
            try:
                if child.isVisible():
                    child.hide()
            except RuntimeError:
                self._registered_flyouts.discard(child)
            except Exception:
                continue
        if not self._any_visible():
            self._remove_event_filter()

    def close_all(self):
        for flyout in list(self._registered_flyouts):
            try:
                if flyout.isVisible():
                    flyout.hide()
            except RuntimeError:
                self._registered_flyouts.discard(flyout)
            except Exception:
                continue
        self._active_flyout = None
        self._anchor_snapshots.clear()
        self._pending_anchor_snapshots.clear()
        self._remove_event_filter()

    @staticmethod
    def _is_pinned(flyout: ManagedFlyout) -> bool:
        return bool(getattr(flyout, "pinned", False))

    def _dismiss_passive(self):
        """Close every dismissable (non-``pinned``) visible flyout.

        Used for events the user did not aim at any flyout on purpose —
        outside click, outside wheel, app/window deactivate. ``pinned``
        flyouts (persistent HUDs, see ``BaseFlyout(pinned=True)``) sit these
        out; only an explicit :meth:`close_all` closes them.
        """
        any_dismissed = False
        for flyout in list(self._registered_flyouts):
            if self._is_pinned(flyout):
                continue
            try:
                if flyout.isVisible():
                    flyout.hide()
                    any_dismissed = True
            except RuntimeError:
                self._registered_flyouts.discard(flyout)
            except Exception:
                continue
        if self._active_flyout is not None and not self._is_pinned(self._active_flyout):
            self._active_flyout = None
        if any_dismissed and not self._any_visible():
            self._remove_event_filter()

    def close_if_outside(self, global_pos: QPoint) -> bool:
        """Hide every visible flyout when ``global_pos`` is outside all of them.

        Returns True if a close was performed. Hosts can call this from their
        own mouse-press routing so flyouts stay in sync even when a parallel
        app-level closer only knows about a subset (e.g. UnifiedFlyout).
        """
        if self._contains_global(global_pos):
            return False
        if not self._any_visible():
            return False
        self.close_all()
        return True

    def is_flyout_active(self, flyout: ManagedFlyout) -> bool:
        return self._active_flyout is flyout and flyout.isVisible()

    def get_active_flyout(self) -> Optional[ManagedFlyout]:
        if self._active_flyout is not None and self._active_flyout.isVisible():
            return self._active_flyout
        return None

    def eventFilter(self, obj, event):
        event_type = event.type()
        if event_type in (
            QEvent.Type.ApplicationDeactivate,
            QEvent.Type.WindowDeactivate,
        ):
            # Wayland flickers deactivate when closing in-window context menus.
            # Defer and only close if the app is still inactive.
            if getattr(self, "_deactivate_close_scheduled", False):
                return False
            self._deactivate_close_scheduled = True

            def _maybe_close() -> None:
                self._deactivate_close_scheduled = False
                app = QApplication.instance()
                if isinstance(app, QApplication):
                    try:
                        from PySide6.QtCore import Qt

                        # Modal prompts (rename, etc.) deactivate the parent
                        # window while the app stays active. Wayland often
                        # reports activeWindow() is None during that handoff —
                        # closing here would dismiss UnifiedFlyout even though
                        # the host correctly keeps the list open.
                        if app.activeModalWidget() is not None:
                            return
                        if (
                            app.applicationState()
                            == Qt.ApplicationState.ApplicationActive
                        ):
                            return
                    except Exception:
                        pass
                self._dismiss_passive()

            QTimer.singleShot(0, _maybe_close)
            return False

        if event_type in (
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.Hide,
            QEvent.Type.Show,
            QEvent.Type.ParentChange,
            QEvent.Type.LayoutRequest,
        ):
            self._close_flyouts_with_moved_anchors()
            return False

        if event_type == QEvent.Type.Wheel:
            if self._active_flyout is not None and self._active_flyout.isVisible():
                try:
                    global_pos = event.globalPosition().toPoint()
                except AttributeError:
                    try:
                        global_pos = event.globalPos()
                    except AttributeError:
                        global_pos = None
                inside = self._is_inside_active_flyout(obj) or (
                    global_pos is not None and self._contains_global(global_pos)
                )
                if not inside:
                    self._dismiss_passive()
            return False

        if event_type == QEvent.Type.MouseButtonPress:
            # Right-press must not close flyouts here: context-menu hosts toggle
            # on the same gesture (press/release). Closing first makes the host
            # reopen a fresh menu, so the second right-click appears to do nothing.
            try:
                if event.button() == Qt.MouseButton.RightButton:
                    return False
            except Exception:
                pass
            try:
                global_pos = event.globalPosition().toPoint()
            except AttributeError:
                try:
                    global_pos = event.globalPos()
                except AttributeError:
                    global_pos = None

            active = self._active_flyout
            if (
                global_pos is not None
                and active is not None
                and active.isVisible()
                and not self._is_pinned(active)
            ):
                on_body = False
                on_anchor = False
                try:
                    contains = getattr(active, "contains_global", None)
                    on_body = bool(contains(global_pos)) if contains is not None else False
                except Exception:
                    on_body = False
                try:
                    trigger_hit = getattr(active, "trigger_contains_global", None)
                    on_anchor = (
                        bool(trigger_hit(global_pos)) if trigger_hit is not None else False
                    )
                except Exception:
                    on_anchor = False
                # Click on the trigger while the menu is open: dismiss, and
                # suppress the trigger's ensuing clicked→reopen for this gesture.
                # Use ONE suppress flag only. Setting both poisons the next
                # open: release consumes ``_suppress_next_click`` without
                # clearing ``_suppress_next_context_menu``, so the following
                # click is a no-op (File/Help CSD menus need two clicks).
                if on_anchor and not on_body:
                    is_context_menu = (
                        getattr(active, "flyout_group", None) == "context_menu"
                    )
                    for anchor in self._trigger_widgets(active):
                        try:
                            if is_context_menu:
                                setattr(anchor, "_suppress_next_context_menu", True)
                            else:
                                # Toggle buttons (font settings, interp combo, …)
                                setattr(anchor, "_suppress_next_click", True)
                        except Exception:
                            pass
                    try:
                        self._hide_with_family(active)
                    except Exception:
                        self.close_all()
                    return False

            if global_pos is not None and not self._contains_global(global_pos):
                self._dismiss_passive()
        return False

    def _schedule_anchor_snapshot(self, flyout: ManagedFlyout) -> None:
        self._snapshot_anchor_geometry(flyout)
        key = id(flyout)
        if key in self._pending_anchor_snapshots:
            return
        self._pending_anchor_snapshots.add(key)
        QTimer.singleShot(0, lambda: self._finish_anchor_snapshot(flyout, key))

    def _finish_anchor_snapshot(self, flyout: ManagedFlyout, key: int) -> None:
        self._pending_anchor_snapshots.discard(key)
        if flyout not in self._registered_flyouts:
            return
        try:
            if flyout.isVisible():
                self._snapshot_anchor_geometry(flyout)
        except RuntimeError:
            self.unregister_flyout(flyout)

    def _snapshot_anchor_geometry(self, flyout: ManagedFlyout) -> None:
        anchors = self._anchor_widgets(flyout)
        snapshots: list[tuple[QWidget, QRect]] = []
        for anchor in anchors:
            try:
                snapshots.append((anchor, self._global_rect(anchor)))
            except RuntimeError:
                continue
        if snapshots:
            self._anchor_snapshots[flyout] = tuple(snapshots)
        else:
            self._anchor_snapshots.pop(flyout, None)

    def _close_flyouts_with_moved_anchors(self) -> None:
        for flyout, snapshots in list(self._anchor_snapshots.items()):
            try:
                if not flyout.isVisible():
                    self._anchor_snapshots.pop(flyout, None)
                    continue
                if self._is_pinned(flyout):
                    # Pinned flyouts reposition instead of closing when their
                    # *own* anchor moves/resizes -- do it here (BaseFlyout.
                    # reposition() is a no-op if never shown/no longer
                    # visible/anchor gone) rather than requiring every
                    # pinned-flyout host to wire its own resize/move handler
                    # for this; hosts that already call reposition()
                    # themselves (e.g. InfoHUD/ZoomIndicator from their own
                    # resize paths) just get a harmless extra no-op call
                    # here. This event filter is installed app-wide (see
                    # _install_event_filter), so it fires on Move/Resize/etc.
                    # of *any* widget anywhere, not just this flyout's own
                    # anchors -- gate on the same snapshot-rect comparison
                    # the non-pinned branch below uses, or every unrelated
                    # layout event in the whole app would re-run this
                    # flyout's full positioning logic.
                    moved = any(
                        self._global_rect(anchor) != previous_rect
                        for anchor, previous_rect in snapshots
                    )
                    if moved:
                        reposition = getattr(flyout, "reposition", None)
                        if callable(reposition):
                            try:
                                reposition()
                            except RuntimeError:
                                self.unregister_flyout(flyout)
                                continue
                        # Refresh so an unmoving anchor doesn't keep
                        # comparing against the pre-move snapshot forever.
                        self._schedule_anchor_snapshot(flyout)
                    continue
                for anchor, previous_rect in snapshots:
                    if self._global_rect(anchor) != previous_rect:
                        self._hide_with_family(flyout)
                        break
            except RuntimeError:
                self.unregister_flyout(flyout)
            except Exception:
                continue

    def _anchor_widgets(self, flyout: ManagedFlyout) -> tuple[QWidget, ...]:
        getter = getattr(flyout, "anchor_widgets", None)
        if getter is not None:
            try:
                anchors = getter()
                return tuple(anchor for anchor in anchors if isinstance(anchor, QWidget))
            except Exception:
                return ()

        anchor = getattr(flyout, "_anchor_widget", None)
        return (anchor,) if isinstance(anchor, QWidget) else ()

    def _trigger_widgets(self, flyout: ManagedFlyout) -> tuple[QWidget, ...]:
        getter = getattr(flyout, "trigger_widgets", None)
        if getter is not None:
            try:
                widgets = getter()
                return tuple(w for w in widgets if isinstance(w, QWidget))
            except Exception:
                return ()
        return self._anchor_widgets(flyout)

    def _global_rect(self, widget: QWidget) -> QRect:
        return QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())

    def _is_inside_active_flyout(self, obj) -> bool:
        flyout = self._active_flyout
        if flyout is None or not isinstance(obj, QWidget):
            return False
        try:
            widget: QWidget | None = obj
            flyout_widget = flyout if isinstance(flyout, QWidget) else None
            if flyout_widget is None:
                return False
            while widget is not None:
                if widget is flyout_widget:
                    return True
                widget = widget.parentWidget()
        except RuntimeError:
            return False
        return False

    def _contains_global(self, global_pos) -> bool:
        for flyout in list(self._registered_flyouts):
            try:
                if not flyout.isVisible():
                    continue
                contains = getattr(flyout, "contains_global", None)
                if contains is not None and contains(global_pos):
                    return True
                anchor_contains = getattr(flyout, "anchor_contains_global", None)
                if anchor_contains is not None and anchor_contains(global_pos):
                    return True
            except RuntimeError:
                self._registered_flyouts.discard(flyout)
            except Exception:
                continue
        return False

    def _any_visible(self) -> bool:
        for flyout in list(self._registered_flyouts):
            try:
                if flyout.isVisible():
                    return True
            except RuntimeError:
                self._registered_flyouts.discard(flyout)
        return False

    def _install_event_filter(self) -> None:
        if self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._event_filter_installed = True

    def _remove_event_filter(self) -> None:
        if not self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._event_filter_installed = False
