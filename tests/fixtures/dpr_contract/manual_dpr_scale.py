# Fixture for tests/test_dpr_contract.py — mode: manual-dpr-scale.
# provenance: NONE. No instance in this repo: every *.py blob reachable from
#   `git rev-list --all --objects` (2776 at 3ccfe91^) was grepped for a `.scale(` call and
#   there is not one — the toolkit has never scaled a painter by hand.
# shape: authored — the canonical wrong form, so the detector has a red case today. This is
#   NOT a shipped defect. It is the failure a naive "fix" of the PR #124 bugs produces:
#   allocating in device px AND scaling the painter by the ratio.
#@findings: 1
#@expect: manual-dpr-scale | painter.scale(dpr, dpr)


def _paint_snapshot(self, painter: QPainter, size: QSize) -> None:
    dpr = max(1.0, float(self.devicePixelRatioF()))
    pixmap = QPixmap(round(size.width() * dpr), round(size.height() * dpr))
    pixmap.setDevicePixelRatio(dpr)
    painter.drawPixmap(0, 0, pixmap)
    painter.scale(dpr, dpr)
    painter.drawRect(0, 0, size.width(), size.height())
