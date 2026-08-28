"""Code section of the inspector — ONE unified, collapsible editor widget.

Instead of separate config/class fields, ``CodeSectionEditor`` shows ONE
text view: the live-config snippet, the widget's class source, and — when
the source file has other code around the class — the rest of the file.
Code that is not currently interesting is collapsed into a single gap row
(``·····``, VS Code-style boundary numbers in the gutter); clicking the
row expands that region inline. The **Full/Compact** toggle button
(top-left, session-picker style) expands everything at once and flips its
own label. **Preview** compiles the edited class and constructs a live
instance (with the current config as constructor kwargs) in a preview
panel that re-builds on every edit, so the effect of a change can be seen
before saving — or reverted. Save reconstructs the whole file with the
edited class region.

Per the thin-owner pattern (CODE_PATTERNS.md), this module keeps the
editor's construction, document model and Qt-required method names; the
preview panel mechanics live in ``preview.py`` and the Apply /
config-apply mechanics in ``apply.py`` (both functions taking the
editor as their first argument, delegating under the same method
names), with the shared snippet parsing in ``config.py``.

The surface is styled like the app's recent-projects shelf: a rounded
"well" fill behind the text and a ``variant="default"`` toggle button.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from .apply import (
    _CLASS_BOOKKEEPING,
    apply_config_to_instance,
    apply_to_live,
    revert_class_patch,
)
from .preview import (
    _panel_color,
    _PanelWell,
    clear_host,
    close,
    rebuild,
    schedule_rebuild,
    set_debug,
    show_error,
    show_status,
    toggle,
)
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label
from sli_ui_toolkit.ui.widgets.buttons.button import Button
from sli_ui_toolkit.ui.widgets.composite.text_view import TextView

logger = logging.getLogger("sli_ui_toolkit.inspector")

#: Collapsed gap row — plain ellipsis; the hidden block's boundary line
#: numbers live in the gutter (VS Code-style: "12" then immediately "17").
_MARKER_TEXT = "·····"
_MARKER_RE = re.compile(r"^·····$")


class CodeSectionEditor(QWidget):
    """Unified class-source editor with collapsible file context.

    ``set_source`` loads a fresh inspection: the widget class source
    (gutter numbered from the actual file lines) plus the live-config
    snippet on top; any other code in the source file (before the class or
    after it) is collapsed into clickable gap rows. The Full/Compact button
    expands/collapses all gaps. Save writes the whole file back with the
    edited class region.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: str | None = None
        self._config_text: str | None = None
        self._qss_text: str | None = None
        self._source_lines: list[str] = []
        self._source_start = 1
        self._file_before: list[str] = []
        self._file_after: list[str] = []
        self._expanded: set[str] = set()
        #: last composed buffer (config + qss + gaps + class region) — the
        #: baseline for _on_changed's edit-location diagnostics
        self._last_build_text = ""
        #: display-line counts of the two synthetic blocks and the two
        #: gaps — the structural anchors used to locate the class region
        #: on save.
        self._config_display_lines = 0
        self._qss_display_lines = 0
        self._gap_a_display_lines = 0
        self._gap_b_display_lines = 0
        #: stashed content of the two gap sections while they are collapsed
        #: (the live buffer only holds the marker row) — toggling Full/
        #: Compact must never discard the user's edits in those sections
        self._stash_before: list[str] | None = None
        self._stash_after: list[str] | None = None
        self._module_vars: dict | None = None
        self._preview_widget: QWidget | None = None
        self._preview_timer: QTimer | None = None
        self._target_class: type | None = None
        self._target_instance: QWidget | None = None
        self._applied = False
        self._patched_names: set[str] = set()
        self._original_class_dict: dict = {}
        #: incremental dirty state — the class region differs from the
        #: loaded source (updated per keystroke at O(1) from the canvas's
        #: last edit line; the full recompute runs on structural edits
        #: (newline add/remove) and on rebuild/save/revert)
        self._class_dirty = False
        #: incremental dirty state for the config snippet — recomputed
        #: exactly on every edit (the snippet is only a few display lines,
        #: so the check is O(snippet), not O(buffer))
        self._snippet_dirty = False
        #: display-line count of the last authoritative buffer snapshot —
        #: a differing count means a structural edit (region boundaries
        #: may have shifted) and triggers a full recompute
        self._last_edit_count = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._toggle_btn = Button(
            text="Full",
            variant="default",
            size=(0, 26),
            corner_radius=8,
        )
        self._toggle_btn.setToolTip(
            "Expand/collapse all hidden code between the config and the class"
        )
        self._toggle_btn.clicked.connect(self._toggle_expansion)
        top_row = QWidget()
        top_buttons = QHBoxLayout(top_row)
        top_buttons.setContentsMargins(0, 0, 0, 0)
        top_buttons.setSpacing(6)
        top_buttons.addWidget(self._toggle_btn)
        top_buttons.addStretch(1)
        root.addWidget(top_row)
        self._top_buttons = top_buttons

        self._view = TextView("")
        self._view.changed.connect(self._on_edit)
        self._canvas = self._view.canvas()
        self._canvas.installEventFilter(self)
        root.addWidget(self._view)

        self._preview_panel = QWidget(self)
        self._preview_panel.setVisible(False)
        preview_layout = QVBoxLayout(self._preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(3)
        self._preview_caption = Label(
            "Preview (live) — rebuilt from the edited class on every change",
            pixel_size=11,
            color_token="dialog.text",
        )
        preview_layout.addWidget(self._preview_caption)
        self._preview_host = _PanelWell(self._preview_panel)
        self._preview_host.setMaximumHeight(160)
        self._preview_host.set_fill_color(_panel_color(ThemeManager.get_instance()))
        self._preview_host_layout = QVBoxLayout(self._preview_host)
        self._preview_host_layout.setContentsMargins(8, 8, 8, 8)
        self._preview_host_layout.setSpacing(0)
        preview_layout.addWidget(self._preview_host)
        self._preview_error = Label("", pixel_size=11, word_wrap=True)
        self._preview_error.setMaximumHeight(48)
        self._preview_error.setVisible(False)
        preview_layout.addWidget(self._preview_error)
        self._preview_debug = Label("", pixel_size=11, word_wrap=True)
        self._preview_debug.setMaximumHeight(48)
        self._preview_debug.setVisible(False)
        preview_layout.addWidget(self._preview_debug)
        root.addWidget(self._preview_panel)

        self._preview_btn = Button(
            text="Preview",
            variant="surface",
            size=(0, 26),
        )
        self._preview_btn.setToolTip(
            "Compile the edited class and show a live instance built from it"
        )
        self._preview_btn.clicked.connect(self._toggle_preview)
        self._apply_btn = Button(
            text="Apply",
            variant="surface",
            size=(0, 26),
        )
        self._apply_btn.setToolTip(
            "Hot-patch the LIVE widget class in place (the real widget "
            "updates; all instances of this class are affected). Revert "
            "restores the original class"
        )
        self._apply_btn.clicked.connect(self._apply_to_live)
        self._edit_btn = Button(text="Edit", variant="surface", size=(0, 26))
        self._edit_btn.setToolTip("Toggle editing of this widget's source file")
        self._edit_btn.clicked.connect(self._toggle_editing)
        self._revert_btn = Button(text="Revert", variant="surface", size=(0, 26))
        self._revert_btn.setToolTip("Discard edits, restore the loaded source")
        self._revert_btn.clicked.connect(self._revert)
        self._save_btn = Button(text="Save", variant="surface", size=(0, 26))
        self._save_btn.setToolTip("Write the edited class source back to the file")
        self._save_btn.clicked.connect(self._save)
        self._save_btn.setEnabled(False)

        buttons_row = QWidget()
        buttons = QHBoxLayout(buttons_row)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(6)
        buttons.addWidget(self._apply_btn)
        buttons.addWidget(self._preview_btn)
        buttons.addWidget(self._edit_btn)
        buttons.addWidget(self._revert_btn)
        buttons.addWidget(self._save_btn)
        buttons.addStretch(1)
        root.addWidget(buttons_row)

        self._view.set_panel_fill(_panel_color(ThemeManager.get_instance()))
        try:
            ThemeManager.get_instance().theme_changed.connect(
                self._on_theme_changed
            )
        except Exception:
            pass

    def _on_theme_changed(self, *_args) -> None:
        """Re-tint the code well after a theme switch. Bound method, so the
        connection dies with the editor (a lambda would survive the widget
        and raise on the deleted C++ view)."""
        try:
            color = _panel_color(ThemeManager.get_instance())
            self._view.set_panel_fill(color)
            self._preview_host.set_fill_color(color)
        except RuntimeError:
            pass

    # -- public surface -----------------------------------------------------

    def set_source(
        self,
        *,
        path: str | None,
        source_text: str,
        source_start: int,
        config_text: str | None,
        qss_text: str | None = None,
        module_vars: dict | None = None,
        target_class: type | None = None,
        target_instance: QWidget | None = None,
    ) -> None:
        """Load a new inspection: class source + config snippet + QSS
        rules (synthetic, above the config) + the surrounding file code
        (collapsed into gap rows). ``module_vars`` is the widget module's
        namespace — the Preview compiles the edited class against it (base
        classes, imports). ``target_class`` / ``target_instance`` are the
        LIVE widget's class and instance — Apply hot-patches the class so
        the real widget changes in place (the snapshot below is what
        Revert restores)."""
        self._path = path
        self._config_text = config_text
        self._qss_text = qss_text
        self._module_vars = dict(module_vars) if module_vars else None
        self._target_class = target_class
        self._target_instance = target_instance
        self._applied = False
        self._patched_names = set()
        self._original_class_dict = {}
        if target_class is not None:
            self._original_class_dict = {
                name: value
                for name, value in vars(target_class).items()
                if name not in _CLASS_BOOKKEEPING
            }
        self._source_lines = source_text.split("\n")
        self._source_start = max(1, int(source_start))
        self._file_before = []
        self._file_after = []
        if path:
            try:
                full = Path(path).read_text(encoding="utf-8").split("\n")
            except OSError:
                full = []
            if full:
                lo = self._source_start - 1
                hi = lo + len(self._source_lines)
                self._file_before = full[:lo] if lo > 0 else []
                self._file_after = full[hi:] if hi < len(full) else []
        self._expanded = set()
        # a fresh inspection: the next rebuild must seed from the loaded
        # state, not from the previous inspection's buffer
        self._last_build_text = ""
        self._qss_display_lines = 0
        self._stash_before = None
        self._stash_after = None
        self._rebuild()
        self._update_toggle_visibility()
        self._edit_btn.setText("Edit")
        self._save_btn.setEnabled(False)
        self._apply_btn.setEnabled(False)
        self._view.exit_edit_mode()
        close(self)

    # -- editing state (for the inspector tests / app hooks) ----------------

    def add_top_action(self, button: Button) -> None:
        """Append a button to the top action row, right of the Full/Compact
        toggle (before the stretch). Used by the pane to add the Docs
        switch — the editor itself has no window knowledge."""
        self._top_buttons.insertWidget(self._top_buttons.count() - 1, button)

    @property
    def view(self) -> TextView:
        """The unified code TextView."""
        return self._view

    @property
    def config_view(self) -> None:
        """Compatibility: the config snippet now lives in the unified view."""
        return None

    def is_dirty(self) -> bool:
        """Whether the class region of the live buffer differs from the
        loaded source. Incrementally maintained on the keystroke path
        (``_on_edit``) and recomputed exactly on rebuild/save/revert."""
        return self._class_dirty

    def _snippet_text(self) -> str:
        """The CURRENT config-snippet text from the live buffer — the
        first ``_config_display_lines`` rows (the snippet's original span;
        edits within it are picked up, including added/removed lines that
        shift the gap/class rows below). The loaded snippet is
        ``self._config_text``. O(snippet) — reads the canvas lines
        directly instead of re-splitting the whole buffer."""
        if self._config_display_lines <= 0:
            return ""
        canvas = self._canvas
        n = min(self._config_display_lines, canvas.line_count())
        return "\n".join(canvas.line_text(i) for i in range(n))

    def snippet_dirty(self) -> bool:
        """Whether the config snippet in the buffer differs from the loaded
        one. Snippet edits drive the preview AND can be applied to the live
        instance's config attributes — but never enable Save (the snippet
        is synthetic, not file content)."""
        return self._snippet_dirty

    # -- apply to the live widget (hot class patch + config apply) ----------
    # thin delegators: the mechanics live in apply.py

    def _apply_to_live(self) -> None:
        apply_to_live(self)

    def _apply_config_to_instance(
        self, kwargs: dict
    ) -> tuple[list[str], list[str]]:
        return apply_config_to_instance(self, kwargs)

    def _revert_class_patch(self) -> None:
        revert_class_patch(self)

    # -- preview ------------------------------------------------------------
    # thin delegators: the panel mechanics live in preview.py

    def _toggle_preview(self) -> None:
        toggle(self)

    def _close_preview(self) -> None:
        close(self)

    def _clear_preview_host(self) -> None:
        clear_host(self)

    def _rebuild_preview(self) -> None:
        rebuild(self)

    def _show_preview_error(self, message: str) -> None:
        show_error(self, message)

    def _show_preview_status(self, message: str) -> None:
        show_status(self, message)

    def _set_preview_debug(self, text: str) -> None:
        set_debug(self, text)

    def _schedule_preview_rebuild(self) -> None:
        schedule_rebuild(self)

    # -- collapse / expand --------------------------------------------------

    def _rebuild(self) -> None:
        """Compose the unified buffer: config + qss + gap + class + gap.

        The LIVE buffer is the source of truth: the config snippet, the
        QSS block, the class region and the gap sections are re-seeded
        from the current text (not from the loaded state), so toggling
        Full/Compact or a gap never discards user edits. Collapsed gap
        sections hold only the marker row in the buffer — their content
        is stashed in ``_stash_before``/``_stash_after`` while collapsed
        and restored on expand. The first build after
        ``set_source``/``_revert`` (``_last_build_text`` empty) seeds
        from the loaded state instead.
        """
        current = self._view.text().split("\n")
        if self._last_build_text:
            # ---- extract the live sections (edits preserved) ----
            markers = [
                i for i, line in enumerate(current) if _MARKER_RE.match(line)
            ]
            config_n = self._config_display_lines
            qss_n = self._qss_display_lines
            if (
                self._file_before
                and self._gap_a_display_lines == 1
                and markers
            ):
                # the before-gap was collapsed: its marker row is the first
                # ellipsis — everything above it is the live synthetic
                # blocks (config + qss), so edits that added/removed rows
                # (which shift the marker down/up) are preserved
                top_n = markers[0]
                live_before = [current[markers[0]]]
                lo_region = markers[0] + 1
            else:
                top_n = config_n + qss_n
                live_before = current[
                    config_n + qss_n : config_n + qss_n + self._gap_a_display_lines
                ]
                lo_region = config_n + qss_n + self._gap_a_display_lines
            if self._file_after and self._gap_b_display_lines == 1 and markers:
                hi_region = markers[-1]
                live_after = [current[markers[-1]]]
            else:
                hi_region = len(current) - self._gap_b_display_lines
                live_after = current[hi_region:]
            hi_region = max(lo_region, hi_region)
            live_config = current[:config_n]
            live_qss = current[config_n:top_n]
            live_region = current[lo_region:hi_region]
        else:
            # first build: the buffer is empty/fresh — seed from loaded state
            live_config = (
                self._config_text.split("\n") if self._config_text else []
            )
            live_qss = self._qss_text.split("\n") if self._qss_text else []
            live_before = []
            live_region = list(self._source_lines)
            live_after = []

        lines: list[str] = []
        gutter: dict[int, str] = {}

        if self._config_text:
            for line in live_config:
                lines.append(line)
                # the snippet is synthetic — a dot, never a file line number
                # (otherwise the counter would restart at 1 below it)
                gutter[len(lines) - 1] = "·"
        self._config_display_lines = len(lines)

        if self._qss_text:
            for line in live_qss:
                lines.append(line)
                # the QSS block is synthetic too (rules assembled from the
                # QSS scan, not a file) — same dot gutter as the config
                gutter[len(lines) - 1] = "·"
        self._qss_display_lines = len(lines) - self._config_display_lines

        if self._file_before:
            if "before" in self._expanded:
                if len(live_before) == 1 and _MARKER_RE.match(live_before[0]):
                    # was collapsed: the content is stashed (or the file)
                    before_rows = (
                        self._stash_before
                        if self._stash_before is not None
                        else list(self._file_before)
                    )
                else:
                    before_rows = live_before
                self._stash_before = None
                for i, line in enumerate(before_rows):
                    lines.append(line)
                    gutter[len(lines) - 1] = str(i + 1)
                self._gap_a_display_lines = len(before_rows)
            else:
                if live_before and (
                    len(live_before) != 1
                    or not _MARKER_RE.match(live_before[0])
                ):
                    self._stash_before = list(live_before)
                lines.append(_MARKER_TEXT)
                # the hidden block's last line — the next visible row (the
                # class statement) shows its real number right after
                gutter[len(lines) - 1] = str(self._source_start - 1)
                self._gap_a_display_lines = 1
        else:
            self._gap_a_display_lines = 0

        for i, line in enumerate(live_region):
            lines.append(line)
            gutter[len(lines) - 1] = str(self._source_start + i)

        if self._file_after:
            off = self._source_start + len(live_region)
            last = off + len(self._file_after) - 1
            if "after" in self._expanded:
                if len(live_after) == 1 and _MARKER_RE.match(live_after[0]):
                    after_rows = (
                        self._stash_after
                        if self._stash_after is not None
                        else list(self._file_after)
                    )
                else:
                    after_rows = live_after
                self._stash_after = None
                for i, line in enumerate(after_rows):
                    lines.append(line)
                    gutter[len(lines) - 1] = str(off + i)
                self._gap_b_display_lines = len(after_rows)
            else:
                if live_after and (
                    len(live_after) != 1 or not _MARKER_RE.match(live_after[0])
                ):
                    self._stash_after = list(live_after)
                lines.append(_MARKER_TEXT)
                # the hidden block's last line (the file's end here)
                gutter[len(lines) - 1] = str(last)
                self._gap_b_display_lines = 1
        else:
            self._gap_b_display_lines = 0

        # snapshot BEFORE set_text: the changed-signal fires inside
        # set_text — this way the diff in _on_changed sees a clean rebuild
        self._last_build_text = "\n".join(lines)
        self._view.set_text("\n".join(lines))
        self._last_edit_count = len(lines)
        self._view.set_line_number_start(1)
        self._canvas.set_line_number_map(gutter)
        # collapsed gap rows carry a disclosure arrow in the gutter; folding
        # stays enabled (reserving the constant arrow offset) while any gap
        # can exist, so the text never shifts between states
        fold_lines = set()
        if self._gap_a_display_lines == 1:
            fold_lines.add(
                self._config_display_lines + self._qss_display_lines
            )
        if self._gap_b_display_lines == 1:
            fold_lines.add(len(lines) - 1)
        if self._file_before or self._file_after:
            self._canvas.set_fold_lines(fold_lines)
        else:
            self._canvas.set_fold_lines(None)
        self._on_changed()  # re-sync save state + live preview
        self._update_toggle_label()

    def _current_text(self) -> str:
        return "\n".join(
            (self._config_text.split("\n") if self._config_text else [])
            + (self._qss_text.split("\n") if self._qss_text else [])
            + self._file_before
            + self._source_lines
            + self._file_after
        )

    def _class_region(self) -> list[str]:
        """The class region of the LIVE buffer — what a save writes back.

        Starts after the synthetic blocks (config + QSS) + the
        collapsed/expanded before-gap and ends at the after-gap. The
        collapsed gap rows are located by their ellipsis text (not by
        index) so edits above the class that shift the rows cannot push a
        marker into the saved region."""
        current = self._view.text().split("\n")
        lo = (
            self._config_display_lines
            + self._qss_display_lines
            + self._gap_a_display_lines
        )
        hi = max(lo, len(current) - self._gap_b_display_lines)
        markers = [i for i, line in enumerate(current) if _MARKER_RE.match(line)]
        if markers:
            # the first ellipsis row is the before-gap, the last one the
            # after-gap (they coincide when only one gap exists)
            if self._file_before and (len(markers) >= 2 or not self._file_after):
                lo = max(lo, markers[0] + 1)
            if self._file_after and (len(markers) >= 2 or not self._file_before):
                hi = min(hi, markers[-1])
        return current[lo:hi]

    def _marker_at(self, line_index: int) -> str | None:
        """The gap id ("before"/"after") whose collapsed row sits at the
        display line, or ``None``. Reads the live buffer so edits that
        destroy a marker just stop matching."""
        lines = self._view.text().split("\n")
        if not (0 <= line_index < len(lines)):
            return None
        if _MARKER_RE.match(lines[line_index]) is None:
            return None
        markers = [i for i, line in enumerate(lines) if _MARKER_RE.match(line)]
        if not markers:
            return None
        first, last = markers[0], markers[-1]
        if self._file_before and line_index == first:
            return "before"
        if self._file_after and line_index == last and last != first:
            return "after"
        if self._file_after and not self._file_before and line_index == first:
            return "after"
        return None

    def _toggle_gap(self, gap: str) -> None:
        if gap in self._expanded:
            self._expanded.discard(gap)
        else:
            self._expanded.add(gap)
        self._rebuild()

    def _toggle_expansion(self) -> None:
        if self._all_expanded():
            self._expanded.clear()
        else:
            self._expanded = {"before", "after"}
        self._rebuild()

    def _all_expanded(self) -> bool:
        return ("before" in self._expanded or not self._file_before) and (
            "after" in self._expanded or not self._file_after
        )

    def _update_toggle_label(self) -> None:
        self._toggle_btn.setText("Compact" if self._all_expanded() else "Full")

    def _update_toggle_visibility(self) -> None:
        self._toggle_btn.setVisible(bool(self._file_before or self._file_after))

    # -- editing ------------------------------------------------------------

    def _on_changed(self) -> None:
        """Authoritative re-sync of the dirty flags + buttons.

        Full-buffer recompute (``_class_region``/``_snippet_text`` are
        O(buffer)) — called on rebuild/save/revert and on structural edits
        (newline added/removed). The per-keystroke path uses ``_on_edit``,
        which is O(1) and delegates here only when the line count moved."""
        self._last_edit_count = self._canvas.line_count()
        class_dirty = self._class_region() != self._source_lines
        snippet_dirty = self._snippet_text() != (self._config_text or "")
        self._class_dirty = class_dirty
        self._snippet_dirty = snippet_dirty
        # Save and Apply stay enabled while ANY change exists (class region
        # or config snippet): Save persists the class region, Apply
        # hot-patches the live class and writes snippet config values onto
        # the live instance. A snippet-only edit is still a change — Save
        # then rewrites the file with the (unchanged) class region, which
        # clears its own enablement while Apply keeps the snippet applyable.
        any_changed = class_dirty or snippet_dirty
        self._save_btn.setEnabled(any_changed)
        self._apply_btn.setEnabled(any_changed)
        old_lines = self._last_build_text.split("\n")
        new_lines = self._view.text().split("\n")
        changed = [
            i
            for i, (a, b) in enumerate(zip(old_lines, new_lines))
            if a != b
        ]
        if len(new_lines) != len(old_lines):
            changed += list(
                range(min(len(old_lines), len(new_lines)), max(len(old_lines), len(new_lines)))
            )
        if changed:
            lo = (
                self._config_display_lines
                + self._qss_display_lines
                + self._gap_a_display_lines
            )
            hi = max(lo, len(new_lines) - self._gap_b_display_lines)
            in_region = [i for i in changed if lo <= i < hi]
            # per-keystroke stream — debug only (visible with --debug)
            logger.debug(
                "[inspector-preview] changed: class_dirty=%s "
                "snippet_dirty=%s changed_lines=%s in_class_region=%s "
                "region=%d..%d apply=%s save=%s",
                class_dirty,
                snippet_dirty,
                changed[:12],
                in_region,
                lo,
                hi,
                class_dirty or snippet_dirty,
                class_dirty,
            )
        schedule_rebuild(self)

    def _on_edit(self) -> None:
        """Per-keystroke handler (canvas ``changed`` signal) — O(1).

        The class-region dirty flag is derived from the single edited
        line: while the flag is clean, the region equals the loaded source
        exactly, so the region is dirty iff the edited line differs from
        its loaded counterpart. Structural edits (newline added/removed,
        which shift the region boundaries) fall back to the authoritative
        ``_on_changed`` recompute. The snippet check is O(snippet) — the
        snippet is a handful of display lines."""
        canvas = self._canvas
        line = canvas.last_edit_line()
        if canvas.line_count() != self._last_edit_count:
            self._on_changed()
            return
        self._snippet_dirty = self._snippet_text() != (self._config_text or "")
        lo = (
            self._config_display_lines
            + self._qss_display_lines
            + self._gap_a_display_lines
        )
        hi = max(lo, canvas.line_count() - self._gap_b_display_lines)
        if not self._class_dirty and lo <= line < hi:
            idx = line - lo
            if idx < len(self._source_lines):
                if canvas.line_text(line) != self._source_lines[idx]:
                    self._class_dirty = True
        any_changed = self._class_dirty or self._snippet_dirty
        self._save_btn.setEnabled(any_changed)
        self._apply_btn.setEnabled(any_changed)
        schedule_rebuild(self)

    def _toggle_editing(self) -> None:
        if not self._view.is_editing():
            self._view.enter_edit_mode()
            self._edit_btn.setText("Stop editing")
        else:
            self._view.exit_edit_mode()
            self._edit_btn.setText("Edit")
            self._on_changed()

    def _revert(self) -> None:
        self._view.exit_edit_mode()
        self._revert_class_patch()
        # discard edits: the next rebuild must seed from the loaded state
        self._last_build_text = ""
        self._stash_before = None
        self._stash_after = None
        self._rebuild()
        self._edit_btn.setText("Edit")
        self._save_btn.setEnabled(False)
        self._apply_btn.setEnabled(False)

    def _save(self) -> None:
        if not self._path:
            return
        # The class region sits between the (config + gap-before) block and
        # the gap-after block; edits above/below it (markers, config) are
        # not file content and are dropped on save.
        class_lines = self._class_region()
        try:
            Path(self._path).write_text(
                "\n".join(self._file_before + class_lines + self._file_after),
                encoding="utf-8",
            )
        except OSError:
            return
        self._source_lines = class_lines
        # re-sync the buttons: Save clears itself (the class region is
        # persisted), Apply stays enabled while the config snippet is still
        # edited — its values can still be written onto the live instance
        self._on_changed()

    # -- marker click handling ----------------------------------------------

    def eventFilter(self, watched, event):  # noqa: N802
        if (
            watched is self._canvas
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            line = self._canvas.line_at(int(event.position().toPoint().y()))
            gap = self._marker_at(line)
            if gap is not None:
                self._toggle_gap(gap)
                return True
        return super().eventFilter(watched, event)


