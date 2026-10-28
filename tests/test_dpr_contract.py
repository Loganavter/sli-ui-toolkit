"""AST contract: every HiDPI raster is allocated in DEVICE px, tagged, painted in logical px.

Why a machine gate instead of one more regression test: PR #124 shipped four
separate HiDPI defects and each was found by eye, one widget at a time. The
underlying arithmetic is fixed and small, so the failure *shapes* are
enumerable — and every one of them is decidable without a window:

``QPainter`` scales every command by the paint device's ratio
(``combinedTransform`` = dpr, ``worldTransform`` = identity). So a raster that
must cover ``logical`` px is allocated at ``round(logical * dpr)`` and tagged
with ``dpr``; the painter then paints it back in logical coordinates. Every bug
in this family is a departure from that one sentence, and each departure has a
shape a parser can see.

The seven modes (see ``docs/dev/DPR_CONTRACT.md`` for the table):

``raster-logical-tagged``
    ``QPixmap(<logical>)`` / ``QImage(<logical>)`` in a function that then tags
    a ratio: the tagged canvas becomes ``logical / dpr`` — the content lands in
    the top-left quadrant at DPR 2. Shipped: button static snapshot, marquee
    strip.
``ratio-dropped-on-copy``
    a new raster allocated from another raster's ``.size()`` with no ratio tag
    (or a literal ``1``): the copy paints ``dpr``× too large, art pinned to the
    corner. Shipped: the icon recolour.
``ratio-rounded``
    ``int(dpr)`` / ``round(dpr)``: a fractional DPR (125% / 150%) collapses to
    an integer, so the raster is off by up to a device pixel per logical one.
``manual-dpr-scale``
    ``painter.scale(dpr, dpr)`` on an already-tagged device: the commands are
    scaled twice.
``ratio-hardcoded``
    ``setDevicePixelRatio(2)``, or a test that substitutes/asserts a literal
    ratio instead of reading the live one — a no-op on any screen that is not
    that ratio.
``pixmap-size-as-logical``
    ``<raster>.width()`` / ``.height()`` / ``.size()`` used as logical geometry
    in ratio-aware code without ``deviceIndependentSize()``: at DPR 2 the
    layout offsets by twice the intended distance. Shipped: the cover/contain
    fit (geometry right, raster upscaled) and a test harness that compared a
    device-resolution render against a logical one.
``dpr-assumed-1``
    a ``dpr=1.0`` default/constant on a raster-layout signature with no device
    read behind it: the caller silently rasterizes at 1× whatever the screen.

Offenders that are intentional (or not yet migrated) live in
``tests/dpr_contract_allowlist.py`` keyed by ``(path, function, rule)``; that
list is shrink-only — a test below fails if an entry no longer matches code.
Empty is the desired state.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, NamedTuple

import pytest

from tests.dpr_contract_allowlist import ALLOWLIST

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGE_ROOT = _REPO_ROOT / "src" / "sli_ui_toolkit"
_TESTS_ROOT = Path(__file__).resolve().parent
_FIXTURE_ROOT = _TESTS_ROOT / "fixtures"
_DOC_PATH = _REPO_ROOT / "docs" / "dev" / "DPR_CONTRACT.md"

#: The complete rule catalog. Adding a mode means: a real bad-code fixture, a
#: detector, this registry, and a row in ``docs/dev/DPR_CONTRACT.md``.
DOCUMENTED_RULES: tuple[str, ...] = (
    "raster-logical-tagged",
    "ratio-dropped-on-copy",
    "ratio-rounded",
    "manual-dpr-scale",
    "ratio-hardcoded",
    "pixmap-size-as-logical",
    "dpr-assumed-1",
    "icon-app-ratio",
)

#: Raster constructors whose size arguments are the allocation decision.
_RASTER_CTORS = frozenset({"QPixmap", "QImage", "QBitmap"})
#: Methods that return a NEW raster (a copy/normalisation the tag can be lost on).
_RASTER_PRODUCERS = frozenset(
    {"scaled", "copy", "toImage", "fromImage", "grab", "mirrored", "transformed"}
)
#: Calls that read a size off a raster; used as the allocation's size source.
_SIZE_GETTERS = frozenset({"size", "width", "height"})
#: Identifiers that name a raster, whatever their binding (covers rasters that
#: arrive through a helper call the parser cannot see into, e.g. ``scaled = _cache_scaled(...)``).
_RASTER_NAME_HINTS = (
    "pixmap",
    "image",
    "bitmap",
    "raster",
    "snapshot",
    "cache",
    "strip",
    "scaled",
)
_TRANSPARENT_INTS = frozenset({"int", "round", "trunc", "floor", "ceil"})


class Finding(NamedTuple):
    """One rule violation, in the shape the repo's other gates use."""

    path: str
    lineno: int
    rule: str
    function: str
    reason: str


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _is_ratio_ident(ident: str) -> bool:
    """Strict device-pixel-ratio identifiers (``dpr``, ``src_ratio``, …).

    Deliberately excludes the bare ``ratio``: this codebase uses it for
    *typography* shares (``ButtonRow.ratio``, ``row.ratio``), which have nothing
    to do with the paint device. A bare ``ratio`` counts as a device ratio only
    inside a unit that already speaks DPR — see :attr:`_Unit.ratio_names`.
    """
    name = ident.lower().lstrip("_")
    if name in {"dpr", "devicepixelratio", "devicepixelratiof", "pixelratio"}:
        return True
    return name.endswith(("_dpr", "_pixelratio", "_devicepixelratio"))


