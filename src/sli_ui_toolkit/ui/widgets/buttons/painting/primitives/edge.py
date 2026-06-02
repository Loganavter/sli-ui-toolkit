"""Примитив: рисование нижнего края (bottom edge line)."""

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import UnderlineConfig, draw_bottom_underline
from ..context import ButtonDrawContext


def draw_bottom_edge(ctx: ButtonDrawContext, tm: ThemeManager) -> None:
    """Рисует декоративную линию снизу если тема это поддерживает."""
    prefix = {"default": "button.toggle", "accent": "button.default", "delete": "button.delete",
              "primary": "button.primary", "surface": "button.dialog.default"}.get(ctx.variant, "button.toggle")
    edge_key = f"{prefix}.bottom.edge"

    if tm.try_get_color(edge_key) is None:
        return

    scale = max(1.0, ctx.widget.rect().height() / 32.0)
    normalized_radius = ctx.corner_radius / scale if scale > 0 else ctx.corner_radius

    draw_bottom_underline(
        ctx.painter,
        ctx.widget.rect(),
        tm,
        UnderlineConfig(
            alpha=40,
            thickness=1.0,
            vertical_offset=0.0,
            arc_radius=normalized_radius,
        ),
    )
