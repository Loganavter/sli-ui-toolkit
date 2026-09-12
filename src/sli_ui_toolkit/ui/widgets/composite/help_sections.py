from __future__ import annotations

import re
from pathlib import Path

from sli_ui_toolkit.ui.widgets.composite.markdown_help_dialog import (
    MarkdownHelpSection,
    strip_heading_attr_suffix,
)

_SECTION_FILENAME_RE = re.compile(r"^(?P<order>\d{3})_(?P<slug>.+)\.md$")


def normalize_help_language(language: str | None) -> str:
    try:
        lang_norm = str(language or "en").strip()
    except Exception:
        lang_norm = "en"
    base = lang_norm.split("_")[0].lower() if "_" in lang_norm else lang_norm.lower()
    if base == "pt":
        return "pt_BR"
    if base.startswith("zh"):
        return "zh"
    if base in ("ru", "en"):
        return base
    return "en"


def toc_title_for_language(language: str | None) -> str:
    lang = normalize_help_language(language)
    if lang == "ru":
        return "На этой странице"
    if lang == "pt_BR":
        return "Nesta pagina"
    if lang == "zh":
        return "本页内容"
    return "On this page"


def extract_markdown_title_and_body(
    raw_text: str, fallback_slug: str
) -> tuple[str, str]:
    lines = raw_text.splitlines()
    title_index = None
    title = ""
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        title_index = idx
        title = strip_heading_attr_suffix(stripped.lstrip("#").strip())
        break
    if not title:
        title = fallback_slug.replace("_", " ").replace("-", " ").strip().title()
    body_lines = list(lines)
    if title_index is not None:
        body_lines.pop(title_index)
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
    return title, "\n".join(body_lines)


def read_markdown_help_sections(directory: str | Path) -> tuple[MarkdownHelpSection, ...]:
    path = Path(directory)
    if not path.is_dir():
        return ()

    sections: list[MarkdownHelpSection] = []
    for item in sorted(path.iterdir(), key=lambda p: p.name):
        match = _SECTION_FILENAME_RE.match(item.name)
        if not match or not item.is_file():
            continue
        raw_text = item.read_text(encoding="utf-8")
        title, body_md = extract_markdown_title_and_body(raw_text, match.group("slug"))
        sections.append(
            MarkdownHelpSection(
                order=int(match.group("order")),
                slug=match.group("slug"),
                title=title,
                body_md=body_md,
            )
        )
    return tuple(sorted(sections, key=lambda section: (section.order, section.slug)))
