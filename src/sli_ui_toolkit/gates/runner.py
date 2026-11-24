"""Discovery, execution and baseline bookkeeping for the host gates.

The runner never imports the scanned module: it parses source text, runs the
selected AST rules, and returns findings. That is what lets a host check code
that needs PySide6, a QApplication or a plugin registry it does not have.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .model import Finding
from .rules import RULES

#: Directories never descended into (build output, caches, vendored envs).
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "venv",
    }
)

#: Baseline file format version; bumped only on an incompatible shape change.
BASELINE_VERSION = 1


@dataclass
class ScanResult:
    """Everything one scan produced."""

    findings: list[Finding] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings and not self.errors


class BaselineError(ValueError):
    """The baseline file exists but cannot be read as a count map."""


def _sorted(findings: Iterable[Finding]) -> list[Finding]:
    """Finding order for reports: file, then line, then rule."""
    return sorted(
        findings, key=lambda f: (f.path, f.line, f.rule, f.message)
    )


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def iter_python_files(paths: Iterable[str | Path]) -> list[Path]:
    """Every ``*.py`` file named by *paths* (files as-is, dirs recursively).

    Hidden and build directories are skipped, so pointing the CLI at a repo
    root does not walk ``.git`` or a local venv.
    """
    found: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            if path.suffix == ".py":
                found.append(path)
            continue
        if not path.is_dir():
            continue
        for candidate in path.rglob("*.py"):
            relative = candidate.relative_to(path)
            if any(
                part in _SKIP_DIRS or part.startswith(".")
                for part in relative.parts[:-1]
            ):
                continue
            found.append(candidate)
    unique: dict[str, Path] = {}
    for path in found:
        unique.setdefault(str(path.resolve()), path)
    return sorted(unique.values(), key=lambda item: str(item))


def check_source(
    source: str,
    path: str = "<memory>",
    rules: Sequence[str] | None = None,
) -> list[Finding]:
    """Run the rules over one source string (parsed, never imported)."""
    tree = ast.parse(source, filename=path)
    selected = list(RULES) if rules is None else list(rules)
    findings: list[Finding] = []
    for name in selected:
        findings.extend(RULES[name](tree, source, path))
    return _sorted(findings)


def check_paths(
    paths: Iterable[str | Path],
    rules: Sequence[str] | None = None,
) -> ScanResult:
    """Scan files/directories; unreadable or unparsable files become errors."""
    result = ScanResult()
    requested = [Path(raw) for raw in paths]
    for raw in requested:
        if not raw.exists():
            result.errors.append((str(raw), "no such file or directory"))
    selected = list(RULES) if rules is None else list(rules)
    for path in iter_python_files(requested):
        display = _display_path(path)
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            result.errors.append((display, f"cannot read: {error}"))
            continue
        try:
            tree = ast.parse(source, filename=display)
        except SyntaxError as error:
            result.errors.append(
                (display, f"cannot parse: line {error.lineno}: {error.msg}")
            )
            continue
        result.files.append(display)
        for name in selected:
            result.findings.extend(RULES[name](tree, source, display))
    result.findings = _sorted(result.findings)
    return result


def findings_to_counts(
    findings: Iterable[Finding],
) -> dict[str, dict[str, int]]:
    """``rule -> path -> count`` — the shape a baseline file stores."""
    counts: dict[str, dict[str, int]] = {}
    for finding in findings:
        files = counts.setdefault(finding.rule, {})
        files[finding.path] = files.get(finding.path, 0) + 1
    return {
        rule: dict(sorted(files.items()))
        for rule, files in sorted(counts.items())
    }


def load_baseline(path: str | Path) -> dict[str, dict[str, int]]:
    """Read a baseline count map, accepting both the wrapped and bare form."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        raise BaselineError(f"cannot read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise BaselineError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(raw, dict):
        raise BaselineError(f"{path}: top-level value must be a JSON object")
    counts = raw.get("counts", raw)
    if not isinstance(counts, dict):
        raise BaselineError(f"{path}: 'counts' must be a JSON object")
    baseline: dict[str, dict[str, int]] = {}
    for rule, files in counts.items():
        if not isinstance(rule, str) or not isinstance(files, dict):
            raise BaselineError(
                f"{path}: expected rule -> {{file: count}}, got {rule!r}"
            )
        recorded: dict[str, int] = {}
        for file_name, count in files.items():
            if not isinstance(file_name, str) or not isinstance(count, int):
                raise BaselineError(
                    f"{path}: {rule}: expected {{file: count}}, got "
                    f"{file_name!r}: {count!r}"
                )
            if count < 0:
                raise BaselineError(f"{path}: {rule}/{file_name}: negative count")
            recorded[file_name] = count
        baseline[rule] = recorded
    return baseline


def baseline_violations(
    counts: Mapping[str, Mapping[str, int]],
    baseline: Mapping[str, Mapping[str, int]],
) -> list[str]:
    """Why *counts* is not within *baseline* (empty means accepted).

    The baseline is a ratchet per rule and per file: a file may only lose
    findings, and a file that has findings but no recorded count is new debt.
    Shrinking to zero, or dropping a rule entirely, is accepted.
    """
    violations: list[str] = []
    for rule in sorted(counts):
        recorded = baseline.get(rule, {})
        for file_name in sorted(counts[rule]):
            count = counts[rule][file_name]
            if file_name not in recorded:
                violations.append(
                    f"{rule}: {file_name} has {count} finding(s) and is not in "
                    "the baseline (new file with findings)"
                )
            elif count > recorded[file_name]:
                violations.append(
                    f"{rule}: {file_name} has {count} finding(s), baseline "
                    f"allows {recorded[file_name]} (grown)"
                )
    return violations


def write_baseline(
    path: str | Path, counts: Mapping[str, Mapping[str, int]]
) -> None:
    """Install *counts* as the accepted ceiling for future runs."""
    target = Path(path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": BASELINE_VERSION,
        "counts": {
            rule: dict(sorted(files.items()))
            for rule, files in sorted(counts.items())
        },
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


__all__ = [
    "BASELINE_VERSION",
    "BaselineError",
    "ScanResult",
    "baseline_violations",
    "check_paths",
    "check_source",
    "findings_to_counts",
    "iter_python_files",
    "load_baseline",
    "write_baseline",
]
