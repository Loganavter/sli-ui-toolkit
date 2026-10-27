# Fixture for tests/test_dpr_contract.py — mode: ratio-hardcoded.
# provenance: tests/test_paint_cache.py:442-458 @ d841b67 (3ccfe91^)
# shape: verbatim.
# shipped: yes, adjacent to PR #124. The spoofed ratio was 2.0 — a no-op under
#   QT_SCALE_FACTOR=2, where the widget is already at DPR 2, so the test could not fail
#   on the screen it named. #124 changed the value to 3.0; that live site is the single
#   recorded entry in tests/dpr_contract_allowlist.py.
#@findings: 1
#@expect: ratio-hardcoded | monkeypatch.setattr(
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
