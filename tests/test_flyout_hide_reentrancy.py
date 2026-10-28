"""A flyout must finish hiding once, even when a focus handler re-hides it.

Red-before (Improve-ImgSLI owner, 2026-10-28 — picking another interpolation in
the loupe's list froze the whole app, no exception, nothing in the log):

``BaseFlyout._restore_focus_policies()`` calls ``setFocus()`` on the anchor, and
Qt delivers the resulting FocusOut/FocusIn **synchronously**. The host's focus
handler then asks for ``hide()`` again — while the first ``_finish_hide`` is
still on the stack. The pair recurses::

    hide -> _finish_hide -> _restore_focus_policies -> setFocus
      -> FocusOut -> host event filter -> hide -> _finish_hide -> ...

The dive ends in a RecursionError that the host swallowed, so it simply repeated
forever: the GUI thread never got back to the event loop (a ``faulthandler`` dump
of the frozen process showed the 10-frame cycle repeated down the stack).

The guard under test: ``_finish_hide`` is a no-op while a previous pass is
mid-flight (the widget is already being hidden and focus is already being
restored).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import BaseFlyout


def _shown_host(qtbot) -> QWidget:
    host = QWidget()
    layout = QVBoxLayout(host)
    anchor = QWidget()
    anchor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    layout.addWidget(anchor)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    return host


def test_finish_hide_is_not_reentrant_through_the_focus_restore(qapp, qtbot):
    host = _shown_host(qtbot)
    flyout = BaseFlyout(host)

    restores: list[int] = []
    original = flyout._restore_focus_policies

    def _restore_then_rehide() -> None:
        # Stand-in for the host handler that reacts to the FocusOut this
        # restore produces by closing the same flyout again.
        restores.append(1)
        original()
        flyout.hide()
        if len(restores) > 50:  # catastrophic recursion: stop the test, not CI
            raise AssertionError(
                f"_restore_focus_policies re-entered {len(restores)} times — a "
                "hide() from inside the focus restore is recursing again"
            )

    flyout._restore_focus_policies = _restore_then_rehide  # type: ignore[method-assign]

    flyout.hide()

    assert len(restores) == 1, (
        f"_restore_focus_policies ran {len(restores)} times for one hide(): the "
        "re-hide from inside the focus restore recursed instead of being ignored "
        "(the 2026-10-28 loupe freeze)"
    )
    assert getattr(flyout, "_finishing_hide", False) is False, (
        "the re-entrancy latch survived the call — every later hide() of this "
        "flyout would be a silent no-op"
    )


def test_finish_hide_latch_clears_when_the_body_raises(qapp, qtbot):
    host = _shown_host(qtbot)
    flyout = BaseFlyout(host)

    def _boom() -> None:
        raise RuntimeError("finish body exploded")

    flyout._finish_hide_body = _boom  # type: ignore[method-assign]

    try:
        flyout.hide()
    except RuntimeError:
        pass

    assert getattr(flyout, "_finishing_hide", False) is False, (
        "a raising body left the latch set — the flyout could never be hidden "
        "again, and a stuck panel is the same class of bug as the freeze"
    )
