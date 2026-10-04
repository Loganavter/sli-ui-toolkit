"""Static-layer cache for marquee ticks: blit + replay instead of re-paint.

Covers the ``Button`` static-layer cache (``button.py``) + the ``RowsContent``
skip path (``content.py``):

- a marquee-only tick performs zero context builds (fast path taken);
- per-tick cost collapses vs the full pipeline (measured ratio, >= 5x);
- EVERY painted-content mutator busts the cache (miss + correct repaint);
- fast-path frames are byte-exact vs full-pipeline frames at the same phase;
- buttons without marquee never allocate a cache;
- resize / DPR changes bust; ripple blocks the fast path; custom layers
  disable the cache entirely.

Harness note: ``QWidget.render(target, offset, region)`` maps the region's
top-left onto ``offset`` — region renders that must land at widget
coordinates pass ``offset=region.topLeft()`` (a zero offset silently shifts
the paint and the parity assertions fail on a correct implementation).
"""

from __future__ import annotations

import statistics
import time

import pytest
from PySide6.QtCore import QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import UiFont
from sli_ui_toolkit.ui.managers.ui_scale import UiScale
from sli_ui_toolkit.ui.widgets.buttons import (
    Button,
    ButtonRegion,
    ButtonRow,
    VerticalSplit,
)
from sli_ui_toolkit.ui.widgets.buttons.button import Button as ButtonImpl
from sli_ui_toolkit.ui.widgets.buttons.capabilities import LongPressCapability
from sli_ui_toolkit.ui.widgets.buttons.content import RowsContent
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer

LONG_TEXT = "Comparison gallery filename number 12345 " * 3


def _cover_pixmap() -> QPixmap:
    pix = QPixmap(120, 40)
    pix.fill(Qt.GlobalColor.darkGray)
    return pix


def make_gallery_card() -> Button:
    """Gallery-like card: cover pixmap + static row + crawling filename row."""
    # NOTE: the cover region is pixmap-only on purpose. A second RowsContent
    # with only static rows would call driver.set_active(False) mid-paint and
    # reset the tick phase before the marquee region paints (pre-existing
    # last-writer-wins wart in the driver wiring, not owned by this lane).
    btn = Button(
        regions=[
            ButtonRegion(id="cover", pixmap=_cover_pixmap()),
            ButtonRegion(
                id="text",
                rows=[
                    ButtonRow(text="2m ago", size=11),
                    ButtonRow(
                        text=LONG_TEXT,
                        size=11,
                        h_align=Qt.AlignmentFlag.AlignLeft,
                        marquee=True,
                    ),
                ],
            ),
        ],
        split=VerticalSplit(),
        size=(120, 64),
        content_padding=(8, 4, 8, 4),
    )
    btn.resize(120, 64)
    return btn


def make_single_card() -> Button:
    """Single-region card exercising the widget-level (_main) mutators."""
    pix = QPixmap(16, 16)
    pix.fill(Qt.GlobalColor.darkBlue)
    btn = Button(
        icon=pix,
        text="Short",
        rows=[
            ButtonRow(text="static", size=11),
            ButtonRow(
                text=LONG_TEXT,
                size=11,
                h_align=Qt.AlignmentFlag.AlignLeft,
                marquee=True,
            ),
        ],
        toggle=True,
        size=(120, 64),
    )
    btn.resize(120, 64)
    return btn


