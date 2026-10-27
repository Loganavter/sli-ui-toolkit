# Fixture for tests/test_dpr_contract.py — mode: ratio-dropped-on-copy.
# provenance: src/sli_ui_toolkit/ui/managers/icon_manager.py:32-43 @ d841b67 (3ccfe91^)
# shape: verbatim.
# shipped: yes. PR #124: a 64x64@2x glyph became a 64x64@1x pixmap, so QIcon painted it
#   twice as large with the art pinned to the top-left corner.
#@findings: 1
#@expect: ratio-dropped-on-copy | result_pixmap = QPixmap(source_pixmap.size())
def _recolor_pixmap(source_pixmap: QPixmap) -> QPixmap:
    result_pixmap = QPixmap(source_pixmap.size())
    result_pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result_pixmap)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
    )
    painter.drawPixmap(0, 0, source_pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(result_pixmap.rect(), QColor("white"))
    painter.end()
    return result_pixmap