def _is_loose_ratio_ident(ident: str) -> bool:
    name = ident.lower().lstrip("_")
    return name == "ratio" or name.endswith("_ratio")


def _is_raster_ident(ident: str) -> bool:
    name = ident.lower()
    return any(hint in name for hint in _RASTER_NAME_HINTS)


def _numeric_literal(node: ast.AST) -> float | None:
    """The value of a pure numeric literal (``1``, ``1.0``, ``-1``), else ``None``."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        inner = _numeric_literal(node.operand)
        if inner is None:
            return None
        return -inner if isinstance(node.op, ast.USub) else inner
    return None


def _annotation_mentions_raster(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Parameter names annotated as a raster (``QPixmap`` / ``QImage`` / ``QBitmap``)."""
    args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    names: set[str] = set()
    for arg in args:
        if arg.annotation is None:
            continue
        annotation = ast.unparse(arg.annotation)
        if any(ctor in annotation for ctor in _RASTER_CTORS):
            names.add(arg.arg)
    return names


def _body_nodes(body: list[ast.stmt]) -> list[ast.AST]:
    """Nodes of *body*, never descending into a nested ``def`` (its own unit)."""
    out: list[ast.AST] = []
    stack = list(reversed(body))
    while stack:
        node = stack.pop()
        out.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))
    return out


@dataclass(frozen=True)
class _Unit:
    """One analysis scope: a function (own body only) or a module body."""

    name: str
    definition: ast.FunctionDef | ast.AsyncFunctionDef | None
    nodes: tuple[ast.AST, ...]
    parents: dict[int, ast.AST]
    idents: frozenset[str]
    ratio_names: frozenset[str]
    raster_names: frozenset[str]
    assignments: dict[str, ast.expr]
    tagged: bool
    tag_arguments: tuple[ast.expr, ...]
    reads_device_ratio: bool

    @property
    def tags_literal_one(self) -> bool:
        """True when every ``setDevicePixelRatio`` call passes a literal ``1``."""
        return bool(self.tag_arguments) and all(
            (value := _numeric_literal(arg)) is not None and value == 1.0
            for arg in self.tag_arguments
        )


def _build_unit(
    name: str,
    definition: ast.FunctionDef | ast.AsyncFunctionDef | None,
    body: list[ast.stmt],
) -> _Unit:
    nodes = _body_nodes(body)
    parents: dict[int, ast.AST] = {}
    for node in nodes:
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    idents: set[str] = set()
    assignments: dict[str, ast.expr] = {}
    tag_arguments: list[ast.expr] = []
    tagged = False
    reads_device_ratio = False
    for node in nodes:
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
            if node.attr in {"devicePixelRatio", "devicePixelRatioF"}:
                reads_device_ratio = True
        elif isinstance(node, ast.Call) and _call_name(node) == "setDevicePixelRatio":
            tagged = True
            tag_arguments.extend(node.args)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                assignments[node.target.id] = node.value

    strict = {ident for ident in idents if _is_ratio_ident(ident)}
    dpr_aware = bool(strict) or reads_device_ratio or tagged
    ratio_names = set(strict)
    if dpr_aware:
        ratio_names |= {ident for ident in idents if _is_loose_ratio_ident(ident)}

    raster_names = {ident for ident in idents if _is_raster_ident(ident)}
    if definition is not None:
        raster_names |= _annotation_mentions_raster(definition)
    for target, value in assignments.items():
        if isinstance(value, ast.Call) and _call_name(value) in (
            _RASTER_CTORS | _RASTER_PRODUCERS
        ):
            raster_names.add(target)

    return _Unit(
        name=name,
        definition=definition,
        nodes=tuple(nodes),
        parents=parents,
        idents=frozenset(idents),
        ratio_names=frozenset(ratio_names),
        raster_names=frozenset(raster_names),
        assignments=assignments,
        tagged=tagged,
        tag_arguments=tuple(tag_arguments),
        reads_device_ratio=reads_device_ratio,
    )


