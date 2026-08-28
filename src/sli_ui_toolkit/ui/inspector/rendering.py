"""Section-page rendering for the inspector pane.

One page per concern: Object identity, Config/State field rows,
Button-family Regions/Layers, Theme tokens (+live capture), and the
shared row/title/source-row helpers. QSS rules are assembled into a
synthetic code block at the top of the Code page
(see ``code.factory._qss_snippet`` — owned by the Code section, not
this mixin). The Code section and the Layout/Constructor trees live in
their own mixins (``code/factory.py`` and ``tree.py``).
"""

from __future__ import annotations

import inspect as _inspect
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label
from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonRow
from sli_ui_toolkit.ui.widgets.composite.dialog_shell import ScrollableDialogPage

from .contract import FieldKind, InspectField, WidgetInspection
from .fields import _Swatch, _field_text


class _PathButton(Button):
    """Path button (source / docs rows): stretches with the window only
    until the text fits, then stops — narrower windows compress it and the
    row's marquee scrolls the overflowing text. Thin wrapper over the
    toolkit's ``text_fit`` mode; kept as a named class so the rows read
    clearly at the call site."""


class _PaneRenderingMixin:
    """Mixin: render the Object/Config/State/Regions/Layers/Theme pages.

    Not a QWidget itself — mixed into _InspectionPane; relies on the pane's
    ``pages`` dict, ``widget``/``_current``/``_theme_manager``/
    ``_token_sources`` state and the ``widget_activated``/``region_selected``
    signals, plus ``ScrollableDialogPage.content_layout``.
    QSS rows (``_qss_rows``) are owned by the Code section
    (``code.factory._qss_snippet``) and not rendered here.
    """

    # Declared here only so mypy can resolve them across the mixin split —
    # the real definitions live in _InspectionPane (view.py). Plain
    # annotations only (no `= value`).
    pages: Any
    widget: Any
    _current: Any
    _theme_manager: Any
    _token_sources: Any
    _qss_rows: Any
    widget_activated: Any
    region_selected: Any

    @staticmethod
    def _clear(page: ScrollableDialogPage) -> None:
        layout = page.content_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # detach immediately (deleteLater alone leaves the widget a
                # visible child until the event loop flushes deferred
                # deletes — a re-inspection would double-render pages)
                widget.setParent(None)
                widget.deleteLater()


    def _path_button(self, text: str, tooltip: str) -> Button:
        """Full-path button (source / docs rows): stretches with the window
        only until the text fits, then stops — narrower windows compress it
        and the row's marquee scrolls the overflowing text."""
        button = _PathButton(
            rows=[ButtonRow(text=text, size=None, ratio=1.0, marquee=True)],
            variant="surface",
            size=(0, 26),
            text_fit=True,
        )
        button.setToolTip(tooltip)
        return button


    def _add_title(self, page: ScrollableDialogPage, text: str) -> None:
        page.content_layout.addWidget(
            Label(
                text,
                variant="group-title",
                pixel_size=15,
                bold=True,
                elide=True,
                selectable=True,
            )
        )


    def _add_field_row(
        self, page: ScrollableDialogPage, field: InspectField, indent: int = 0
    ) -> None:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(indent, 0, 0, 0)
        lay.setSpacing(6)
        name = field.name + (" (private)" if field.private else "")
        lay.addWidget(Label(name, pixel_size=13, bold=True, elide=True, selectable=True))
        if field.kind is FieldKind.COLOR and isinstance(field.value, str):
            color = QColor(field.value)
            if color.isValid():
                lay.addWidget(_Swatch(color))
            if field.meta.get("missing"):
                lay.addWidget(Label("missing token", pixel_size=13, selectable=True))
                lay.addWidget(Label(_field_text(field), pixel_size=13, elide=True, selectable=True))
            else:
                lay.addWidget(Label(_field_text(field), pixel_size=13, elide=True, selectable=True))
        elif field.kind is FieldKind.REF and isinstance(field.value, QWidget):
            widget = field.value
            object_name = widget.objectName()
            text = type(widget).__name__ + (
                f"#{object_name}" if object_name else ""
            )
            button = Button(
                text=text,
                variant="surface",
                size=(0, 26),
            )
            # Bound the REF row's minimum width: an unbounded text width (or
            # a raw str(widget) like "<PySide6... at 0x...>") would push the
            # section content's minimum beyond the scroll viewport, wedging
            # the scroll area (content sticks out of the window, no
            # horizontal scrollbar). The button elides its text when narrow.
            from sli_ui_toolkit.managers import scaled_px

            button.setMaximumWidth(scaled_px(220))
            button.setToolTip(str(widget))
            button.clicked.connect(
                lambda _checked=False, w=widget: self.widget_activated.emit(w)
            )
            lay.addWidget(button)
        else:
            lay.addWidget(Label(_field_text(field), pixel_size=13, elide=True, selectable=True))
        lay.addStretch(1)
        page.content_layout.addWidget(row)


    def _render_object(self, widget: QWidget | None) -> None:
        page = self.pages["Object"]
        self._clear(page)
        if widget is None:
            return
        self._add_title(page, type(widget).__name__)
        identity = [
            ("object_name", widget.objectName()),
            ("class", type(widget).__name__),
            ("geometry", f"{widget.geometry().x()},{widget.geometry().y()} "
                         f"{widget.geometry().width()}x{widget.geometry().height()}"),
            ("visible", widget.isVisible()),
            ("enabled", widget.isEnabled()),
            ("under_mouse", widget.underMouse()),
            ("has_focus", widget.hasFocus()),
        ]
        for name, value in identity:
            self._add_field_row(
                page, InspectField(name=name, value=value)
            )
        import inspect as _inspect

        try:
            source = _inspect.getsourcefile(type(widget))
            line = _inspect.getsourcelines(type(widget))[1]
            if source:
                self._add_source_row(page, source, line)
        except (OSError, TypeError):
            pass
        if self._current is not None and self._current.docs:
            self._add_docs_row(page, self._current.docs)


    def _render_docs(self) -> None:
        """Docs section: the widget family's documentation file rendered
        in the read-only text view (markdown document mode)."""
        page = self.pages["Docs"]
        self._clear(page)
        docs_ref = (
            self._current.docs if self._current is not None else ""
        )
        if not docs_ref:
            return
        from sli_ui_toolkit.ui.inspector.spec import _resolve_docs_path
        from sli_ui_toolkit.ui.widgets.composite.text_view import TextView

        self._add_title(page, "Docs")
        view = TextView("")
        path = _resolve_docs_path(docs_ref)
        try:
            view.set_markdown(Path(path).read_text(encoding="utf-8"))
        except OSError:
            view.set_text(f"docs: {docs_ref}\n\n(file not found: {path})")
        # No trailing stretch: the Expanding TextView fills the page and
        # scrolls internally — it must flex with the window, not expand to
        # a fixed content-derived size.
        page.content_layout.addWidget(view)


    def _add_docs_row(self, page: ScrollableDialogPage, docs_ref: str) -> None:
        """``docs`` row: the widget family's documentation file, resolved
        against the toolkit repo (or the working dir for app-side refs) and
        opened in the system editor on click."""
        from sli_ui_toolkit.ui.inspector.spec import _resolve_docs_path

        path = _resolve_docs_path(docs_ref)
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(Label("docs", pixel_size=13, bold=True, selectable=True))
        button = self._path_button(str(path), docs_ref)
        button.clicked.connect(
            lambda _checked=False, target=path: QDesktopServices.openUrl(
                QUrl.fromLocalFile(target)
            )
        )
        lay.addWidget(button)
        lay.addStretch(1)
        page.content_layout.addWidget(row)


    def _add_source_row(self, page: ScrollableDialogPage, source: str, line: int) -> None:
        """``source`` row: clicking opens the file in the system editor."""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(Label("source", pixel_size=13, bold=True, selectable=True))
        button = self._path_button(f"{source}:{line}", "Open in the system text editor")
        button.clicked.connect(
            lambda _checked=False, path=source: QDesktopServices.openUrl(
                QUrl.fromLocalFile(path)
            )
        )
        lay.addWidget(button)
        lay.addStretch(1)
        page.content_layout.addWidget(row)


    def _render_fields(self, section: str, fields) -> None:
        page = self.pages[section]
        self._clear(page)
        if not fields:
            return
        self._add_title(page, section)
        for field in fields:
            self._add_field_row(page, field)
        page.content_layout.addStretch(1)


    def _render_regions(self, regions) -> None:
        page = self.pages["Regions"]
        self._clear(page)
        if not regions:
            return
        self._add_title(page, "Regions")
        for region in regions:
            states = ", ".join(sorted(s.name for s in region.states)) or "—"
            rect = region.rect
            rect_text = (
                f"{rect.x():.0f},{rect.y():.0f} {rect.width():.0f}x{rect.height():.0f}"
                if rect is not None
                else "—"
            )
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
            button = Button(text=region.id, variant="surface", size=(0, 26))
            button.clicked.connect(
                lambda _checked=False, rid=region.id: self.region_selected.emit(rid)
            )
            lay.addWidget(button)
            lay.addWidget(Label(f"[{states}]  {rect_text}", pixel_size=13, elide=True, selectable=True))
            lay.addStretch(1)
            page.content_layout.addWidget(row)
        page.content_layout.addStretch(1)


    def _render_layers(self, layers) -> None:
        page = self.pages["Layers"]
        self._clear(page)
        if not layers:
            return
        self._add_title(page, "Layers (paint order)")
        for layer in layers:
            self._add_field_row(
                page,
                InspectField(name=layer.name, value=layer.scope),
            )
        page.content_layout.addStretch(1)


    def _add_color_row(
        self,
        page: ScrollableDialogPage,
        label: str,
        color,
        detail: str,
    ) -> None:
        """One Colors-section row: label + swatch + hex + origin detail."""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(Label(label, pixel_size=13, bold=True, elide=True, selectable=True))
        if color is not None and color.isValid():
            lay.addWidget(_Swatch(QColor(color)))
            lay.addWidget(Label(QColor(color).name(), pixel_size=13, selectable=True))
        lay.addWidget(Label(detail, pixel_size=13, elide=True, selectable=True))
        lay.addStretch(1)
        page.content_layout.addWidget(row)


    def _render_colors(self) -> None:
        """Colors section: the selected widget's background / text / border
        colors and WHERE each comes from (QSS rule → palette role →
        ThemeManager token → custom painting)."""
        from .colors import (
            first_painting_ancestor,
            has_custom_paint,
            palette_background,
            qss_background_rows,
            qss_border_rows,
            qss_text_rows,
            tokens_for_color,
            widget_flags,
        )

        page = self.pages["Colors"]
        self._clear(page)
        widget = self.widget
        if widget is None:
            return
        tm = self._theme_manager
        self._add_title(page, f"{type(widget).__name__} — colors")

        # ---- background ----
        self._add_title(page, "Background")
        bg_rows = qss_background_rows(self._qss_rows, tm)
        if bg_rows:
            for row in bg_rows:
                self._add_color_row(page, "QSS", row.color, f"{row.value}  ← {row.origin}")
        else:
            role, color, auto_fill = palette_background(widget)
            painted = "paints from palette" if auto_fill else "transparent — does NOT paint"
            self._add_color_row(
                page, f"palette {role}", color, f"{painted} (autoFillBackground {'on' if auto_fill else 'off'})"
            )
            if not auto_fill:
                ancestor = first_painting_ancestor(widget)
                if ancestor is not None:
                    ancestor_role, ancestor_color, _on = palette_background(ancestor)
                    self._add_color_row(
                        page,
                        f"shows {type(ancestor).__name__}#{ancestor.objectName() or ''}",
                        ancestor_color,
                        f"paints palette {ancestor_role} (autoFill on)",
                    )
        if has_custom_paint(widget):
            self._add_color_row(
                page,
                "paint",
                None,
                "custom paintEvent — the fill comes from the widget's own painter "
                "(see Regions / Layers / Config)",
            )
        if widget.styleSheet():
            self._add_color_row(page, "styleSheet", None, widget.styleSheet())
        trace_color = bg_rows[0].color if bg_rows else palette_background(widget)[1]
        if trace_color is not None and trace_color.isValid():
            # The reverse lookup collects every alias of the same color;
            # prefer the app-defined tokens (with source labels) and the
            # core roles, then cap the row spam.
            tokens = sorted(
                tokens_for_color(tm, trace_color),
                key=lambda t: (0 if self._token_sources.get(t) else 1, t),
            )
            shown = tokens[:8]
            for token in shown:
                source = self._token_sources.get(token, "")
                self._add_color_row(
                    page,
                    "= token",
                    QColor(tm.get_color(token)),
                    f"{token}  {source}" if source else token,
                )
            if len(tokens) > len(shown):
                self._add_color_row(
                    page,
                    "= token",
                    None,
                    f"… +{len(tokens) - len(shown)} more aliases of this color",
                )

        # ---- text ----
        self._add_title(page, "Text")
        text_rows = qss_text_rows(self._qss_rows, tm)
        if text_rows:
            for row in text_rows:
                self._add_color_row(page, "QSS", row.color, f"{row.value}  ← {row.origin}")
        else:
            palette = widget.palette()
            for role_name in ("Text", "WindowText"):
                color_role = getattr(QPalette.ColorRole, role_name, None)
                if color_role is None:
                    continue
                color = QColor(palette.color(color_role))
                if not color.isValid():
                    continue
                self._add_color_row(page, f"palette {role_name}", color, "paints text")
                tokens = sorted(
                    tokens_for_color(tm, color),
                    key=lambda t: (0 if self._token_sources.get(t) else 1, t),
                )
                for token in tokens[:4]:
                    source = self._token_sources.get(token, "")
                    self._add_color_row(
                        page, "= token", QColor(tm.get_color(token)),
                        f"{token}  {source}" if source else token,
                    )

        # ---- border ----
        border_rows = qss_border_rows(self._qss_rows, tm)
        if border_rows:
            self._add_title(page, "Border (QSS)")
            for row in border_rows:
                self._add_color_row(page, row.label, row.color, f"{row.value}  ← {row.origin}")

        # ---- flags ----
        self._add_title(page, "Paint flags")
        for name, state in widget_flags(widget):
            self._add_field_row(page, InspectField(name=name, value=state))
        page.content_layout.addStretch(1)


    def _render_theme(self, inspection: WidgetInspection) -> None:
        page = self.pages["Theme"]
        self._clear(page)
        tm = self._theme_manager
        if not inspection.token_family and not inspection.live_tokens:
            return
        self._add_title(page, "Token family (static)")
        for token in inspection.token_family:
            value = None
            if tm is not None:
                try:
                    color = tm.try_get_color(token) if hasattr(tm, "try_get_color") else None
                    value = color.name() if color is not None else None
                except Exception:
                    value = None
            source = self._token_sources.get(token, "")
            label = f"{token}  {source}" if source else token
            self._add_field_row(
                page,
                InspectField(
                    name=label,
                    value=value or "?",
                    kind=FieldKind.COLOR if value else FieldKind.TEXT,
                    meta={"missing": value is None},
                ),
            )
        if inspection.live_tokens:
            self._add_title(page, "Live capture")
            for field in inspection.live_tokens:
                self._add_field_row(page, field)
        page.content_layout.addStretch(1)



