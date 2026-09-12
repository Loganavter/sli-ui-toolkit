# Why Not QML (and Why Probably Never)

QML would, in theory, be better. Declarative UI, GPU scene graph, fluid
animations, designer handoff from Figma, and a training-data footprint
orders of magnitude larger than this library. None of that is disputed
below. This document explains why this project still stays on
custom-painted `QWidget`s — and which conditions would have to change
for that decision to flip.

Short version: **we are neither a carmaker nor the KDE community.**
QML pays off for designer-driven composition at industrial scale. This
project does painter-driven invention at workshop scale.

## Who QML is for (and why we are not them)

- **Automotive / embedded / industrial.** Fixed hardware, own display,
  C++ backend, designer UI with a ten-year life: Mercedes MBUX,
  Renault OpenR Link, Hyundai ccOS, medical/industrial consoles.
  One binary, GPU scene, animations — QML's home turf.
- **KDE / mobile Linux.** The entire Plasma shell (panel, widgets,
  lock screen, KWin scripts), Sailfish Silica, Lomiri. Note what KDE
  keeps on Widgets: Dolphin, Kate, Okular, Konsole — dense instruments
  stay Widgets; QML owns shell and chrome.
- **Rare desktop outliers.** VLC 4.0 being the visible one. Standard
  business desktop remains Widgets or web.

A compact custom desktop instrument shared by small host apps sits in
none of these buckets.

## Hard constraints (verified against Qt 6.8–6.13 docs)

These are not opinions; the wording is byte-identical across Qt
versions, with per-window relaxation deferred since the 6.4 blog:

1. **One graphics API per top-level window.** A `QQuickWidget` and a
   `QQuickWidget` and a GPU canvas widget in one window must agree on the
   backend, set once and early. A second negotiator does not fall back —
   one of them silently stops rendering. Hosts embedding GPU canvas
   widgets next to Quick chrome lose backend flexibility the moment
   Quick moves in.
   (`QQuickWidget` Graphics API Support, `QRhiWidget` Detailed
   Description, `QQuickWindow::setGraphicsApi`.)
2. **Transparent Quick does not blend under raster siblings.**
   `QQuickWidget` is composited before regular widgets; widgets
   underneath stay invisible. `WA_AlwaysStackOnTop` "fixes" it by
   forbidding anything on top. Verified live as recently as 2025
   (`KDDockWidgets#658` on Wayland). Practical airspace rule: Quick
   chrome only *above* an opaque base layer, never transparent Quick
   *below* overlays that expect blending.
3. **Custom scene-graph integrations do not port.** Anything a host
   renders through a raw graphics API inside its own canvas re-expresses
   only as `QSGRenderNode` / underlay / texture items — a rewrite with
   its own threading traps (`prepare()` vs `render()`,
   `DirectConnection`, no copy ops inside `render()` on Vulkan/Metal),
   not a port.
4. **One technology per window.** CSD shell + mask sync,
   transient-parent popup policy, grab/focus ownership must live in a
   single stack per window. Mixing replays
   the compositor-stacking bug class, not a new one.

## What evaporates vs what persists

Judged over ~90 past tasks (internal investigations plus the full
changelog), steady-state *after* a hypothetical completed migration,
ignoring one-time rewrite cost: **~half gets cheaper, ~a third stays
or gets costlier.**

Evaporates (maintenance QML simply has no such class): backing-store
alpha holes, double-scaled strides, theme-switch freezes,
`setUpdatesEnabled` storms, CSD 1-bit mask juggling, autofill fights,
freed-C++-pointer guards, `singleShot` reentrancy. Of ~30 past
bugfixes, 17 vanish.

Persists or gets costlier (custom policy, re-proof burden): the
navigation graph, flyout dismiss/coexist/cascade rules, painted text
selection semantics, the inspector over custom layers, bespoke
gestures, per-region button paint. These are the systems the project
keeps investing in — the migration does not touch them, it re-bills
them, plus ~5 new QML-native classes (binding loops with false
positives and no `qmllint` coverage, scene-graph timing, render-thread
sync, xdg-popup grab races — several with 2024–2025 bug IDs).

Net: QML deletes paint debt and lifecycle garbage. It deletes none of
the systems this toolkit exists for.

## The testing gap (decisive for a Python shop)

- Component level: Qt Quick Test is alive but C++/JS; no Python bridge.
- Python level: `pytest-qml` dead since 2020 (PySide2-only);
  `pytest-qt` has no QML API (open issue since 2018); `qtbot`
  cannot see `QQuickItem`.
- System level: commercial Squish (no community edition) — or
  openQA-scale infrastructure (image builds, VM workers, AT-SPI
  drivers), i.e. heavier than a 30-second `pytest` run by an order
  of magnitude.

The current stack's determinism (synchronous paint/focus/geometry,
offscreen runs, contract tests) was earned over years. QML resets
that harness to zero in a worse currency: scene-graph timing instead
of synchronous asserts.

## The dataset discount is real but bounded

Standard QML patterns live in training data; this library's
semantics live only in this repo. An agent (or a newcomer) assembles
standard QML an order of magnitude faster. But training data knows
"how a popup is written", not "how *our* flyouts behave": group
policies, anchor tracking, trial-dispatch, tokens, store bridges
stay repo-specific reading either way. The discount applies to
components, never to systems.

## What would flip this decision

All of these at once: the roadmap turns from inventing controls to
assembling standard flows; animation/effects needs exceed snapshot
compositing; all host apps commit to a synchronized shell migration
(no dual-stack years); QA budget appears (Squish or openQA-scale
infra). None of these is on the horizon — hence "probably never".

## See also

- [Logging convention](../dev/LOGGING.md) — shared diagnostics discipline
- [Design language](../dev/DESIGN_LANGUAGE.md) — tokens, variants, visual rules
- [Flyout system](FLYOUT_SYSTEM.md) — the policy system QML has no equivalent of
- [Navigation](../dev/NAVIGATION.md) — app-wide arrow-key ownership
- Qt docs: `QQuickWidget` Limitations + Graphics API Support,
  `QRhiWidget` Detailed Description, `QSGRenderNode`, Qt Quick Test
