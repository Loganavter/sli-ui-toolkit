"""Value-edit contract gate: registry + AST scan + behavioural coverage.

Owner rule (2026-10-19 wave, both repos): while merely navigating, arrows never
change a value; **Enter** enters edit mode on a value control; arrows/WASD
adjust only in edit mode; Enter commits the adjusted value; Esc reverts to the
value captured on entry. ``navigation_sections.arrow_gate_open`` /
``value_control_is_editing`` enforce it for widgets that implement
``is_editing()``; ``ToolbarRowsSection._widget_handles`` consults the gate
before trial-dispatching arrows at the focused widget.

``tests/test_slider_edit_mode.py`` and ``tests/test_nav_arrow_key_contract.py``
cover today's widgets behaviourally — they cannot notice a **new** value
control that starts eating navigation arrows, because a new control is simply
not in their code. This module closes that hole:

1. ``tests/value_controls_allowlist.py`` holds ``VALUE_CONTROLS`` (registered
   value controls with an edit mode: reason + factory + WASD flag),
   ``KEYBOARD_STEP_CONTROLS`` (typed value fields that step with
   PageUp/PageDown: reason + factory + value reader) and ``ALLOWLIST`` (things
   that declare value-control machinery but are text editors / focus walks,
   with a reason).
2. The AST scan below walks ``src/sli_ui_toolkit`` and fails, naming
   ``module:Class``, for any class that subclasses ``Slider``, defines
   ``is_editing``, or steps its own value from ``keyPressEvent`` that is in
   neither table. A new value control therefore has to declare one of the two
   shapes — Arrow-driven edit mode or typed-field PageUp/PageDown — instead of
   silently eating navigation keys.
3. Each ``VALUE_CONTROLS`` entry gets behavioural coverage with REAL keys
   through a real ``ToolbarRowsSection`` (``QTest.keyClick``, not a direct
   ``keyPressEvent`` call): idle arrows leave the value untouched and move the
   ring (not consumed), Enter enters edit mode, arrows (and WASD) adjust,
   Enter commits, Esc reverts. Each ``KEYBOARD_STEP_CONTROLS`` entry gets the
   typed-field half: idle Up/Down move the ring and leave the value alone,
   PageUp/PageDown step it.

Falsification of the scan (recorded here on purpose — a guard nobody has seen
go red is not trusted). Against the pre-guard source the behavioural tests are
green by construction (``Slider`` already implements the contract), so the red
evidence is the scan itself, exercised on synthetic sources inside this module:

* ``test_scan_flags_an_unregistered_is_editing_class`` — a source declaring
  ``class Mystery(QWidget): def is_editing(...)`` turns the scan red and names
  ``synthetic.controls:Mystery``; the same source with a registry or allowlist
  entry for that key passes.
* ``test_scan_flags_an_unregistered_slider_subclass`` — ``class Fancy(Slider)``
  (inherits the machinery without naming it) is flagged the same way.

The scan is deliberately simple AST matching: it resolves the ``Slider``
subclass relation transitively by simple class name within the package, and it
only looks at module-level ``ClassDef`` nodes (the shape every toolkit widget
uses). Keyboard stepping is detected from a class's own ``keyPressEvent``: it
must both mention a keyboard step key and call a value-mutating helper
(``setValue`` or a ``_step*`` method that itself calls ``setValue``/``setText``/
``setTime``), so a text widget's caret movement or a popup's focus walk is not
mistaken for a value step. A class built dynamically (``type(...)``), imported
under an alias it does not declare, or stepping through a helper defined
outside the scanned tree cannot be seen — known limits, not covered cases.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection
from tests.value_controls_allowlist import (
    ALLOWLIST,
    KEYBOARD_STEP_CONTROLS,
    VALUE_CONTROLS,
    ValueControl,
    covered_ids,
)

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "sli_ui_toolkit"

#: The root of the value-edit machinery in the toolkit. A class deriving from
#: it inherits ``is_editing()`` and the gate applies whether or not the base is
#: named in the subclass body.
_SLIDER_ROOT = "Slider"

#: Key constants that signal "this branch is about stepping/adjusting".
_STEP_KEY_ATTRS = frozenset(
    {
        "Key_Up",
        "Key_Down",
        "Key_Left",
        "Key_Right",
        "Key_PageUp",
        "Key_PageDown",
        "Key_W",
        "Key_A",
        "Key_S",
        "Key_D",
    }
)

#: Calls that finish a value step when a ``_step*`` helper reaches them.
_VALUE_WRITERS = frozenset({"setValue", "setText", "setTime"})


# ---------------------------------------------------------------------------
# AST scan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Declaration:
    """One module-level class declaration found in a scanned source."""

    module: str
    name: str
    bases: tuple[str, ...]
    defines_is_editing: bool
    #: Self-called method names in this class's ``keyPressEvent`` that could be
    #: a value step (``setValue`` / any ``_step*`` helper).
    keyboard_calls: frozenset[str] = frozenset()
    #: Whether that ``keyPressEvent`` mentions a step/arrow key constant.
    mentions_step_key: bool = False
    #: ``_step*`` methods defined in this class that write the value
    #: (``setValue``/``setText``/``setTime``).
    value_writing_step_methods: frozenset[str] = frozenset()

    @property
    def key(self) -> str:
        """Stable identity used by the registry and allowlist: ``module:Class``."""
        return f"{self.module}:{self.name}"


def _simple_name(node: ast.expr) -> str | None:
    """``Widget`` / ``module.Widget`` -> ``Widget``; anything else -> ``None``.

    Import aliases are not resolved; the toolkit names ``Slider`` directly in
    every base list, and an alias would still have to declare ``is_editing``
    (shape b) to evade the gate silently.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _module_id(path: Path, root: Path) -> str:
    """``<root>/ui/widgets/atomic/slider.py`` -> ``ui.widgets.atomic.slider``."""
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _self_called(func: ast.AST) -> frozenset[str]:
    """Names of ``self.<name>(...)`` calls anywhere inside *func*."""
    return frozenset(
        node.func.attr
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    )


