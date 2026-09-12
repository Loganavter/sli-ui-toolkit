"""Golden tests for ThemeManager._scale_qss_px (HiDPI QSS rewriting)."""
from __future__ import annotations
import pytest
from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.ui.managers.theme_manager import _scale_qss_px
@pytest.fixture(autouse=True)
def _reset_scale():
    UiScale.get_instance().set_factor(1.0)
    yield
    UiScale.get_instance().set_factor(1.0)
def test_scale_factor_one_is_identity():
    UiScale.get_instance().set_factor(1.0)
    qss = "QWidget { margin: 4px; padding: 1px; border: 0.5px solid red; }"
    assert _scale_qss_px(qss) == qss
def test_hairlines_stay_unscaled_at_200pct():
    UiScale.get_instance().set_factor(2.0)
    qss = "border: 1px; margin: 1.5px; outline: 0px; offset: -1px; hair: 0.5px;"
    assert _scale_qss_px(qss) == qss
@pytest.mark.parametrize("factor,qss,expected", [(1.5, "padding: 4px;", "padding: 6px;"), (2.0, "margin: 10px;", "margin: 20px;"), (2.0, "radius: 10.5px;", "radius: 21px;"), (1.25, "spacing: 8px;", "spacing: 10px;"), (2.0, "inset: -4px;", "inset: -8px;")])
def test_scale_qss_px_parametrized(factor, qss, expected):
    UiScale.get_instance().set_factor(factor)
    assert _scale_qss_px(qss) == expected
def test_scale_mixed_qss_golden():
    UiScale.get_instance().set_factor(2.0)
    qss = """
    QWidget {
        margin: 4px;
        border: 1px solid #000;
        padding: 2px 10px;
        border-radius: 6px;
        offset: -2px;
    }
    """
    result = _scale_qss_px(qss)
    assert "8px" in result
    assert "border: 1px" in result
    assert "20px" in result
    assert "12px" in result
    assert "-4px" in result
    assert "4px" in result
def test_scale_preserves_non_px_units():
    UiScale.get_instance().set_factor(2.0)
    qss = "font-size: 12pt; width: 50%; height: 2em;"
    assert _scale_qss_px(qss) == qss
