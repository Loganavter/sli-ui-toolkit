from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from sli_ui_toolkit import __version__


def test_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    assert data["project"]["version"] == __version__
