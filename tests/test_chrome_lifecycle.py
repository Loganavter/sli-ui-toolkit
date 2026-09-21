"""Chrome lifecycle: idempotent install, per-window margin, attach dedup."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from sli_ui_toolkit import (
    FLUENT_DARK,
    FLUENT_LIGHT,
    CustomTitleBar,
    ThemeManager,
    WindowChrome,
    WindowChromeConfig,
    apply_frameless,
    remove_frameless,
)
from sli_ui_toolkit.ui.windows import frameless as frameless_pkg
from sli_ui_toolkit.ui.windows.frameless import _ResizeFilter


def _register_palettes(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("dark", qapp)


def test_apply_frameless_twice_keeps_single_patch(qapp):
    """A second apply must not double-wrap resize (4*band expansion)."""
    w = QWidget()
    w.resize(100, 100)
    apply_frameless(w, resizable=True, outer_band=6)
    patch = w._csd_outer_band_patch
    apply_frameless(w, resizable=True, outer_band=6)
    assert w._csd_outer_band_patch is patch
    w.resize(100, 100)
    assert (w.width(), w.height()) == (112, 112)
    w.deleteLater()


def test_remove_frameless_restores_geometry_setters(qapp):
    w = QWidget()
    w.resize(100, 100)
    apply_frameless(w, resizable=True, outer_band=6)
    w.resize(100, 100)
    assert w.width() == 112
    remove_frameless(w)
    assert getattr(w, "_csd_outer_band_patch", None) is None
    w.resize(100, 100)
    assert (w.width(), w.height()) == (100, 100)
    # Removing twice is harmless.
    remove_frameless(w)
    w.deleteLater()


def test_window_chrome_install_twice_returns_same(qapp):
    _register_palettes(qapp)
    dialog = QDialog()
    QVBoxLayout(dialog)
    first = WindowChrome.install(dialog, config=WindowChromeConfig(title="Hi"))
    second = WindowChrome.install(dialog, config=WindowChromeConfig(title="Other"))
    assert second is first
    bars = dialog.findChildren(CustomTitleBar)
    assert len(bars) == 1
    # Content-size semantics survived (single patch, not compounded).
    dialog.resize(200, 150)
    band = int(dialog.property("_csd_outer_band") or 0)
    assert (dialog.width(), dialog.height()) == (200 + 2 * band, 150 + 2 * band)
    dialog.deleteLater()


def test_resize_margin_is_per_window(qapp):
    """One window's margin must not retune another's (nor the default)."""
    _register_palettes(qapp)
    before = int(frameless_pkg.RESIZE_MARGIN)
    wide = QDialog()
    QVBoxLayout(wide)
    plain = QDialog()
    QVBoxLayout(plain)
    WindowChrome.install(
        wide, config=WindowChromeConfig(title="W", resizable=True, resize_margin=8)
    )
    WindowChrome.install(plain, config=WindowChromeConfig(title="P"))
    try:
        assert int(frameless_pkg.RESIZE_MARGIN) == before
        assert int(wide.property("_csd_resize_margin")) == 8
        assert plain.property("_csd_resize_margin") is None
        fa = wide.findChild(_ResizeFilter)
        fb = plain.findChild(_ResizeFilter)
        assert fa is not None and fb is not None
        assert fa._resize_margin == 8 + 8
        assert fb._resize_margin == before + before
    finally:
        wide.deleteLater()
        plain.deleteLater()


def test_attach_window_dedups_same_window(qapp):
    _register_palettes(qapp)
    window = QWidget()
    bar = CustomTitleBar(title="Test")
    try:
        bar.attach_window(window)
        bar.attach_window(window)
        bar.attach_window(window)
        assert bar._target_window is window
        # Exactly one wiring set — no stacked duplicate slots.
        assert len(bar._window_slots) == 3
    finally:
        window.deleteLater()
        bar.deleteLater()


def test_attach_window_moves_to_new_window(qapp):
    _register_palettes(qapp)
    first = QWidget()
    second = QWidget()
    bar = CustomTitleBar(title="Test")
    try:
        bar.attach_window(first)
        bar.attach_window(second)
        assert bar._target_window is second
        assert len(bar._window_slots) == 3
    finally:
        first.deleteLater()
        second.deleteLater()
        bar.deleteLater()


def test_attach_window_unpins_on_destroy(qapp):
    from PySide6.QtCore import QEvent

    _register_palettes(qapp)
    window = QWidget()
    bar = CustomTitleBar(title="Test")
    bar.attach_window(window)
    assert bar._target_window is window
    window.deleteLater()
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    assert bar._target_window is None
    assert bar._window_slots == []
    bar.deleteLater()
