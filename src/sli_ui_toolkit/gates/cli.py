"""``python -m sli_ui_toolkit.gates`` — the host-facing gate runner.

Exit codes: ``0`` clean (or within the installed baseline), ``1`` findings
(including a baseline that was grown or gained a file), ``2`` the scan itself
could not run (unreadable/unparsable file, broken baseline).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .rules import RULES
from .runner import (
    BaselineError,
    ScanResult,
    baseline_violations,
    check_paths,
    findings_to_counts,
    load_baseline,
    write_baseline,
)

_DESCRIPTION = """\
Check host UI code against the conventions this toolkit enforces on itself.

Each rule is a standalone AST pass: no PySide6 import is needed, so the check
runs on a CI box without a display.
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sli_ui_toolkit.gates",
        description=_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="files or directories to scan (default: the current tree)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print a machine-readable report instead of text lines",
    )
    parser.add_argument(
        "--baseline",
        metavar="PATH",
        help=(
            "JSON count file from --write-baseline; findings within it pass, "
            "a grown count or a new file with findings fails"
        ),
    )
    parser.add_argument(
        "--write-baseline",
        metavar="PATH",
        help="record the current findings as the accepted ceiling, then exit 0",
    )
    parser.add_argument(
        "--allow-qcolor",
        action="append",
        metavar="GLOB",
        default=[],
        help=(
            "exempt a palette module from qcolor-at-import (basename glob, "
            "repeatable); palette.py/palettes.py/colors.py/colours.py are "
            "exempt already"
        ),
    )
    parser.add_argument(
        "--rule",
        action="append",
        choices=list(RULES),
        metavar="NAME",
        help=f"run one rule (repeatable); one of: {', '.join(RULES)}",
    )
    return parser


def _json_payload(
    result: ScanResult,
    baseline_path: str | None,
    violations: Sequence[str],
) -> dict[str, object]:
    counts = findings_to_counts(result.findings)
    by_rule = {rule: sum(files.values()) for rule, files in counts.items()}
    return {
        "version": 1,
        "findings": [
            {
                "rule": finding.rule,
                "path": finding.path,
                "line": finding.line,
                "message": finding.message,
            }
            for finding in result.findings
        ],
        "counts": counts,
        "summary": {
            "findings": len(result.findings),
            "files_scanned": len(result.files),
            "files_with_findings": len({f.path for f in result.findings}),
            "by_rule": by_rule,
        },
        "errors": [
            {"path": path, "message": message} for path, message in result.errors
        ],
        "baseline": (
            None
            if baseline_path is None
            else {"path": baseline_path, "violations": list(violations)}
        ),
    }


def _report_text(
    result: ScanResult,
    baseline_path: str | None,
    violations: Sequence[str],
) -> tuple[str, list[str]]:
    """The text report: stdout lines and stderr lines, stdout last."""
    stdout: list[str] = [finding.format() for finding in result.findings]
    stderr = [f"{path}: error: {message}" for path, message in result.errors]
    stderr.extend(f"baseline violation: {violation}" for violation in violations)
    if result.findings:
        counts = findings_to_counts(result.findings)
        by_rule = ", ".join(
            f"{rule}={sum(files.values())}" for rule, files in counts.items()
        )
        files = len({finding.path for finding in result.findings})
        stdout.append(
            f"{len(result.findings)} finding(s) in {files} file(s) "
            f"across {len(result.files)} scanned: {by_rule}"
        )
    else:
        stdout.append(f"no findings in {len(result.files)} scanned file(s)")
    if baseline_path is not None and not violations:
        stdout.append(f"baseline {baseline_path}: accepted")
    return "\n".join(stdout), stderr


def _error(message: str) -> int:
    print(f"gates: {message}", file=sys.stderr)
    return 2


def _emit(text: str) -> bool:
    """Write *text*; ``False`` when the consumer closed the pipe."""
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
        return True
    except BrokenPipeError:
        # A pager/`head` closed the pipe; silence the interpreter's shutdown
        # flush instead of printing "Exception ignored".
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return False


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gates; returns the process exit code (see module docstring)."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    paths: list[str] = list(args.paths) or [str(Path.cwd())]
    selected: list[str] = args.rule or list(RULES)

    result = check_paths(paths, selected, qcolor_allow=args.allow_qcolor)
    counts = findings_to_counts(result.findings)

    if args.write_baseline:
        write_baseline(args.write_baseline, counts)
        print(
            f"baseline written to {args.write_baseline}: "
            f"{len(result.findings)} finding(s) recorded"
        )
        return 2 if result.errors else 0

    violations: list[str] = []
    if args.baseline:
        try:
            baseline = load_baseline(args.baseline)
        except BaselineError as error:
            return _error(str(error))
        violations = baseline_violations(counts, baseline)

    if args.json:
        stdout_text = json.dumps(
            _json_payload(result, args.baseline, violations),
            indent=2,
            sort_keys=True,
        )
        stderr_lines: list[str] = []
    else:
        stdout_text, stderr_lines = _report_text(
            result, args.baseline, violations
        )
    for line in stderr_lines:
        print(line, file=sys.stderr)
    if not _emit(stdout_text):
        return 1

    if result.errors:
        return 2
    if args.baseline:
        return 1 if violations else 0
    return 1 if result.findings else 0


__all__ = ["main"]
