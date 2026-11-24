"""The host-facing AST rules.

Each rule is a plain function ``(tree, source, path) -> list[Finding]``: no
PySide6 import, no widget construction, no source rewriting. A host runs them
over its own tree (``python -m sli_ui_toolkit.gates <paths...>``) so the
conventions the toolkit enforces on itself do not have to be re-derived host
side.
"""

from __future__ import annotations

import ast
import fnmatch
import io
import re
import tokenize
from collections.abc import Callable, Iterable, Iterator

from .model import Finding

#: Rule ids, also the values accepted by ``--rule``.
RULE_TOOLKIT_QSS = "toolkit-qss"
RULE_RAW_CHROME_PX = "raw-chrome-px"
RULE_DOUBLE_SCALED_PX = "double-scaled-px"
RULE_QCOLOR_AT_IMPORT = "qcolor-at-import"
RULE_EMPTY_STYLESHEET = "empty-stylesheet"
RULE_SILENT_SWALLOW = "silent-swallow"
RULE_TOKEN_OWNERSHIP = "token-ownership"
RULE_TOKEN_OWNERSHIP_DYNAMIC = "token-ownership-dynamic"
RULE_TOKEN_OWNERSHIP_UNRESOLVED = "token-ownership-unresolved"

#: Path fragment -> widget family that owns the palette keys the file paints
#: with. First match wins, so the order is the precedence: a rule that reads a
#: path must be unambiguous. A file that matches nothing owns no family, and a
#: family token in it is a finding — new widget trees cannot escape the gate by
#: living in a directory nobody mapped; they declare ownership instead with
#: ``# token-family: <name>``.
TOKEN_FAMILIES: tuple[tuple[str, str], ...] = (
    ("buttons/", "button"),
    ("comboboxes/", "button"),
    ("atomic/custom_line_edit", "input"),
    ("atomic/spinbox", "input"),
    ("atomic/time_line_edit", "input"),
    ("atomic/text_labels", "label"),
    ("atomic/slider", "slider"),
    ("atomic/switch", "switch"),
    ("atomic/checkbox", "checkbox"),
    ("atomic/radio", "checkbox"),
    ("list_panel", "list_item"),
    ("sidebar_nav_list", "list_item"),
    ("text_list_widget", "list_item"),
    ("context_menu", "menu"),
    ("menustrip", "menu"),
    ("base_flyout", "flyout"),
    ("simple_options_flyout", "flyout"),
    ("toast", "toast"),
    ("timeline_widget", "timeline"),
    ("calendar_widget", "calendar"),
    ("custom_title_bar", "titlebar"),
    ("window_controls", "titlebar"),
    ("dialogs/", "dialog"),
    ("progress_bar", "progress"),
    ("text/", "label"),
)

#: Token roots every family may read: shared chrome rather than one family's
#: private palette. Matched on the key's first dotted segment, so ``separator``
#: covers ``separator.color``.
NEUTRAL_TOKENS: frozenset[str] = frozenset(
    {"accent", "link", "separator", "shadow", "surface"}
)

#: Qt's own palette roles, resolved through ``ThemeManager`` like a token: no
#: family owns them.
QT_PALETTE_ROLES: frozenset[str] = frozenset(
    {
        "AlternateBase",
        "Base",
        "BrightText",
        "Button",
        "ButtonText",
        "Highlight",
        "HighlightedText",
        "Text",
        "ToolTipBase",
        "ToolTipText",
        "Window",
        "WindowText",
    }
)

#: Pseudo-family for the tokens every family may read (see ``NEUTRAL_TOKENS``).
NEUTRAL_FAMILY = "neutral"

#: Palette key root -> family that owns it. Roots absent here (``help``,
#: ``tooltip``, ``chat_panel`` …) belong to a panel or router no widget family
#: claims, so they are not judged. ``color_dialog`` is the dialog family's
#: variant prefix, not a family of its own.
TOKEN_OWNERS: dict[str, str] = {
    "button": "button",
    "calendar": "calendar",
    "checkbox": "checkbox",
    "color_dialog": "dialog",
    "dialog": "dialog",
    "flyout": "flyout",
    "input": "input",
    "label": "label",
    "list_item": "list_item",
    "menu": "menu",
    "progress": "progress",
    "slider": "slider",
    "switch": "switch",
    "timeline": "timeline",
    "titlebar": "titlebar",
    "toast": "toast",
}

