"""Pure geometry for flyout placement — no widget state, no theme.

Point-spec parsing (``"bottom-left"``), named-point alignment, shadow-halo
clearance, slide-start deltas and the flip-when-overflowing placement rule.
Everything here is a function of its arguments: unit-testable without a
live flyout (see ``tests/test_flyout_slide_start.py``).
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import QPoint, QRect, QSize

from sli_ui_toolkit.ui.in_window_surface import clamp_surface_rect

from .debug import _flyout_debug

AnimationAxis = Literal["auto", "vertical", "horizontal", "diagonal"]

_H_AXIS = {"left": 0.0, "center": 0.5, "right": 1.0}
_V_AXIS = {"top": 0.0, "center": 0.5, "bottom": 1.0}


def _parse_point(spec: str) -> tuple[float, float]:
    """Return (fx, fy) fractions in [0, 1] from a string like 'bottom-left' or 'top'."""
    parts = spec.split("-") if "-" in spec else [spec, "center"]
    v, h = (parts + ["center"])[:2]
    if v in _H_AXIS and h in _V_AXIS:
        v, h = h, v
    return (_H_AXIS.get(h, 0.5), _V_AXIS.get(v, 0.5))


def _point_in_rect(rect: QRect, spec: str) -> QPoint:
    fx, fy = _parse_point(spec)
    return QPoint(
        int(round(rect.left() + fx * rect.width())),
        int(round(rect.top() + fy * rect.height())),
    )


def _content_rect_in_flyout(size: QSize, shadow_radius: int) -> QRect:
    """Visible panel rect inside the outer flyout size (excludes shadow halo)."""
    r = max(0, int(shadow_radius))
    return QRect(
        r,
        r,
        max(0, int(size.width()) - 2 * r),
        max(0, int(size.height()) - 2 * r),
    )


def _flyout_point_local(size: QSize, spec: str, shadow_radius: int) -> QPoint:
    """Named point on the *rendered* panel, not the outer shadow bounds.

    Aligning ``top-left`` of the full widget to an anchor left edge leaves the
    opaque panel shifted right/down by ``SHADOW_RADIUS`` (the drop-shadow
    margin). Callers of ``show_aligned`` expect edge alignment of what the
    user sees.
    """
    return _point_in_rect(_content_rect_in_flyout(size, shadow_radius), spec)


def _flip_point_vertical(spec: str) -> str:
    """Swap top/bottom tokens in a point spec (``bottom-left`` → ``top-left``)."""
    parts = [p for p in spec.split("-") if p]
    flipped: list[str] = []
    for part in parts:
        if part == "top":
            flipped.append("bottom")
        elif part == "bottom":
            flipped.append("top")
        else:
            flipped.append(part)
    return "-".join(flipped) if flipped else spec


def slide_start_delta(
    final_rect: QRect,
    anchor_rect: QRect,
    *,
    distance: int,
    animation_axis: AnimationAxis,
    shadow_radius: int,
    ux: float,
    uy: float,
    length: float,
) -> tuple[int, int]:
    """Return ``(dx, dy)`` from final pos to slide-in start.

    ``distance`` is the desired travel of the *outer* widget. When opening
    below/above an anchor, a naive ``final - distance`` start puts the
    opaque panel (inset by ``shadow_radius``) through the middle of a short
    toolbar button — the same class of bug as aligning to the shadow halo
    instead of the visible panel. Clamp so the panel edge does not cross
    into the anchor.

    Use ``y + height`` / ``x + width`` for edges — not ``QRect.bottom()`` /
    ``right()``, which are inclusive last-pixel coordinates and sit one
    device pixel short of the true outer edge.
    """
    dist = max(0, int(distance))
    radius = max(0, int(shadow_radius))
    anchor_left = anchor_rect.x()
    anchor_top = anchor_rect.y()
    anchor_right = anchor_rect.x() + anchor_rect.width()
    anchor_bottom = anchor_rect.y() + anchor_rect.height()

    def _vertical_dy() -> int:
        if final_rect.center().y() >= anchor_rect.center().y():
            # Below: panel top = outer_y + radius; keep panel_top >= anchor bottom edge.
            desired = final_rect.y() - dist
            min_y = anchor_bottom - radius
            start_y = max(desired, min_y)
        else:
            # Above: panel bottom = outer_y + height - radius; keep <= anchor top edge.
            desired = final_rect.y() + dist
            max_y = anchor_top - final_rect.height() + radius
            start_y = min(desired, max_y)
        return start_y - final_rect.y()

    def _horizontal_dx() -> int:
        if final_rect.center().x() >= anchor_rect.center().x():
            desired = final_rect.x() - dist
            min_x = anchor_right - radius
            start_x = max(desired, min_x)
        else:
            desired = final_rect.x() + dist
            max_x = anchor_left - final_rect.width() + radius
            start_x = min(desired, max_x)
        return start_x - final_rect.x()

    if animation_axis == "vertical":
        return 0, _vertical_dy()
    if animation_axis == "horizontal":
        return _horizontal_dx(), 0
    if animation_axis == "diagonal":
        # Both axes travel the full `distance`, each independently clamped
        # against the anchor edge -- unlike "auto" below (which splits one
        # `distance`-length vector along anchor->flyout, so a corner-aligned
        # flyout whose centers differ a lot more on one axis than the other
        # gets a near-invisible slide on the smaller axis: e.g. a wide panel
        # barely offset vertically from a narrow anchor button ends up
        # looking like a near-pure horizontal slide, or vice-versa). This
        # guarantees a clearly visible motion on *both* axes regardless of
        # how the anchor and flyout sizes compare.
        return _horizontal_dx(), _vertical_dy()
    # auto: along anchor→flyout, still clamp the dominant axis against the
    # shadow inset so a wide menu under a narrow button does not foreshorten
    # into a diagonal dive through the trigger.
    if length <= 0:
        return 0, 0
    slide_dx = int(round(-ux * dist))
    slide_dy = int(round(-uy * dist))
    start = QPoint(final_rect.x() + slide_dx, final_rect.y() + slide_dy)
    if abs(uy) >= abs(ux):
        if final_rect.center().y() >= anchor_rect.center().y():
            min_y = anchor_bottom - radius
            if start.y() < min_y:
                start.setY(min_y)
        else:
            max_y = anchor_top - final_rect.height() + radius
            if start.y() > max_y:
                start.setY(max_y)
    else:
        if final_rect.center().x() >= anchor_rect.center().x():
            min_x = anchor_right - radius
            if start.x() < min_x:
                start.setX(min_x)
        else:
            max_x = anchor_left - final_rect.width() + radius
            if start.x() > max_x:
                start.setX(max_x)
    return start.x() - final_rect.x(), start.y() - final_rect.y()


def _compute_aligned_top_left(
    anchor_rect: QRect,
    flyout_size: QSize,
    *,
    anchor_point: str,
    flyout_point: str,
    offset: int,
    shadow_radius: int,
) -> QPoint:
    """Align visible panel point to anchor point, then clear the shadow halo.

    Content-point alignment alone puts the opaque panel just outside the
    anchor, but the outer widget still extends ``shadow_radius`` back over the
    button (drop-shadow margin). Clearance is therefore at least
    ``shadow_radius`` so the halo never sits on top of the anchor — but it is
    *not* added on top of ``offset``: per show_aligned's own contract, offset
    is the total visible pixel gap the caller asked for, so once offset
    already clears the halo on its own it should be used as-is (a caller
    passing offset=10 should not silently get an 18px gap).

    Caveat callers keep tripping over: this means any ``offset <
    shadow_radius`` (the common ``BaseFlyout.SHADOW_RADIUS = 8`` default)
    is silently raised to ``shadow_radius`` -- e.g. offset=2 and offset=4
    render *identically* (both floored to 8px), so tuning a value in that
    range looks like "offset does nothing" with zero indication why. Logged
    below at DEBUG when the floor actually changes the requested value;
    pass an offset at or above the flyout's own ``SHADOW_RADIUS`` (or lower
    ``SHADOW_RADIUS`` itself) to get the exact pixel gap requested.
    """
    anchor_pt = _point_in_rect(anchor_rect, anchor_point)
    flyout_pt_local = _flyout_point_local(flyout_size, flyout_point, shadow_radius)
    top_left = QPoint(
        anchor_pt.x() - flyout_pt_local.x(),
        anchor_pt.y() - flyout_pt_local.y(),
    )
    afx, afy = _parse_point(anchor_point)
    ffx, ffy = _parse_point(flyout_point)
    clearance = max(int(offset), max(0, int(shadow_radius)))
    if clearance != int(offset):
        _flyout_debug(
            "[flyout-nav] show_aligned: offset=%s floored to shadow_radius=%s "
            "(anchor_point=%r, flyout_point=%r) -- pass offset>=shadow_radius "
            "for the exact gap requested",
            offset,
            clearance,
            anchor_point,
            flyout_point,
        )
    # Axis-aligned push: dropdowns open straight down/up (or left/right),
    # not along the center-to-center diagonal (which foreshortens the gap
    # when widths differ). Independent if-blocks, not if/elif -- a true
    # corner-to-corner anchor (e.g. anchor "top-left" / flyout
    # "bottom-right") differs on *both* axes and needs clearance pushed on
    # both, otherwise one axis is left flush against the anchor with zero
    # gap (only the first block that happened to match ever fired).
    if afy > ffy:
        top_left.setY(top_left.y() + clearance)
    elif afy < ffy:
        top_left.setY(top_left.y() - clearance)
    if afx > ffx:
        top_left.setX(top_left.x() + clearance)
    elif afx < ffx:
        top_left.setX(top_left.x() - clearance)
    return top_left


def aligned_flyout_rect(
    anchor_rect: QRect,
    flyout_size: QSize,
    *,
    anchor_point: str,
    flyout_point: str,
    offset: int,
    shadow_radius: int,
    available: QRect,
) -> QRect:
    """Place flyout by named points; flip vertically when the preferred side overflows."""
    preferred = QRect(
        _compute_aligned_top_left(
            anchor_rect,
            flyout_size,
            anchor_point=anchor_point,
            flyout_point=flyout_point,
            offset=offset,
            shadow_radius=shadow_radius,
        ),
        flyout_size,
    )
    flipped_anchor = _flip_point_vertical(anchor_point)
    flipped_flyout = _flip_point_vertical(flyout_point)
    if flipped_anchor != anchor_point or flipped_flyout != flyout_point:
        flipped = QRect(
            _compute_aligned_top_left(
                anchor_rect,
                flyout_size,
                anchor_point=flipped_anchor,
                flyout_point=flipped_flyout,
                offset=offset,
                shadow_radius=shadow_radius,
            ),
            flyout_size,
        )
        # Same policy as place_surface_rect("bottom"): flip instead of sliding
        # over the anchor when the preferred side does not fit.
        if (
            preferred.bottom() > available.bottom()
            and flipped.top() >= available.top()
        ):
            preferred = flipped
        elif (
            preferred.top() < available.top()
            and flipped.bottom() <= available.bottom()
        ):
            preferred = flipped
    return clamp_surface_rect(preferred, available)


__all__ = ["AnimationAxis", "aligned_flyout_rect", "slide_start_delta"]
