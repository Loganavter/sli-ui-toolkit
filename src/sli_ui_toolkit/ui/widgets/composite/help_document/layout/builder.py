"""Block layout: measure help document body and produce a LayoutResult."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QPixmap

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.composite.help_document.blocks import (
    FigureBlock,
    HeadingBlock,
    HelpBlock,
    ImageBlock,
    InlineSpan,
    ListBlock,
    ParagraphBlock,
    parse_inline,
    spans_to_plain,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.constants import (
    BLOCK_SPACING,
    BODY_FONT_PX,
    CAPTION_FONT_PX,
    CAPTION_SPACING,
    H2_FONT_PX,
    H3_FONT_PX,
    LIST_INDENT,
    SIDE_FIGURE_SPACING,
    SIDE_FIGURE_V_MARGIN,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.segment_map import (
    build_segment_map,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.text_layout import (
    build_text_layout,
    styles_from_spans,
    text_layout_height,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.types import (
    AssetResolver,
    LayoutResult,
    PixmapFragment,
    TextFragment,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.structure import (
    LayoutItem,
    SideFigureGroup,
    group_side_figures,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.text_index import (
    DocumentTextIndex,
    TextSegment,
)


def layout_document(
    blocks: tuple[HelpBlock, ...],
    text_index: DocumentTextIndex,
    width: float,
    theme: ThemeManager,
    resolve_asset: AssetResolver | None = None,
) -> LayoutResult:
    builder = _LayoutBuilder(
        blocks=blocks,
        width=max(1.0, width),
        theme=theme,
        resolve_asset=resolve_asset,
        text_index=text_index,
    )
    builder.layout_items(group_side_figures(blocks))
    return builder.finish()


@dataclass
class _LayoutBuilder:
    blocks: tuple[HelpBlock, ...]
    width: float
    theme: ThemeManager
    resolve_asset: AssetResolver | None
    text_index: DocumentTextIndex
    y: float = 0.0
    text_fragments: list[TextFragment] | None = None
    pixmaps: list[PixmapFragment] | None = None
    anchors: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.text_fragments is None:
            self.text_fragments = []
        if self.pixmaps is None:
            self.pixmaps = []
        if self.anchors is None:
            self.anchors = {}
        self._segment_map = build_segment_map(self.text_index)

    def _block_index(self, block: HelpBlock) -> int:
        return self.blocks.index(block)

    def _segment_for(
        self,
        block_index: int,
        *,
        list_item_index: int | None = None,
        caption: bool = False,
    ) -> TextSegment | None:
        key = (block_index, list_item_index, caption)
        return self._segment_map.get(key)

    def finish(self) -> LayoutResult:
        return LayoutResult(
            width=self.width,
            height=self.y,
            text_fragments=tuple(self.text_fragments or []),
            pixmaps=tuple(self.pixmaps or []),
            anchors=dict(self.anchors or {}),
        )

    def _body_font(self) -> QFont:
        font = QFont()
        font.setPixelSize(BODY_FONT_PX)
        return font

    def _heading_font(self, level: int) -> QFont:
        font = QFont()
        font.setPixelSize(H2_FONT_PX if level <= 2 else H3_FONT_PX)
        font.setBold(True)
        return font

    def _caption_font(self) -> QFont:
        font = QFont()
        font.setPixelSize(CAPTION_FONT_PX)
        return font

    def _layout_segment(
        self,
        segment: TextSegment,
        *,
        x: float,
        max_width: float,
        base_font: QFont,
        color_token: str = "dialog.text",
        caption_spans: tuple[InlineSpan, ...] | None = None,
    ) -> float:
        if caption_spans:
            text = spans_to_plain(caption_spans)
            styles, roles = styles_from_spans(caption_spans)
        else:
            text = self.text_index.text[segment.start : segment.end]
            styles = self.text_index.styles[segment.start : segment.end]
            roles = self.text_index.roles[segment.start : segment.end]
        if not text:
            return 0.0
        layout, links = build_text_layout(
            text,
            styles,
            roles,
            base_font=base_font,
            theme=self.theme,
            color_token=color_token,
            width=max_width,
        )
        natural = text_layout_height(layout)
        rect = QRectF(x, self.y, max_width, natural)
        self.text_fragments.append(
            TextFragment(
                rect=rect,
                global_start=segment.start,
                global_end=segment.end,
                layout=layout,
                links=links,
            )
        )
        return natural

    def _advance(self, height: float) -> None:
        self.y += height + BLOCK_SPACING

    def _finish_block(self) -> None:
        self.y += BLOCK_SPACING

    def _fit_image_width(
        self,
        *,
        px: int | None = None,
        percent: float | None = None,
    ) -> int:
        content_w = max(1, int(self.width))
        if percent is not None:
            frac = max(1.0, min(100.0, float(percent))) / 100.0
            return max(1, min(content_w, int(round(content_w * frac))))
        if px is None:
            return content_w
        return max(1, min(int(px), content_w))

    def _figure_target_box(self, block: FigureBlock) -> tuple[int, int | None]:
        """Return ``(max_w, max_h)`` for KeepAspectRatio fitting."""
        content_w = max(1, int(self.width))
        has_w = block.width is not None or block.width_percent is not None
        max_w = (
            self._fit_image_width(px=block.width, percent=block.width_percent)
            if has_w
            else content_w
        )
        max_h = max(1, int(block.height)) if block.height is not None else None
        return max_w, max_h

    def layout_items(self, items: list[LayoutItem]) -> None:
        for item in items:
            if isinstance(item, SideFigureGroup):
                self._layout_side_figure(item)
            elif isinstance(item, HeadingBlock):
                self._layout_heading(item)
            elif isinstance(item, ParagraphBlock):
                self._layout_paragraph(item)
            elif isinstance(item, ListBlock):
                self._layout_list(item)
            elif isinstance(item, ImageBlock):
                self._layout_image(item)
            elif isinstance(item, FigureBlock):
                self._layout_figure(item)

    def _layout_heading(self, block: HeadingBlock) -> None:
        if block.anchor:
            self.anchors[block.anchor] = self.y
        segment = self._segment_for(self._block_index(block))
        if segment is None:
            return
        h = self._layout_segment(
            segment,
            x=0.0,
            max_width=self.width,
            base_font=self._heading_font(block.level),
        )
        self._advance(h)

    def _layout_paragraph(self, block: ParagraphBlock) -> None:
        segment = self._segment_for(self._block_index(block))
        if segment is None:
            return
        h = self._layout_segment(
            segment,
            x=0.0,
            max_width=self.width,
            base_font=self._body_font(),
        )
        self._advance(h)

    def _layout_list(self, block: ListBlock) -> None:
        block_index = self._block_index(block)
        for item_index, _item in enumerate(block.items):
            segment = self._segment_for(block_index, list_item_index=item_index)
            if segment is None:
                continue
            h = self._layout_segment(
                segment,
                x=LIST_INDENT,
                max_width=max(1.0, self.width - LIST_INDENT),
                base_font=self._body_font(),
            )
            self._advance(h)

    def _layout_image(self, block: ImageBlock) -> None:
        pix_h = self._place_pixmap(
            block.path,
            block.alt,
            max_w=self._fit_image_width(),
            max_h=None,
            x=0.0,
            center=False,
        )
        self.y += pix_h
        self._finish_block()

    def _layout_figure(self, block: FigureBlock) -> None:
        center = block.side == "center"
        max_w, max_h = self._figure_target_box(block)
        pix_w, pix_h = self._place_pixmap_sized(
            block.path,
            block.alt,
            max_w=max_w,
            max_h=max_h,
            x=0.0,
            center=center,
        )
        self.y += pix_h
        segment = self._segment_for(self._block_index(block), caption=True)
        if segment is not None:
            self.y += CAPTION_SPACING
            cap_x = 0.0
            cap_w = float(self.width)
            if center:
                cap_x = max(0.0, (self.width - pix_w) / 2.0)
                cap_w = float(pix_w)
            cap_h = self._layout_segment(
                segment,
                x=cap_x,
                max_width=cap_w,
                base_font=self._caption_font(),
                color_token="list_item.text.rating",
                caption_spans=parse_inline(block.caption) if block.caption else None,
            )
            self.y += cap_h
        self._finish_block()

    def _layout_side_figure(self, group: SideFigureGroup) -> None:
        max_w, max_h = self._figure_target_box(group.figure)
        # Probe scaled size for column split (same rules as paint).
        _probe, figure_w, _figure_h = self._scaled_pixmap(
            group.figure.path, max_w=max_w, max_h=max_h
        )
        min_text_w = max(80.0, self.width * 0.35)
        side_by_side = figure_w + SIDE_FIGURE_SPACING + min_text_w <= self.width
        if not side_by_side:
            self._layout_side_figure_stacked(group, max_w, max_h)
            return

        self.y += SIDE_FIGURE_V_MARGIN
        row_y = self.y
        text_x = 0.0
        text_w = self.width
        fig_x = 0.0
        if group.figure.side == "left":
            text_x = figure_w + SIDE_FIGURE_SPACING
            text_w = max(1.0, self.width - text_x)
            fig_x = 0.0
        else:
            text_w = max(1.0, self.width - figure_w - SIDE_FIGURE_SPACING)
            fig_x = text_w + SIDE_FIGURE_SPACING

        text_start_y = row_y
        self.y = text_start_y
        for para in group.paragraphs:
            segment = self._segment_for(self._block_index(para))
            if segment is None:
                continue
            h = self._layout_segment(
                segment,
                x=text_x,
                max_width=text_w,
                base_font=self._body_font(),
            )
            self.y += h + BLOCK_SPACING
        text_end_y = self.y

        self.y = row_y
        _pix_w, fig_h = self._place_pixmap_sized(
            group.figure.path,
            group.figure.alt,
            max_w=max_w,
            max_h=max_h,
            x=fig_x,
            center=False,
        )
        if group.figure.caption:
            segment = self._segment_for(
                self._block_index(group.figure),
                caption=True,
            )
            if segment is not None:
                self.y = row_y + fig_h + CAPTION_SPACING
                cap_h = self._layout_segment(
                    segment,
                    x=fig_x,
                    max_width=float(figure_w),
                    base_font=self._caption_font(),
                    color_token="list_item.text.rating",
                    caption_spans=parse_inline(group.figure.caption),
                )
                fig_h += CAPTION_SPACING + cap_h

        row_h = max(fig_h, text_end_y - row_y)
        self.y = row_y + row_h + SIDE_FIGURE_V_MARGIN + BLOCK_SPACING

    def _layout_side_figure_stacked(
        self,
        group: SideFigureGroup,
        max_w: int,
        max_h: int | None,
    ) -> None:
        """Narrow column: image then caption then paragraphs at full width."""
        for para in group.paragraphs:
            segment = self._segment_for(self._block_index(para))
            if segment is None:
                continue
            h = self._layout_segment(
                segment,
                x=0.0,
                max_width=self.width,
                base_font=self._body_font(),
            )
            self._advance(h)

        center = group.figure.side == "center"
        _pix_w, pix_h = self._place_pixmap_sized(
            group.figure.path,
            group.figure.alt,
            max_w=max_w,
            max_h=max_h,
            x=0.0,
            center=center,
        )
        self.y += pix_h
        if group.figure.caption:
            self.y += CAPTION_SPACING
            segment = self._segment_for(
                self._block_index(group.figure),
                caption=True,
            )
            if segment is not None:
                cap_h = self._layout_segment(
                    segment,
                    x=0.0,
                    max_width=self.width,
                    base_font=self._caption_font(),
                    color_token="list_item.text.rating",
                    caption_spans=parse_inline(group.figure.caption),
                )
                self.y += cap_h
        self._finish_block()

    def _scaled_pixmap(
        self,
        path: str,
        *,
        max_w: int,
        max_h: int | None,
    ) -> tuple[QPixmap | None, int, int]:
        pix = self._load_pixmap(path)
        content_w = max(1, int(self.width))
        box_w = max(1, min(int(max_w), content_w))
        if pix is None or pix.isNull():
            box_h = max_h if max_h is not None else max(1, int(round(box_w * 9 / 16)))
            return None, box_w, max(1, int(box_h))
        if max_h is None:
            if pix.width() != box_w:
                pix = pix.scaledToWidth(
                    box_w, Qt.TransformationMode.SmoothTransformation
                )
        else:
            box_h = max(1, int(max_h))
            pix = pix.scaled(
                box_w,
                box_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return pix, max(1, int(pix.width())), max(1, int(pix.height()))

    def _place_pixmap(
        self,
        path: str,
        alt: str,
        *,
        max_w: int,
        max_h: int | None,
        x: float,
        center: bool,
    ) -> float:
        _w, h = self._place_pixmap_sized(
            path, alt, max_w=max_w, max_h=max_h, x=x, center=center
        )
        return h

    def _place_pixmap_sized(
        self,
        path: str,
        alt: str,
        *,
        max_w: int,
        max_h: int | None,
        x: float,
        center: bool,
    ) -> tuple[float, float]:
        pix, pix_w, pix_h = self._scaled_pixmap(path, max_w=max_w, max_h=max_h)
        draw_x = x
        if center:
            draw_x = max(0.0, (self.width - pix_w) / 2.0)
        rect = QRectF(draw_x, self.y, pix_w, pix_h)
        self.pixmaps.append(
            PixmapFragment(
                rect=rect,
                pixmap=pix,
                alt=alt or path,
                source_path=path,
            )
        )
        return float(pix_w), float(pix_h)

    def _load_pixmap(self, path: str) -> QPixmap | None:
        resolved: str | Path | QPixmap | None = path
        if self.resolve_asset is not None:
            resolved = self.resolve_asset(path)
        if resolved is None:
            return None
        if isinstance(resolved, QPixmap):
            return resolved
        file_path = Path(resolved)
        if not file_path.is_file():
            return None
        pix = QPixmap(str(file_path))
        return pix if not pix.isNull() else None
