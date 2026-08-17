"""Code section of the inspector — package init (thin, no implementation).

The editor lives in ``editor.py`` (thin owner + use_cases: ``apply.py`` /
``preview.py`` / ``config.py`` hold the mechanics); this module only
re-exports the public surface. See ``editor.py`` for the full description.
"""

from sli_ui_toolkit.ui.inspector.code.editor import (
    CodeSectionEditor,
    build_code_section,
)

__all__ = ["CodeSectionEditor", "build_code_section"]
