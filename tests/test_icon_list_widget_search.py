"""IconListWidget search filtering + resizable SidebarDialogShell."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QSplitter

from sli_ui_toolkit.widgets import IconListWidget, SidebarDialogShell


@pytest.fixture()
def nav(qapp) -> IconListWidget:
    nav = IconListWidget()
    for text in ("General", "Appearance", "Keyboard", "Optimization", "Image Compare"):
        nav.add_item(text)
    return nav


def test_no_filter_shows_all_rows(nav):
    assert nav.count() == 5
    assert nav.item(2).text() == "Keyboard"
    assert nav.row_button(4) is not None


def test_filter_hides_non_matching_rows_in_place(nav):
    nav.set_search_text("key")
    assert nav.count() == 1
    assert nav.item(0).text() == "Keyboard"
    # Rows are reused, not rebuilt: the same button object stays alive.
    button = nav.row_button(0)
    nav.set_search_text("k")
    assert nav.count() == 1
    assert nav.row_button(0) is button


def test_filter_clears_back_to_full_list(nav):
    nav.set_search_text("appearance")
    assert nav.count() == 1
    nav.set_search_text("")
    assert nav.count() == 5
    assert nav.visible_source_index(3) == 3


def test_filter_ranks_by_match_score(nav):
    nav.add_item("Keyboard Layout")
    nav.set_search_text("keyboard")
    # Exact-prefix "Keyboard" ranks above substring "Keyboard Layout".
    assert nav.item(0).text() == "Keyboard"
    assert nav.count() == 2


def test_filter_matches_extra_search_texts(nav):
    nav.add_item("Font", search_texts=("шрифт",))
    nav.set_search_text("шрифт")
    assert nav.count() == 1
    assert nav.item(0).text() == "Font"


def test_selection_drops_when_current_row_filtered_out(nav):
    nav.setCurrentRow(0)  # General
    emitted: list[int] = []
    nav.currentRowChanged.connect(emitted.append)
    nav.set_search_text("keyboard")
    assert nav.currentRow() == -1
    assert -1 in emitted


def test_selection_maps_through_visible_indices(nav):
    nav.set_search_text("a")
    # General + Appearance + Keyboard match "a".
    visible = [nav.item(i).text() for i in range(nav.count())]
    assert "Appearance" in visible
    appearance_visible_idx = visible.index("Appearance")
    nav.setCurrentRow(appearance_visible_idx)
    assert nav.currentRow() == 1  # source index of "Appearance"
    # The selected source row is not explicitly hidden (isHidden — the
    # widget itself is not shown offscreen, so isVisible would be False).
    assert not nav.row_button(appearance_visible_idx).isHidden()


def test_no_results_row_appears_and_disappears(nav):
    nav.set_no_results_text("No matching")
    nav.set_search_text("zzzz")
    assert nav.count() == 1
    assert nav.item(0).text() == "No matching"
    assert nav.item(0).data() is None
    assert not nav.row_button(0).isHidden()
    nav.set_search_text("general")
    assert nav.count() == 1
    assert nav.item(0).text() == "General"


def test_resizable_sidebar_shell_uses_splitter(qapp):
    shell = SidebarDialogShell(resizable_sidebar=True)
    assert shell.splitter is not None
    assert isinstance(shell.splitter, QSplitter)
    assert shell.splitter.count() == 2
    assert shell.splitter.widget(0) is shell.sidebar
    assert shell.splitter.widget(1) is shell.content_area
    assert shell.main_layout.itemAt(0).widget() is shell.splitter


def test_resizable_sidebar_shell_with_header_uses_column_in_splitter(qapp):
    header = QLabel("search")
    shell = SidebarDialogShell(sidebar_header=header, resizable_sidebar=True)
    assert shell.splitter.widget(0) is shell.sidebar_column
    assert shell.splitter.widget(1) is shell.content_area


def test_non_resizable_shell_has_no_splitter(qapp):
    shell = SidebarDialogShell()
    assert shell.splitter is None
    assert shell.main_layout.itemAt(0).widget() is shell.sidebar


def test_splitter_min_width_tracks_sidebar_width(qapp):
    shell = SidebarDialogShell(resizable_sidebar=True, sidebar_width=240)
    shell.resize(800, 400)
    shell.show()
    qapp.processEvents()
    assert shell.sidebar.minimumWidth() == 240
    sizes = shell.splitter.sizes()
    assert sizes[0] >= 240
