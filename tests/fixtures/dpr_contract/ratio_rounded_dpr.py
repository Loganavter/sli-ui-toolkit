# Fixture for tests/test_dpr_contract.py — mode: ratio-rounded.
# provenance: NONE. No instance in this repo: every *.py blob reachable from
#   `git rev-list --all --objects` (2776 at 3ccfe91^) was grepped for int()/round()/floor()
#   applied to a device ratio, and there is no match.
# shape: authored — the canonical wrong form, so the detector has a red case today. This is
#   NOT a shipped defect; do not cite it as one. Same family as the PR #124 bugs (it is the
#   arithmetic those four sites use), one step further: at 125% the ratio becomes 1.0.
#@findings: 1
#@expect: ratio-rounded | dpr = int(self.devicePixelRatioF())


def _device_snapshot(self, size: QSize) -> QPixmap:
    dpr = int(self.devicePixelRatioF())
    pixmap = QPixmap(size.width() * dpr, size.height() * dpr)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap
