"""The remaining painters read their own family's keys, not a neighbour's.

P3b of the colour-token migration: the calendar plate, a flyout's body labels,
the progress bar's label and trough, the painted text renderer, and (by
declaration) the group-box frame. Every site here used to read the dialog, the
button or the list family, so a host that restyled a dialog repainted them.

Each test gives the owned and the borrowed token *different* sentinel colours.
A pixel, a resolved palette colour or a laid-out format that answers the
borrowed token is exactly the borrow this change removes — the pre-migration
tree answers the opposite on every one of them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage, QPalette
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.gates.rules import (
    check_token_ownership,
    check_token_ownership_dynamic,
    check_token_ownership_unresolved,
    token_ownership_family,
)
from sli_ui_toolkit.ui.widgets.composite.calendar_widget.day_button import (
    CalendarDayButton,
)
from sli_ui_toolkit.ui.widgets.composite.calendar_widget.models import (
    build_default_view_model,
)
from sli_ui_toolkit.ui.widgets.text.engine.layout.builder import layout_document
from sli_ui_toolkit.ui.widgets.text.engine.markdown import parse_help_blocks
from sli_ui_toolkit.ui.widgets.text.engine.text_index import build_text_index
from sli_ui_toolkit.widgets import (
    BaseFlyout,
    CalendarWidget,
    CustomGroupWidget,
    ProgressBar,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"

_OWNED = "#ff00ff"
_BORROWED = "#00ff00"
_NEUTRAL = "#00ffff"


@pytest.fixture(autouse=True)
def _restore_palettes(qapp):
    """Leave the shipped palettes registered for the next module."""
    yield
    manager = ThemeManager.get_instance()
    manager.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    manager.set_theme("light", qapp, await_ripples=False)
    manager._flush_pending_theme()  # type: ignore[attr-defined]


def _register(qapp, theme: str, *, drop: tuple[str, ...] = (), **overrides: str):
    """Register the shipped palettes with sentinels on the *active* theme."""
    palettes = {}
    for name, source in (("light", FLUENT_LIGHT), ("dark", FLUENT_DARK)):
        palette = {key: value for key, value in source.items() if key not in drop}
        if name == theme:
            palette.update({key: QColor(value) for key, value in overrides.items()})
        palettes[name] = palette
    manager = ThemeManager.get_instance()
    manager.register_palettes(palettes["light"], palettes["dark"])
    manager.set_theme(theme, qapp, await_ripples=False)
    manager._flush_pending_theme()  # type: ignore[attr-defined]
    return manager


def _render(widget: QWidget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    return image


def _bytes(image: QImage) -> bytes:
    return bytes(image.constBits())


def _count(image: QImage, colour: str, tolerance: int = 40) -> int:
    target = QColor(colour)
    found = 0
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if (
                abs(pixel.red() - target.red()) <= tolerance
                and abs(pixel.green() - target.green()) <= tolerance
                and abs(pixel.blue() - target.blue()) <= tolerance
            ):
                found += 1
    return found


def _day_button(widget: CalendarWidget, date) -> CalendarDayButton:
    for button in widget.findChildren(CalendarDayButton):
        if button.date == date:
            return button
    raise AssertionError(f"no day cell for {date.toString('yyyy-MM-dd')}")


def _fragment_colours(markdown: str) -> set[str]:
    """Foreground colour of every laid-out text fragment, by hex name."""
    blocks = parse_help_blocks(markdown)
    result = layout_document(
        blocks,
        build_text_index(blocks),
        width=400.0,
        theme=ThemeManager.get_instance(),
    )
    colours: set[str] = set()
    for fragment in result.text_fragments:
        for format_range in fragment.layout.formats():
            colours.add(format_range.format.foreground().color().name())
    return colours


# ---------------------------------------------------------------- calendar


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_calendar_data_chip_follows_the_calendar_family(qapp, theme):
    """A data day's chip is the calendar's, not a checked focal button's."""
    manager = _register(
        qapp,
        theme,
        **{
            "calendar.background.data": _OWNED,
            "button.toggle.background.checked": _BORROWED,
        },
    )
    widget = CalendarWidget()
    widget.resize(320, 400)
    view_model = build_default_view_model(2026, 11)
    marked = view_model.days[10]
    marked.message_count = "3"
    marked.is_available = True
    widget.update_view(view_model)

    chip = _day_button(widget, marked.date)
    assert chip.getBackgroundColor() is not None
    assert chip.getBackgroundColor().name() == _OWNED

    manager.set_color("button.toggle.background.checked", QColor("#123456"))
    assert _day_button(widget, marked.date).getBackgroundColor().name() == _OWNED

    manager.set_color("calendar.background.data", QColor("#fedcba"))
    assert _day_button(widget, marked.date).getBackgroundColor().name() == "#fedcba"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_calendar_ink_reads_the_neutral_text_role(qapp, theme):
    """The plate and the ink are neutral: no `calendar.*` plate/ink family exists."""
    manager = _register(qapp, theme, **{"Text": _OWNED, "dialog.text": _BORROWED})
    widget = CalendarWidget()
    widget.resize(320, 400)

    image = _render(widget)
    assert _count(image, _OWNED) > 0, f"{theme}: the weekday ink is the neutral `Text` role"
    assert _count(image, _BORROWED) == 0, f"{theme}: the ink is not `dialog.text`"

    snapshot = _bytes(image)
    manager.set_color("dialog.text", QColor("#123456"))
    assert _bytes(_render(widget)) == snapshot
    manager.set_color("Text", QColor("#fedcba"))
    assert _bytes(_render(widget)) != snapshot