#: ``# token-family: <name>`` — a file's declaration of the family it paints
#: for, when the path map cannot see it (a helper shared by one family, a host
#: layout of its own).
_TOKEN_FAMILY_COMMENT = re.compile(r"#\s*token-family:\s*([A-Za-z][\w-]*)")

#: A name ending in ``prefix`` bound to a literal (``prefix = "button.primary"``,
#: ``token_prefix="button.warning"``) is what an f-string token is built from.
_PREFIX_SUFFIX = "prefix"

#: File basenames that own colours by definition: a palette module is *made* of
#: module-scope ``QColor`` constants, so ``qcolor-at-import`` cannot tell it
#: from the defect it looks for. A host whose palette module has another name
#: adds it with ``--allow-qcolor GLOB``.
DEFAULT_QCOLOR_EXEMPT_GLOBS: tuple[str, ...] = (
    "palette.py",
    "palettes.py",
    "colors.py",
    "colours.py",
)


def is_qcolor_exempt(path: str, extra: Iterable[str] = ()) -> bool:
    """True when *path*'s basename is a palette module (default or *extra*).

    The check is on the basename alone: a palette module's location is the
    host's business, and matching the full path would force one directory
    layout on every host.
    """
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatchcase(name, glob)
        for glob in (*DEFAULT_QCOLOR_EXEMPT_GLOBS, *extra)
    )

#: ``(tree, source, path) -> findings``; the raw ``source`` is needed only for
#: comment inspection (``silent-swallow``).
Rule = Callable[[ast.Module, str, str], list[Finding]]

_TOOLKIT_ROOT = "sli_ui_toolkit"

#: Calls that stamp a design-space pixel value straight onto a widget or size.
_RAW_PX_CALLS = frozenset(
    {
        "setFixedWidth",
        "setFixedHeight",
        "setFixedSize",
        "setMinimumWidth",
        "setMinimumHeight",
        "setMinimumSize",
        "setMaximumWidth",
        "setMaximumHeight",
        "setMaximumSize",
        "resize",
        "QSize",
        "setContentsMargins",
        "setSpacing",
    }
)

#: Structural values, not design px: 0 = collapsed, 1 = a single hairline
#: unit that already means "one device-ish step" in Qt sizing order,
#: 16777215 = QWIDGETSIZE_MAX.
_STRUCTURAL_LITERALS = frozenset({0, 1, 16777215})

_NUMERIC_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)

#: Toolkit constructors whose ``size`` keyword is already design px and is
#: scaled internally — wrapping it in ``scaled_px()`` scales twice.
#: ``ButtonSpec`` / ``ShapeSpec`` are excluded on purpose: their ``size`` is the
#: already-real widget size (``Button`` builds ``ShapeSpec`` from ``self.width()``).
_DESIGN_SIZE_CONSTRUCTORS = frozenset({"Button", "ButtonConfig"})

#: Logging methods; a handler that calls one is not a silent swallow.
_LOGGING_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
)

#: Application singletons are not widgets: app-level QSS is the toolkit's
#: documented path for native/stock Qt widgets, so ``app.setStyleSheet(...)``
#: is not a toolkit-widget violation.
_APPLICATION_CLASSES = frozenset(
    {"QApplication", "QCoreApplication", "QGuiApplication"}
)


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_scaled_px_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node.func) == "scaled_px"


