"""Sizing math for ``SimpleOptionsFlyout`` -- split out of the single-file
``simple_options_flyout.py`` to keep the facade thin, mirroring
``base_flyout/geometry.py``'s split-by-concern shape.

``update_size`` takes the flyout widget explicitly (it reads live row
sizeHints, content-layout margins and installed row/option state, then
applies the computed size back onto the widget) rather than being fully
argument-pure like ``base_flyout/geometry.py`` -- the row list and layout
metrics are cheap to read off the widget but expensive to thread through a
long parameter list without losing readability.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.layout_settle import settle_layout


def update_size(
    flyout,
    match_width: int = 0,
    exact_match: bool = False,
    available_height: int | None = None,
) -> None:
    """Size the panel to the longest row, optionally at least ``match_width``.

    ``exact_match`` is kept for ``show_below`` call-site compatibility; when
    ``match_width`` is set, width is ``max(content, anchor)`` (no 180px floor).
    Row heights are taken from each installed row's ``sizeHint()``, so
    arbitrary widgets (variable heights) size the panel correctly.
    """
    del exact_match
    rows = flyout._rows
    spacing = flyout._rows_layout.spacing()
    outer_margins = flyout.content_layout.contentsMargins()
    margins_v = outer_margins.top() + outer_margins.bottom()
    margins_h = outer_margins.left() + outer_margins.right()

    if not rows:
        content_h = 50
    else:
        heights = [max(1, row.sizeHint().height()) for row in rows]
        visible = min(len(rows), flyout._max_visible_items)
        if available_height is not None:
            # Subtract flyout outer margins + inner row container margins.
            budget = available_height - 2 * flyout.MARGIN - margins_v
            if budget > 0:
                count = 0
                running = 0
                for h in heights:
                    add = h + (spacing if count else 0)
                    if running + add > budget:
                        break
                    running += add
                    count += 1
                visible = min(visible, max(1, count))
        content_h = sum(heights[:visible]) + spacing * max(0, visible - 1)

    container_h = content_h + margins_v

    # Natural content width lives on the widget (hosts reuse it to fit
    # anchors); geometry only reconciles it with the anchor match here.
    margins_h = outer_margins.left() + outer_margins.right()
    content_w = flyout.content_width_hint()

    if match_width > 0:
        target_container_width = max(1, match_width - (flyout.MARGIN * 2))
        width = max(content_w, target_container_width)
    else:
        width = max(1, content_w)

    # Refresh row hints BEFORE deriving the fixed sizes below (see the
    # ordering note after the setters).
    settle_layout(flyout._rows_container, *rows)

    flyout.container.setFixedSize(width, container_h)
    total_width = width + flyout.MARGIN * 2
    flyout.setFixedSize(total_width, container_h + flyout.MARGIN * 2)
    # Synchronous settle (qt-selfsizing T1): both fixed sizes above derive
    # from live row hints while QLayouts place the children — refresh the
    # hints and re-run each affected layout now so the first painted frame
    # already agrees (a posted re-run splits the growth into the wrong
    # child for one frame). Two ordering constraints (both probe-verified
    # in .agent/scratch/):
    # - rows refresh BEFORE the fixed sizes: the sizes propagate
    #   synchronously through the scroll area (container resize ->
    #   scroll resize -> updateScrollBars -> contents resize), and that
    #   cascade pins the contents to whatever minimum is current — with
    #   stale hints a shrink sticks wide for a frame (probe_flyout3).
    # - the rows level needs its own activate AFTER the ancestors
    #   resized its host: an outer activate alone misattributes growth
    #   through a nested fixed-size host (probe_cascade2: 60/60 splits
    #   instead of 20/100).
    settle_layout(flyout.container, flyout._scroll_area, flyout._rows_container)
    settle_layout(flyout, flyout.container)
    settle_layout(flyout._rows_container, *rows)