# ------------------------------------------------------------------ flyout


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_flyout_body_labels_read_the_flyout_ink(qapp, theme):
    """`add_section`/`add_row`/`add_radio_row` build a card body, not a dialog."""
    _register(qapp, theme, **{"flyout.text": _OWNED, "dialog.text": _BORROWED})
    host = QWidget()
    host.resize(420, 320)
    host.show()
    flyout = BaseFlyout(parent=host)

    section = flyout.add_section("Section")
    row = flyout.add_row("Row", ProgressBar())
    radio_label, _group, _radios = flyout.add_radio_row("Pick", [("a", 1), ("b", 2)])

    for label in (section, row, radio_label):
        ink = label.palette().color(QPalette.ColorRole.WindowText).name()
        assert ink == _OWNED, f"{theme}: flyout body label reads `flyout.text`"


# ---------------------------------------------------------------- progress


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_progress_label_reads_the_progress_ink(qapp, theme):
    manager = _register(
        qapp, theme, **{"progress.text": _OWNED, "dialog.text": _BORROWED}
    )
    bar = ProgressBar()
    bar.setText("50%")
    bar.resize(240, 24)

    image = _render(bar)
    assert _count(image, _OWNED) > 0, f"{theme}: the label is `progress.text`"
    assert _count(image, _BORROWED) == 0, f"{theme}: the label is not `dialog.text`"

    snapshot = _bytes(image)
    manager.set_color("dialog.text", QColor("#123456"))
    assert _bytes(_render(bar)) == snapshot
    manager.set_color("progress.text", QColor("#fedcba"))
    assert _bytes(_render(bar)) != snapshot


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_progress_trough_falls_back_to_the_neutral_hairline(qapp, theme):
    """A palette without the trough key gets the neutral border, not a dialog's."""
    _register(
        qapp,
        theme,
        drop=("progress.track.background",),
        **{"separator.color": _OWNED, "dialog.border": _BORROWED},
    )
    bar = ProgressBar()
    bar.resize(240, 24)

    image = _render(bar)
    assert _count(image, _OWNED) > 0, f"{theme}: the trough falls back to `separator.color`"
    assert _count(image, _BORROWED) == 0, f"{theme}: it does not fall back to `dialog.border`"


# ------------------------------------------------------------ text engine


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_text_engine_body_reads_the_label_ink(qapp, theme):
    _register(qapp, theme, **{"label.text": _OWNED, "dialog.text": _BORROWED})
    assert _fragment_colours("Body paragraph text here.\n") == {_OWNED}


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_text_engine_caption_reads_the_muted_label_ink(qapp, theme):
    """A figure caption is muted label text, not a list row's rating grey."""
    _register(
        qapp,
        theme,
        **{"label.text.muted": _NEUTRAL, "list_item.text.rating": _BORROWED},
    )
    markdown = ":::figure{side=center}\n![alt](missing.png)\nCaption line\n:::\n"
    assert _fragment_colours(markdown) == {_NEUTRAL}


# ------------------------------------------------------------------- group


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_group_frame_and_legend_stay_dialog_family(qapp, theme):
    """The fieldset frame is dialog chrome; the neutral hairline is not its edge.

    The file declares ``# token-family: dialog`` instead of moving the values:
    no palette family owns a group frame, and a host mirrors this paint routine
    to dock flush underneath a group.
    """
    manager = _register(
        qapp,
        theme,
        **{"dialog.border": _OWNED, "dialog.text": _BORROWED, "separator.color": _NEUTRAL},
    )
    group = CustomGroupWidget("Legend", caption="top")
    group.resize(240, 120)

    image = _render(group)
    assert _count(image, _OWNED, tolerance=24) > 0, f"{theme}: the frame is `dialog.border`"
    assert _count(image, _BORROWED, tolerance=24) > 0, f"{theme}: the legend is `dialog.text`"
    assert _count(image, _NEUTRAL, tolerance=24) == 0, f"{theme}: not the neutral hairline"

    snapshot = _bytes(image)
    manager.set_color("separator.color", QColor("#123456"))
    assert _bytes(_render(group)) == snapshot


def test_the_group_box_declares_the_family_it_serves():
    path = SRC / "sli_ui_toolkit/ui/widgets/atomic/custom_group_widget.py"
    source = path.read_text(encoding="utf-8")
    assert token_ownership_family(str(path), source) == "dialog"
    assert check_token_ownership(ast.parse(source), source, str(path)) == []


# --------------------------------------------------------------- underline


def test_the_underline_painter_declares_the_button_family():
    """Its default rule is the button family's; the caller may name another."""
    path = SRC / "sli_ui_toolkit/ui/widgets/helpers/underline_painter.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert token_ownership_family(str(path), source) == "button"
    assert check_token_ownership(tree, source, str(path)) == []
    assert check_token_ownership_dynamic(tree, source, str(path)) == []

    # The one finding left is the caller-supplied prefix: `token_prefix="input"`
    # is a genuinely runtime family, so a `# token-prefix:` declaration would lie.
    unresolved = check_token_ownership_unresolved(tree, source, str(path))
    assert len(unresolved) == 1
    assert "token_prefix" in unresolved[0].message