def _literal_value(node: ast.AST) -> float | None:
    """Numeric value of a pure-literal expression, or ``None``.

    ``None`` means the expression depends on runtime state (a name, a call, an
    attribute) and therefore may already be a design-px constant, which is the
    sanctioned form.
    """
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        inner = _literal_value(node.operand)
        if inner is None:
            return None
        return -inner if isinstance(node.op, ast.USub) else inner
    if isinstance(node, ast.BinOp) and isinstance(node.op, _NUMERIC_BINOPS):
        left = _literal_value(node.left)
        right = _literal_value(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right if right else None
        if isinstance(node.op, ast.FloorDiv):
            return left // right if right else None
        return left % right if right else None
    return None


class _ImportIndex:
    """Which names in a module came from ``sli_ui_toolkit`` (and from where).

    Deliberately textual: the gates never import the host's modules, so a
    conditional import or a plugin loader is resolved to the module string it
    names and nothing more.
    """

    def __init__(self, tree: ast.Module) -> None:
        #: local name -> module it was imported from (``from x import name``)
        self.classes: dict[str, str] = {}
        #: local alias -> module it names (``import x.y as alias``)
        self.modules: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    self.classes[alias.asname or alias.name] = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    self.modules[local] = alias.name if alias.asname else local

    def resolve(self, node: ast.expr) -> str | None:
        """Qualified module path an expression's symbol was imported from."""
        if isinstance(node, ast.Name):
            if node.id in self.modules:
                return self.modules[node.id]
            return self.classes.get(node.id)
        if isinstance(node, ast.Attribute):
            base = self.resolve(node.value)
            if base is None:
                return None
            return f"{base}.{node.attr}"
        return None

    def is_toolkit(self, node: ast.expr) -> bool:
        module = self.resolve(node)
        return module is not None and (
            module == _TOOLKIT_ROOT or module.startswith(_TOOLKIT_ROOT + ".")
        )


def _is_application_instance(node: ast.expr) -> bool:
    """``QApplication.instance()`` — an app object, never a toolkit widget."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "instance"):
        return False
    base = func.value
    if isinstance(base, ast.Name):
        return base.id in _APPLICATION_CLASSES
    if isinstance(base, ast.Attribute):
        return base.attr in _APPLICATION_CLASSES
    return False


def _annotation_is_application(annotation: ast.expr | None) -> bool:
    """``app: QApplication`` / ``app: QApplication | None`` — a declared app."""
    if isinstance(annotation, ast.Name):
        return annotation.id in _APPLICATION_CLASSES
    if isinstance(annotation, ast.Attribute):
        return annotation.attr in _APPLICATION_CLASSES
    if isinstance(annotation, ast.Subscript):
        return _annotation_is_application(annotation.slice)
    if isinstance(annotation, ast.BinOp):
        left = _annotation_is_application(annotation.left)
        return left or _annotation_is_application(annotation.right)
    if isinstance(annotation, ast.Constant):
        return isinstance(annotation.value, str) and any(
            name in annotation.value for name in _APPLICATION_CLASSES
        )
    return False


def _receiver_kind(index: _ImportIndex, node: ast.expr) -> str | None:
    """``"toolkit"`` / ``"other"`` / ``"unknown"`` for an instantiated receiver."""
    if isinstance(node, ast.Call):
        if _is_application_instance(node):
            return "other"
        if index.is_toolkit(node.func):
            return "toolkit"
        if index.resolve(node.func) is not None:
            return "other"
        return "unknown"
    if isinstance(node, ast.Name) and index.resolve(node) is not None:
        # ``Button().setStyleSheet`` is handled above; a bare imported name
        # here is not an instance, so it stays unresolved.
        return "unknown"
    return "unknown"


class _QssVisitor(ast.NodeVisitor):
    """Resolve local bindings and report ``setStyleSheet`` receivers.

    Scope chain only (module → class → function): enough for the shapes hosts
    actually write (``btn = Button()``, ``self._btn = Button()``), and never
    guesses about a receiver it cannot see — that is reported as ``unresolved``
    instead of passing silently.
    """

    def __init__(self, index: _ImportIndex, path: str) -> None:
        self.index = index
        self.scopes: list[dict[str, str]] = [{}]
        self.findings: list[Finding] = []
        self._path = path
        self._class_kind: str | None = None

    def _bind(self, key: str, kind: str) -> None:
        self.scopes[-1][key] = kind

    def _lookup(self, key: str) -> str | None:
        for scope in reversed(self.scopes):
            if key in scope:
                return scope[key]
        return None

    def _kind_of_value(self, node: ast.expr) -> str:
        if isinstance(node, ast.Call):
            return _receiver_kind(self.index, node) or "unknown"
        if isinstance(node, ast.Name):
            return self._lookup(node.id) or "unknown"
        return "unknown"

    def _record_binding(self, target: ast.expr, value: ast.expr) -> None:
        if isinstance(target, ast.Name):
            key = target.id
        elif isinstance(target, ast.Attribute):
            key = ast.unparse(target)
        else:
            return
        self._bind(key, self._kind_of_value(value))

    def _receiver_kind(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            found = self._lookup(node.id)
            return found or "unknown"
        if isinstance(node, ast.Attribute):
            found = self._lookup(ast.unparse(node))
            return found or "unknown"
        if isinstance(node, ast.Call):
            return _receiver_kind(self.index, node) or "unknown"
        return "unknown"

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scopes.append({})
        previous = self._class_kind
        self._class_kind = (
            "toolkit"
            if any(self.index.is_toolkit(base) for base in node.bases)
            else "other"
        )
        self.generic_visit(node)
        self._class_kind = previous
        self.scopes.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scopes.append({})
        arguments = [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
        for argument in arguments:
            if _annotation_is_application(argument.annotation):
                self._bind(argument.arg, "other")
        if (
            self._class_kind is not None
            and node.args.args
            and node.args.args[0].arg in ("self", "cls")
        ):
            self._bind(node.args.args[0].arg, self._class_kind)
        self.generic_visit(node)
        self.scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        for target in node.targets:
            self._record_binding(target, node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.generic_visit(node)
        if node.value is not None:
            self._record_binding(node.target, node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "setStyleSheet":
            if not _is_empty_stylesheet(node):
                kind = self._receiver_kind(func.value)
                if kind == "toolkit":
                    self.findings.append(
                        Finding(
                            RULE_TOOLKIT_QSS,
                            self._path,
                            node.lineno,
                            "setStyleSheet() on a toolkit widget — painters own "
                            "the visual output; theme through ThemeManager tokens",
                        )
                    )
                elif kind != "other":
                    self.findings.append(
                        Finding(
                            RULE_TOOLKIT_QSS,
                            self._path,
                            node.lineno,
                            "setStyleSheet() receiver is unresolved — cannot prove "
                            "it is not a toolkit widget; bind it to a local "
                            "variable or drop the stylesheet",
                        )
                    )
        self.generic_visit(node)


def _is_empty_stylesheet(call: ast.Call) -> bool:
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return not arg.value.strip()
    for keyword in call.keywords:
        if keyword.arg == "styleSheet" and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            if isinstance(value, str):
                return not value.strip()
    return False


def check_toolkit_qss(
    tree: ast.Module, source: str, path: str = "<memory>"
) -> list[Finding]:
    """``toolkit-qss``: no QSS on a toolkit widget, and no unresolved receiver."""
    visitor = _QssVisitor(_ImportIndex(tree), path)
    visitor.visit(tree)
    return sorted(visitor.findings)


def check_raw_chrome_px(
    tree: ast.Module, source: str, path: str = "<memory>"
) -> list[Finding]:
    """``raw-chrome-px``: geometry calls carrying a bare design-space number."""
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node.func) not in _RAW_PX_CALLS:
            continue
        values = [
            value
            for value in (_literal_value(arg) for arg in node.args)
            if value is not None
        ]
        values.extend(
            value
            for value in (
                _literal_value(keyword.value) for keyword in node.keywords
            )
            if value is not None
        )
        offenders = [value for value in values if value not in _STRUCTURAL_LITERALS]
        if not offenders:
            continue
        findings.append(
            Finding(
                RULE_RAW_CHROME_PX,
                path,
                node.lineno,
                f"{ast.unparse(node)} — raw design px "
                f"({', '.join(_format_number(v) for v in offenders)}); "
                "route it through scaled_px()",
            )
        )
    return sorted(findings)


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def check_double_scaled_px(
    tree: ast.Module, source: str, path: str = "<memory>"
) -> list[Finding]:
    """``double-scaled-px``: ``scaled_px`` applied twice to one value."""
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if _is_scaled_px_call(node):
            assert isinstance(node, ast.Call)
            inner = [*node.args, *(keyword.value for keyword in node.keywords)]
            if any(_is_scaled_px_call(arg) for arg in inner):
                findings.append(
                    Finding(
                        RULE_DOUBLE_SCALED_PX,
                        path,
                        node.lineno,
                        "scaled_px(scaled_px(...)) — the value is scaled twice; "
                        "scale the design value once",
                    )
                )
    index = _ImportIndex(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name not in _DESIGN_SIZE_CONSTRUCTORS or not index.is_toolkit(node.func):
            continue
        for keyword in node.keywords:
            if keyword.arg != "size":
                continue
            if any(_is_scaled_px_call(sub) for sub in ast.walk(keyword.value)):
                findings.append(
                    Finding(
                        RULE_DOUBLE_SCALED_PX,
                        path,
                        node.lineno,
                        f"{name}(size=...) takes design px and scales internally — "
                        f"pass the design value, not {ast.unparse(keyword.value)}",
                    )
                )
    return sorted(findings)


class _ImportTimeQColorVisitor(ast.NodeVisitor):
    """Report ``QColor(...)`` evaluated where it can never follow a theme.

    Module and class bodies (plus decorators/defaults, which also evaluate at
    import) are import time; a function body is not, because it re-runs on every
    theme change.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []

    def _visit_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        candidates: list[ast.expr | None] = [*node.args.defaults, *node.args.kw_defaults]
        for candidate in candidates:
            if candidate is not None:
                self.visit(candidate)
        for decorator in node.decorator_list:
            self.visit(decorator)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_defaults(node)  # the body runs per call — intentionally skipped

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_defaults(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func) == "QColor":
            self.findings.append(
                Finding(
                    RULE_QCOLOR_AT_IMPORT,
                    self.path,
                    node.lineno,
                    "QColor() evaluated at import time — the colour is frozen "
                    "before ThemeManager picks a theme; read a token at paint "
                    "time instead",
                )
            )
        self.generic_visit(node)


def check_qcolor_at_import(
    tree: ast.Module, source: str, path: str = "<memory>"
) -> list[Finding]:
    """``qcolor-at-import``: a literal colour evaluated in module/class scope."""
    visitor = _ImportTimeQColorVisitor(path)
    visitor.visit(tree)
    return sorted(visitor.findings)


def check_empty_stylesheet(
    tree: ast.Module, source: str, path: str = "<memory>"
) -> list[Finding]:
    """``empty-stylesheet``: ``setStyleSheet("")`` — theming text that does nothing."""
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node.func) != "setStyleSheet":
            continue
        if _is_empty_stylesheet(node):
            findings.append(
                Finding(
                    RULE_EMPTY_STYLESHEET,
                    path,
                    node.lineno,
                    'setStyleSheet("") is dead theming text — remove the call; '
                    "the painter pipeline owns the visuals",
                )
            )
    return sorted(findings)


