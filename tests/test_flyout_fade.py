"""Fade show/hide animations on BaseFlyout (``animation="fade"`` / ``"slide-fade"``).

In-window flyouts are plain child widgets (not toplevels), so ``windowOpacity()``
would not work. Fade is implemented without a ``QGraphicsEffect`` either (a
graphics effect on the shell conflicts with the container's ``RoundedClipEffect``
and the shell's own ``QPainter(self)`` paintEvent on composited windows):
a one-shot ``grab()`` snapshot captured outside ``paintEvent`` is composited
with the animated opacity.
"""

from __future__ import annotations

from PySide6.QtCore import QParallelAnimationGroup, QPropertyAnimation, Qt, QVariantAnimation
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout

FADE_MS = 60


def _make_host() -> tuple[QWidget, QWidget]:
    host = QWidget()
    host.resize(400, 300)
    host.show()
    anchor = QWidget(host)
    anchor.setGeometry(10, 10, 60, 40)
    anchor.show()
    return host, anchor


def _teardown(*widgets: QWidget) -> None:
    for widget in widgets:
        try:
            widget.deleteLater()
        except RuntimeError:
            pass


def test_fade_in_animates_fade_opacity(qtbot, qapp):
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        assert flyout.isVisible()
        # No graphics effect involved — fade is driven by the opacity property.
        assert flyout.graphicsEffect() is None
        assert flyout._fade.opacity == 0.0

        qtbot.wait(FADE_MS * 3)
        assert flyout._fade.opacity == 1.0  # fully settled
        assert flyout._show_animation is None
        assert not flyout.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert flyout.isVisible()
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_slide_fade_runs_both_animations(qtbot, qapp):
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="slide-fade", animation_duration_ms=FADE_MS,
        )
        assert flyout.graphicsEffect() is None
        assert isinstance(flyout._show_animation, QParallelAnimationGroup)
        assert flyout._fade.opacity == 0.0
        start_pos = flyout.pos()

        qtbot.wait(FADE_MS * 3)
        assert flyout.pos() != start_pos  # the slide actually ran
        assert flyout._show_animation is None
        assert flyout._fade.opacity == 1.0
        assert flyout.isVisible()
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_plain_slide_creates_no_fade(qtbot, qapp):
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="slide", animation_duration_ms=FADE_MS,
        )
        assert flyout.graphicsEffect() is None
        assert flyout._fade.opacity == 1.0  # never fades
        qtbot.wait(FADE_MS * 3)
        assert flyout._fade.opacity == 1.0
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_hide_fades_out_when_shown_with_fade(qtbot, qapp):
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        qtbot.wait(FADE_MS * 3)
        assert flyout._fade.opacity == 1.0  # fade-in fully settled

        flyout.hide()
        # Still on screen mid-fade-out, with the opacity already animating down.
        assert flyout.isVisible()
        assert flyout._fade.hide_fade_in_progress
        assert flyout._fade.hide_animation is not None

        qtbot.wait(FADE_MS * 3)
        assert not flyout.isVisible()
        assert not flyout._fade.hide_fade_in_progress
        assert flyout._fade.opacity == 1.0  # reset for the next show
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_second_show_after_fade_out_keeps_content_size(qtbot, qapp):
    """Regression: after a fade-out, the direct children (container) stayed
    hidden (the hide fade reset opacity to 1.0 without restoring them), so
    the next show_aligned's cancel() → set_opacity(1.0) early-returned and
    adjustSize() collapsed the flyout to shadow-margin size (16x16) — an
    empty flyout. The children must be restored when the hide fade finishes.
    """
    host, anchor = _make_host()
    try:
        from PySide6.QtWidgets import QLabel

        flyout = BaseFlyout(host)
        flyout.add_widget(QLabel("content", flyout.container))
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        qtbot.wait(FADE_MS * 3)
        first_size = flyout.size()
        assert first_size.width() > 16  # content contributes to the size

        flyout.hide()
        qtbot.wait(FADE_MS * 3)
        assert not flyout.isVisible()
        # The fade-out must not leave the content hidden for the next show.
        for child in flyout.findChildren(QWidget):
            if child.objectName() == "FlyoutContainer":
                assert not child.isHidden()

        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        qtbot.wait(FADE_MS * 3)
        assert flyout.size() == first_size
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_hide_is_instant_when_shown_without_fade(qtbot, qapp):
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.show_aligned(anchor, "bottom-left", "top-left", offset=4)
        assert flyout.isVisible()

        flyout.hide()
        assert not flyout.isVisible()  # no fade-out for animation="none"
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_reposition_preserves_fade_out(qtbot, qapp):
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host, pinned=True)
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        qtbot.wait(FADE_MS * 3)

        anchor.setGeometry(10, 120, 60, 40)
        flyout.reposition()  # forces animation="none" internally
        assert flyout._fade.fade_out_enabled  # close animation survives reposition

        flyout.hide()
        assert flyout.isVisible()  # fading out, not vanished
        qtbot.wait(FADE_MS * 3)
        assert not flyout.isVisible()
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_fade_out_duration_uses_config(qtbot, qapp):
    configure_toolkit(timings=FlyoutTimingConfig(flyout_fade_out_duration_ms=FADE_MS))
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        qtbot.wait(FADE_MS * 3)

        flyout.hide()
        hide_anim = flyout._fade.hide_animation
        assert hide_anim is not None
        assert hide_anim.duration() == FADE_MS
        qtbot.wait(FADE_MS * 3)
        assert not flyout.isVisible()
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_global_default_flyout_animation_from_config(qtbot, qapp):
    """A host can fade every default flyout from one config value: omitted
    ``animation`` resolves to ``FlyoutTimingConfig.default_flyout_animation``."""
    configure_toolkit(
        timings=FlyoutTimingConfig(
            default_flyout_animation="fade",
            flyout_fade_out_duration_ms=FADE_MS,
        )
    )
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.show_aligned(  # animation omitted -> config default "fade"
            anchor, "bottom-left", "top-left", offset=4,
            animation_duration_ms=FADE_MS,
        )
        assert flyout._fade.opacity == 0.0
        assert flyout._fade.fade_out_enabled
        qtbot.wait(FADE_MS * 3)
        assert flyout._fade.opacity == 1.0

        flyout.hide()  # fade-out also applies via the config default
        assert flyout.isVisible()
        qtbot.wait(FADE_MS * 3)
        assert not flyout.isVisible()
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_explicit_none_ignores_config_default(qtbot, qapp):
    configure_toolkit(timings=FlyoutTimingConfig(default_flyout_animation="fade"))
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="none",  # explicit beats the config default
        )
        assert flyout._fade.opacity == 1.0
        assert not flyout._fade.fade_out_enabled
        flyout.hide()
        assert not flyout.isVisible()
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_reposition_of_visible_default_flyout_does_not_reanimate(qtbot, qapp):
    configure_toolkit(
        timings=FlyoutTimingConfig(
            default_flyout_animation="fade",
            flyout_fade_out_duration_ms=FADE_MS,
        )
    )
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation_duration_ms=FADE_MS,
        )
        qtbot.wait(FADE_MS * 3)
        settled_pos = flyout.pos()
        assert flyout._fade.opacity == 1.0

        # Reposition while visible: stay put (no re-animation), close fade kept.
        anchor.setGeometry(10, 120, 60, 40)
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation_duration_ms=FADE_MS,
        )
        assert flyout._fade.opacity == 1.0  # no blink
        assert flyout.pos() != settled_pos  # still re-anchored
        assert flyout._fade.fade_out_enabled  # close animation preserved

        flyout.hide()
        assert flyout.isVisible()  # still fades out on close
        qtbot.wait(FADE_MS * 3)
        assert not flyout.isVisible()
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_context_menu_animation_resolves_global_default(qapp):
    """Context-menu helpers keep their historical 'slide' unless a global
    default is configured (then it applies); explicit values win."""
    from sli_ui_toolkit.ui.widgets.composite.context_menu.builders import (
        _context_menu_animation,
    )

    configure_toolkit(timings=FlyoutTimingConfig())
    assert _context_menu_animation(None) == "slide"  # historical fallback
    assert _context_menu_animation("none") == "none"  # explicit wins
    assert _context_menu_animation("fade") == "fade"

    configure_toolkit(timings=FlyoutTimingConfig(default_flyout_animation="fade"))
    assert _context_menu_animation(None) == "fade"  # global default applies
    assert _context_menu_animation("slide") == "slide"  # explicit still wins


