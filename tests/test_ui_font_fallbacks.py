"""Contract: the UI font resolver must keep the host's fallback families.

Regression this closes (measured 2026-10-21): the host installs its bundled
CJK fallback on ``QApplication.font()`` via ``QFont.setFamilies(["Source Sans
3", "Noto Sans SC"])``. ``UiFont.base_font()`` copied that font and then called
``QFont.setFamily()``, which *clears* the families list — every toolkit-painted
string with a CJK glyph fell back to the system font (Source Han / Malgun on
the measuring host), so help-figure captures were not reproducible and a
runner without a CJK font rendered tofu.

``_set_ui_family`` keeps the primary family first and preserves the chain; an
explicit ``family=`` override stays primary without dropping the fallback.
"""

from __future__ import annotations

from PySide6.QtGui import QFont

from sli_ui_toolkit.ui.managers import UiFont, ui_font
from sli_ui_toolkit.ui.managers.ui_font import rebase_family


def test_ui_font_keeps_the_host_fallback_chain(qapp):
    previous = QFont(qapp.font())
    host = QFont("Source Sans 3")
    host.setFamilies(["Source Sans 3", "Noto Sans SC"])
    qapp.setFont(host)
    ui = UiFont.get_instance()
    try:
        ui.set_family("Source Sans 3")

        assert ui_font().families()[:2] == ["Source Sans 3", "Noto Sans SC"]
        assert ui_font(pixel_size=13).families()[1] == "Noto Sans SC"
        assert rebase_family(QFont("Whatever")).families()[1] == "Noto Sans SC"

        overridden = ui_font(family="Some Custom Face")
        assert overridden.families()[0] == "Some Custom Face"
        assert "Noto Sans SC" in overridden.families()
    finally:
        ui.set_family(None)
        qapp.setFont(previous)


def test_explicit_family_without_host_fallbacks_is_a_single_family(qapp):
    previous = QFont(qapp.font())
    plain = QFont("Plain Face")
    plain.setFamilies(["Plain Face"])
    qapp.setFont(plain)
    ui = UiFont.get_instance()
    try:
        ui.set_family("Plain Face")
        assert ui_font().families() == ["Plain Face"]
    finally:
        ui.set_family(None)
        qapp.setFont(previous)
