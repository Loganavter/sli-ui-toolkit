"""A closing flyout must not lose its keyboard focus mid-fade.

Regression (measured live 2026-10-18, toolkit `FlyoutFadeController`):
``sync_container_visibility`` hides every direct child of the flyout while the
opacity is below 1.0, so only the pre-rendered snapshot shows. When the keyboard
focus sat on a row inside that container, hiding it made Qt fall back to the
window's **first tab-order widget** (the CSD menu trigger) for the rest of the
fade — the focus ring visibly hopped to the title bar and only returned when
``_finish_hide`` restored the anchor. The stale comment in ``_finish_hide``
blamed ``_unregister_nav_section``; the live stack (focusChanged) pointed here:

    on_fade_value_changed -> set_opacity -> sync_container_visibility -> child.setHidden(True)

Falsified by: removing the hold-focus handoff from ``sync_container_visibility``
— the focus leaves the flyout and lands on the window's first focusable.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout

FADE_MS = 60


def test_fade_out_keeps_focus_inside_the_closing_flyout(qtbot, qapp):
    host = QWidget()
    host.resize(400, 300)
    host.show()
    # The window's first tab-order widget — in the app this is the CSD menu
    # trigger, the widget the ring hopped to.
    early = QWidget(host)
    early.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    early.setGeometry(5, 5, 60, 24)
    early.show()
    anchor = QWidget(host)
    anchor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    anchor.setGeometry(90, 5, 60, 24)
    anchor.show()

    flyout = BaseFlyout(host)
    row = QWidget(flyout)
    row.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    row.setGeometry(6, 6, 80, 22)
    row.show()
    flyout.show_aligned(
        anchor, "bottom-left", "top-left", offset=4,
        animation="fade", animation_duration_ms=FADE_MS,
    )
    qtbot.wait(FADE_MS * 3)
    row.setFocus(Qt.FocusReason.OtherFocusReason)
    assert QApplication.focusWidget() is row, "precondition: the row holds the keyboard focus"

    # The hide fade's first step: children hidden, snapshot-only composite.
    flyout._fade.hide_fade_in_progress = True
    flyout._fade.opacity = 0.5
    flyout._fade.sync_container_visibility(flyout)

    focused = QApplication.focusWidget()
    assert focused is not None and (focused is flyout or flyout.isAncestorOf(focused)), (
        "focus left the closing flyout during the fade: "
        f"{focused!r} (the window's first element is {early!r})"
    )
    assert focused is not early, "focus hopped to the window's first tab-order widget"

    flyout._fade.hide_fade_in_progress = False
    for widget in (flyout, early, anchor, host):
        try:
            widget.deleteLater()
        except RuntimeError:
            pass
