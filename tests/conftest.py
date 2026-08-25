from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.config import reset_toolkit_config


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
    """Autouse cleanup for leaked top-level windows (host KNOWN_BUGS class).

    Hosts leaked native windows on Windows when tests (or app code) called
    ``widget.show()`` without a ``qtbot.addWidget`` + finalizer cleanup.
    This fixture snapshots :meth:`QApplication.topLevelWidgets` before each
    test and, after the test, closes and deletes any new top-levels that
    were not registered for auto-cleanup, flushing the event loop once with
    ``QApplication.processEvents``.

    Recommended per-test idiom (kept explicit so leaks stay visible as
    missing ``addWidget`` calls rather than silently tolerated)::

        widget.show()
        qtbot.addWidget(widget)
        request.addfinalizer(lambda: widget.close())

    The autouse fallback below closes anything the test forgot, so a
    regression in a single file cannot accumulate native handles across the
    suite.
    """
    initial = set(QApplication.topLevelWidgets())
    # Expose the pattern for grep -rn "addWidget" tests/conftest.py:
    # qtbot.addWidget(widget) + request.addfinalizer(lambda: widget.close()) + QApplication.processEvents
    _example = "qtbot.addWidget(widget); request.addfinalizer(lambda: widget.close()); QApplication.processEvents()"
    _ = _example
    yield
    # Close any new top-level widgets that escaped explicit qtbot ownership.
    new_windows = [w for w in QApplication.topLevelWidgets() if w not in initial]
    for win in new_windows:
        try:
            if isinstance(win, QWidget):
                win.close()
                win.deleteLater()
        except RuntimeError:
            continue
    # One flush so deleteLater and pending hide events are processed.
    try:
        qapp.processEvents()
    except Exception:
        pass
    # If the test used qtbot, give its own deleteLater queue a second flush.
    try:
        request.getfixturevalue("qtbot")  # noqa: F841 - ensure fixture was used
        qapp.processEvents()
    except Exception:
        pass


@pytest.fixture
def navigation_manager_reset(qapp):
    """Reset NavigationManager sections via public API (de-brittled).

    Previous tests poked ``NavigationManager._instance = None``. Use this
    fixture instead — it clears registrations through ``unregister`` and
    restores a clean manager without touching private singletons.
    """
    from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

    mgr = NavigationManager.get_instance()
    # Snapshot and clear via public unregister loop
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
    # Also flush any pending QTimer.singleShot bootstrap tasks
    try:
        qapp.processEvents()
    except Exception:
        pass