def iter_units(tree: ast.Module) -> Iterator[_Unit]:
    yield _build_unit("<module>", None, tree.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield _build_unit(node.name, node, node.body)


def _is_raster_expr(node: ast.AST, unit: _Unit) -> bool:
    """True when *node* denotes a raster (by binding, annotation or name)."""
    if isinstance(node, ast.Name):
        return node.id in unit.raster_names
    if isinstance(node, ast.Attribute):
        return node.attr in unit.raster_names
    if isinstance(node, ast.Call):
        name = _call_name(node)
        if name in (_RASTER_CTORS | _RASTER_PRODUCERS):
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr in _SIZE_GETTERS:
            return _is_raster_expr(node.func.value, unit)
    return False


def _contains_ratio(node: ast.AST, unit: _Unit) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in unit.ratio_names:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in unit.ratio_names:
            return True
    return False


def _resolve(expr: ast.expr, unit: _Unit) -> ast.expr:
    """Follow a ``Name`` to its last assignment (one hop chain, cycle-safe)."""
    seen: set[str] = set()
    while isinstance(expr, ast.Name) and expr.id in unit.assignments:
        if expr.id in seen:
            break
        seen.add(expr.id)
        expr = unit.assignments[expr.id]
    return expr


def _is_raster_size_read(expr: ast.expr, unit: _Unit) -> bool:
    """``<raster>.size()`` / ``.width()`` / ``.height()`` — this raster IS the source."""
    return (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr in _SIZE_GETTERS
        and _is_raster_expr(expr.func.value, unit)
    )


def _size_arguments(node: ast.Call, unit: _Unit) -> list[ast.expr]:
    """The size expressions an allocation is built from (``[]`` when not a sizing call)."""
    if not node.args:
        return []
    resolved = [_resolve(arg, unit) for arg in node.args[:2]]
    first = resolved[0]
    size_shaped = (
        len(node.args) >= 2
        or (isinstance(first, ast.Call) and _call_name(first) in {"QSize", "QSizeF"})
        # ``QPixmap(self.size())`` — a QSize-valued read, widget or raster.
        or (isinstance(first, ast.Call) and _call_name(first) in _SIZE_GETTERS)
    )
    if not size_shaped:
        return []
    return resolved[: len(node.args) if len(node.args) < 2 else 2]


def _is_ratio_expr(node: ast.AST, unit: _Unit) -> bool:
    """The expression *is* a device ratio (not merely contains one)."""
    if isinstance(node, ast.Name):
        return node.id in unit.ratio_names
    if isinstance(node, ast.Attribute):
        return node.attr in unit.ratio_names
    if isinstance(node, ast.Call) and len(node.args) == 1:
        if _call_name(node) == "float":
            return _is_ratio_expr(node.args[0], unit)
    if isinstance(node, ast.Call) and not node.args:
        # ``self.devicePixelRatioF()`` — reading the ratio off the device.
        return isinstance(node.func, ast.Attribute) and node.func.attr in unit.ratio_names
    return False


def _scaled_by_ratio(node: ast.AST, unit: _Unit) -> bool:
    """``node`` sits inside ``node * ratio`` / ``node / ratio`` (a device-px conversion)."""
    parent = unit.parents.get(id(node))
    if not isinstance(parent, ast.BinOp) or not isinstance(
        parent.op, (ast.Mult, ast.Div)
    ):
        return False
    other = parent.right if parent.left is node else parent.left
    return _contains_ratio(other, unit)


def _compared_with_zero(node: ast.AST, unit: _Unit) -> bool:
    parent = unit.parents.get(id(node))
    if not isinstance(parent, ast.Compare):
        return False
    return any(
        _numeric_literal(side) == 0.0 for side in [parent.left, *parent.comparators]
    )


# -- detectors -------------------------------------------------------------
#
# Signature: one unit -> ``[(lineno, reason)]``. The runner attaches path/rule.


def detect_raster_logical_tagged(unit: _Unit) -> list[tuple[int, str]]:
    """A device-sized raster allocated from a LOGICAL size, then tagged."""
    if not unit.tagged:
        return []  # a raster with no ratio tag is not scaled by the painter
    hits: list[tuple[int, str]] = []
    for node in unit.nodes:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in _RASTER_CTORS:
            continue
        sizes = _size_arguments(node, unit)
        if not sizes:
            continue
        if any(_contains_ratio(size, unit) for size in sizes):
            continue  # round(logical * dpr) — the device-sized form
        if any(_is_raster_size_read(size, unit) for size in sizes):
            continue  # sized from another raster: ratio-dropped-on-copy's business
        if any(
            isinstance(sub, ast.Call) and _call_name(sub) == "grab"
            for size in sizes
            for sub in ast.walk(size)
        ):
            continue  # grab() already returns device-resolution pixels
        hits.append(
            (
                node.lineno,
                f"{ast.unparse(node)} allocates a raster from a logical size and is "
                "then tagged with the device ratio — the canvas becomes size/dpr "
                "(half-size at DPR 2). Allocate round(logical * dpr) instead.",
            )
        )
    return hits


def detect_ratio_dropped_on_copy(unit: _Unit) -> list[tuple[int, str]]:
    """A new raster sized from another raster, with the ratio tag lost."""
    if unit.tagged and not unit.tags_literal_one:
        return []  # the copy is tagged with a real ratio
    hits: list[tuple[int, str]] = []
    for node in unit.nodes:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in _RASTER_CTORS:
            continue
        sizes = _size_arguments(node, unit)
        if not any(_is_raster_size_read(size, unit) for size in sizes):
            continue
        hits.append(
            (
                node.lineno,
                f"{ast.unparse(node)} copies a raster's device-pixel size but never "
                "tags the result with its ratio — the copy paints dpr× too large "
                "with the art pinned to the top-left. Tag it with "
                "source.devicePixelRatio().",
            )
        )
    return hits


def detect_ratio_rounded(unit: _Unit) -> list[tuple[int, str]]:
    """``int(dpr)`` / ``round(dpr)`` — a fractional ratio must survive as a float."""
    hits: list[tuple[int, str]] = []
    for node in unit.nodes:
        if not isinstance(node, ast.Call) or len(node.args) != 1:
            continue
        if _call_name(node) not in _TRANSPARENT_INTS:
            continue
        if not _is_ratio_expr(node.args[0], unit):
            continue
        hits.append(
            (
                node.lineno,
                f"{ast.unparse(node)} collapses the device ratio to an integer — "
                "at 125%/150% the raster is off by a fraction of a device pixel per "
                "logical one. Round the DEVICE size (round(logical * dpr)), never "
                "the ratio.",
            )
        )
    return hits


def detect_manual_dpr_scale(unit: _Unit) -> list[tuple[int, str]]:
    """``painter.scale(dpr, dpr)`` on an already-tagged device: double scaling."""
    hits: list[tuple[int, str]] = []
    for node in unit.nodes:
        if not isinstance(node, ast.Call) or len(node.args) < 2:
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "scale":
            continue
        both_ratio = all(_is_ratio_expr(arg, unit) for arg in node.args[:2])
        if not (both_ratio or unit.tagged):
            continue
        hits.append(
            (
                node.lineno,
                f"{ast.unparse(node)} scales the painter by the device ratio that the "
                "paint device already applies (QPainter's combinedTransform is dpr) — "
                "commands land at dpr². Paint in logical px.",
            )
        )
    return hits


def detect_ratio_hardcoded_source(unit: _Unit) -> list[tuple[int, str]]:
    """``setDevicePixelRatio(2)`` — a literal ratio instead of the device's."""
    hits: list[tuple[int, str]] = []
    for node in unit.nodes:
        if not isinstance(node, ast.Call) or _call_name(node) != "setDevicePixelRatio":
            continue
        if not node.args:
            continue
        value = _numeric_literal(node.args[0])
        if value is None:
            continue
        hits.append(
            (
                node.lineno,
                f"{ast.unparse(node)} hardcodes the device ratio — a literal is only "
                "correct on a screen that happens to be that ratio. Read it from the "
                "paint device (devicePixelRatioF()).",
            )
        )
    return hits


def detect_ratio_hardcoded_tests(unit: _Unit) -> list[tuple[int, str]]:
    """A test that substitutes/asserts a literal ratio instead of the live one."""
    hits: list[tuple[int, str]] = []
    for node in unit.nodes:
        if isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            for index, side in enumerate(sides):
                if not (
                    isinstance(side, ast.Call)
                    and isinstance(side.func, ast.Attribute)
                    and side.func.attr in {"devicePixelRatio", "devicePixelRatioF"}
                ):
                    continue
                others = [s for i, s in enumerate(sides) if i != index]
                if not any(_numeric_literal(other) is not None for other in others):
                    continue
                hits.append(
                    (
                        node.lineno,
                        f"{ast.unparse(node)} asserts a live device ratio against a "
                        "literal — the assertion is vacuous on every other screen. "
                        "Compare with widget.devicePixelRatioF().",
                    )
                )
        elif isinstance(node, ast.Call) and _call_name(node) == "setattr":
            if len(node.args) < 3:
                continue
            attribute = node.args[1]
            if not (
                isinstance(attribute, ast.Constant)
                and attribute.value in {"devicePixelRatio", "devicePixelRatioF"}
            ):
                continue
            spoof = node.args[2]
            if not (
                isinstance(spoof, ast.Lambda)
                and _numeric_literal(spoof.body) is not None
            ):
                continue
            hits.append(
                (
                    node.lineno,
                    f"{ast.unparse(node)} spoofs the device ratio with a literal — "
                    "pick a value the live run does not use, and say so in a comment "
                    "(a hardcoded ratio is a no-op on the screen it names).",
                )
            )
    return hits


def detect_pixmap_size_as_logical_source(unit: _Unit) -> list[tuple[int, str]]:
    """``<raster>.width()`` used as logical geometry inside ratio-aware code."""
    ratio_aware = (
        unit.tagged or unit.reads_device_ratio or bool(unit.ratio_names)
    )
    if not ratio_aware or "deviceIndependentSize" in unit.idents:
        return []  # nothing converts device px here, or the honest accessor is used
    hits: list[tuple[int, str]] = []
    for node in unit.nodes:
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr not in _SIZE_GETTERS:
            continue
        if not _is_raster_expr(node.func.value, unit):
            continue
        parent = unit.parents.get(id(node))
        if isinstance(parent, ast.Attribute) and parent.attr in _SIZE_GETTERS:
            continue  # the receiver of another size read (``bitmap.size().width()``)
        if _allocation_sized(node, unit):
            continue  # copied into a new raster: ratio-dropped-on-copy's business
        if _scaled_by_ratio(node, unit) or _compared_with_zero(node, unit):
            continue  # width/ratio is the conversion; > 0 is an emptiness check
        hits.append(
            (
                node.lineno,
                f"{ast.unparse(node)} reads a raster's DEVICE px as logical geometry "
                "— at DPR 2 every offset computed from it is twice the intended "
                "distance. Use deviceIndependentSize(), or divide by the ratio.",
            )
        )
    return hits


def _allocation_sized(node: ast.AST, unit: _Unit) -> bool:
    """``node`` is (part of) the size argument of a raster allocation."""
    current: ast.AST | None = node
    for _ in range(3):
        current = unit.parents.get(id(current)) if current is not None else None
        if current is None:
            return False
        if (
            isinstance(current, ast.Call)
            and isinstance(current.func, ast.Name)
            and current.func.id in _RASTER_CTORS
        ):
            return True
    return False


def detect_dpr_assumed_one(unit: _Unit) -> list[tuple[int, str]]:
    """A ratio default/constant of ``1`` with no device read behind it."""
    if unit.reads_device_ratio:
        return []  # the real ratio is read; a 1.0 default is a documented fallback
    hits: list[tuple[int, str]] = []
    definition = unit.definition
    if definition is not None:
        positional = [*definition.args.posonlyargs, *definition.args.args]
        for arg, default in zip(
            positional[len(positional) - len(definition.args.defaults) :],
            definition.args.defaults,
        ):
            if not _is_ratio_ident(arg.arg) and arg.arg not in unit.ratio_names:
                continue
            if _numeric_literal(default) is None:
                continue
            hits.append(
                (
                    definition.lineno,
                    f"{definition.name}({arg.arg}={ast.unparse(default)}) assumes a "
                    "device ratio in its signature and never reads one — every caller "
                    "silently rasterizes at that ratio. Take the ratio from the paint "
                    "device (or require it, with no default).",
                )
            )
    return hits


def detect_dpr_assumed_one_constant(unit: _Unit) -> list[tuple[int, str]]:
    """A module-level ``DPR = 1.0`` constant with no device read behind it."""
    if unit.definition is not None or unit.reads_device_ratio:
        return []
    hits: list[tuple[int, str]] = []
    for node in unit.nodes:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not _is_ratio_ident(target.id):
            continue
        if _numeric_literal(node.value) is None:
            continue
        if unit.parents.get(id(node)) is not None:
            continue  # not a module-level statement (inside a class/if body)
        hits.append(
            (
                node.lineno,
                f"{target.id} = {ast.unparse(node.value)} freezes the device ratio at "
                "import — it can never follow a screen change. Read it at the use site.",
            )
        )
    return hits


@dataclass(frozen=True)
class Rule:
    """One detector, scoped to the tree it can decide (source vs. tests)."""

    id: str
    scope: str
    summary: str
    detect: Callable[[_Unit], list[tuple[int, str]]]




def _pixmap_call_has_no_ratio(node: ast.Call) -> bool:
    """``icon.pixmap(size)`` / ``icon.pixmap(w, h)`` with no ratio argument.

    The legal forms are ``pixmap(size, ratio, ...)`` and the helper call with
    ``dpr=``; a bare size (one arg) or a bare ``(w, h)`` pair rasterizes at the
    application ratio / 1:1, both wrong for a window painting at another ratio.
    """
    if not node.args:
        return False
    if len(node.args) == 1:
        return True
    # The bare name ``ratio`` is legal HERE (unlike typography shares):
    # QIcon.pixmap's second positional argument is the device ratio.
    return not any(
        _is_ratio_ident(ast.unparse(arg)) or _is_loose_ratio_ident(ast.unparse(arg))
        for arg in node.args
    )


def detect_icon_app_ratio(unit: _Unit) -> list[tuple[int, str]]:
    """Icon rasters must be produced at the paint device's ratio.

    ``QIcon.pixmap(QSize)`` and ``normalized_icon_pixmap()`` without an explicit
    ratio take ``QGuiApplication.devicePixelRatio()``. Under fractional scaling
    that is not the window's ratio: measured 2026-10-28 on KDE/Wayland at 125 %,
    application 2.0 vs window 1.25, so a 22 px icon was rasterized 44x44 @2.0
    and painted into 27.5 device px (0.625 resample) — thin strokes looked
    ragged while the same icons were crisp at 100 %.
    """
    out: list[tuple[int, str]] = []
    for node in unit.nodes:
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name == "normalized_icon_pixmap":
            if not any(keyword.arg == "dpr" for keyword in node.keywords):
                out.append(
                    (
                        node.lineno,
                        "normalized_icon_pixmap() without dpr=... rasterizes at "
                        "the application ratio, not the paint device's",
                    )
                )
        elif name == "pixmap" and _pixmap_call_has_no_ratio(node):
            out.append(
                (
                    node.lineno,
                    "QIcon.pixmap(...) with no explicit ratio uses the "
                    "application ratio (wrong for the window under fractional "
                    "scaling); use normalized_icon_pixmap(..., dpr=...)",
                )
            )
    return out


RULES: tuple[Rule, ...] = (
    Rule(
        "raster-logical-tagged",
        "src",
        "raster allocated from a logical size then tagged with the ratio",
        detect_raster_logical_tagged,
    ),
    Rule(
        "ratio-dropped-on-copy",
        "src",
        "raster copied from another raster's size with the ratio tag lost",
        detect_ratio_dropped_on_copy,
    ),
    Rule(
        "ratio-rounded",
        "src",
        "device ratio collapsed to an integer",
        detect_ratio_rounded,
    ),
    Rule(
        "manual-dpr-scale",
        "src",
        "painter scaled by the ratio the paint device already applies",
        detect_manual_dpr_scale,
    ),
    Rule(
        "ratio-hardcoded",
        "src",
        "literal device ratio instead of the paint device's",
        detect_ratio_hardcoded_source,
    ),
    Rule(
        "ratio-hardcoded",
        "tests",
        "test substitutes or asserts a literal device ratio",
        detect_ratio_hardcoded_tests,
    ),
    Rule(
        "pixmap-size-as-logical",
        "src",
        "raster device px used as logical geometry",
        detect_pixmap_size_as_logical_source,
    ),
    Rule(
        "dpr-assumed-1",
        "src",
        "ratio default of 1 with no device read behind it",
        detect_dpr_assumed_one,
    ),
    Rule(
        "dpr-assumed-1",
        "src",
        "module-level ratio constant with no device read behind it",
        detect_dpr_assumed_one_constant,
    ),
    Rule(
        "icon-app-ratio",
        "src",
        "icon raster produced at the application ratio, not the paint device's",
        detect_icon_app_ratio,
    ),
)


# -- scanning --------------------------------------------------------------


def scan_module(tree: ast.Module, *, path: str, scope: str) -> list[Finding]:
    """Every finding of every rule applicable to *scope*, allowlist NOT applied."""
    findings: list[Finding] = []
    for unit in iter_units(tree):
        for rule in RULES:
            if rule.scope != scope:
                continue
            for lineno, reason in rule.detect(unit):
                findings.append(
                    Finding(
                        path=path,
                        lineno=lineno,
                        rule=rule.id,
                        function=unit.name,
                        reason=reason,
                    )
                )
    return findings


def scan_file(path: Path, *, root: Path, scope: str) -> list[Finding]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return scan_module(tree, path=path.relative_to(root).as_posix(), scope=scope)


def scan_tree(root: Path, *, scope: str, relative_to: Path | None = None) -> list[Finding]:
    """Scan every module under *root*; fixtures are intentional bad code.

    ``relative_to`` makes finding paths repo-relative (``src/…`` / ``tests/…``),
    which is also the allowlist key — a bare filename would not say which tree
    an exemption belongs to.
    """
    findings: list[Finding] = []
    for path in sorted(root.rglob("*.py")):
        if _FIXTURE_ROOT in path.parents:
            continue
        findings.extend(scan_file(path, root=relative_to or root, scope=scope))
    return findings


def scan_source() -> list[Finding]:
    return scan_tree(_PACKAGE_ROOT, scope="src", relative_to=_REPO_ROOT)


def scan_test_suite() -> list[Finding]:
    return scan_tree(_TESTS_ROOT, scope="tests", relative_to=_REPO_ROOT)


def raw_findings() -> list[Finding]:
    """Every finding on the current tree, allowlist ignored (the inventory)."""
    return [*scan_source(), *scan_test_suite()]


def findings() -> list[Finding]:
    """Findings left after the allowlist — must be empty."""
    return [
        finding
        for finding in raw_findings()
        if (finding.path, finding.function, finding.rule) not in ALLOWLIST
    ]


def _format(items: list[Finding]) -> str:
    return "\n".join(
        f"{item.path}:{item.lineno} [{item.rule}] {item.function}() — {item.reason}"
        for item in items
    )


# -- the gate --------------------------------------------------------------


def test_no_dpr_contract_violations() -> None:
    """0 violations: no raster may repeat a shipped HiDPI failure mode."""
    offenders = findings()
    assert offenders == [], (
        "HiDPI raster contract violated (allocate round(logical * dpr), tag the "
        "ratio, paint in logical px — see docs/dev/DPR_CONTRACT.md):\n"
        + _format(offenders)
    )


def test_allowlist_is_shrink_only() -> None:
    """Every exemption still matches code: a stale entry fails the gate."""
    raw = {(item.path, item.function, item.rule) for item in raw_findings()}
    stale = sorted(set(ALLOWLIST) - raw)
    assert stale == [], (
        "tests/dpr_contract_allowlist.py has entries that no longer match a "
        f"finding (delete them):{chr(10)}"
        + "\n".join(f"{path}::{function} [{rule}]" for path, function, rule in stale)
    )


def test_allowlist_entries_carry_a_reason() -> None:
    empty = sorted(key for key, reason in ALLOWLIST.items() if not reason.strip())
    assert empty == [], f"allowlist entries without a reason: {empty}"


def test_rule_registry_matches_the_documented_catalog() -> None:
    """Adding a mechanism means adding a doc row, not just a function."""
    registered = {rule.id for rule in RULES}
    assert registered == set(DOCUMENTED_RULES), (
        "rule ids drifted from the documented catalog: "
        f"{sorted(registered ^ set(DOCUMENTED_RULES))}"
    )
    doc = _DOC_PATH.read_text(encoding="utf-8")
    missing = [rule for rule in DOCUMENTED_RULES if rule not in doc]
    assert missing == [], (
        f"docs/dev/DPR_CONTRACT.md does not document {missing} — the table is the "
        "catalog this gate encodes"
    )


def test_detectors_are_not_blind_on_the_current_tree() -> None:
    """Self-falsification: the scanners must actually see the DPR-aware code.

    A gate that goes green because it parses nothing is worse than no gate. The
    inventory numbers here are structural (files that touch a device ratio and
    the rasters they allocate), so they only move when the DPR surface does.
    """
    scanned = {path.relative_to(_PACKAGE_ROOT).as_posix() for path in _PACKAGE_ROOT.rglob("*.py")}
    assert len(scanned) > 50, f"package scan found only {len(scanned)} modules"
    ratio_aware = {
        "ui/managers/icon_manager.py",
        "ui/widgets/buttons/button.py",
        "ui/widgets/buttons/content.py",
        "ui/widgets/helpers/marquee_text.py",
        "ui/widgets/composite/sidebar_nav_list/icons.py",
        "ui/windows/rounded_body.py",
    }
    seen: set[str] = set()
    for path in _PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(_PACKAGE_ROOT).as_posix()
        if "devicePixelRatio" not in path.read_text(encoding="utf-8"):
            continue
        seen.add(rel)
    assert ratio_aware <= seen, (
        "the scanner no longer sees the DPR boundary: "
        f"{sorted(ratio_aware - seen)} do not mention devicePixelRatio"
    )


# -- the positive invariant future tests should call -----------------------


def assert_device_sized(
    pixmap: object,
    logical_rect: object,
    *,
    ratio: float | None = None,
) -> None:
    """Assert a raster carries *logical_rect* at ``ratio`` device px per logical px.

    The one arithmetic every raster in this family must satisfy:

    * ``pixmap.size() == round(logical * ratio)`` — allocated in DEVICE px;
    * ``pixmap.deviceIndependentSize() == logical`` — tagged with the ratio, so
      the painter blits it back at the intended logical footprint.

    ``ratio`` defaults to the pixmap's own ratio (the tags must match the
    allocation). Pass it explicitly when the caller knows the device ratio the
    raster was built for, e.g. a painter passed ``dpr=``. A half-pixel tolerance
    absorbs the integer rounding of the device size; the failure messages name
    the shape you probably just wrote.
    """
    width = float(logical_rect.width())  # QRect/QSizeF/QSize all expose this
    height = float(logical_rect.height())
    assert not pixmap.isNull(), "raster is null: the allocation was skipped"
    effective = float(ratio if ratio is not None else pixmap.devicePixelRatioF())
    expected = (int(round(width * effective)), int(round(height * effective)))
    actual = (pixmap.width(), pixmap.height())
    footprint = pixmap.deviceIndependentSize()
    problems: list[str] = []
    if actual != expected:
        problems.append(
            f"device size {actual} != round(logical * ratio) {expected}"
        )
    if (
        abs(footprint.width() - width) > 0.51
        or abs(footprint.height() - height) > 0.51
    ):
        hint = ""
        if effective != 1.0 and abs(footprint.width() - width / effective) <= 0.51:
            hint = (
                " — allocated in LOGICAL px then tagged with the ratio: the canvas "
                "shrank to logical/dpr (content lands in the top-left quadrant)"
            )
        elif effective != 1.0 and abs(footprint.width() - width * effective) <= 0.51:
            hint = (
                " — the ratio tag was dropped (an untagged copy): the raster paints "
                "dpr× too large"
            )
        problems.append(
            f"deviceIndependentSize {footprint.width():.2f}x{footprint.height():.2f} "
            f"!= logical {width:.2f}x{height:.2f} at ratio {effective}{hint}"
        )
    assert not problems, "raster is not device-sized:\n  " + "\n  ".join(problems)


def test_assert_device_sized_accepts_the_dev_px_form(qapp) -> None:
    """Green case: round(logical * dpr) + tag, at every ratio we care about."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPixmap

    for ratio in (1.0, 1.25, 1.5, 2.0):
        pixmap = QPixmap(
            max(1, int(round(120 * ratio))), max(1, int(round(64 * ratio)))
        )
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(0)
        assert_device_sized(pixmap, QRect(0, 0, 120, 64))


def test_assert_device_sized_rejects_logical_allocation(qapp) -> None:
    """Red case 1 (shipped: button snapshot): QPixmap(120, 64) then tag 2.0."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPixmap

    pixmap = QPixmap(120, 64)
    pixmap.setDevicePixelRatio(2.0)
    pixmap.fill(0)
    with pytest.raises(AssertionError) as caught:
        assert_device_sized(pixmap, QRect(0, 0, 120, 64))
    assert "LOGICAL px" in str(caught.value)


def test_assert_device_sized_rejects_a_dropped_ratio(qapp) -> None:
    """Red case 2 (shipped: icon tint): device-sized copy with no tag."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPixmap

    source = QPixmap(120, 64)
    source.setDevicePixelRatio(2.0)
    source.fill(0)
    copy = QPixmap(source.size())
    copy.fill(0)
    with pytest.raises(AssertionError) as caught:
        assert_device_sized(copy, QRect(0, 0, 60, 32), ratio=2.0)
    assert "tag was dropped" in str(caught.value)
