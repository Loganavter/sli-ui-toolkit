from __future__ import annotations

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
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.config import reset_toolkit_config


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