def render_full(btn: QWidget) -> QImage:
    image = QImage(btn.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    btn.render(image, QPoint(0, 0))
    return image


def render_row_region(btn: QWidget, rect) -> QImage:
    """Repaint exactly ``rect`` at widget coordinates (marquee-tick shape)."""
    image = QImage(btn.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    region = QRegion(rect)
    btn.render(image, region.boundingRect().topLeft(), region)
    return image


def warm(btn: Button, qapp) -> None:
    btn.show()
    qapp.processEvents()
    render_full(btn)
    qapp.processEvents()
    assert btn._static_cache is not None, "cache must warm on first full paint"
    assert btn._marquee_row_paints, "marquee paints must record on full paint"
    assert btn._marquee_driver.dirty_rect(), "driver dirty union must register"


def count_context_builds(btn: Button, monkeypatch) -> list:
    calls: list = []
    origin = ButtonImpl._make_context

    def counting(self, painter):
        calls.append(1)
        return origin(self, painter)

    monkeypatch.setattr(ButtonImpl, "_make_context", counting)
    return calls


def test_fast_path_taken_zero_context_builds(qapp, monkeypatch) -> None:
    """A marquee-only tick blits + replays: no make_draw_context at all."""
    btn = make_gallery_card()
    try:
        warm(btn, qapp)
        calls = count_context_builds(btn, monkeypatch)
        hits0 = btn._static_fast_hits
        dirty = btn._marquee_driver.dirty_rect()
        render_row_region(btn, dirty)
        assert btn._static_fast_hits == hits0 + 1
        assert calls == [], "fast path must skip the whole context build"
    finally:
        btn.deleteLater()


def test_per_tick_cost_collapse(qapp) -> None:
    """Median fast tick <= 1/5th of the full-pipeline median (measured)."""
    btn = make_gallery_card()
    try:
        warm(btn, qapp)
        dirty = btn._marquee_driver.dirty_rect()
        region = QRegion(dirty)
        offset = region.boundingRect().topLeft()

        def time_full(n: int = 60) -> float:
            samples = []
            for _ in range(n):
                image = QImage(btn.size(), QImage.Format.Format_ARGB32)
                image.fill(0)
                start = time.perf_counter()
                btn.render(image, QPoint(0, 0))
                samples.append(time.perf_counter() - start)
            return statistics.median(samples)

        def time_fast(n: int = 60) -> float:
            samples = []
            for _ in range(n):
                image = QImage(btn.size(), QImage.Format.Format_ARGB32)
                image.fill(0)
                start = time.perf_counter()
                btn.render(image, offset, region)
                samples.append(time.perf_counter() - start)
            return statistics.median(samples)

        full_median = time_full()
        fast_median = time_fast()
        ratio = full_median / fast_median if fast_median > 0 else float("inf")
        print(f"\npaint-cache tick: full={full_median*1e3:.3f}ms "
              f"fast={fast_median*1e3:.3f}ms ratio={ratio:.1f}x")
        assert fast_median <= full_median / 5.0, (
            f"fast tick {fast_median*1e3:.3f}ms must be <= 1/5th of "
            f"full {full_median*1e3:.3f}ms (ratio {ratio:.1f}x)"
        )
    finally:
        btn.deleteLater()


@pytest.mark.parametrize("phase", [0.0, 7.0, 12.5])
def test_pixel_parity_fast_vs_full(qapp, phase: float) -> None:
    """Fast-path frame vs full-pipeline frame at the same phase: byte-exact."""
    btn = make_gallery_card()
    try:
        warm(btn, qapp)
        driver = btn._marquee_driver
        driver.phase = phase
        btn._marquee_phase = phase  # noqa: SLF001 — mirror the tick write
        full_image = render_full(btn)
        fast_image = full_image.copy()
        dirty = driver.dirty_rect()
        region = QRegion(dirty)
        btn.render(fast_image, region.boundingRect().topLeft(), region)
        assert (full_image.width(), full_image.height()) == (
            fast_image.width(), fast_image.height())
        mismatches = [
            (x, y)
            for y in range(full_image.height())
            for x in range(full_image.width())
            if full_image.pixel(x, y) != fast_image.pixel(x, y)
        ]
        assert mismatches == [], f"{len(mismatches)} pixels differ, e.g. {mismatches[:5]}"
    finally:
        btn.deleteLater()


def test_pixel_parity_compact_single_region(qapp) -> None:
    """Parity also holds for compact single-region rows (metrics layout)."""
    btn = make_single_card()
    try:
        btn._rows_compact = True
        warm(btn, qapp)
        driver = btn._marquee_driver
        driver.phase = 7.0
        btn._marquee_phase = 7.0  # noqa: SLF001
        full_image = render_full(btn)
        fast_image = full_image.copy()
        region = QRegion(driver.dirty_rect())
        btn.render(fast_image, region.boundingRect().topLeft(), region)
        mismatches = [
            (x, y)
            for y in range(full_image.height())
            for x in range(full_image.width())
            if full_image.pixel(x, y) != fast_image.pixel(x, y)
        ]
        assert mismatches == []
    finally:
        btn.deleteLater()


def _red_icon() -> QPixmap:
    pix = QPixmap(8, 8)
    pix.fill(Qt.GlobalColor.darkRed)
    return pix


def _single_mutators() -> list:
    return [
        ("setText", lambda b: b.setText("mutated")),
        ("setIcon", lambda b: b.setIcon(None)),
        ("setIconPix", lambda b: b.setIcon(_red_icon())),
        ("setRows", lambda b: b.setRows([
            ButtonRow(text=LONG_TEXT + "!", size=11, marquee=True)])),
        ("setBadge", lambda b: b.setBadge(5)),
        ("setBadgeStyle", lambda b: b.set_badge_style(filled=True)),
        ("setUnderlineColor", lambda b: b.setUnderlineColor(QColor("#ff0000"))),
        ("setUnderlineThickness", lambda b: b.setUnderlineThickness(2.0)),
        ("setUnderlineTongueReach", lambda b: b.setUnderlineTongueReach(3.0)),
        ("setUnderlineRing", lambda b: b.setUnderlineRing(True)),
        ("setUnderlineFade", lambda b: b.setUnderlineFade(True)),
        ("setShowUnderline", lambda b: b.setShowUnderline(True)),
        ("set_override_bg_color",
         lambda b: b.set_override_bg_color(QColor("#112233"))),
        ("set_bg_locked", lambda b: b.set_bg_locked(True)),
        ("set_hover_color", lambda b: b.set_hover_color(QColor("#445566"))),
        ("set_hover_compose", lambda b: b.set_hover_compose("stack")),
        ("set_background_color",
         lambda b: b.set_background_color(QColor("#778899"))),
        ("setBorderColor", lambda b: b.setBorderColor(QColor("#aabbcc"))),
        ("set_show_strike_through",
         lambda b: b.set_show_strike_through(True)),
        ("setVariant", lambda b: b.setVariant("surface")),
        ("setDensity", lambda b: b.setDensity("compact")),
        ("setIconSizePx", lambda b: b.setIconSizePx(30)),
        ("setIconSize", lambda b: b.setIconSize(QSize(30, 30))),
        ("setGap", lambda b: b.setGap(10)),
        ("setContentAlign",
         lambda b: b.setContentAlign(
             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)),
        ("setContentPadding", lambda b: b.setContentPadding((2, 2, 2, 2))),
        ("setCornerRadiusPx", lambda b: b.setCornerRadiusPx(8)),
        ("setForegroundColor",
         lambda b: b.setForegroundColor(QColor("#123456"))),
        ("setAccentColor", lambda b: b.setAccentColor(QColor("#654321"))),
        ("set_width_texts", lambda b: b.set_width_texts(["aaa", "b"])),
        ("setFlyoutOpen", lambda b: b.setFlyoutOpen(True)),
        ("set_footer_mode", lambda b: b.set_footer_mode(True)),
        ("setChecked", lambda b: b.setChecked(True)),
        ("setRegionChecked", lambda b: b.setRegionChecked("_main", True)),
        ("setEnabledOff", lambda b: b.setEnabled(False)),
        ("setPropertyVariant",
         lambda b: b.setProperty("variant", "surface")),
        ("setPropertyDensity",
         lambda b: b.setProperty("density", "compact")),
        ("setPropertyCorner",
         lambda b: b.setProperty("cornerRadiusPx", 9)),
        ("setFont", lambda b: b.setFont(QFont("Sans", 14))),
        ("on_scale_changed", lambda b: b.on_scale_changed(1.0)),
        ("theme_changed",
         lambda b: ThemeManager.get_instance().theme_changed.emit()),
        ("font_changed",
         lambda b: UiFont.get_instance().font_changed.emit()),
        ("attach_capability",
         lambda b: b.attach_capability(LongPressCapability())),
        ("update_region_badge",
         lambda b: b.update_region("_main", badge=9)),
        ("update_region_rows",
         lambda b: b.update_region("_main", rows=[
             ButtonRow(text=LONG_TEXT + "?", size=11, marquee=True)])),
        ("region_text",
         lambda b: setattr(b.region("_main"), "text", "via-handle")),
        ("region_checked",
         lambda b: setattr(b.region("_main"), "checked", True)),
        ("set_spec_roundtrip", lambda b: b.set_spec(b.spec())),
        ("set_regions_roundtrip",
         lambda b: b.set_regions(list(b.regions()))),
    ]


@pytest.mark.parametrize("name,mutate", _single_mutators(),
                         ids=[m[0] for m in _single_mutators()])
def test_invalidation_single_region(qapp, name, mutate) -> None:
    """Every widget-level mutator busts the cache, then repaints correctly."""
    del name
    btn = make_single_card()
    try:
        warm(btn, qapp)
        mutate(btn)
        # Synchronous: update() bumps the version inline; the posted repaint
        # has not run yet, so the snapshot must be gone right here.
        assert btn._static_cache is None, "mutator must retire the snapshot"
        image = render_full(btn)
        assert image.width() == btn.width()
        assert btn._marquee_driver.dirty_rect(), "marquee must stay live"
        assert btn._static_cache is not None, "full repaint must re-snapshot"
    finally:
        btn.deleteLater()


def test_invalidation_multi_region(qapp) -> None:
    """Region-level writes (update_region / RegionHandle) bust the cache."""
    btn = make_gallery_card()
    try:
        warm(btn, qapp)
        btn.update_region("cover", custom_bg_color=QColor("#112233"))
        assert btn._static_cache is None
        render_full(btn)
        assert btn._static_cache is not None

        btn.region("text").text = "handle write"
        assert btn._static_cache is None
        render_full(btn)
        assert btn._static_cache is not None
    finally:
        btn.deleteLater()


def test_invalidation_static_rows_drop_cache(qapp) -> None:
    """Removing the marquee rows leaves no cache allocated at all."""
    btn = make_single_card()
    try:
        warm(btn, qapp)
        btn.setRows([ButtonRow(text="plain", size=11)])
        assert btn._static_cache is None
        render_full(btn)
        assert btn._marquee_row_paints == []
        assert btn._static_cache is None, "no marquee -> no snapshot"
    finally:
        btn.deleteLater()


def test_no_marquee_never_caches(qapp, monkeypatch) -> None:
    """Plain buttons never take the fast path and never allocate a pixmap."""
    btn = Button(text="hello", size=(120, 40))
    try:
        btn.resize(120, 40)
        btn.show()
        qapp.processEvents()
        render_full(btn)
        render_full(btn)
        assert btn._static_cache is None
        assert btn._marquee_row_paints == []
        assert btn._static_fast_hits == 0

        calls = count_context_builds(btn, monkeypatch)
        render_full(btn)
        assert calls, "no-marquee buttons always run the full pipeline"
        assert btn._static_cache is None
    finally:
        btn.deleteLater()


def test_fitting_marquee_row_never_caches(qapp) -> None:
    """marquee=True rows that fit draw as plain text: no cache, no timer."""
    btn = Button(
        rows=[ButtonRow(text="fits", size=11, marquee=True)],
        size=(200, 40),
    )
    try:
        btn.resize(200, 40)
        btn.show()
        qapp.processEvents()
        render_full(btn)
        assert btn._static_cache is None
        assert btn._static_fast_hits == 0
    finally:
        btn.deleteLater()


def test_resize_busts_cache(qapp) -> None:
    """Resize retires the snapshot and re-snapshots at the new geometry."""
    btn = Button(
        rows=[ButtonRow(text=LONG_TEXT, size=11, marquee=True)],
        size=(0, 64),
    )
    try:
        btn.resize(150, 64)
        warm(btn, qapp)
        assert btn._static_cache is not None
        btn.resize(170, 64)
        assert btn._static_cache is None, "resize must retire the snapshot"
        render_full(btn)
        assert btn._static_cache is not None
        assert btn._static_cache.size().width() == 170
    finally:
        btn.deleteLater()


def test_dpr_change_busts_cache(qapp, monkeypatch) -> None:
    """A devicePixelRatio change retires the snapshot (spoofed DPR)."""
    btn = make_gallery_card()
    try:
        warm(btn, qapp)
        key_before = btn._static_key
        monkeypatch.setattr(
            ButtonImpl, "devicePixelRatioF", lambda self: 2.0)
        assert btn._static_key_now() != key_before
        calls = count_context_builds(btn, monkeypatch)
        dirty = btn._marquee_driver.dirty_rect()
        hits0 = btn._static_fast_hits
        render_row_region(btn, dirty)
        assert btn._static_fast_hits == hits0, "DPR change must miss fast path"
        assert calls, "DPR change must run the full pipeline"
    finally:
        btn.deleteLater()


def test_ripple_blocks_fast_path(qapp, monkeypatch) -> None:
    """An in-flight ripple forces the full pipeline (no frozen wave)."""
    btn = make_gallery_card()
    try:
        warm(btn, qapp)
        # Simulate an in-flight wave without posting update() (which would
        # bump the version anyway): the guard must decide on ripple state.
        btn._ripple._center = QPointF(10.0, 10.0)  # noqa: SLF001
        try:
            assert btn._ripple_active()
            cache_before = btn._static_cache
            calls = count_context_builds(btn, monkeypatch)
            hits0 = btn._static_fast_hits
            render_row_region(btn, btn._marquee_driver.dirty_rect())
            assert btn._static_fast_hits == hits0
            assert calls, "active ripple must run the full pipeline"
            assert btn._static_cache is cache_before, (
                "must not bake a ripple frame into the snapshot")
        finally:
            btn._ripple.cancel()  # noqa: SLF001
        qapp.processEvents()
    finally:
        btn.deleteLater()


def test_ripple_colors_do_not_corrupt(qapp) -> None:
    """Gradient ripple config alone keeps the idle fast path valid."""
    btn = make_gallery_card()
    try:
        warm(btn, qapp)
        btn.setRippleColors(QColor("#ff0000"), QColor("#00ff00"))
        # No repaint scheduled by the setter and no wave in flight: the
        # idle snapshot still describes every painted pixel.
        assert btn._static_cache is not None
        hits0 = btn._static_fast_hits
        render_row_region(btn, btn._marquee_driver.dirty_rect())
        assert btn._static_fast_hits == hits0 + 1
        btn.clearRippleColors()
    finally:
        btn.deleteLater()


class _NoopLayer(Layer):
    scope = "widget"

    def applies(self, ctx) -> bool:  # noqa: ANN001, ANN202
        return False

    def draw(self, ctx, tm) -> None:  # noqa: ANN001, ANN202
        pass


def test_custom_layers_disable_cache(qapp) -> None:
    """Opaque host paint code opts out: never snapshot, never fast-path."""
    btn = Button(
        rows=[ButtonRow(text=LONG_TEXT, size=11, marquee=True)],
        size=(120, 40),
        extra_layers=[_NoopLayer()],
    )
    try:
        btn.resize(120, 40)
        btn.show()
        qapp.processEvents()
        assert not btn._static_cache_allowed
        render_full(btn)
        assert btn._static_cache is None
        assert btn._static_fast_hits == 0
    finally:
        btn.deleteLater()


def test_overlay_painter_disables_cache(qapp) -> None:
    btn = Button(
        rows=[ButtonRow(text=LONG_TEXT, size=11, marquee=True)],
        size=(120, 40),
        overlay_painter=lambda painter, rect: None,
    )
    try:
        btn.resize(120, 40)
        btn.show()
        qapp.processEvents()
        assert not btn._static_cache_allowed
        render_full(btn)
        assert btn._static_cache is None
    finally:
        btn.deleteLater()


def test_draw_marquee_rows_entry(qapp) -> None:
    """RowsContent.draw_marquee_rows paints only the crawling rows."""
    # Square corners: rounded-corner AA fringe composites over different
    # bases in a pixmap snapshot vs a window-background render, which is
    # static-layer territory (covered by the fast-vs-full parity tests).
    btn = Button(
        regions=[
            ButtonRegion(id="cover", pixmap=_cover_pixmap()),
            ButtonRegion(
                id="text",
                rows=[
                    ButtonRow(text="2m ago", size=11),
                    ButtonRow(
                        text=LONG_TEXT,
                        size=11,
                        h_align=Qt.AlignmentFlag.AlignLeft,
                        marquee=True,
                    ),
                ],
            ),
        ],
        split=VerticalSplit(),
        size=(120, 64),
        content_padding=(8, 4, 8, 4),
        corner_radius=0,
        corner_radii=(0, 0, 0, 0),
    )
    btn.resize(120, 64)
    try:
        warm(btn, qapp)
        region = next(r for r in btn.regions() if r.id == "text")
        content = btn._build_region_content(region)  # noqa: SLF001
        assert isinstance(content, RowsContent)
        driver = btn._marquee_driver
        driver.phase = 7.0
        btn._marquee_phase = 7.0  # noqa: SLF001

        full_image = render_full(btn)
        # Reset the row area to the static snapshot, then replay only the
        # crawl through the entry: the base is identical by construction, so
        # any glyph misplacement shows up as a mismatch. (A bare transparent
        # base would mismatch on rounded-corner fringe by compositing alone,
        # which belongs to the static layer, not this entry.)
        assert btn._static_cache is not None
        static = btn._static_cache.toImage()
        assert static.size() == full_image.size()
        dirty = driver.dirty_rect()
        replay = full_image.copy()
        painter = QPainter(replay)
        painter.drawImage(dirty.topLeft(), static, dirty)
        ctx = btn._make_context(painter)  # noqa: SLF001
        scoped = next(
            s for s in btn.iter_regions(ctx) if s.region_id == "text")
        content.draw_marquee_rows(painter, scoped, driver.phase)
        painter.end()

        mismatches = [
            (x, y)
            for y in range(dirty.top(), dirty.bottom() + 1)
            for x in range(dirty.left(), dirty.right() + 1)
            if full_image.pixel(x, y) != replay.pixel(x, y)
        ]
        assert mismatches == [], f"{len(mismatches)} row pixels differ"
    finally:
        btn.deleteLater()


def test_skip_render_keeps_dirty_union(qapp) -> None:
    """skip_marquee_rows renders backgrounds only, union untouched."""
    btn = make_gallery_card()
    try:
        warm(btn, qapp)
        driver = btn._marquee_driver
        union_before = driver.dirty_rect()
        renders_before = driver.strip_cache_renders

        image = QImage(btn.size(), QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        ctx = btn._make_context(painter)  # noqa: SLF001
        scoped = next(
            s for s in btn.iter_regions(ctx) if s.region_id == "text")
        assert isinstance(scoped.region_content, RowsContent)
        scoped.region_content.draw(
            scoped, ThemeManager.get_instance(), skip_marquee_rows=True)
        painter.end()

        assert driver.dirty_rect() == union_before
        assert driver.strip_cache_renders == renders_before, (
            "skip path must not re-render strips")
    finally:
        btn.deleteLater()


def test_hover_state_busts_key(qapp) -> None:
    """HOVERED flips take the full pipeline even with a warm snapshot."""
    btn = make_gallery_card()
    try:
        warm(btn, qapp)
        from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
        btn._set_region_state("text", ButtonState.HOVERED, True)  # noqa: SLF001
        assert btn._static_cache is None
        render_full(btn)
        assert btn._static_cache is not None
        btn._set_region_state("text", ButtonState.HOVERED, False)  # noqa: SLF001
    finally:
        btn.deleteLater()


def test_ui_scale_busts_cache(qapp) -> None:
    """UiScale changes retire the snapshot (fonts/layout rescale)."""
    btn = make_gallery_card()
    try:
        warm(btn, qapp)
        scale = UiScale.get_instance()
        factor_before = scale.factor()
        try:
            scale.set_factor(2.0)
            assert btn._static_cache is None
        finally:
            scale.set_factor(factor_before)
            qapp.processEvents()
    finally:
        btn.deleteLater()
