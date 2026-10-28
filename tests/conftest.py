from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# The installed editable package may point at a sibling checkout; force the
# in-repo source onto the path so the suite tests the working tree.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.config import reset_toolkit_config
from sli_ui_toolkit.managers import UiFont, UiScale
from sli_ui_toolkit.ui.managers.theme_manager import ThemeManager


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print the counted result line even when pytest's own stats are quiet.

    ``pyproject.toml`` sets ``addopts = "-q"``; a gate command that also passes
    ``-q`` lands on verbosity -2, where pytest suppresses its final
    ``N passed in Xs`` line — the one line a CI log or a review needs to cite
    (observed: a fully green tier whose log ended at the ``Docs:`` line). Count
    the reporter's own stats here so the result is visible at any verbosity.
    """
    # pytest itself prints the stats line at verbosity >= -1 (terminal.py
    # TerminalReporter.summary_stats); only fill in where it stays silent.
    if getattr(terminalreporter, "verbosity", 0) >= -1:
        return
    stats = getattr(terminalreporter, "stats", {}) or {}
    parts = []
    for outcome in ("passed", "failed", "error", "skipped", "xfailed", "xpassed"):
        count = len(stats.get(outcome) or [])
        if count:
            parts.append(f"{count} {outcome}")
    try:
        # pytest's Duration carries the precise performance-counter span.
        elapsed = terminalreporter._session_start.elapsed().seconds
    except Exception:
        elapsed = 0.0
    terminalreporter.write_line(
        f"{', '.join(parts) or 'no tests ran'} in {elapsed:.2f}s"
    )


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_toolkit_config():
    """configure_toolkit state is process-wide; isolate every test from it."""
    reset_toolkit_config()
    yield
    reset_toolkit_config()


@pytest.fixture(autouse=True)
def _restore_applied_theme_state(qapp):
    """Restore the *applied* theme surface, not just the theme name.

    ``ThemeManager``'s applied state and Qt's application slots are
    process-wide, so a test that registers palettes / a QSS path and switches
    the theme hands all of it to whatever runs next: the palettes it
    registered, the QSS template built from them (and the application
    stylesheet that template produced), the application palette, the
    ``UiFont`` pin and the ``UiScale`` factor. Under a random order the next
    module then paints through someone else's ``QWidget { background-color }``
    rule, and the red names a widget that never touched a theme.

    Measured on ``tests/test_ui_font.py``: its two QSS-ordering tests leave a
    registered ``QWidget { background-color: @Window }`` template behind, so
    ``test_icon_list_surface``'s explicitly painted ``dialog.background``
    token loses to that stale application stylesheet. Same class as
    Improve-ImgSLI #693, where a module fixture restored only
    ``_current_theme`` and the font + palette slots stayed behind.

    Restores are conditional and never replay a signal: a test that does no
    theme work pays a few comparisons, and widgets from the finished test are
    already closed (this fixture is set up before ``_autouse_widget_cleanup``,
    so it tears down after it) when the application stylesheet changes.
    """
    tm = ThemeManager.get_instance()
    app = QApplication.instance()
    saved_theme = tm._current_theme
    saved_pending = tm._pending_theme
    saved_flush_scheduled = tm._theme_flush_scheduled
    saved_flush_app = tm._theme_flush_app
    saved_light = copy.deepcopy(tm._light_palette)
    saved_dark = copy.deepcopy(tm._dark_palette)
    saved_template = tm._qss_template
    saved_paths = list(tm._qss_paths)
    saved_stylesheet = app.styleSheet() if app is not None else ""
    saved_palette = QPalette(app.palette()) if app is not None else None
    saved_app_font = QFont(app.font()) if app is not None else None
    font_manager = UiFont.get_instance()
    saved_family = font_manager._family_override
    scale = UiScale.get_instance()
    saved_factor = scale.factor()
    yield
    tm._current_theme = saved_theme
    tm._pending_theme = saved_pending
    tm._theme_flush_scheduled = saved_flush_scheduled
    tm._theme_flush_app = saved_flush_app
    tm._light_palette = saved_light
    tm._dark_palette = saved_dark
    tm._qss_template = saved_template
    tm._qss_paths = saved_paths
    # Direct field writes, not set_family()/set_factor(): replaying either
    # would fan out font_changed/scale_changed into the previous test's dead
    # widgets, and a scale emit re-applies the (stale) QSS on the way out.
    font_manager._family_override = saved_family
    scale._factor = saved_factor
    if app is None:
        return
    if (app.styleSheet() or "") != saved_stylesheet:
        app.setStyleSheet(saved_stylesheet)
    if saved_palette is not None and app.palette() != saved_palette:
        app.setPalette(saved_palette)
    if saved_app_font is not None and app.font() != saved_app_font:
        app.setFont(saved_app_font)


@pytest.fixture(autouse=True)
def _autouse_widget_cleanup(request, qapp):
    """Autouse cleanup for leaked top-level windows (host KNOWN_BUGS class)."""
    initial = set(QApplication.topLevelWidgets())
    _example = "qtbot.addWidget(widget); request.addfinalizer(lambda: widget.close()); QApplication.processEvents()"
    _ = _example
    yield
    new_windows = [w for w in QApplication.topLevelWidgets() if w not in initial]
    for win in new_windows:
        try:
            if isinstance(win, QWidget):
                win.close()
                win.deleteLater()
        except RuntimeError:
            continue
    try:
        qapp.processEvents()
    except Exception:
        pass
    try:
        # Force the deferred deletes: a widget that installed ITSELF as an
        # application event filter (BaseFlyout's focus guard) only drops that
        # filter when its C++ object dies — a `deleteLater` the loop never
        # reaches leaves the guard installed for the next test, which then
        # swallows every FocusIn outside the dead flyout's subtree.
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    except Exception:
        pass
    try:
        request.getfixturevalue("qtbot")
        qapp.processEvents()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_navigation_manager_state(qapp):
    """Isolate NavigationManager across tests (public API, no _instance poke)."""
    from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

    mgr = NavigationManager.get_instance()
    for owner, _ in list(getattr(mgr, "_sections", [])):
        try:
            mgr.unregister(owner)
        except Exception:
            pass
    for attr in ("_flyout_side", "_extensions", "_group_extensions", "_extension_owners", "_skip_extension"):
        try:
            getattr(mgr, attr).clear()
        except Exception:
            pass
    try:
        mgr._last_input_keyboard = False
    except Exception:
        pass
    yield
    for owner, _ in list(getattr(mgr, "_sections", [])):
        try:
            mgr.unregister(owner)
        except Exception:
            pass
    for attr in ("_flyout_side", "_extensions", "_group_extensions", "_extension_owners", "_skip_extension"):
        try:
            getattr(mgr, attr).clear()
        except Exception:
            pass
    try:
        mgr._last_input_keyboard = False
    except Exception:
        pass
    try:
        qapp.processEvents()
    except Exception:
        pass


@pytest.fixture
def navigation_manager_reset(qapp):
    """Reset NavigationManager sections via public API (de-brittled)."""
    from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

    mgr = NavigationManager.get_instance()
    for owner, _ in list(mgr._sections):
        try:
            mgr.unregister(owner)
        except Exception:
            pass
    yield mgr
    for owner, _ in list(mgr._sections):
        try:
            mgr.unregister(owner)
        except Exception:
            pass
    try:
        qapp.processEvents()
    except Exception:
        pass
