"""Falsification tests for the subtree-scoped translator + declarative keys.

Every assertion here targets behaviour added by ``bind_translator`` /
``install_translator`` and the ``text_key``/``badge_key``/``tooltip_key``
declarative fields. Against the pre-change base these fail with
``ImportError`` (no such symbols) or, for the rows case, because
``translatable_text`` never touches a rows button.
"""

from __future__ import annotations

import pytest

from sli_ui_toolkit import (
    TranslationManager,
    emit_language_changed,
)
from sli_ui_toolkit.i18n import (
    ToolkitTranslationEvents,
    bind_translator,
    install_translator,
    translator_for,
)
from sli_ui_toolkit.widgets import (
    Button,
    ButtonRow,
    ContextMenu,
    ContextMenuAction,
    Label,
    Text,
)


@pytest.fixture(autouse=True)
def _restore_i18n_state(qapp):
    """Restore the global translator provider/backend after every test."""
    mgr = TranslationManager()
    saved = (
        mgr._custom_translator,
        mgr._language_provider,
        mgr._current_lang,
        mgr._events,
    )
    yield
    (
        mgr._custom_translator,
        mgr._language_provider,
        mgr._current_lang,
        mgr._events,
    ) = saved


def _lang_prefix(key: str, lang: str) -> str:
    return f"{lang}:{key}"


# ---------------------------------------------------------------------------
# Button rows (the trap: painter reads rows, not setText)
# ---------------------------------------------------------------------------


def test_button_rows_retranslate_updates_painted_text(qapp, qtbot):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")

    root = QWidget()
    qtbot.addWidget(root)
    btn = Button(
        rows=[ButtonRow(text="English literal", text_key="row.key")],
        size=(160, 40),
        parent=root,
    )
    install_translator(root, _lang_prefix)

    def _render() -> QImage:
        btn.resize(160, 40)
        btn.show()
        image = QImage(btn.size(), QImage.Format.Format_ARGB32)
        image.fill(0)
        btn.render(image, QPoint(0, 0))
        return image

    emit_language_changed("ru")
    assert btn._rows[0].text == "ru:row.key"
    before = bytes(_render().constBits())

    emit_language_changed("de")
    assert btn._rows[0].text == "de:row.key"
    after = bytes(_render().constBits())
    # The rows actually repaint (base: translatable_text no-ops on a rows
    # button, so the pixels would be identical).
    assert before != after


def test_badge_key_retranslates_badge(qapp, qtbot):
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    btn = Button(icon="play", badge_key="badge.count", parent=root)
    install_translator(root, _lang_prefix)

    emit_language_changed("ru")
    assert btn._badge == "ru:badge.count"


def test_button_text_key_retranslates_main_text(qapp, qtbot):
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    btn = Button(text="Literal", text_key="main.key", parent=root)
    install_translator(root, _lang_prefix)

    emit_language_changed("ru")
    assert btn._text == "ru:main.key"


# ---------------------------------------------------------------------------
# Label / Text
# ---------------------------------------------------------------------------


def test_label_text_key_retranslates(qapp, qtbot):
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    label = Label("Literal", text_key="label.key", parent=root)
    install_translator(root, _lang_prefix)

    emit_language_changed("ru")
    assert label.text() == "ru:label.key"


def test_text_text_key_retranslates(qapp, qtbot):
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    text = Text("Literal", text_key="text.key", parent=root)
    install_translator(root, _lang_prefix)

    emit_language_changed("ru")
    assert text.text() == "ru:text.key"


# ---------------------------------------------------------------------------
# Context menu
# ---------------------------------------------------------------------------


def test_context_menu_action_text_key_retranslates_row(qapp, qtbot):
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    menu = ContextMenu(
        root,
        entries=[
            ContextMenuAction(action_id="open", text="Open literal", text_key="menu.open"),
        ],
    )
    qtbot.addWidget(menu)
    bind_translator(menu, _lang_prefix)

    emit_language_changed("ru")
    row = menu.row_for_action("open")
    assert row is not None
    assert row._text == "ru:menu.open"


def test_context_menu_tooltip_key_retranslates_tooltip(qapp, qtbot):
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    menu = ContextMenu(
        root,
        entries=[
            ContextMenuAction(
                action_id="open",
                text="Open",
                tooltip="Open the file",
                tooltip_key="menu.open.tip",
            ),
        ],
    )
    qtbot.addWidget(menu)
    bind_translator(menu, _lang_prefix)

    emit_language_changed("ru")
    row = menu.row_for_action("open")
    assert row is not None
    assert row.toolTip() == "ru:menu.open.tip"


# ---------------------------------------------------------------------------
# install_translator coverage of future descendants
# ---------------------------------------------------------------------------


