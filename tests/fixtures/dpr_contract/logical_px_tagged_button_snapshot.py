# Fixture for tests/test_dpr_contract.py — mode: raster-logical-tagged.
# provenance: src/sli_ui_toolkit/ui/widgets/buttons/button.py:1123-1168 @ d841b67 (3ccfe91^)
# shape: verbatim method body, dedented one level; the enclosing class was elided so the
#   fragment parses. Not one line of the method itself was edited.
# shipped: yes. PR #124: QPixmap(QSize) tagged with dpr gave a 60x32 logical canvas for a
#   120x64 card at DPR 2 — 1440 ink px per fast frame against 7680 for the full frame.
#@findings: 1
#@expect: raster-logical-tagged | pixmap = QPixmap(size)
def _maybe_snapshot_static(self, event: Any) -> None:
    """Re-render the static layer after a full paint with marquee live.

    One extra full render, amortized over hundreds of cheap ticks. Only
    from a paint that covered the whole widget — a row-clipped tick
    repaint must never bake a partial frame into the snapshot.
    """
    if not self._static_cache_allowed:
        return
    if not self._marquee_row_paints:
        return
    if self._ripple_active():
        return
    if not event.rect().contains(self.rect(), False):
        return
    key = self._static_key_now()
    if self._static_cache is not None and self._static_key == key:
        return
    size = self.size()
    if size.width() <= 0 or size.height() <= 0:
        return
    dpr = float(self.devicePixelRatioF() or 1.0)
    pixmap = QPixmap(size)
    if pixmap.isNull():
        return
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    snapshot = QPainter(pixmap)
    if not snapshot.isActive():
        return
    # ContentLayer calls RowsContent.draw(ctx, tm) without the skip
    # flag, so the flag travels on the widget for the snapshot render.
    self._paint_skip_marquee = True
    try:
        snapshot.save()
        try:
            self._painter.paint(self._make_context(snapshot))
        finally:
            snapshot.restore()
    finally:
        self._paint_skip_marquee = False
        snapshot.end()
    if pixmap.isNull():
        return
    self._static_cache = pixmap
    self._static_key = key
