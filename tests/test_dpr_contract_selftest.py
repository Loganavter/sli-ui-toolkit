"""Every detector is red on REAL bad code — and green on the tree that fixed it.

A DPR detector is worthless if it only fires on a snippet invented beside it.
So each fixture under ``tests/fixtures/dpr_contract/`` is a fragment of code
that this repo actually shipped (cut from ``3ccfe91^``, the commit before PR
#124 fixed four HiDPI rasters), with the provenance in its header, and with its
expected findings declared in the same header::

    # provenance: src/…/marquee_text.py:116-141 @ d841b67 (3ccfe91^)
    #@findings: 1
    #@expect: raster-logical-tagged | pixmap = QPixmap(max(1, cycle), …

Three modes (``ratio-rounded``, ``manual-dpr-scale``, ``dpr-assumed-1``) were
never shipped here — an exhaustive grep over every ``*.py`` blob in the repo's
history finds no instance. Their fixtures are **authored** and say
``provenance: NONE`` in the header, and the test below refuses to let any other
mode be authored: a fixture that claims history must cite a commit, and a rule
that has history cannot be faked with an invented snippet. That is the line
between "this gate is calibrated on our own bugs" and "this gate is calibrated
on a drawing of our bugs".

Fixtures are parsed, never imported — they reference ``self``, ``QPixmap`` and
helpers that are not defined at module scope on purpose.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.dpr_contract_allowlist import ALLOWLIST
from tests.test_dpr_contract import (
    DOCUMENTED_RULES,
    Finding,
    RULES,
    scan_file,
    scan_module,
    scan_source,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "dpr_contract"
_PROBE_ROOT = Path(__file__).resolve().parent.parent / ".probe" / "prefix"

#: Modes with **no** shipped instance in this repository's history (verified by
#: grepping every ``*.py`` blob reachable from ``git rev-list --all --objects``:
#: 2776 blobs at 3ccfe91^). Their fixtures are authored and must say so.
_NO_HISTORY_RULES = frozenset({"ratio-rounded", "manual-dpr-scale", "dpr-assumed-1"})

#: The pre-#124 source files, keyed to the rule their shipped defect trips. Used
#: by the probe test at the bottom: the same scanner has to find the four real
#: defects in the whole historical files, not only in the extracted fragment.
_SHIPPED_DEFECTS: dict[str, str] = {
    "src/sli_ui_toolkit/ui/widgets/helpers/marquee_text.py": "raster-logical-tagged",
    "src/sli_ui_toolkit/ui/widgets/buttons/button.py": "raster-logical-tagged",
    "src/sli_ui_toolkit/ui/managers/icon_manager.py": "ratio-dropped-on-copy",
    "src/sli_ui_toolkit/ui/widgets/buttons/content.py": "pixmap-size-as-logical",
}


def _fixtures() -> list[Path]:
    return sorted(_FIXTURE_ROOT.glob("*.py"))


def _header(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("#")]


def _provenance(path: Path) -> str:
    for line in _header(path):
        if line.startswith("# provenance:"):
            return line
    raise AssertionError(f"{path.name}: fixture has no '# provenance:' header")


def _has_history(path: Path) -> bool:
    return "NONE" not in _provenance(path)


def _scope(path: Path) -> str:
    """Fixture scope, read off its provenance: tests fragments obey the test rules."""
    return "tests" if re.search(r"\btests/", _provenance(path)) else "src"


def _expectations(path: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in _header(path):
        if not line.startswith("#@expect:"):
            continue
        rule, _, needle = line[len("#@expect:") :].partition("|")
        out.append((rule.strip(), needle.strip()))
    return out


def _expected_total(path: Path) -> int:
    for line in _header(path):
        if line.startswith("#@findings:"):
            return int(line[len("#@findings:") :].strip())
    raise AssertionError(f"{path.name}: fixture has no '#@findings:' header")


def _scan_fixture(path: Path) -> tuple[list[Finding], list[str]]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=path.name)
    return (
        scan_module(tree, path=path.name, scope=_scope(path)),
        text.splitlines(),
    )


@pytest.mark.parametrize("path", _fixtures(), ids=lambda item: item.name)
def test_detector_is_red_on_its_fixture(path: Path) -> None:
    """The declared findings are exactly what the scanner reports on the fixture."""
    findings, lines = _scan_fixture(path)
    for rule, needle in _expectations(path):
        hits = [item for item in findings if item.rule == rule and needle in lines[item.lineno - 1]]
        assert hits, (
            f"{path.name}: rule {rule!r} did not fire on {needle!r}; got "
            f"{[(item.rule, item.lineno, lines[item.lineno - 1].strip()) for item in findings]}"
        )
    assert len(findings) == _expected_total(path), (
        f"{path.name}: {len(findings)} findings, expected {_expected_total(path)}: "
        f"{[(item.rule, item.lineno) for item in findings]}"
    )


def test_every_documented_rule_has_a_fixture_that_fires() -> None:
    """No rule may enter the catalog without a red case it is calibrated on."""
    fired: set[str] = set()
    for path in _fixtures():
        fired |= {item.rule for item in _scan_fixture(path)[0]}
    assert fired == set(DOCUMENTED_RULES), (
        f"rules without a red fixture: {sorted(set(DOCUMENTED_RULES) - fired)} / "
        f"undeclared rules: {sorted(fired - set(DOCUMENTED_RULES))}"
    )


@pytest.mark.parametrize("path", _fixtures(), ids=lambda item: item.name)
def test_provenance_is_honest(path: Path) -> None:
    """A fixture claiming history cites a commit; only the three no-history modes are authored."""
    rules_on_fixture = {item.rule for item in _scan_fixture(path)[0]}
    if _has_history(path):
        assert re.search(r"@\s+[0-9a-f]{7,}", _provenance(path)), (
            f"{path.name}: a historical fixture must cite <path>:<line> @ <commit>"
        )
        return
    invented = rules_on_fixture - _NO_HISTORY_RULES
    assert not invented, (
        f"{path.name}: {sorted(invented)} has shipped instances in this repo, so its "
        "fixture must be cut from real code — an authored snippet calibrates the "
        "detector on a drawing of the bug"
    )


def test_the_no_history_set_is_real_and_not_a_shortcut() -> None:
    """The three authored modes are exactly the ones with no shipped instance."""
    authored: set[str] = set()
    for path in _fixtures():
        if not _has_history(path):
            authored |= {item.rule for item in _scan_fixture(path)[0]}
    assert authored == set(_NO_HISTORY_RULES), (
        "the authored-fixture set drifted: "
        f"declared {sorted(_NO_HISTORY_RULES)}, fixtures {sorted(authored)} — before "
        "adding a mode here, grep the full history (`git rev-list --all --objects` "
        "| git cat-file --batch) for the shape; if it shipped, cut the fixture from it"
    )


@pytest.mark.parametrize("path", _fixtures(), ids=lambda item: item.name)
def test_scanner_is_green_on_the_fixed_file(path: Path) -> None:
    """The rule red on the historical fragment is silent on the tree that fixed it."""
    if not _has_history(path):
        pytest.skip("authored fixture: no fixed counterpart to compare against")
    scope = _scope(path)
    match = re.search(r"# provenance:\s*(\S+?):[\d,\-]+\s+@", _provenance(path))
    assert match, f"{path.name}: provenance must read '<path>:<line> @ <commit>'"
    repository_path = match.group(1)
    current = _REPO_ROOT / repository_path
    assert current.is_file(), f"{path.name}: provenance path {repository_path} is gone"
    live = scan_module(
        ast.parse(current.read_text(encoding="utf-8")), path=repository_path, scope=scope
    )
    fired_on_fixture = {item.rule for item in _scan_fixture(path)[0]}
    survivors = {
        item.rule
        for item in live
        if (item.path, item.function, item.rule) not in ALLOWLIST
    }
    assert not (fired_on_fixture & survivors), (
        f"{path.name}: {sorted(fired_on_fixture & survivors)} still fires on the "
        f"current {repository_path} — the fixture is not describing a fixed defect"
    )
    recorded = {item.rule for item in live} & fired_on_fixture
    for rule in recorded:
        assert any(
            rule == key[2] and key[0] == repository_path for key in ALLOWLIST
        ), (
            f"{path.name}: {rule} still fires on the live {repository_path} but is not "
            "a recorded, justified entry in tests/dpr_contract_allowlist.py"
        )


def test_registry_rules_all_are_reachable() -> None:
    """Every registered detector is exercised by at least one scope (no dead code)."""
    for rule in RULES:
        assert rule.scope in {"src", "tests"}, rule.id
        assert rule.summary.strip(), rule.id


@pytest.mark.skipif(
    not _PROBE_ROOT.is_dir(),
    reason="reproducible proof, not a committed artifact: copy the pre-#124 files "
    "with `git show 3ccfe91^:<path> > .probe/prefix/<path>` first",
)
def test_probe_finds_the_four_shipped_defects_in_whole_files() -> None:
    """Red-before on the real historical tree, not just on the extracted fragments.

    ``.probe/prefix`` holds the four pre-#124 files at their package-relative
    paths. Each must trip the rule its shipped defect belongs to — this is the
    number recorded in the PR description that introduced this gate.
    """
    found: dict[str, set[str]] = {}
    for path in sorted(_PROBE_ROOT.rglob("*.py")):
        rel = path.relative_to(_PROBE_ROOT).as_posix()
        found[rel] = {item.rule for item in scan_file(path, root=_PROBE_ROOT, scope="src")}
    for relative_path, rule in _SHIPPED_DEFECTS.items():
        assert relative_path in found, f"probe tree is missing {relative_path}"
        assert rule in found[relative_path], (
            f"{relative_path}: expected {rule}, got {sorted(found[relative_path])}"
        )
    assert not scan_source(), "the live tree must stay clean while the probe is dirty"