def _mentions_step_key(func: ast.AST) -> bool:
    """Whether *func* refers to an arrow/step key constant."""
    return any(
        isinstance(node, ast.Attribute) and node.attr in _STEP_KEY_ATTRS
        for node in ast.walk(func)
    )


def _value_writing_steps(node: ast.ClassDef) -> frozenset[str]:
    """``_step*`` methods of *node* that end in a value write."""
    names = set()
    for item in node.body:
        if not isinstance(item, ast.FunctionDef) or not item.name.startswith("_step"):
            continue
        if _self_called(item) & _VALUE_WRITERS or any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr == "_value"
            for sub in ast.walk(item)
            if isinstance(sub, ast.Assign)
            for target in sub.targets
        ):
            names.add(item.name)
    return frozenset(names)


def parse_declarations(source: str, module: str) -> list[Declaration]:
    """Parse *source* and return its module-level class declarations.

    A syntax error is a hard failure (not an empty list): a scanner that
    quietly skips a file it cannot parse would report a clean tree while blind.
    """
    tree = ast.parse(source, filename=module)
    declarations: list[Declaration] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = tuple(
            name for name in (_simple_name(base) for base in node.bases) if name
        )
        defines_is_editing = any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == "is_editing"
            for item in node.body
        )
        key_handler = next(
            (
                item
                for item in node.body
                if isinstance(item, ast.FunctionDef)
                and item.name == "keyPressEvent"
            ),
            None,
        )
        keyboard_calls = (
            frozenset(
                name
                for name in _self_called(key_handler)
                if name == "setValue" or name.startswith("_step")
            )
            if key_handler is not None
            else frozenset()
        )
        declarations.append(
            Declaration(
                module,
                node.name,
                bases,
                defines_is_editing,
                keyboard_calls=keyboard_calls,
                mentions_step_key=(
                    key_handler is not None and _mentions_step_key(key_handler)
                ),
                value_writing_step_methods=_value_writing_steps(node),
            )
        )
    return declarations


