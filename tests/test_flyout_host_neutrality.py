"""The flyout must stay host-agnostic — and a host must be able to opt in.

Two gates in one file:

1. The flyout-sibling protocol. A control that keyboard navigation enters
   *on purpose* (a host value capsule that opens its own flyout) must not be
   dragged back to the anchor when a neighbouring flyout hides. The toolkit
   may not name host classes (AGENTS.md), so the control declares itself:

       class HostValueCapsule(QWidget):
           flyout_focus_sibling = True      # attribute ...
           # ... or a zero-arg method: def flyout_focus_sibling(self) -> bool

   ``BaseFlyout._restore_focus_policies`` then leaves focus where navigation
   put it. Without the declaration the guard stays narrow: a plain sibling is
   still not a reason to skip the restore.

2. A source guard: no host-application class name may appear anywhere under
   ``src/sli_ui_toolkit``. The deny-list is a hygiene gate, not a parser; a
   genuine exception needs an entry in ``_ALLOWLIST`` with a written reason
   (and an entry that no longer suppresses anything fails as stale).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import BaseFlyout

#: Host-application classes that must never leak into the shared library.
HOST_CLASS_NAMES = (
    "ScrollValueButton",
    "_ScrollValueFlyout",
    "AppMessageDialog",
    "ImageCompare",
)

#: ``(path relative to src/sli_ui_toolkit, needle) -> reason``. Every entry
#: must carry a written reason and must still match a real occurrence.
_ALLOWLIST: dict[tuple[str, str], str] = {}

_MIN_REASON_CHARS = 30


class _DeclaredSibling(QWidget):
    """A host control that is not a toolkit class — only the protocol differs."""

    flyout_focus_sibling = True


class _DeclaredSiblingMethod(QWidget):
    """Same declaration as a zero-arg method (properties work too)."""

    def flyout_focus_sibling(self) -> bool:
        return True


def _src_root() -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "sli_ui_toolkit"


def _scan() -> list[tuple[str, int, str, str]]:
    """``(rel_path, lineno, line, needle)`` for every deny-listed name."""
    hits: list[tuple[str, int, str, str]] = []
    root = _src_root()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            for needle in HOST_CLASS_NAMES:
                if needle in line:
                    hits.append((rel, lineno, line.strip(), needle))
    return hits


def test_src_names_no_host_application_class():
    violations = [
        f"{rel}:{lineno} [{needle}] {line}"
        for rel, lineno, line, needle in _scan()
        if not _ALLOWLIST.get((rel, needle))
    ]
    assert not violations, (
        "the toolkit must not name host-application classes (AGENTS.md: "
        "host-specific logic stays outside the library; ARCHITECTURE.md: an "
        "app cannot be a dependency). Report the capability generically or "
        "expose a documented protocol. Violations:\n  "
        + "\n  ".join(violations)
    )


def test_allowlist_entries_are_justified_and_live():
    hits = _scan()
    for (rel, needle), reason in _ALLOWLIST.items():
        assert len(reason.strip()) >= _MIN_REASON_CHARS, (
            f"allowlist entry {rel} [{needle}] needs a written reason "
            f"(>= {_MIN_REASON_CHARS} chars), got {reason!r}"
        )
        assert any(
            hit_rel == rel and hit_needle == needle
            for hit_rel, _lineno, _line, hit_needle in hits
        ), (
            f"stale allowlist entry {rel} [{needle}]: nothing in the source "
            "matches it any more — drop it"
        )


def _host_with_anchor_and_sibling(qtbot, sibling: QWidget):
    host = QWidget()
    layout = QVBoxLayout(host)
    anchor = QWidget()
    anchor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    layout.addWidget(anchor)
    sibling.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    layout.addWidget(sibling)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    return host, anchor, sibling


def _hide_with_focus_on(qapp, host, anchor, sibling):
    """Focus *sibling*, then run a hide that would restore to *anchor*."""
    hider = BaseFlyout(host)
    hider._anchor_widget = anchor
    hider._previous_focus_widget = anchor

    anchor.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    assert QApplication.focusWidget() is anchor

    sibling.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    assert QApplication.focusWidget() is sibling

    hider._restore_focus_policies()
    qapp.processEvents()
    return hider


def test_declared_sibling_attribute_keeps_focus(qapp, qtbot):
    sibling = _DeclaredSibling()
    host, anchor, sibling = _host_with_anchor_and_sibling(qtbot, sibling)
    try:
        hider = _hide_with_focus_on(qapp, host, anchor, sibling)
        assert QApplication.focusWidget() is sibling, (
            "a control declaring flyout_focus_sibling = True must keep the "
            "keyboard: hiding a neighbouring flyout may not yank it back"
        )
    finally:
        sibling.deleteLater()


def test_declared_sibling_method_keeps_focus(qapp, qtbot):
    sibling = _DeclaredSiblingMethod()
    host, anchor, sibling = _host_with_anchor_and_sibling(qtbot, sibling)
    try:
        _hide_with_focus_on(qapp, host, anchor, sibling)
        assert QApplication.focusWidget() is sibling, (
            "a zero-arg flyout_focus_sibling() method is the same declaration"
        )
    finally:
        sibling.deleteLater()


def test_undeclared_sibling_still_restores_to_anchor(qapp, qtbot):
    """The protocol is opt-in: an ordinary widget is no reason to skip."""
    sibling = QWidget()
    host, anchor, sibling = _host_with_anchor_and_sibling(qtbot, sibling)
    try:
        _hide_with_focus_on(qapp, host, anchor, sibling)
        assert QApplication.focusWidget() is anchor, (
            "without a declaration the hide still restores focus to the anchor"
        )
    finally:
        sibling.deleteLater()
