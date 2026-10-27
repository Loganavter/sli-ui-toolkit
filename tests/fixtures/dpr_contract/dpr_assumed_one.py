# Fixture for tests/test_dpr_contract.py — mode: dpr-assumed-1.
# provenance: NONE. No instance in this repo: no signature in `git rev-list --all --objects`
#   history (2776 *.py blobs at 3ccfe91^) declares a device-ratio parameter with a numeric
#   default. The closest real code is the pre-#124 fallback `except Exception: dpr = 1.0`
#   in the old `_scaled_pixmap_rect`, which silently pinned the ratio to 1 — same mistake,
#   different position, and it is covered by the pixmap-size-as-logical fixtures.
# shape: authored — the canonical wrong form, so the detector has a red case today. This is
#   NOT a shipped defect.
#@findings: 1
#@expect: dpr-assumed-1 | def _render_raster(width: int, height: int, dpr: float = 1.0) -> QPixmap:


def _render_raster(width: int, height: int, dpr: float = 1.0) -> QPixmap:
    pixmap = QPixmap(round(width * dpr), round(height * dpr))
    pixmap.setDevicePixelRatio(dpr)
    return pixmap