def _comment_lines(source: str) -> Iterator[int]:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                yield token.start[0]
    except (tokenize.TokenError, IndentationError):
        for number, line in enumerate(source.splitlines(), start=1):
            if "#" in line:
                yield number


def _has_comment(comment_lines: set[int], first: int, last: int) -> bool:
    return any(first <= line <= last for line in comment_lines)


def _has_logging_call(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _call_name(sub.func) in _LOGGING_METHODS:
            return True
    return False


def check_silent_swallow(
    tree: ast.Module, source: str, path: str = "<memory>"
) -> list[Finding]:
    """``silent-swallow``: ``except ...: pass`` with no comment and no logging."""
    findings: list[Finding] = []
    comment_lines = set(_comment_lines(source))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        body = node.body
        if len(body) != 1 or not isinstance(body[0], ast.Pass):
            continue
        last = node.end_lineno or node.lineno
        if _has_comment(comment_lines, node.lineno, last):
            continue
        if _has_logging_call(node):
            continue
        exception = ast.unparse(node.type) if node.type is not None else "everything"
        findings.append(
            Finding(
                RULE_SILENT_SWALLOW,
                path,
                node.lineno,
                f"except {exception}: pass discards the failure — log it or add a "
                "comment explaining why the failure is expected",
            )
        )
    return sorted(findings)


def token_ownership_family(path: str, source: str = "") -> str | None:
    """The widget family *path*'s file paints for, or ``None``.

    ``source`` is read only for the ``# token-family: <name>`` declaration,
    which wins over the path map: a helper that serves one family (or a host
    layout the map does not know) states its ownership instead of borrowing.
    """
    declared = _declared_family(source)
    if declared:
        return declared
    normalised = path.replace("\\", "/")
    for fragment, family in TOKEN_FAMILIES:
        if fragment in normalised:
            return family
    return None


def _declared_family(source: str) -> str | None:
    """``# token-family: <name>`` from a real comment (never a string literal)."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                found = _TOKEN_FAMILY_COMMENT.search(token.string)
                if found:
                    return found.group(1)
    except (tokenize.TokenError, IndentationError):
        found = _TOKEN_FAMILY_COMMENT.search(source)
        if found:
            return found.group(1)
    return None


def _token_root(token: str) -> str | None:
    """First dotted segment of a palette key, or ``None`` for a non-token string.

    Prose, paths, QSS text and sentences all contain dots; a palette key does
    not contain whitespace and its root is a bare identifier.
    """
    if "." not in token or any(character.isspace() for character in token):
        return None
    root = token.split(".", 1)[0]
    if not root or not (root[0].isalpha() or root[0] == "_"):
        return None
    return root


def _token_family(token: str) -> str | None:
    """Owning family of a palette key; ``NEUTRAL_FAMILY`` for shared tokens."""
    root = _token_root(token)
    if root is None:
        return None
    if root in NEUTRAL_TOKENS or root in QT_PALETTE_ROLES:
        return NEUTRAL_FAMILY
    return TOKEN_OWNERS.get(root)


def _ownership_hint(family: str | None) -> str:
    if family is None:
        return "this file declares no family"
    return f"this file paints the {family} family"


def _fstring_prefix(node: ast.JoinedStr) -> ast.expr | None:
    """The leading ``{...}`` expression when *node* has the shape of a token key.

    ``f"{prefix}.background.hover"`` is a palette key built at runtime;
    ``f"{name}.emit(...) is blocked`` is prose. Only the first case is judged:
    a formatted value followed immediately by ``"."" and a whitespace-free
    literal tail.
    """
    values = node.values
    if len(values) < 2:
        return None
    head, tail = values[0], values[1]
    if not isinstance(head, ast.FormattedValue):
        return None
    if not isinstance(tail, ast.Constant) or not isinstance(tail.value, str):
        return None
    if not tail.value.startswith(".") or len(tail.value) < 2:
        return None
    literal = "".join(
        value.value
        for value in values
        if isinstance(value, ast.Constant) and isinstance(value.value, str)
    )
    if any(character.isspace() for character in literal):
        return None
    return head.value


def _prefix_key(target: ast.expr) -> str | None:
    name: str | None = None
    if isinstance(target, ast.Name):
        name = target.id
    elif isinstance(target, ast.Attribute):
        name = target.attr
    if name is None or name.rsplit("_", 1)[-1] != _PREFIX_SUFFIX:
        return None
    return name


class _TokenOwnershipVisitor(ast.NodeVisitor):
    """Report palette keys a file reads outside its own family.

    Ownership is per file: the path map (or a ``# token-family:`` comment)
    names the family the file paints for, and a literal from any other family
    is a borrow. Three shapes: a literal key, an f-string key whose prefix
    variable has a literal assignment (judged like a literal), and an f-string
    whose prefix cannot be resolved (reported, not guessed).
    """

    def __init__(self, path: str, source: str) -> None:
        self.path = path
        self.family = token_ownership_family(path, source)
        self.prefixes: dict[str, str] = {}
        self.findings: list[Finding] = []
        # Palette modules are *made* of every family's keys; the same basename
        # exemption ``qcolor-at-import`` uses.
        self.exempt = is_qcolor_exempt(path)

    def collect_prefixes(self, tree: ast.Module) -> None:
        for node in ast.walk(tree):
            pairs: list[tuple[ast.expr, ast.expr]] = []
            if isinstance(node, ast.Assign):
                pairs = [(target, node.value) for target in node.targets]
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                pairs = [(node.target, node.value)]
            for target, value in pairs:
                if not isinstance(value, ast.Constant) or not isinstance(
                    value.value, str
                ):
                    continue
                key = _prefix_key(target)
                if key is not None:
                    self.prefixes.setdefault(key, value.value)

    def _resolve(self, node: ast.expr) -> str | None:
        candidates = [ast.unparse(node)]
        if isinstance(node, ast.Name):
            candidates.append(node.id)
        elif isinstance(node, ast.Attribute):
            candidates.append(node.attr)
        for candidate in candidates:
            if candidate in self.prefixes:
                return self.prefixes[candidate]
        return None

    def _borrow_message(self, owner: str, key: str) -> str:
        remedy = (
            "read a neutral token"
            if self.family is None
            else f"read a {self.family} or neutral token"
        )
        return (
            f"{key} is a {owner} token, but {_ownership_hint(self.family)} — "
            f"{remedy}, or declare \"# token-family: {owner}\" when this file "
            "serves that family"
        )

    def visit_Constant(self, node: ast.Constant) -> None:
        if self.exempt or not isinstance(node.value, str):
            return
        owner = _token_family(node.value)
        if owner is None or owner == NEUTRAL_FAMILY or owner == self.family:
            return
        self.findings.append(
            Finding(
                RULE_TOKEN_OWNERSHIP,
                self.path,
                node.lineno,
                self._borrow_message(owner, f'"{node.value}"'),
            )
        )

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        if self.exempt:
            return
        prefix = _fstring_prefix(node)
        if prefix is not None:
            text = ast.unparse(node)
            variable = ast.unparse(prefix)
            resolved = self._resolve(prefix)
            if resolved is None:
                self.findings.append(
                    Finding(
                        RULE_TOKEN_OWNERSHIP_UNRESOLVED,
                        self.path,
                        node.lineno,
                        f"{text} builds a palette key from {variable!r}, which "
                        "has no literal prefix assignment here — bind "
                        f'{variable} = "<family>.<variant>" so the family is '
                        "checkable",
                    )
                )
            else:
                owner = _token_family(resolved)
                if (
                    owner is not None
                    and owner != NEUTRAL_FAMILY
                    and owner != self.family
                ):
                    self.findings.append(
                        Finding(
                            RULE_TOKEN_OWNERSHIP_DYNAMIC,
                            self.path,
                            node.lineno,
                            f"{text} reads the {owner} family through {variable!r} "
                            f"({resolved!r}), but {_ownership_hint(self.family)} "
                            "— give the file its own family prefix",
                        )
                    )
        self.generic_visit(node)


def _token_ownership_findings(
    tree: ast.Module, source: str, path: str
) -> list[Finding]:
    visitor = _TokenOwnershipVisitor(path, source)
    visitor.collect_prefixes(tree)
    visitor.visit(tree)
    return visitor.findings


def check_token_ownership(
    tree: ast.Module, source: str, path: str = "<memory>"
) -> list[Finding]:
    """``token-ownership``: a literal palette key from another family."""
    return sorted(
        finding
        for finding in _token_ownership_findings(tree, source, path)
        if finding.rule == RULE_TOKEN_OWNERSHIP
    )


def check_token_ownership_dynamic(
    tree: ast.Module, source: str, path: str = "<memory>"
) -> list[Finding]:
    """``token-ownership-dynamic``: an f-string key built on another family."""
    return sorted(
        finding
        for finding in _token_ownership_findings(tree, source, path)
        if finding.rule == RULE_TOKEN_OWNERSHIP_DYNAMIC
    )


def check_token_ownership_unresolved(
    tree: ast.Module, source: str, path: str = "<memory>"
) -> list[Finding]:
    """``token-ownership-unresolved``: an f-string token key with no known prefix."""
    return sorted(
        finding
        for finding in _token_ownership_findings(tree, source, path)
        if finding.rule == RULE_TOKEN_OWNERSHIP_UNRESOLVED
    )


#: Rule registry, in the CLI/`--rule` order.
RULES: dict[str, Rule] = {
    RULE_TOOLKIT_QSS: check_toolkit_qss,
    RULE_RAW_CHROME_PX: check_raw_chrome_px,
    RULE_DOUBLE_SCALED_PX: check_double_scaled_px,
    RULE_QCOLOR_AT_IMPORT: check_qcolor_at_import,
    RULE_EMPTY_STYLESHEET: check_empty_stylesheet,
    RULE_SILENT_SWALLOW: check_silent_swallow,
    RULE_TOKEN_OWNERSHIP: check_token_ownership,
    RULE_TOKEN_OWNERSHIP_DYNAMIC: check_token_ownership_dynamic,
    RULE_TOKEN_OWNERSHIP_UNRESOLVED: check_token_ownership_unresolved,
}

__all__ = [
    "NEUTRAL_FAMILY",
    "NEUTRAL_TOKENS",
    "QT_PALETTE_ROLES",
    "RULE_DOUBLE_SCALED_PX",
    "RULE_EMPTY_STYLESHEET",
    "RULE_QCOLOR_AT_IMPORT",
    "RULE_RAW_CHROME_PX",
    "RULE_SILENT_SWALLOW",
    "RULE_TOKEN_OWNERSHIP",
    "RULE_TOKEN_OWNERSHIP_DYNAMIC",
    "RULE_TOKEN_OWNERSHIP_UNRESOLVED",
    "RULE_TOOLKIT_QSS",
    "RULES",
    "Rule",
    "TOKEN_FAMILIES",
    "TOKEN_OWNERS",
    "check_double_scaled_px",
    "check_empty_stylesheet",
    "check_qcolor_at_import",
    "check_raw_chrome_px",
    "check_silent_swallow",
    "check_token_ownership",
    "check_token_ownership_dynamic",
    "check_token_ownership_unresolved",
    "check_toolkit_qss",
    "token_ownership_family",
]
