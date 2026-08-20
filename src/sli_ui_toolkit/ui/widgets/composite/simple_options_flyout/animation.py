"""Show-animation building for ``SimpleOptionsFlyout.show_below`` -- split out
of the single-file ``simple_options_flyout.py`` to keep the facade thin,
mirroring ``base_flyout/animation.py``'s split-by-concern shape (that module
owns the fade *pipeline*; this one owns the slide/fade *group construction*
for this widget's own ``show_below`` path).
"""

from __future__ import annotations

from PySide6.QtCore import QParallelAnimationGroup, QPoint, QPropertyAnimation, QVariantAnimation


def start_show_animation(
    flyout,
    want_slide: bool,
    want_fade: bool,
    start_pos: QPoint,
    end_pos: QPoint,
) -> None:
    """Build and start the slide/fade animation for ``flyout``, storing it on
    ``flyout._anim`` and wiring completion to ``flyout._on_animation_finished``.
    No-op if neither slide nor fade is wanted (caller already positioned the
    widget directly via ``move(start_pos)`` with ``start_pos == end_pos``)."""
    if want_slide and want_fade:
        group = QParallelAnimationGroup(flyout)
        anim_pos = QPropertyAnimation(flyout, b"pos", flyout)
        anim_pos.setDuration(flyout._move_duration_ms)
        anim_pos.setStartValue(start_pos)
        anim_pos.setEndValue(end_pos)
        anim_pos.setEasingCurve(flyout._move_easing)
        fade_anim = QVariantAnimation(flyout)
        fade_anim.setDuration(flyout._move_duration_ms)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(flyout._move_easing)
        fade_anim.valueChanged.connect(
            lambda value: flyout._fade.on_fade_value_changed(flyout, value)
        )
        group.addAnimation(anim_pos)
        group.addAnimation(fade_anim)
        group.finished.connect(flyout._on_animation_finished)
        flyout._anim = group
        group.start()
    elif want_slide:
        anim_pos = QPropertyAnimation(flyout, b"pos", flyout)
        anim_pos.setDuration(flyout._move_duration_ms)
        anim_pos.setStartValue(start_pos)
        anim_pos.setEndValue(end_pos)
        anim_pos.setEasingCurve(flyout._move_easing)
        anim_pos.finished.connect(flyout._on_animation_finished)
        flyout._anim = anim_pos
        anim_pos.start()
    elif want_fade:
        fade_anim = QVariantAnimation(flyout)
        fade_anim.setDuration(flyout._move_duration_ms)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(flyout._move_easing)
        fade_anim.valueChanged.connect(
            lambda value: flyout._fade.on_fade_value_changed(flyout, value)
        )
        fade_anim.finished.connect(flyout._on_animation_finished)
        flyout._anim = fade_anim
        fade_anim.start()


def on_animation_finished(flyout) -> None:
    if flyout._anim:
        anim_obj = flyout._anim
        flyout._anim = None
        anim_obj.deleteLater()
    # A completed fade-in must drop the snapshot so live content (hover
    # rows, re-populate) shows again instead of the stale cached frame.
    flyout._fade.clear()
