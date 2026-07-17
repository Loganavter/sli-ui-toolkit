"""Background resolve — override base, bg_locked, hover_color, hover_compose."""

from __future__ import annotations

from PySide6.QtGui import QColor

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.buttons.layers.background import (
    BgResolveParams,
    resolve_button_background,
)
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.buttons.variants import get_variant


def _tm() -> ThemeManager:
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    return tm


def _default_variant():
    return get_variant("default")


def test_override_unlocked_stacks_hover_overlay():
    base = QColor(10, 20, 30, 255)
    layers, _border = resolve_button_background(
        BgResolveParams(
            states=frozenset({ButtonState.HOVERED}),
            variant=_default_variant(),
            override_bg=base,
            bg_locked=False,
        ),
        _tm(),
    )
    assert layers[0] == base
    assert len(layers) >= 2


def test_ghost_idle_has_no_opaque_base():
    """Ghost idle must stay transparent — do not fall back to toggle.normal."""
    tm = _tm()
    layers, _border = resolve_button_background(
        BgResolveParams(
            states=frozenset(),
            variant=get_variant("ghost"),
        ),
        tm,
    )
    assert layers == []

    hovered, _ = resolve_button_background(
        BgResolveParams(
            states=frozenset({ButtonState.HOVERED}),
            variant=get_variant("ghost"),
        ),
        tm,
    )
    assert hovered and hovered[0].alpha() > 0


def test_override_locked_is_base_only():
    base = QColor(10, 20, 30, 255)
    layers, border = resolve_button_background(
        BgResolveParams(
            states=frozenset({ButtonState.HOVERED, ButtonState.PRESSED}),
            variant=_default_variant(),
            override_bg=base,
            hover_color=QColor(255, 0, 0),
            bg_locked=True,
        ),
        _tm(),
    )
    assert layers == [base]
    assert border is None


def test_hover_color_replace_uses_custom_local():
    custom = QColor(1, 2, 3, 200)
    layers, _border = resolve_button_background(
        BgResolveParams(
            states=frozenset({ButtonState.HOVERED}),
            variant=_default_variant(),
            hover_color=custom,
            hover_compose="replace",
        ),
        _tm(),
    )
    assert custom in layers
    assert layers[-1] == custom


def test_stack_ambient_on_sibling_local_on_pointer():
    local = QColor(9, 8, 7, 180)
    sibling_layers, _ = resolve_button_background(
        BgResolveParams(
            states=frozenset({ButtonState.HOVERED}),
            variant=_default_variant(),
            hover_color=local,
            hover_compose="stack",
            group="card",
            region_id="left",
            hovered_region_id="right",
        ),
        _tm(),
    )
    assert local not in sibling_layers
    assert len(sibling_layers) >= 2  # base + ambient

    pointer_layers, _ = resolve_button_background(
        BgResolveParams(
            states=frozenset({ButtonState.HOVERED}),
            variant=_default_variant(),
            hover_color=local,
            hover_compose="stack",
            group="card",
            region_id="right",
            hovered_region_id="right",
        ),
        _tm(),
    )
    assert local in pointer_layers
    assert pointer_layers[-1] == local


def test_stack_without_group_behaves_like_replace():
    local = QColor(9, 8, 7, 180)
    layers, _ = resolve_button_background(
        BgResolveParams(
            states=frozenset({ButtonState.HOVERED}),
            variant=_default_variant(),
            hover_color=local,
            hover_compose="stack",
            group=None,
            region_id="_main",
            hovered_region_id="_main",
        ),
        _tm(),
    )
    # replace: single local hover, not ambient+local of the same color twice
    assert layers.count(local) == 1


def test_button_set_hover_color_writes_main_region(qtbot):
    from sli_ui_toolkit.widgets import Button

    _tm()
    button = Button(text="x", size=(80, 36))
    qtbot.addWidget(button)
    color = QColor(1, 2, 3, 90)
    button.set_hover_color(color)
    assert button.hover_color() == color
    assert button.region("_main").hover_color == color


def test_button_group_stack_resolve_via_iter_regions(qtbot):
    """Real Button: stack compose + pointer region gets local hover_color."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage, QPainter

    from sli_ui_toolkit.ui.widgets.buttons.layers.background import BackgroundLayer
    from sli_ui_toolkit.widgets import Button, ButtonRegion, HorizontalSplit

    _tm()
    local = QColor(5, 6, 7, 160)
    button = Button(
        regions=[
            ButtonRegion(
                id="left",
                text="L",
                group="card",
                hover_compose="stack",
                weight=1.0,
            ),
            ButtonRegion(
                id="right",
                text="R",
                group="card",
                hover_compose="stack",
                hover_color=local,
                weight=1.0,
            ),
        ],
        split=HorizontalSplit(),
        size=(120, 36),
    )
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)

    right_rect = button._controller.rects["right"]
    button._update_hover_region(QPointF(right_rect.center()))

    assert button._hovered_region == "right"
    assert ButtonState.HOVERED in button.region_states("left")
    assert ButtonState.HOVERED in button.region_states("right")

    layer = BackgroundLayer()
    img = QImage(button.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    ctx = button._make_context(painter)
    resolved = {
        scoped.region_id: layer._resolve(scoped, _tm())[0]
        for scoped in button.iter_regions(ctx)
    }
    painter.end()

    assert local not in resolved["left"]
    assert local in resolved["right"]
    assert resolved["right"][-1] == local