def test_child_added_after_install_is_covered(qapp, qtbot):
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    install_translator(root, _lang_prefix)
    emit_language_changed("ru")

    # Created unparented, so the ctor cannot see root's translator yet and the
    # key is shown verbatim.
    btn = Button(text_key="late.key")
    assert btn._text == "late.key"

    btn.setParent(root)
    qtbot.waitUntil(lambda: btn._text == "ru:late.key", timeout=2000)
    assert btn._text == "ru:late.key"


def test_multiple_children_share_one_subscription(qapp, qtbot):
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    install_translator(root, _lang_prefix)
    a = Label("x", text_key="a.key", parent=root)
    b = Label("y", text_key="b.key", parent=root)

    emit_language_changed("ru")
    # Children created *with* a parent are registered on the next loop turn
    # (ChildAdded fires mid-construction); the shared fan-out then drives both.
    qtbot.waitUntil(lambda: a.text() == "ru:a.key" and b.text() == "ru:b.key", timeout=2000)
    assert (a.text(), b.text()) == ("ru:a.key", "ru:b.key")


# ---------------------------------------------------------------------------
# Missing translator => key is visible (never silent English)
# ---------------------------------------------------------------------------


def test_text_key_without_translator_shows_key(qapp, qtbot):
    # No bundles configured and no custom backend: tr() returns the key.
    label = Label("English literal", text_key="greeting.hello")
    qtbot.addWidget(label)
    assert label.text() == "greeting.hello"

    btn = Button(rows=[ButtonRow(text="English literal", text_key="row.missing")])
    qtbot.addWidget(btn)
    assert btn._rows[0].text == "row.missing"

    text = Text("English literal", text_key="text.missing")
    qtbot.addWidget(text)
    assert text.text() == "text.missing"


def test_translator_for_falls_back_to_global_tr(qapp, qtbot):
    from PySide6.QtWidgets import QWidget

    widget = QWidget()
    qtbot.addWidget(widget)
    assert translator_for(widget)("some.missing.key", "ru") == "some.missing.key"


def test_translator_for_walks_to_bound_ancestor(qapp, qtbot):
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    child = QWidget(root)
    install_translator(root, _lang_prefix)

    assert translator_for(child) is _lang_prefix


# ---------------------------------------------------------------------------
# Per-subtree events isolation
# ---------------------------------------------------------------------------


def test_subtree_events_isolation(qapp, qtbot):
    bus_a = ToolkitTranslationEvents()
    bus_b = ToolkitTranslationEvents()
    label = Label("x", text_key="iso.key")
    qtbot.addWidget(label)
    install_translator(label, lambda key, lang: f"A:{lang}:{key}", events=bus_a)

    initial = label.text()
    assert initial.startswith("A:")

    # The global bus must not drive a bus_a-owned subtree.
    emit_language_changed("global")
    assert label.text() == initial

    # A sibling custom bus must not drive it either.
    bus_b._emit_language_changed("b")
    assert label.text() == initial

    bus_a._emit_language_changed("a")
    assert label.text() == "A:a:iso.key"


def test_global_bus_still_drives_default_install(qapp, qtbot):
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    label = Label("x", text_key="g.key", parent=root)
    install_translator(root, _lang_prefix)

    emit_language_changed("ru")
    assert label.text() == "ru:g.key"


def test_install_covers_widget_added_to_existing_descendant(qapp, qtbot):
    """A widget added later to an EXISTING descendant (not root) is covered.

    Red-before: the ChildAdded watcher was installed on ``root`` only, so a
    widget parented to a descendant that predates the install (e.g. a card
    menu popup parented to a card) never re-translated on a language change.
    """
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    mid = QWidget(root)  # exists BEFORE install
    install_translator(root, _lang_prefix)

    deep = Label("English literal", text_key="deep.key", parent=mid)
    qtbot.addWidget(deep)

    emit_language_changed("zz")
    qapp.processEvents()
    assert deep.text() == "zz:deep.key"


def test_install_covers_descendant_of_later_child(qapp, qtbot):
    """New child (of root) + a grandchild under it are both covered."""
    from PySide6.QtWidgets import QWidget

    root = QWidget()
    qtbot.addWidget(root)
    install_translator(root, _lang_prefix)

    mid = QWidget(root)
    deep = Label("English literal", text_key="d2.key", parent=mid)
    qtbot.addWidget(deep)

    qapp.processEvents()
    emit_language_changed("yy")
    qapp.processEvents()
    assert deep.text() == "yy:d2.key"


# ---------------------------------------------------------------------------
# configure_i18n wiring is covered in tests/test_i18n.py
# ---------------------------------------------------------------------------