def scan_package(root: Path = _PACKAGE_ROOT) -> list[Declaration]:
    """Every module-level declaration in the toolkit source tree."""
    declarations: list[Declaration] = []
    for path in sorted(root.rglob("*.py")):
        declarations.extend(
            parse_declarations(
                path.read_text(encoding="utf-8"), _module_id(path, root)
            )
        )
    return declarations


def find_uncovered(
    declarations: list[Declaration],
    covered: frozenset[str] | set[str] | None = None,
) -> list[str]:
    """Return sorted ``module:Class`` keys that violate the gate.

    A declaration is covered when it is registered as a value control (either
    shape) or allowlisted. Otherwise it must not (a) define ``is_editing``,
    (b) subclass ``Slider`` (transitively, by simple class name within the
    scanned set), or (c) step its own value from ``keyPressEvent`` — a
    ``setValue`` call, or a ``_step*`` helper that some scanned class defines
    as value-writing, in a handler that also mentions a step key.
    """
    accepted = covered_ids() if covered is None else covered

    slider_names = {_SLIDER_ROOT}
    changed = True
    while changed:
        changed = False
        for declaration in declarations:
            if (
                declaration.name not in slider_names
                and any(base in slider_names for base in declaration.bases)
            ):
                slider_names.add(declaration.name)
                changed = True

    value_writers = {"setValue"}
    for declaration in declarations:
        value_writers |= declaration.value_writing_step_methods

    def steps_value_from_keyboard(declaration: Declaration) -> bool:
        return bool(
            declaration.mentions_step_key
            and declaration.keyboard_calls & value_writers
        )

    return sorted(
        declaration.key
        for declaration in declarations
        if declaration.key not in accepted
        and (
            declaration.defines_is_editing
            or declaration.name in slider_names
            or steps_value_from_keyboard(declaration)
        )
    )


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------

def test_every_toolkit_value_control_is_covered():
    offenders = find_uncovered(scan_package())
    assert offenders == [], (
        "unregistered value-control declaration(s): "
        f"{', '.join(offenders)} — add a VALUE_CONTROLS entry (reason + "
        "factory) or an ALLOWLIST entry (one-line reason why it is not a "
        "value control) in tests/value_controls_allowlist.py"
    )


def test_registry_and_allowlist_name_real_declarations():
    """A dead entry fails: typos/renames must not silently widen the gate."""
    keys = {declaration.key for declaration in scan_package()}
    for key in VALUE_CONTROLS:
        assert key in keys, f"VALUE_CONTROLS entry {key!r} matches no class"
    for key in KEYBOARD_STEP_CONTROLS:
        assert key in keys, f"KEYBOARD_STEP_CONTROLS entry {key!r} matches no class"
    for key in ALLOWLIST:
        assert key in keys, f"ALLOWLIST entry {key!r} matches no class"


def test_allowlist_entries_carry_a_one_line_reason():
    for key, reason in ALLOWLIST.items():
        assert reason.strip(), f"ALLOWLIST entry {key!r} has no reason"
        assert "\n" not in reason, f"ALLOWLIST entry {key!r} reason is not one line"


def test_registry_entries_are_value_controls_with_a_reason():
    for key, entry in VALUE_CONTROLS.items():
        assert isinstance(entry, ValueControl)
        assert entry.reason.strip(), f"VALUE_CONTROLS entry {key!r} has no reason"
        assert callable(entry.factory), f"VALUE_CONTROLS entry {key!r} has no factory"


def test_keyboard_step_entries_carry_reason_factory_and_reader():
    for key, entry in KEYBOARD_STEP_CONTROLS.items():
        assert entry.reason.strip(), (
            f"KEYBOARD_STEP_CONTROLS entry {key!r} has no reason"
        )
        assert callable(entry.factory), (
            f"KEYBOARD_STEP_CONTROLS entry {key!r} has no factory"
        )
        assert callable(entry.read), (
            f"KEYBOARD_STEP_CONTROLS entry {key!r} has no value reader"
        )


