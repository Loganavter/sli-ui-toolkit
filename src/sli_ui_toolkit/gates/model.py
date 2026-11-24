"""The one record every gate rule returns.

Kept free of PySide6 and of the runner so a rule module can be imported on its
own (a host may embed the rules in its own test suite).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Finding:
    """One rule violation, anchored at the line that produced it.

    ``rule`` is the stable rule id (``raw-chrome-px``, …), ``path`` is the
    display path the runner was given (relative to the working directory when
    possible), ``line`` is 1-based, and ``message`` explains both the offending
    source and the fix a host should apply.
    """

    rule: str
    path: str
    line: int
    message: str

    def format(self) -> str:
        """``path:line: rule: message`` — the CLI's text form."""
        return f"{self.path}:{self.line}: {self.rule}: {self.message}"


__all__ = ["Finding"]
