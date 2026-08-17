from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

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