# ---------------------------------------------------------------------------
# Falsification: the scan must go red on an unregistered declaration
# ---------------------------------------------------------------------------

_UNREGISTERED_IS_EDITING_SOURCE = """
class Mystery(QWidget):
    def is_editing(self) -> bool:
        return False
"""

_UNREGISTERED_SLIDER_SUBCLASS_SOURCE = """
class Fancy(Slider):
    pass
"""


def test_scan_flags_an_unregistered_is_editing_class():
    declarations = parse_declarations(
        _UNREGISTERED_IS_EDITING_SOURCE, "synthetic.controls"
    )
    assert find_uncovered(declarations) == ["synthetic.controls:Mystery"], (
        "the scan must fail and name an unregistered is_editing() class"
    )

    # The same source is accepted once the key is covered — by a value-control
    # registry entry or by an allowlist entry (both are just covered keys to
    # the scan; they differ only in what the behavioural layer does with them).
    for entry in (
        frozenset({*covered_ids(), "synthetic.controls:Mystery"}),
        frozenset({*VALUE_CONTROLS, "synthetic.controls:Mystery"}),
        frozenset({*ALLOWLIST, "synthetic.controls:Mystery"}),
    ):
        assert find_uncovered(declarations, covered=entry) == []


def test_scan_flags_an_unregistered_slider_subclass():
    declarations = parse_declarations(
        _UNREGISTERED_SLIDER_SUBCLASS_SOURCE, "synthetic.controls"
    )
    assert find_uncovered(declarations) == ["synthetic.controls:Fancy"], (
        "a Slider subclass inherits the edit machinery and must be registered "
        "even when it never spells out is_editing()"
    )
    assert find_uncovered(
        declarations,
        covered=frozenset({*covered_ids(), "synthetic.controls:Fancy"}),
    ) == []


def test_scan_flags_an_indirect_slider_subclass():
    source = """
class Fancy(Slider):
    pass

class Fancier(Fancy):
    pass
"""
    assert find_uncovered(
        parse_declarations(source, "synthetic.controls")
    ) == ["synthetic.controls:Fancier", "synthetic.controls:Fancy"]


_KEYBOARD_STEPPING_SOURCE = """
class Twiddler(QWidget):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_PageUp:
            self.setValue(self.value() + 1)
            event.accept()

class CaretOnly(QWidget):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.cursorBackward(False)
            event.accept()
"""


def test_scan_flags_a_class_that_steps_its_value_from_the_keyboard():
    declarations = parse_declarations(
        _KEYBOARD_STEPPING_SOURCE, "synthetic.controls"
    )
    assert find_uncovered(declarations) == ["synthetic.controls:Twiddler"], (
        "a class that steps its value in keyPressEvent must declare one of the "
        "two contract shapes; caret-only arrow handling must not be flagged"
    )


def test_scan_flags_stepping_through_a_value_writing_helper():
    source = """
class Twiddler(QWidget):
    def _step_minutes(self, delta):
        self.setText("x")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_PageUp:
            self._step_minutes(1)
"""
    assert find_uncovered(
        parse_declarations(source, "synthetic.controls")
    ) == ["synthetic.controls:Twiddler"]


def test_scan_ignores_a_keyboard_helper_that_does_not_write_the_value():
    """``ComboBox``'s ``_step_typing_focus`` walks a popup's rows, not a value."""
    source = """
class Picker(QWidget):
    def _step_typing_focus(self, step):
        self._set_typing_focus(step)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Down:
            self._step_typing_focus(1)
"""
    assert find_uncovered(parse_declarations(source, "synthetic.controls")) == []


def test_every_typed_field_entry_is_reached_by_the_keyboard_step_scan():
    """Derived red evidence: each typed-field control is caught *because* it
    steps from ``keyPressEvent`` — unregistering one must make the scan name
    exactly that class, not merely stop covering it."""
    declarations = scan_package()
    for key in sorted(KEYBOARD_STEP_CONTROLS):
        without = covered_ids() - {key}
        assert find_uncovered(declarations, covered=without) == [key], (
            f"{key} must be caught by the keyboard-step detection on its own"
        )


