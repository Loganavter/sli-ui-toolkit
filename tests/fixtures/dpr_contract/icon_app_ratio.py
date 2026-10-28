# Fixture for tests/test_dpr_contract.py — mode: icon-app-ratio.
# provenance: src/sli_ui_toolkit/ui/widgets/helpers/icon_pixmap.py:52 @ bdfdae7
# shape: verbatim body of the shipped helper before this fix (the cache lookup and
#   only-slightly-different docstring elided); the rasterization line is untouched.
# shipped: yes. 2026-10-28: QIcon.pixmap(QSize) used the application ratio. On
#   KDE/Wayland at 125 % that is 2.0 while the window paints at 1.25, so a 22 px
#   icon came back as 44x44 @2.0 and was resampled by 0.625 into 27.5 device px —
#   thin strokes looked ragged, while the same icons were crisp at 100 %.
#@findings: 1
#@expect: icon-app-ratio | pixmap = icon.pixmap(QSize(target_w, target_h))


def normalized_icon_pixmap(icon_value, size):
    icon = icon_value if isinstance(icon_value, QIcon) else resolve_icon(icon_value)
    pixmap = icon.pixmap(QSize(target_w, target_h))
    return pixmap
