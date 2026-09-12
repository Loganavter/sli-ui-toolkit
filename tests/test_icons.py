from __future__ import annotations

import pytest
from PySide6.QtGui import QIcon

from sli_ui_toolkit.icons import resolve_icon


@pytest.mark.parametrize(
    "name",
    ["add", "delete", "edit", "save", "check", "chevron-down", "settings"],
)
def test_bundled_icons_resolve(qapp, name):
    icon = resolve_icon(name)
    assert isinstance(icon, QIcon)
    assert not icon.isNull(), f"bundled icon {name!r} resolved to a null QIcon"


def test_resolve_none_returns_empty_icon(qapp):
    icon = resolve_icon(None)
    assert isinstance(icon, QIcon)
    assert icon.isNull()
