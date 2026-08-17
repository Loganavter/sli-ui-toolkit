"""Shared helpers for the inspector test modules."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.inspector.contract import (
    FieldKind,
    InspectField,
    InspectLayer,
    InspectRegion,
    WidgetInspection,
)
from sli_ui_toolkit.ui.inspector.view import InspectorWindow
from sli_ui_toolkit.widgets import Button, ButtonRegion, Label, Switch

def _page_labels(window: InspectorWindow, section: str) -> list[str]:
    page = window._pages[section]
    out: list[str] = []
    for label in page.content_widget.findChildren(Label):
        out.append(label.text())
    for button in page.content_widget.findChildren(Button):
        out.append(str(getattr(button, "_text", "") or ""))
        for row in getattr(button, "_rows", ()) or ():
            out.append(str(getattr(row, "text", "") or ""))
    return out


def _build_button_inspection():
    from sli_ui_toolkit.ui.inspector import inspect_widget

    return inspect_widget(Button(regions=[ButtonRegion(id="cover"), ButtonRegion(id="text")]))


def _open_probe(win, source_text, tmp_path_factory, monkeypatch, source_start=4, *, config=None):
    """Open a probe widget whose source file is a string; returns the pane."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QWidget

    class _LocalProbe(QWidget):
        def __init__(self):
            super().__init__()

    tmp = tmp_path_factory.mktemp("probe")
    source_file = tmp / "probe_widget.py"
    source_file.write_text(source_text, encoding="utf-8")

    class _FakePath:
        def __init__(self, path):
            self.path = path

        def read_text(self, encoding=None):
            return source_file.read_text(encoding=encoding)

        def write_text(self, text, encoding=None):
            written.append((self.path, text, encoding))

    written = []
    # the implementation module (the package __init__ is thin re-exports)
    import sli_ui_toolkit.ui.inspector.code.editor as code_module

    monkeypatch.setattr(code_module, "Path", _FakePath)
    monkeypatch.setattr("inspect.getsourcefile", lambda _cls: str(source_file))
    source_lines = source_text.split("\n")[source_start - 1 :]
    monkeypatch.setattr(
        "inspect.getsourcelines",
        lambda _cls: ([line + "\n" for line in source_lines], source_start),
    )
    win.set_inspection(
        WidgetInspection(family="QWidget", config=config or ()), widget=_LocalProbe()
    )
    return win.active_pane(), source_file, written


def _spin_event_loop(qapp):
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(400, loop.quit)  # > the preview rebuild debounce
    loop.exec()
    qapp.processEvents()

