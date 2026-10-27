# Fixture for tests/test_dpr_contract.py — mode: raster-logical-tagged.
# provenance: src/sli_ui_toolkit/ui/widgets/helpers/marquee_text.py:116-141 @ d841b67 (3ccfe91^)
# shape: verbatim — the whole pre-fix function, unchanged.
# shipped: yes. PR #124: at DPR 2 the strip's logical canvas was cycle/2 wide, so the
#   glyph run was clipped mid-word and the blit landed half a cycle early.
#@findings: 1
#@expect: raster-logical-tagged | pixmap = QPixmap(max(1, cycle), max(1, int(height)))
def _render_marquee_strip(
    *,
    font: QFont,
    pen: QColor,
    text: str,
    text_width: int,
    height: int,
    gap: int,
    dpr: float,
) -> QPixmap:
    """Render one full marquee cycle (text + trailing gap) into a pixmap."""
    cycle = marquee_cycle_px(text_width, gap=gap)
    pixmap = QPixmap(max(1, cycle), max(1, int(height)))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    strip_painter = QPainter(pixmap)
    strip_painter.setFont(font)
    strip_painter.setPen(pen)
    # Same alignment the direct path uses, so blits land on identical pixels.
    strip_painter.drawText(
        QRect(0, 0, cycle, max(1, int(height))),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        text,
    )
    strip_painter.end()
    return pixmap
