"""QSS scanning for the inspector: candidate rules + dead-selector analysis.

Qt exposes no computed CSS origins — the candidate list is heuristic (same
logic the app's inspector used). ``dead_selectors`` flags rules that match no
live widget in the current widget tree, so stale selectors become visible
(e.g. legacy icon-button / fluent-combobox rules).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PySide6.QtWidgets import QApplication, QWidget

_QSS_BLOCK_RE = re.compile(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", re.S)


@dataclass(frozen=True)
class QssRule:
    source: str
    selector: str
    body: str
    line: int = 0


@dataclass(frozen=True)
class _ParsedSelector:
    """Selector decomposed once, so per-widget matching is set lookups
    instead of re-running several regexes for every rule × widget pair."""

    leaf: str
    selector_type: str | None
    selector_object: str | None
    properties: tuple[tuple[str, str], ...]
    prefix_types: tuple[str, ...]


class QssIndex:
    def __init__(self, rules: Iterable[QssRule]):
        self._rules = tuple(rules)
        self._parsed: tuple[tuple[QssRule, _ParsedSelector], ...] = tuple(
            (rule, parsed)
            for rule in self._rules
            if (parsed := _parse_selector(rule.selector)) is not None
        )

    @property
    def rules(self) -> tuple[QssRule, ...]:
        return self._rules

    @classmethod
    def from_theme_manager(cls, theme_manager) -> "QssIndex":
        paths = tuple(getattr(theme_manager, "_qss_paths", ()) or ())
        return cls.from_paths(paths)

    @classmethod
    def from_paths(cls, paths: Iterable[str]) -> "QssIndex":
        rules: list[QssRule] = []
        for path in paths:
            if not path or not os.path.exists(path):
                continue
            rules.extend(_parse_rules(path, Path(path).read_text(encoding="utf-8")))
        return cls(rules)

    @classmethod
    def from_text(cls, text: str, source: str = "<string>") -> "QssIndex":
        return cls(_parse_rules(source, text))

    def candidates_for(self, widget: QWidget) -> tuple[QssRule, ...]:
        class_names = _class_mro_names(widget)
        object_name = widget.objectName()
        properties: dict[str, str] = {}
        for name in widget.dynamicPropertyNames():
            key = bytes(name).decode("utf-8", errors="replace")
            try:
                properties[key] = str(widget.property(key))
            except (RuntimeError, TypeError):
                continue
        ancestor_names = _ancestor_mro_names(widget)
        return tuple(
            rule
            for rule, parsed in self._parsed
            if _parsed_may_match(
                parsed,
                class_names=class_names,
                object_name=object_name,
                properties=properties,
                ancestor_names=ancestor_names,
            )
        )

    def dead_selectors(self, widgets: Iterable[QWidget]) -> tuple[tuple[QssRule, bool], ...]:
        """(rule, matched_any) for every rule against the given widgets.

        ``matched_any`` False = no live widget satisfies the rule's leaf
        type/objectName/property constraints — a likely-dead selector.
        """
        widgets = list(widgets)
        contexts = [_widget_match_context(w) for w in widgets]
        return tuple(
            (rule, any(_parsed_may_match(parsed, **ctx) for ctx in contexts))
            for rule, parsed in self._parsed
        )

    def dead_selectors_in_app(self) -> tuple[tuple[QssRule, bool], ...]:
        """dead_selectors over every live widget in the application."""
        widgets: list[QWidget] = []
        for top in QApplication.topLevelWidgets():
            widgets.append(top)
            widgets.extend(top.findChildren(QWidget))
        return self.dead_selectors(widgets)


def _widget_match_context(widget: QWidget) -> dict[str, object]:
    properties: dict[str, str] = {}
    for name in widget.dynamicPropertyNames():
        key = bytes(name).decode("utf-8", errors="replace")
        try:
            properties[key] = str(widget.property(key))
        except (RuntimeError, TypeError):
            continue
    return {
        "class_names": _class_mro_names(widget),
        "object_name": widget.objectName(),
        "properties": properties,
        "ancestor_names": _ancestor_mro_names(widget),
    }


def _parse_rules(source: str, text: str) -> list[QssRule]:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    rules: list[QssRule] = []
    for match in _QSS_BLOCK_RE.finditer(text):
        body = match.group("body").strip()
        start = match.start()
        while start < len(text) and text[start] in "\n\r\t ":
            start += 1
        line = text.count("\n", 0, start) + 1
        for selector in match.group("selectors").split(","):
            selector = " ".join(selector.strip().split())
            if selector:
                rules.append(
                    QssRule(source=source, selector=selector, body=body, line=line)
                )
    return rules


def _parse_selector(selector: str) -> _ParsedSelector | None:
    leaf = selector.split(">")[-1].split()[-1].strip()
    if not leaf:
        return None
    selector_object = None
    if "#" in leaf:
        _, _, raw_object = leaf.partition("#")
        selector_object = re.split(r"[:\[]", raw_object, maxsplit=1)[0]
    type_match = re.match(r"^[A-Za-z_][A-Za-z0-9_]*", leaf)
    selector_type = type_match.group(0) if type_match else None
    return _ParsedSelector(
        leaf=leaf,
        selector_type=selector_type,
        selector_object=selector_object,
        properties=tuple(re.findall(r"\[([^=\]]+)=\"([^\"]*)\"\]", selector)),
        prefix_types=tuple(
            re.findall(
                r"\b[A-Za-z_][A-Za-z0-9_]*\b", selector.rsplit(leaf, 1)[0]
            )
        ),
    )


def _parsed_may_match(
    parsed: _ParsedSelector,
    *,
    class_names: tuple[str, ...],
    object_name: str,
    properties: dict[str, str],
    ancestor_names: frozenset[str],
) -> bool:
    if parsed.selector_object is not None and parsed.selector_object != object_name:
        return False
    if parsed.selector_type is not None and parsed.selector_type not in class_names:
        return False
    for prop, expected in parsed.properties:
        if properties.get(prop) != expected:
            return False
    for parent_type in parsed.prefix_types:
        if parent_type not in ancestor_names and parent_type != "QWidget":
            return False
    return bool(
        parsed.selector_type is not None
        or parsed.selector_object is not None
        or parsed.properties
    )


def _class_mro_names(widget: QWidget) -> tuple[str, ...]:
    """Every class in the widget's MRO — Qt type selectors match subclasses
    too, so ``AdaptiveTabStrip {...}`` applies to ``WorkspaceTabStrip``."""
    return tuple(c.__name__ for c in type(widget).__mro__)


def _ancestor_mro_names(widget: QWidget) -> frozenset[str]:
    """MRO names of every ancestor widget, for descendant selectors."""
    names: set[str] = set()
    parent = widget.parentWidget()
    while parent is not None:
        names.update(c.__name__ for c in type(parent).__mro__)
        parent = parent.parentWidget()
    return frozenset(names)


__all__ = ["QssIndex", "QssRule"]
