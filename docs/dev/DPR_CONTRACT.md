# The DPR contract — HiDPI rasters, as a machine gate

Every raster in this toolkit (`QPixmap`, `QImage`, `QBitmap`) can be broken in a
handful of ways, and the toolkit has shipped four of them at once (PR #124). This
document is the catalog the gate encodes: `tests/test_dpr_contract.py` scans
`src/sli_ui_toolkit/**` (and the ratio-literal shape in `tests/**`) with AST
detectors, one per failure mode, and `tests/test_dpr_contract_selftest.py` keeps
every detector honest against real pre-fix code.

## The one fact everything rests on

`QPainter` scales **every command** by the paint device's
`devicePixelRatio`: `combinedTransform` is already `scale(dpr)` while
`worldTransform` stays identity. Three consequences, and nothing else in this
document needs to be memorised:

1. a raster that must cover `logical` px is allocated at
   **`round(logical * dpr)`** and tagged with `setDevicePixelRatio(dpr)`;
2. painting into it stays in **logical** coordinates — the painter applies the
   ratio for you;
3. therefore a manual `painter.scale(dpr, dpr)` on a tagged device scales
   commands **twice**, and a raster allocated in logical px and then tagged gets
   a logical canvas of `size / dpr`.

The sanitised shape, in full:

```python
pixmap = QPixmap(round(w * dpr), round(h * dpr))   # DEVICE px
pixmap.setDevicePixelRatio(dpr)                    # before the painter is built
pixmap.fill(Qt.GlobalColor.transparent)
painter = QPainter(pixmap)
painter.drawText(QRect(0, 0, w, h), ..., text)      # LOGICAL px
painter.end()
```

## Modes

`tests/test_dpr_contract.py` rule ids, in registry order.

| mode | shape the scanner sees | how it looks on screen | sanctioned answer |
| --- | --- | --- | --- |
| `raster-logical-tagged` | `QPixmap(<logical>)` / `QImage(<logical>)` in a function that then calls `setDevicePixelRatio(...)`, where no size argument multiplies by a ratio name and none is another raster's `.size()`/`grab()` | content occupies the top-left `1/dpr` of its box — at 200% a full-widget snapshot is a quarter-size picture in the corner, and every fast frame blits that quadrant | allocate `round(logical * dpr)`; keep painting in logical px |
| `ratio-dropped-on-copy` | a new `QPixmap`/`QImage` sized from another raster's `.size()`/`.width()`/`.height()` in a function with no ratio tag (or a literal `1`) | the copy paints `dpr`× too large, art pinned to the top-left; a tinted 64×64@2x icon covers a 128×128 box | `result.setDevicePixelRatio(source.devicePixelRatio())` — the `tinted_pixmap` sibling is the reference |
| `ratio-rounded` | `int(dpr)`, `round(dpr)`, `math.trunc(dpr)` — the *ratio* itself, not a device size | at 125%/150% the ratio collapses to 1: the raster is visibly soft and up to one device pixel per logical pixel short | round the **device size** (`round(logical * dpr)`); keep the ratio a float end to end |
| `manual-dpr-scale` | `painter.scale(dpr, dpr)` with ratio arguments, or inside a function that tags the device | commands land at `dpr²`: text and art are twice the intended size, clipped by the box | delete the call — the tagged device already scales |
| `ratio-hardcoded` | `setDevicePixelRatio(2)`; in tests, `assert x.devicePixelRatio() == 2` or `setattr(X, "devicePixelRatioF", lambda self: 2.0)` | correct on exactly one screen; everywhere else the raster is soft (DPR > literal) or oversized (DPR < literal) | read the paint device: `devicePixelRatioF()`; in a test, pass the live ratio or a value the run does not use, and say why |
| `pixmap-size-as-logical` | `<raster>.width()` / `.height()` / `.size()` in a function that is ratio-aware (tag, `devicePixelRatio` read, or a ratio name) with no `deviceIndependentSize()` in scope — excluding `w / ratio`, an emptiness check against `0`, a copy's allocation size, and the `size()` inside `.size().width()` | geometry drifts by up to `dpr`× — a centred image sits at twice the intended inset at 200%, an aspect fit crops the long side | `raster.deviceIndependentSize()` (a `QSizeF` in logical px), or divide the device px by the ratio |
| `dpr-assumed-1` | a device-ratio parameter with a numeric default (`dpr: float = 1.0`) or a module-level `DPR = 1.0`, in a unit that never reads `devicePixelRatio(F)` | the call site silently rasterizes at 1× on a HiDPI screen: soft text, aliased edges, no error | take the ratio from the paint device, or require it — `dpr: float | None = None` resolved from the device at the use site |

Two shapes are deliberately **not** detector rules:

- **a test hand-rolling a size comparison** (`assert image.width() == btn.width()`,
  the pre-#124 harness). It cannot be separated statically from its benign twins
  (`assert scaled.width() >= 20` is a coverage bound; `assert pix.width() == 8`
  round-trips the source's own pixels), and the sanitised answer already exists:
  call `assert_device_sized()` instead of re-deriving the arithmetic;
- **a `.scaled(w, h)` call with logical arguments.** Whether `w`/`h` are device
  or logical px depends on the caller, which a single-function scan cannot see:
  the sanctioned `_device_scaled(source, dev_w, dev_h, ratio)` is
  `source.scaled(dev_w, dev_h)` + a tag, and the broken form is
  `source.scaled(tw, th)` + a tag — the two differ only in where the numbers came
  from. So the *allocation* is not judged; the answer is to keep the tagging
  local and visible (`_device_scaled` in `buttons/content.py`), and the
  `pixmap-size-as-logical` rule still catches the geometry half of a bad fit.

## The positive invariant — `assert_device_sized(pixmap, logical_rect)`

Live in `tests/test_dpr_contract.py`; import it instead of re-writing the
arithmetic:

```python
from tests.test_dpr_contract import assert_device_sized

strip = _render_marquee_strip(..., dpr=1.25)
assert_device_sized(strip, QRect(0, 0, cycle, height))
```

It asserts both halves — `pixmap.size() == round(logical * ratio)` and
`pixmap.deviceIndependentSize() == logical` — and its failure messages name the
shape you probably just wrote ("allocated in LOGICAL px then tagged", "the ratio
tag was dropped"). `ratio=` defaults to the pixmap's own tag; pass it explicitly
when you know the device ratio the raster was built for. The half-pixel
tolerance absorbs integer rounding of the device size.

## Allowlist — `tests/dpr_contract_allowlist.py`

`{(relative_path, function_name, rule_id): reason}`, repo-relative paths
(`src/…`, `tests/…`). Shrink-only: `test_allowlist_is_shrink_only` fails when an
entry no longer matches a finding, so a fixed site cannot keep its exemption, and
`test_allowlist_entries_carry_a_reason` refuses an unexplained row. **Empty is the
normal state.** Today it holds exactly one entry —
`tests/test_paint_cache.py::test_dpr_change_busts_cache`, which spoofs a device
ratio on purpose; distinguishing "spoof a change" from "assume the screen" needs
the live ratio, which no static scan can know.

## Adding a new mode

1. **Find the numbers.** Reproduce the defect and write down what the screen
   shows and what the arithmetic was (a mode without a measured symptom is a
   hypothesis, not a rule). Grep the history first:
   `git rev-list --all --objects | awk '$2 ~ /\.py$/ {print $1}' | sort -u |
   while read b; do git cat-file -p "$b"; done | grep -n <shape>`.
2. **Add a fixture from real code.** `git show <commit>^:<path>` → the failing
   function, verbatim, into `tests/fixtures/dpr_contract/`, with a header:
   `# provenance: <path>:<line> @ <commit>`, `#@findings: <n>`, and one
   `#@expect: <rule> | <source substring>` per expected finding. If history has
   **no** instance, the header must say `provenance: NONE` and explain the search
   — and the mode must be added to `_NO_HISTORY_RULES` in the selftest. A
   detector calibrated only on an invented snippet is a detector calibrated on a
   drawing of the bug.
3. **Add the detector.** `Rule(id, scope, summary, detect)` where
   `detect(unit) -> [(lineno, reason)]`; `unit` exposes the function's own nodes,
   parents, ratio names, raster names and assignments. Scope is `src` or `tests`.
4. **Run it over the tree**, not only over the fixture:
   `PYTHONPATH=$PWD/src python3 -c "from tests.test_dpr_contract import raw_findings;
   print(*raw_findings(), sep='\n')"`. A new mode that fires on hundreds of
   innocent sites is mis-specified — narrow the shape (see the two "not rules"
   above) before reaching for the allowlist.
5. **Add the allowlist entry only if the site is correct**, with a reason that
   explains why the shape is right here. Then add the row to the table above —
   `test_rule_registry_matches_the_documented_catalog` fails until you do.

Red-before proof for the whole gate at the time it landed (PR that introduced
this contract): the pre-#124 files copied to `.probe/prefix/`
(`git show 3ccfe91^:<path>`), scanned with the same function — 13 findings in 4
of the 6 files (`content.py` 10 × `pixmap-size-as-logical`, `icon_manager.py` 1 ×
`ratio-dropped-on-copy`, `button.py` 1 + `marquee_text.py` 1 ×
`raster-logical-tagged`), and 0 on `rounded_body.py` / `sidebar_nav_list/icons.py`
— the two working siblings. The current tree reports 1 finding, allowlisted.

`test_probe_finds_the_four_shipped_defects_in_whole_files` re-runs that proof when
`.probe/prefix/` exists and skips otherwise (it is not a committed artifact).

## Running it

```bash
PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen python3 -m pytest \
    tests/test_dpr_contract.py tests/test_dpr_contract_selftest.py -q -o addopts=""
# the scan is static, so a second ratio must not change the verdict:
QT_SCALE_FACTOR=2 PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen python3 -m pytest \
    tests/test_dpr_contract.py -q -o addopts=""
```

The behavioural guards for the four shipped defects live in
`tests/test_dpr_rasters.py`; this contract is the structural half — it stops the
next instance from being written somewhere the behavioural tests do not look.