# ---------------------------------------------------------------------------
# Behavioural coverage: real keys through the real section gate
# ---------------------------------------------------------------------------

class _Focusable(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = label
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


def _section_host(qtbot, widget: QWidget):
    """host -> row1 (``top``) / row2 (``neighbor`` then ``widget``).

    Mirrors ``test_slider_edit_mode._two_row_host``: rows are containers so
    ``ToolbarRowsSection._focusable`` sees the children, and geometry makes the
    x-sort put ``neighbor`` left of ``widget``.
    """
    host = QWidget()
    host.resize(400, 200)
    qtbot.addWidget(host)

    row1 = QWidget(host)
    row1.setGeometry(10, 10, 120, 30)
    top = _Focusable("top", row1)
    top.setGeometry(0, 0, 120, 30)

    row2 = QWidget(host)
    row2.setGeometry(10, 60, 320, 40)
    neighbor = _Focusable("neighbor", row2)
    neighbor.setGeometry(0, 5, 80, 30)

    widget.setParent(row2)
    widget.setGeometry(120, 5, 160, 30)
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    host.show()
    qtbot.waitExposed(host)
    NavigationManager.get_instance().register(
        host,
        ToolbarRowsSection(
            lambda: [row1, row2], tag=f"value-contract-{id(widget)}"
        ),
    )
    return host, top, neighbor, widget


def _focus(widget: QWidget) -> None:
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()


def _press(widget: QWidget, key) -> None:
    QTest.keyClick(widget, key)
    QApplication.processEvents()


_ENTRIES = sorted(VALUE_CONTROLS.items())
_IDS = [control_id for control_id, _ in _ENTRIES]


@pytest.mark.parametrize("control_id,entry", _ENTRIES, ids=_IDS)
def test_idle_arrows_navigate_without_touching_the_value(
    qapp, qtbot, control_id, entry
):
    """Contract 1: while navigating, arrows never change a value (and are not
    consumed — the ring moves instead)."""
    widget = entry.factory()
    host, top, neighbor, widget = _section_host(qtbot, widget)
    base = widget.value()

    _focus(widget)
    assert QApplication.focusWidget() is widget

    _press(widget, Qt.Key.Key_Left)
    assert QApplication.focusWidget() is neighbor, (
        f"{control_id} consumed Left while idle instead of moving the ring"
    )
    assert widget.value() == base, f"{control_id} changed its value on idle Left"

    _press(neighbor, Qt.Key.Key_Right)
    assert QApplication.focusWidget() is widget
    assert widget.value() == base, f"{control_id} changed its value on idle Right"

    _press(widget, Qt.Key.Key_Up)
    assert QApplication.focusWidget() is top, (
        f"{control_id} consumed Up while idle instead of moving the ring"
    )
    assert widget.value() == base, f"{control_id} changed its value on idle Up"

    _press(top, Qt.Key.Key_Down)
    assert widget.value() == base

    # Idle WASD is not a value key either (contract 3's negative half).
    _focus(widget)
    for key in (Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D):
        _press(widget, key)
        assert widget.value() == base, (
            f"{control_id} changed its value on idle {key!r}"
        )
    assert QApplication.focusWidget() is widget


@pytest.mark.parametrize("control_id,entry", _ENTRIES, ids=_IDS)
def test_enter_edits_arrows_adjust_and_enter_commits(qapp, qtbot, control_id, entry):
    """Contract 2-4: Enter enters edit mode, arrows (and WASD) adjust, Enter
    commits the adjusted value."""
    widget = entry.factory()
    host, top, neighbor, widget = _section_host(qtbot, widget)
    _focus(widget)

    assert widget.is_editing() is False
    base = widget.value()

    _press(widget, Qt.Key.Key_Return)
    assert widget.is_editing() is True, (
        f"Enter on {control_id} did not enter edit mode"
    )

    _press(widget, Qt.Key.Key_Right)
    assert widget.value() > base, f"Right in edit mode did not raise {control_id}"
    after_right = widget.value()

    _press(widget, Qt.Key.Key_Left)
    assert widget.value() < after_right, (
        f"Left in edit mode did not lower {control_id}"
    )

    # Up/Down are navigation keys while idle; in edit mode they adjust.
    before_up = widget.value()
    _press(widget, Qt.Key.Key_Up)
    assert widget.value() > before_up, f"Up in edit mode did not raise {control_id}"
    before_down = widget.value()
    _press(widget, Qt.Key.Key_Down)
    assert widget.value() < before_down, (
        f"Down in edit mode did not lower {control_id}"
    )

    if entry.wasd:
        before_d = widget.value()
        _press(widget, Qt.Key.Key_D)
        assert widget.value() > before_d, (
            f"D in edit mode did not raise {control_id}"
        )
        before_a = widget.value()
        _press(widget, Qt.Key.Key_A)
        assert widget.value() < before_a, (
            f"A in edit mode did not lower {control_id}"
        )

    committed = widget.value()
    _press(widget, Qt.Key.Key_Return)
    assert widget.is_editing() is False, (
        f"Enter again did not commit and leave edit mode on {control_id}"
    )
    assert widget.value() == committed, (
        f"committing changed {control_id}'s adjusted value"
    )


@pytest.mark.parametrize("control_id,entry", _ENTRIES, ids=_IDS)
def test_escape_reverts_to_the_entry_value(qapp, qtbot, control_id, entry):
    """Contract 5: Esc reverts to the value captured when edit mode was entered."""
    widget = entry.factory()
    host, top, neighbor, widget = _section_host(qtbot, widget)
    _focus(widget)

    entry_value = widget.value()
    _press(widget, Qt.Key.Key_Return)
    assert widget.is_editing() is True
    for _ in range(3):
        _press(widget, Qt.Key.Key_Right)
    assert widget.value() != entry_value, "test setup: the value must have moved"

    _press(widget, Qt.Key.Key_Escape)
    assert widget.is_editing() is False, f"Esc did not leave edit mode on {control_id}"
    assert widget.value() == entry_value, (
        f"Esc did not revert {control_id} to the value captured on entry"
    )


# ---------------------------------------------------------------------------
# Behavioural coverage: typed-field shape (PageUp/PageDown, idle Up/Down free)
# ---------------------------------------------------------------------------

_STEP_ENTRIES = sorted(KEYBOARD_STEP_CONTROLS.items())
_STEP_IDS = [control_id for control_id, _ in _STEP_ENTRIES]


@pytest.mark.parametrize("control_id,entry", _STEP_ENTRIES, ids=_STEP_IDS)
def test_idle_up_down_move_the_ring_and_page_keys_step_the_value(
    qapp, qtbot, control_id, entry
):
    """Typed-field shape: the field is not a value control until PageUp/PageDown.

    Up/Down while idle must reach the ring (never the value); PageUp/PageDown
    are the declared step keys and must move it.
    """
    widget = entry.factory()
    host, top, neighbor, widget = _section_host(qtbot, widget)
    base = entry.read(widget)

    _focus(widget)
    assert QApplication.focusWidget() is widget

    _press(widget, Qt.Key.Key_Up)
    assert QApplication.focusWidget() is top, (
        f"{control_id} consumed Up while idle instead of moving the ring"
    )
    assert entry.read(widget) == base, f"{control_id} stepped on idle Up"

    _press(top, Qt.Key.Key_Down)
    assert entry.read(widget) == base, f"{control_id} stepped on idle Down"

    _focus(widget)

    _press(widget, Qt.Key.Key_PageUp)
    raised = entry.read(widget)
    assert raised > base, f"PageUp did not step {control_id} up"

    _press(widget, Qt.Key.Key_PageDown)
    assert entry.read(widget) < raised, f"PageDown did not step {control_id} back"
