# Fixture for tests/test_dpr_contract.py — mode: pixmap-size-as-logical.
# provenance: src/sli_ui_toolkit/ui/widgets/buttons/content.py:120-178 @ d841b67 (3ccfe91^)
# shape: verbatim — the whole pre-fix function, unchanged.
# shipped: yes. PR #124: the cover/contain geometry ran on device px (a @2x source was
#   treated as twice as wide as it paints) and the raster itself was 1/dpr, which the
#   painter then upscaled.
#@findings: 10
#@expect: pixmap-size-as-logical | sw = max(1, source.width())
#@expect: pixmap-size-as-logical | sh = max(1, source.height())
#@expect: pixmap-size-as-logical | x = target.x() + (tw - scaled.width()) // 2
#@expect: pixmap-size-as-logical | return scaled, QRect(x, y, scaled.width(), scaled.height())
def _scaled_pixmap_rect(
    source: QPixmap, target: QRect, fill: str
) -> tuple[QPixmap, QRect]:
    """Return (scaled_pixmap, dest_rect) for cover/contain/stretch into target."""
    tw = max(1, int(target.width()))
    th = max(1, int(target.height()))
    sw = max(1, source.width())
    sh = max(1, source.height())
    mode = normalize_image_fill(fill)
    # One cache key per (source, target box, fill, dpr): the scaled result is a
    # pure function of those, and the paint path may run it many times a second.
    try:
        dpr = float(source.devicePixelRatio() or 1.0)
    except Exception:
        dpr = 1.0
    key = (source.cacheKey(), tw, th, mode, dpr)

    if mode == "stretch":
        scaled = _cache_scaled(
            key,
            lambda: source.scaled(
                tw,
                th,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ),
        )
        return scaled, QRect(target.x(), target.y(), tw, th)

    if mode == "contain":
        scaled = _cache_scaled(
            key,
            lambda: source.scaled(
                tw,
                th,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ),
        )
        x = target.x() + (tw - scaled.width()) // 2
        y = target.y() + (th - scaled.height()) // 2
        return scaled, QRect(x, y, scaled.width(), scaled.height())

    # cover — scale to fill, crop overflow by clipping to target
    scale = max(tw / sw, th / sh)
    nw = max(1, int(round(sw * scale)))
    nh = max(1, int(round(sh * scale)))
    scaled = _cache_scaled(
        key,
        lambda: source.scaled(
            nw,
            nh,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ),
    )
    x = target.x() + (tw - scaled.width()) // 2
    y = target.y() + (th - scaled.height()) // 2
    return scaled, QRect(x, y, scaled.width(), scaled.height())
