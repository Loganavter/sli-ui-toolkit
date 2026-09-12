"""Mixin that makes theme-change repaint non-optional for a widget class.

See ``docs/dev/THEME_REPAINT_UNIFICATION.md`` in the ``Improve-ImgSLI`` app
repo for the design rationale: this folds the "connect theme_changed to
update() in every subclass's __init__" pattern already used by ~20 toolkit
widgets into a base class, so new widgets get it for free instead of
opt-in per file.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.managers.theme_manager import ThemeManager


class ThemedWidget:
    """Auto-subscribes to ``ThemeManager.theme_changed`` and repaints.

    Subclasses override :meth:`on_theme_changed` for anything beyond a
    plain ``update()`` (palette/background writes, cached-color recompute,
    etc.) and must call ``super().on_theme_changed()`` to still get the
    repaint. Do not override ``__init__``'s subscription logic — that is
    the part this mixin exists to make non-optional.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self.on_theme_changed)
        self.on_theme_changed()

    def on_theme_changed(self) -> None:
        self.update()
