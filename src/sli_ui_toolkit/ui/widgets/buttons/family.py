"""Behavioral button family — shared policies + combined geometry.

A ``ButtonFamily`` is a non-visual link between separate ``Button`` widgets
("one button, but different buttons"): the members keep their own visuals,
paint and clicks, while the family mirrors runtime state across them
according to its policies and reports their combined area.

This is different from the other two group concepts in this codebase:

- ``ButtonRegion.group`` links regions *inside one* ``Button`` (shared
  capsule paints/states for abutting regions of a single widget);
- ``CustomGroupWidget`` / ``ButtonGroup`` / ``RadioButtonGroup`` are layout
  containers or (radio-only) exclusive checkers with their own visuals —
  ``RadioButtonGroup`` additionally only accepts ``RadioButton``.

``ButtonFamily`` owns no visuals and reparents nothing: it installs an event
filter on each member (Enter/Leave for hover, Move/Resize/Show/Hide for
geometry) and listens to ``toggled`` for the exclusive policy. Removing a
member (or destroying it) detaches cleanly; disabling ``shared_hover``
clears the mirrored glow.

Policies (independent, combinable):

- ``shared_hover`` — the pointer inside *any* member lights ``HOVERED`` on
  *every* member (whole buttons, all non-disabled regions), cleared when the
  pointer leaves all of them. Mirrors the region-``group=`` hover semantic
  across widgets instead of within one.
- ``exclusive`` — checking one member unchecks the rest (radio-like, works
  for any toggle ``Button``, not just ``RadioButton``).

Combined geometry (global screen coordinates unless stated):

- ``unionRect()`` — bounding rect of all *visible* members (null ``QRect``
  when empty/none visible); ``unionRectMappedTo(widget)`` maps it into
  another widget's coordinates; ``center()`` is the union center.
- ``geometryChanged`` fires when any member moves, resizes, shows or hides,
  so hosts can re-pin overlays anchored to the family area.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Signal

from .state import ButtonState

if TYPE_CHECKING:
    from .button import Button


class ButtonFamily(QObject):
    """Non-visual family link for ``Button`` widgets (see module docstring)."""

    geometryChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[Button] = []
        self._shared_hover = False
        self._exclusive = False
        self._hovered: set[Button] = set()
        self._syncing = False
        self._toggled_slots: dict[int, object] = {}

    # -------- membership --------

    def addButton(self, button: Button) -> None:
        """Link *button* into the family (no-op when already a member)."""
        if button is None or button in self._buttons:
            return
        self._buttons.append(button)
        try:
            button.installEventFilter(self)
        except Exception:
            pass
        try:
            slot = lambda checked, b=button: self._on_toggled(b, checked)
            button.toggled.connect(slot)
            self._toggled_slots[id(button)] = slot
        except Exception:
            pass
        try:
            button.destroyed.connect(lambda _obj=None, b=button: self.removeButton(b))
        except Exception:
            pass
        try:
            if button.underMouse():
                self._hovered.add(button)
        except Exception:
            pass
        self._apply_hover()
        self.geometryChanged.emit()

    def removeButton(self, button: Button) -> None:
        """Detach *button* (no-op when not a member); clears its family glow."""
        if button not in self._buttons:
            return
        self._buttons.remove(button)
        self._hovered.discard(button)
        try:
            button.removeEventFilter(self)
        except Exception:
            pass
        try:
            slot = self._toggled_slots.pop(id(button), None)
            if slot is not None:
                button.toggled.disconnect(slot)
        except Exception:
            pass
        self._clear_button_hover(button)
        self._apply_hover()
        self.geometryChanged.emit()

    def buttons(self) -> list[Button]:
        """Live members in add order."""
        return list(self._buttons)

    # -------- policies --------

    def setSharedHover(self, on: bool) -> None:
        """Mirror hover across members (any-inside → all glow)."""
        self._shared_hover = bool(on)
        self._apply_hover()

    def sharedHover(self) -> bool:
        return self._shared_hover

    def setExclusive(self, on: bool) -> None:
        """Radio-like checking: checking one member unchecks the rest."""
        self._exclusive = bool(on)

    def isExclusive(self) -> bool:
        return self._exclusive

    # -------- combined geometry --------

    def unionRect(self) -> QRect:
        """Bounding rect of all visible members, in global coordinates."""
        acc = QRect()
        for button in list(self._buttons):
            try:
                if not button.isVisible():
                    continue
                top_left = button.mapToGlobal(button.rect().topLeft())
                acc = acc.united(QRect(top_left, button.rect().size()))
            except Exception:
                continue
        return acc

    def unionRectMappedTo(self, widget: QObject) -> QRect:
        """``unionRect()`` mapped into *widget*'s local coordinates."""
        union = self.unionRect()
        if union.isNull():
            return QRect()
        try:
            top_left = widget.mapFromGlobal(union.topLeft())  # type: ignore[attr-defined]
            return QRect(top_left, union.size())
        except Exception:
            return QRect()

    def center(self) -> QPoint:
        """Global center of ``unionRect()`` (null ``QPoint`` when empty)."""
        union = self.unionRect()
        if union.isNull():
            return QPoint()
        return union.center()

    # -------- internals --------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched in self._buttons:
            try:
                event_type = event.type()
            except Exception:
                return False
            if event_type == QEvent.Type.Enter:
                self._hovered.add(watched)  # type: ignore[arg-type]
                self._apply_hover()
            elif event_type == QEvent.Type.Leave:
                self._hovered.discard(watched)  # type: ignore[arg-type]
                self._apply_hover()
            elif event_type in (
                QEvent.Type.Move,
                QEvent.Type.Resize,
                QEvent.Type.Show,
                QEvent.Type.Hide,
            ):
                self.geometryChanged.emit()
        return False

    def _on_toggled(self, button: Button, checked: bool) -> None:
        if not self._exclusive or not checked or self._syncing:
            return
        self._syncing = True
        try:
            for other in list(self._buttons):
                if other is not button:
                    try:
                        other.setChecked(False)
                    except Exception:
                        pass
        finally:
            self._syncing = False

    def _member_regions(self, button: Button) -> list[str]:
        try:
            regions = button._regions  # type: ignore[attr-defined]
        except Exception:
            return []
        try:
            return [region.id for region in regions]
        except Exception:
            return []

    def _clear_button_hover(self, button: Button) -> None:
        try:
            controller = button._controller  # type: ignore[attr-defined]
        except Exception:
            return
        try:
            for region_id in self._member_regions(button):
                try:
                    controller.set_state(region_id, ButtonState.HOVERED, False)
                except Exception:
                    continue
            button.update()
        except Exception:
            pass

    def _apply_hover(self) -> None:
        want = self._shared_hover and bool(self._hovered)
        for button in list(self._buttons):
            try:
                controller = button._controller  # type: ignore[attr-defined]
            except Exception:
                continue
            try:
                for region_id in self._member_regions(button):
                    try:
                        if ButtonState.DISABLED in controller.states(region_id):
                            continue
                        controller.set_state(region_id, ButtonState.HOVERED, want)
                    except Exception:
                        continue
                button.update()
            except Exception:
                continue
