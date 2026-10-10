from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import QDialog

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import (
    SurfaceScrollArea,
)
from sli_ui_toolkit.ui.widgets.composite.dialog_shell import SidebarDialogShell
from sli_ui_toolkit.ui.widgets.composite.text_view.markdown import (
    HeadingBlock,
    HelpBlock,
    parse_help_blocks,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.widget import TextView

AssetResolver = Callable[[str], str | Path | QPixmap | None]

@dataclass(frozen=True)
class MarkdownHelpSection:
    order: int
    slug: str
    title: str
    body_md: str

_TITLE_ATTR_SUFFIX_RE = re.compile(r"\s*\{#[-a-zA-Z0-9_:.]+\}\s*$")
_MD_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$")
_MD_LINK_LABEL_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_INLINE_MARKUP_RE = re.compile(r"[*`]")

def strip_heading_attr_suffix(text: str) -> str:
    return _TITLE_ATTR_SUFFIX_RE.sub("", text).strip()

def slugify_anchor(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug

def _heading_plain_text(title: str) -> str:
    """Heading title with ``{#anchor}``, link labels and emphasis stripped —
    the text ``slugify_anchor`` turns into an auto-generated anchor."""
    text = strip_heading_attr_suffix(title)
    text = _MD_LINK_LABEL_RE.sub(r"\1", text)
    text = _MD_INLINE_MARKUP_RE.sub("", text)
    return text.strip()

def inject_heading_anchors(md_text: str, *, fallback_prefix: str) -> str:
    """Give every markdown heading an explicit ``{#anchor}`` so links and the
    page TOC can target it.

    Mirrors the old HTML pipeline's ``ensure_heading_ids``: headings that
    already carry ``{#…}`` are left untouched; the rest get a slug derived
    from their plain text (de-duplicated with ``-2``, ``-3`` …), with a
    ``<fallback_prefix>-section-N`` fallback for slug-less titles.
    """
    counters: dict[str, int] = {}
    generated_index = 0
    out: list[str] = []
    for line in md_text.splitlines():
        stripped = line.strip()
        match = _MD_HEADING_RE.match(stripped)
        if not match:
            out.append(line)
            continue
        title = match.group("title").strip()
        if _TITLE_ATTR_SUFFIX_RE.search(title):
            out.append(line)
            continue
        base = slugify_anchor(_heading_plain_text(title))
        if not base:
            base = f"{fallback_prefix}-section-{generated_index}"
            generated_index += 1
        count = counters.get(base, 0)
        counters[base] = count + 1
        anchor = base if count == 0 else f"{base}-{count + 1}"
        out.append(f"{match.group('hashes')} {title} {{#{anchor}}}")
    return "\n".join(out)

def _level3_anchors(blocks: tuple[HelpBlock, ...]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for block in blocks:
        if isinstance(block, HeadingBlock) and block.level == 3 and block.anchor:
            items.append((block.anchor, block.text))
    return items

def build_toc_markdown(md_text: str, *, title: str) -> str:
    """Markdown table of contents for a page with ≥2 ``###`` headings.

    Returns ``""`` when the page has fewer than two anchored level-3
    headings (matching the old ``build_page_toc`` threshold).
    """
    blocks = parse_help_blocks(md_text)
    items = _level3_anchors(blocks)
    if len(items) < 2:
        return ""
    lines = [f"**{title}**", ""]
    lines.extend(f"- [{text}](#{anchor})" for anchor, text in items)
    lines.append("")
    return "\n".join(lines)

class MarkdownHelpPageView(TextView):
    """Painted help page in document mode.

    The view is a ``TextView`` (painted ``TextCanvas``, no stock text
    widget). It reports its parsed content height through
    ``sizeHint``/``minimumSizeHint`` so the dialog's outer
    ``SurfaceScrollArea`` scrolls the whole page rather than the view's own
    (disabled) scrollbar.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(400, max(200, self.canvas().minimumHeight() + 8))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def anchor_vertical_offset(self, anchor: str) -> int | None:
        """Back-compat shim for the old browser-based accessor — the
        widget-space y of ``anchor`` (``None`` when absent)."""
        return self.anchor_y(anchor)

class MarkdownHelpDialog(QDialog):
    def __init__(
        self,
        *,
        title: str = "Help",
        toc_title: str = "On this page",
        sections: tuple[MarkdownHelpSection, ...] | list[MarkdownHelpSection] = (),
        resolve_asset: AssetResolver | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("MarkdownHelpDialog")
        self.theme_manager = ThemeManager.get_instance()
        self._dialog_surface_color = QColor("#000000")
        self._read_dialog_surface_color()
        self._pages: list[MarkdownHelpPageView] = []
        self._sections: tuple[MarkdownHelpSection, ...] = ()
        self._toc_title_text = str(toc_title)
        self._resolve_asset: AssetResolver | None = resolve_asset

        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.resize(800, 600)

        self._setup_ui()
        self.set_sections(sections)
        self._apply_styles()
        self.theme_manager.theme_changed.connect(self._apply_styles)

    def _setup_ui(self) -> None:
        from PySide6.QtWidgets import QHBoxLayout

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.shell = SidebarDialogShell(content_margins=(0, 0, 0, 0), content_spacing=0)
        self.nav_widget = self.shell.sidebar
        self.nav_widget.enable_minimal_scrollbar()
        self.nav_widget.currentRowChanged.connect(self.change_page)

        self.scroll_area = SurfaceScrollArea()
        self.scroll_area.viewport().installEventFilter(self)

        self.shell.pages_stack.hide()
        self.shell.content_layout.addWidget(self.scroll_area, 1)
        main_layout.addWidget(self.shell)

    def set_toc_title(self, title: str) -> None:
        self._toc_title_text = str(title)
        self._render_pages()

    def set_asset_resolver(self, resolver: AssetResolver | None) -> None:
        """Set the inline-image resolver used by every page."""
        self._resolve_asset = resolver
        self._render_pages()

    def set_sections_from_directory(
        self,
        directory,
        language: str | None = None,
    ) -> None:
        from sli_ui_toolkit.ui.widgets.composite.help_sections import (
            read_markdown_help_sections,
            toc_title_for_language,
        )

        base = Path(directory)
        self.set_asset_resolver(
            lambda path: path if Path(path).is_absolute() else str(base / path)
        )
        self.set_sections(read_markdown_help_sections(directory))
        if language is not None:
            self.set_toc_title(toc_title_for_language(language))

    def set_sections(
        self,
        sections: tuple[MarkdownHelpSection, ...] | list[MarkdownHelpSection],
    ) -> None:
        self._sections = tuple(sorted(sections, key=lambda item: (item.order, item.slug)))
        self.nav_widget.clear()

        old = self.scroll_area.takeWidget()
        if old is not None:
            old.deleteLater()

        for page in self._pages:
            page.deleteLater()
        self._pages.clear()

        for section in self._sections:
            nav_item = self.nav_widget.add_item(section.title)
            nav_item.setSizeHint(QSize(0, 35))
            content_page = MarkdownHelpPageView()
            content_page.linkActivated.connect(self._on_link_activated)
            self._pages.append(content_page)

        if self.nav_widget.count() > 0:
            self.nav_widget.setCurrentRow(0)

        self._render_pages()
        self._update_nav_width()
        self._apply_styles()

    def _render_section_markdown(self, section: MarkdownHelpSection) -> str:
        md_text = inject_heading_anchors(
            section.body_md, fallback_prefix=section.slug
        )
        toc_md = build_toc_markdown(md_text, title=self._toc_title_text)
        return f"{toc_md}{md_text}" if toc_md else md_text

    def _render_pages(self) -> None:
        for page, section in zip(self._pages, self._sections):
            page.set_markdown(
                self._render_section_markdown(section),
                resolve_asset=self._resolve_asset,
            )

    def _update_nav_width(self) -> None:
        max_text_width = 0
        metrics = QFontMetrics(self.nav_widget.font())
        for i in range(self.nav_widget.count()):
            item = self.nav_widget.item(i)
            if item is None:
                continue
            max_text_width = max(max_text_width, metrics.horizontalAdvance(item.text()))
        self.nav_widget.setMinimumWidth(max_text_width + 32)

    def change_page(self, index: int) -> None:
        if index < 0 or index >= len(self._pages):
            return

        old_widget = self.scroll_area.takeWidget()
        if old_widget is not None:
            old_widget.hide()
            old_widget.setParent(None)

        page = self._pages[index]
        self.scroll_area.setWidget(page)
        self._sync_page_width(page)
        page.show()
        self.scroll_area.verticalScrollBar().setValue(0)

    def _sync_page_width(self, page: MarkdownHelpPageView | None) -> None:
        if page is None:
            return
        viewport_width = max(1, self.scroll_area.viewport().width())
        page.resize(viewport_width, page.height())
        page.updateGeometry()

    def eventFilter(self, watched, event):
        if watched is self.scroll_area.viewport() and event.type() == QEvent.Type.Resize:
            current = self.scroll_area.widget()
            if isinstance(current, MarkdownHelpPageView):
                self._sync_page_width(current)
        return super().eventFilter(watched, event)

    def _find_section_index(self, slug: str) -> int:
        for index, section in enumerate(self._sections):
            if section.slug == slug:
                return index
        return -1

    def navigate_to(self, slug: str, anchor: str | None = None) -> None:
        """Open a help section by slug and optionally scroll to an in-page anchor."""
        self._navigate_to_help_target(slug, anchor)

    def _navigate_to_help_target(self, slug: str, anchor: str | None = None) -> None:
        index = self._find_section_index(slug)
        if index < 0:
            return
        self.nav_widget.setCurrentRow(index)
        if anchor:
            self._scroll_current_page_to_anchor(anchor)

    def _scroll_current_page_to_anchor(self, anchor: str) -> None:
        current = self.nav_widget.currentRow()
        if not (0 <= current < len(self._pages)):
            return
        page = self._pages[current]
        y = page.anchor_y(anchor)
        if y is None:
            return
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(min(max(0, y), bar.maximum()))

    def _on_link_activated(self, href: str) -> None:
        href = (href or "").strip()
        if not href:
            return
        if href.startswith("#"):
            anchor = href[1:].strip()
            if anchor:
                self._scroll_current_page_to_anchor(anchor)
            return

        url = QUrl(href)
        scheme = (url.scheme() or "").lower()
        if scheme in {"http", "https"}:
            QDesktopServices.openUrl(url)
            return

        if scheme == "help":
            slug = url.host().strip() or url.path().strip("/")
            if slug:
                self._navigate_to_help_target(slug, url.fragment().strip() or None)

    def _read_dialog_surface_color(self) -> None:
        """Re-read the ``dialog.background`` token into ``_dialog_surface_color``.

        Re-read on every ``theme_changed`` (via ``_apply_styles``, never
        cached forever): hosts may override the token via
        ``ThemeManager.set_color``. ThemeManager may be uninitialized in
        some test contexts — fall back to the palette Window role as a last
        resort.
        """
        try:
            color = QColor(
                ThemeManager.get_instance().get_color("surface.background")
            )
        except Exception:
            color = QColor(self.palette().window().color())
        self._dialog_surface_color = color

    def paintEvent(self, event) -> None:  # noqa: N802
        """Fill the dialog surface with the ``dialog.background`` token.

        Top-level QDialog QSS surface paint dies with host QSS: with no
        stylesheet the dialog paints the QPalette Window role, which hosts
        keep darker than the dialog surface token — the explicit paint keeps
        the surface consistent with the shell's ``_SurfaceWidget`` /
        ``IconListWidget`` fills.
        """
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._dialog_surface_color)
        painter.end()

    def _apply_styles(self) -> None:
        self._read_dialog_surface_color()
        self.theme_manager.apply_theme_to_dialog(self)