def test_popup_context_menu_fades_in_and_out(qtbot, qapp):
    """Cursor-positioned popup context menus (popup_at) follow the global
    default: fade in at the cursor, and aboutToHide fires only after the
    fade-out actually hides the menu (deleteLater timing)."""
    from PySide6.QtCore import QPoint

    from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import ContextMenu
    from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
        ContextMenuAction,
    )

    configure_toolkit(
        timings=FlyoutTimingConfig(
            flyout_animation_duration_ms=FADE_MS,
            flyout_fade_out_duration_ms=FADE_MS,
            default_flyout_animation="fade",
        )
    )

    host = QWidget()
    host.resize(400, 300)
    host.show()
    menu = ContextMenu(
        host,
        entries=[ContextMenuAction(action_id="a", text="A")],
        surface="popup",
    )
    try:
        menu.popup_at(QPoint(120, 100))  # no animation arg -> global "fade"
        assert menu._fade.fade_out_enabled
        assert menu._fade.opacity == 0.0
        qtbot.wait(FADE_MS * 3)
        assert menu._fade.opacity == 1.0

        hide_signals: list[bool] = []
        menu.aboutToHide.connect(lambda: hide_signals.append(True))
        menu.hide()
        assert menu.isVisible()  # fading out, not yet hidden
        assert hide_signals == []  # aboutToHide deferred until hidden
        qtbot.wait(FADE_MS * 3)
        assert hide_signals == [True]  # emitted after the fade-out
    finally:
        host.deleteLater()


