"""Creation-site slicing for the Code section's plain-QWidget fallback.

A bare ``QWidget`` has no class source of its own, so the Code section
falls back to the nearest app ancestor. ``_creation_site_region`` narrows
that to the enclosing function that actually creates/configures the
selected widget (matched by objectName or an instance attribute identity)
instead of showing the whole ancestor class.
"""

from __future__ import annotations

import importlib.util
import sys

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.inspector.code.factory import _creation_site_region


def _load_module(name: str, path) -> type:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def host_module(tmp_path, monkeypatch):
    """Import a fake app module from a real file (so inspect.getsourcefile
    works), with a dialog class holding a plain QWidget as ``content``."""
    src = tmp_path / "fake_host.py"
    src.write_text(
        "\n".join(
            [
                "from PySide6.QtWidgets import QWidget",
                "",
                "class FakeDialog(QWidget):",
                "    def __init__(self):",
                "        super().__init__()",
                "        self.unrelated = QWidget()",
                "",
                "    def create_content(self):",
                "        self.content = QWidget(self)",
                "        self.content.setObjectName('TheContent')",
                "",
                "    def unrelated(self):",
                "        x = 1",
                "        y = 2",
                "        return x + y",
                "",
            ]
        ),
        encoding="utf-8",
    )
    module = _load_module("fake_host", src)
    yield module, src
    sys.modules.pop("fake_host", None)


def test_creation_site_region_matches_attribute_identity(
    qapp, host_module
):
    module, src = host_module
    dialog = module.FakeDialog()
    dialog.create_content()
    widget = dialog.content
    assert type(widget) is QWidget
    assert widget.parentWidget() is dialog

    site = _creation_site_region(widget, dialog)
    assert site is not None
    file, lines, start = site
    assert file == str(src)
    joined = "\n".join(lines)
    assert "def create_content(self):" in joined
    assert "self.content = QWidget(self)" in joined
    assert "class FakeDialog" not in joined
    assert "def unrelated(self):" not in joined
    assert start == 8


def test_creation_site_region_matches_object_name(qapp, tmp_path):
    src = tmp_path / "fake_row.py"
    src.write_text(
        "\n".join(
            [
                "from PySide6.QtWidgets import QWidget",
                "",
                "class FakeDialog(QWidget):",
                "    def __init__(self):",
                "        super().__init__()",
                "",
                "def make_row():",
                "    row = QWidget()",
                "    row.setObjectName('FancyRow')",
                "    return row",
                "",
                "def other():",
                "    return QWidget()",
                "",
            ]
        ),
        encoding="utf-8",
    )
    module = _load_module("fake_row", src)
    try:
        row = module.make_row()
        dialog = module.FakeDialog()
        assert row.objectName() == "FancyRow"

        site = _creation_site_region(row, dialog)
        assert site is not None
        file, lines, start = site
        assert file == str(src)
        joined = "\n".join(lines)
        assert "def make_row():" in joined
        assert "setObjectName('FancyRow')" in joined
        assert "def other():" not in joined
    finally:
        sys.modules.pop("fake_row", None)


def test_creation_site_region_none_without_markers(qapp, tmp_path):
    """A widget built by toolkit-like code with only a local reference has
    no locatable creation site — the caller keeps the whole-class fallback."""
    src = tmp_path / "fake_plain.py"
    src.write_text(
        "\n".join(
            [
                "from PySide6.QtWidgets import QWidget",
                "",
                "class FakeDialog(QWidget):",
                "    def __init__(self):",
                "        super().__init__()",
                "",
                "def make_plain():",
                "    row = QWidget()",
                "    return row",
                "",
            ]
        ),
        encoding="utf-8",
    )
    module = _load_module("fake_plain", src)
    try:
        row = module.make_plain()
        assert type(row) is QWidget
        assert not row.objectName()
        assert _creation_site_region(row, module.FakeDialog()) is None
    finally:
        sys.modules.pop("fake_plain", None)


def test_creation_site_region_finds_imported_builder_file(qapp, tmp_path):
    """The settings pattern: the ancestor module imports a builder module
    that creates the widget — the region must come from the builder's file."""
    builder = tmp_path / "fake_builder.py"
    builder.write_text(
        "\n".join(
            [
                "from PySide6.QtWidgets import QWidget",
                "",
                "def create_page_content():",
                "    page = QWidget()",
                "    page.setObjectName('PageContent')",
                "    return page",
                "",
            ]
        ),
        encoding="utf-8",
    )
    main = tmp_path / "fake_main.py"
    main.write_text(
        "\n".join(
            [
                "from PySide6.QtWidgets import QWidget",
                "from fake_builder import create_page_content",
                "",
                "class FakeDialog(QWidget):",
                "    def __init__(self):",
                "        super().__init__()",
                "",
                "    def setup(self):",
                "        page = create_page_content()",
                "        return page",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _load_module("fake_builder", builder)
    main_module = _load_module("fake_main", main)
    try:
        dialog = main_module.FakeDialog()
        page = dialog.setup()
        assert page.objectName() == "PageContent"

        site = _creation_site_region(page, dialog)
        assert site is not None
        file, lines, start = site
        assert file == str(builder)
        joined = "\n".join(lines)
        assert "def create_page_content():" in joined
        assert "setObjectName('PageContent')" in joined
        assert "class FakeDialog" not in joined
    finally:
        sys.modules.pop("fake_main", None)
        sys.modules.pop("fake_builder", None)


def test_toolkit_scrollable_page_content_widget(qapp, tmp_path):
    """The user's reported case: ScrollableDialogPage.content_widget (a
    toolkit-built anonymous QWidget) must resolve to the app builder
    function that creates the page — not the whole app dialog class."""
    from sli_ui_toolkit.widgets import ScrollableDialogPage

    builder = tmp_path / "fake_pages.py"
    builder.write_text(
        "\n".join(
            [
                "from PySide6.QtWidgets import QSizePolicy",
                "from sli_ui_toolkit.widgets import ScrollableDialogPage",
                "",
                "def create_scrollable_page():",
                "    page = ScrollableDialogPage()",
                "    page.content_widget.setSizePolicy(",
                "        QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding",
                "    )",
                "    return page, page.content_layout",
                "",
            ]
        ),
        encoding="utf-8",
    )
    main = tmp_path / "fake_dialog.py"
    main.write_text(
        "\n".join(
            [
                "from PySide6.QtWidgets import QWidget",
                "from fake_pages import create_scrollable_page",
                "",
                "class FakeDialog(QWidget):",
                "    def __init__(self):",
                "        super().__init__()",
                "",
                "    def create_page(self):",
                "        page, layout = create_scrollable_page()",
                "        return page",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _load_module("fake_pages", builder)
    main_module = _load_module("fake_dialog", main)
    try:
        dialog = main_module.FakeDialog()
        page = dialog.create_page()
        widget = page.content_widget
        assert type(widget) is QWidget

        site = _creation_site_region(widget, dialog)
        assert site is not None
        file, lines, start = site
        assert file == str(builder)
        joined = "\n".join(lines)
        assert "def create_scrollable_page():" in joined
        assert "page.content_widget.setSizePolicy(" in joined
        assert "class FakeDialog" not in joined
        assert start == 4
    finally:
        sys.modules.pop("fake_dialog", None)
        sys.modules.pop("fake_pages", None)