def test_construction_hide_via_host_overlay_before_fade_state_init(qtbot, qapp):
    """A host overlay may call ``hide()`` during ``BaseFlyout.__init__`` (e.g.
    while re-parenting an invisible widget). ``hide()`` reads the fade state,
    so that state must exist before ``attach_in_window_widget`` runs — this
    regressed as ``AttributeError: no attribute '_hide_fade_in_progress'``."""
    calls = []

    class _HostOverlay:
        def __init__(self, host):
            self._host = host

        def attach(self, widget):
            calls.append("attach")
            if not widget.isVisible():
                widget.hide()  # the app-overlay pattern that regressed

        def host(self):
            return self._host

    host = QWidget()
    configure_toolkit(overlay_resolver=lambda anchor: _HostOverlay(host))

    try:
        flyout = BaseFlyout(host)
        assert flyout._fade.hide_fade_in_progress is False
        assert flyout._fade.fade_out_enabled is False
        assert calls == ["attach"]
        flyout.deleteLater()
        host.deleteLater()
    finally:
        pass


def test_simple_options_show_below_respects_global_default(qtbot, qapp):
    """SimpleOptionsFlyout.show_below uses its own show path; it must respect
    the process-wide default_flyout_animation too (here: pure fade)."""
    configure_toolkit(
        timings=FlyoutTimingConfig(
            flyout_animation_duration_ms=FADE_MS,
            default_flyout_animation="fade",
            flyout_fade_out_duration_ms=FADE_MS,
        )
    )
    from sli_ui_toolkit.widgets import SimpleOptionsFlyout

    host, anchor = _make_host()
    try:
        flyout = SimpleOptionsFlyout(parent_widget=host)
        flyout.populate(["A", "B"], 0)
        flyout.show_below(anchor)
        assert flyout._fade.fade_out_enabled
        assert flyout._fade.opacity == 0.0
        # Pure fade -> the active animation is the opacity one, not a pos slide.
        assert isinstance(flyout._anim, QVariantAnimation)

        qtbot.wait(FADE_MS * 3)
        assert flyout._fade.opacity == 1.0
        assert flyout._fade.cache is None  # snapshot dropped after fade-in

        flyout.hide()
        assert flyout.isVisible()  # fades out
        qtbot.wait(FADE_MS * 3)
        assert not flyout.isVisible()
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_simple_options_show_below_per_instance_slide(qtbot, qapp):
    """Per-instance animation='slide' overrides the global default on
    show_below (pos slide animation, no fade)."""
    configure_toolkit(timings=FlyoutTimingConfig(default_flyout_animation="none"))
    from sli_ui_toolkit.widgets import SimpleOptionsFlyout

    host, anchor = _make_host()
    try:
        flyout = SimpleOptionsFlyout(parent_widget=host, animation="slide")
        flyout.populate(["A", "B"], 0)
        flyout.show_below(anchor)
        assert isinstance(flyout._anim, QPropertyAnimation)
        assert flyout._fade.opacity == 1.0  # no fade
        qtbot.wait(FADE_MS * 3)
        assert flyout._fade.opacity == 1.0
        flyout.hide()
        assert not flyout.isVisible()  # slide mode -> instant hide
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_icon_action_flyout_per_instance_animation(qtbot, qapp):
    """IconActionFlyout(animation='fade') is passed through show_above and
    overrides the global default."""
    configure_toolkit(timings=FlyoutTimingConfig(default_flyout_animation="none"))
    from sli_ui_toolkit.widgets import IconAction, IconActionFlyout

    host, anchor = _make_host()
    try:
        flyout = IconActionFlyout(host, animation="fade")
        flyout.set_actions([IconAction("a", "copy", "Copy")])
        flyout.show_above(anchor)
        assert flyout._fade.opacity == 0.0
        assert flyout._fade.fade_out_enabled
        qtbot.wait(FADE_MS * 3)
        assert flyout._fade.opacity == 1.0
        flyout.hide()
        assert flyout.isVisible()
        qtbot.wait(FADE_MS * 3)
        assert not flyout.isVisible()
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_fade_hides_live_container_until_opaque(qtbot, qapp):
    """While fading, only the snapshot must be painted — not the live content.

    Regression: paintEvent composites the grab() snapshot at the animated
    opacity, but Qt still painted the container (all content widgets) on top
    at full opacity — the panel/shadow faded while the content popped in
    binarily. The container is hidden for the fade duration and restored at
    1.0.
    """
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.add_section("Fade content")
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        assert flyout._fade.opacity == 0.0
        # Mid-fade: the live container must not paint over the snapshot.
        assert not flyout.container.isVisible(), (
            "live container painted at full opacity during the fade — "
            "content appears binarily while the panel/shadow fades"
        )

        qtbot.wait(FADE_MS * 3)
        assert flyout._fade.opacity == 1.0
        assert flyout.container.isVisible(), (
            "container must be restored once the flyout is fully opaque"
        )
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_fade_out_hides_container_too(qtbot, qapp):
    """The hide-fade must also drop the live container under the snapshot."""
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.add_section("Fade content")
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        qtbot.wait(FADE_MS * 3)
        assert flyout.container.isVisible()

        flyout.hide()  # fade-out path (fade_out_enabled)
        assert flyout._fade.hide_fade_in_progress or not flyout.isVisible()
        if flyout._fade.hide_fade_in_progress:
            qtbot.wait(40)  # let the fade-out drop opacity below 1.0
            assert not flyout.container.isVisible(), (
                "live container painted at full opacity during the hide-fade"
            )
        qtbot.wait(FADE_MS * 3)
        assert not flyout.isVisible()
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_fade_hides_sibling_widgets_outside_container(qtbot, qapp):
    """Sibling children (e.g. a glass-panel display) must not stay opaque.

    Regression: the fade sync only hid ``container``, but flyouts can have
    direct children beside it (GlassHUD's ``_display`` panel widget) — those
    painted at full opacity over the fading snapshot, so the panel (its
    corners included) popped in binarily while everything else faded.
    """
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.add_section("Fade content")
        sibling = QWidget(flyout)
        sibling.setObjectName("SiblingPanel")
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        assert flyout._fade.opacity == 0.0
        assert sibling.isHidden(), (
            "sibling widget painted at full opacity during the fade — "
            "its corners pop in binarily while the snapshot fades"
        )
        assert flyout.container.isHidden()

        qtbot.wait(FADE_MS * 3)
        assert flyout._fade.opacity == 1.0
        assert not sibling.isHidden()
        assert not flyout.container.isHidden()
        _teardown(flyout, anchor, host)
    finally:
        pass


def test_hide_clears_stale_show_animation_reference(qtbot, qapp):
    """hide() during the show animation must clear the flyout's
    ``_show_animation`` reference — the animation was stopped and
    ``deleteLater``-ed, and a lingering reference would point at a deleted
    C++ object and crash the next hide (slider-hint style rapid
    show/hide/reposition cycles)."""
    host, anchor = _make_host()
    try:
        flyout = BaseFlyout(host)
        flyout.show_aligned(
            anchor, "bottom-left", "top-left", offset=4,
            animation="fade", animation_duration_ms=FADE_MS,
        )
        assert flyout._show_animation is not None
        # hide mid-animation: stops + schedules deletion of the show animation
        flyout.hide()
        qtbot.wait(FADE_MS * 3)  # let deleteLater + the hide fade settle
        assert flyout._show_animation is None
        # a reposition-style cancel + hide must not touch a deleted animation
        flyout._fade.cancel(flyout)
        flyout.hide()
        _teardown(flyout, anchor, host)
    finally:
        pass
