import os
from pathlib import Path
from typing import Dict, Type, TypeVar, Union

from PySide6.QtGui import QIcon

from sli_ui_toolkit.theme import ThemeManager

T = TypeVar("T")

class IconService:
    def __init__(
        self, project_root: str, icons_relative_path: str = "resources/assets/icons"
    ):
        self.project_root = Path(project_root)
        self.icons_path = self.project_root / icons_relative_path
        self._md_cache: Dict[str, Dict[str, QIcon]] = {}
        self._icon_cache: Dict[tuple[str, bool], QIcon] = {}

    def get_icon(self, icon_name: str, is_dark: bool = None) -> QIcon:
        if is_dark is None:
            theme_manager = ThemeManager.get_instance()
            is_dark = theme_manager.is_dark()

        # Allow callers to pass either "name" or "name.svg".
        if not os.path.splitext(icon_name)[1]:
            icon_name_with_ext = icon_name + ".svg"
        else:
            icon_name_with_ext = icon_name

        cache_key = (icon_name_with_ext, bool(is_dark))
        cached = self._icon_cache.get(cache_key)
        if cached is not None:
            return cached

        candidates = []
        if is_dark:
            candidates.append(self.icons_path / "dark" / icon_name_with_ext)
        candidates.append(self.icons_path / "light" / icon_name_with_ext)
        candidates.append(self.icons_path / icon_name_with_ext)

        for path in candidates:
            try:
                if os.path.exists(str(path)):
                    icon = QIcon(str(path))
                    self._icon_cache[cache_key] = icon
                    return icon
            except (AttributeError, RecursionError):
                continue

        # Last resort — return the (likely empty) QIcon constructed from light path.
        fallback = self.icons_path / "light" / icon_name_with_ext
        icon = QIcon(str(fallback))
        self._icon_cache[cache_key] = icon
        return icon

    def get_enum_icon(
        self, icon_enum: Union[str, object], enum_class: Type[T]
    ) -> QIcon:
        if isinstance(icon_enum, str):
            for item in enum_class:
                if item.value == icon_enum:
                    return self.get_icon(item.value)
            raise ValueError(f"Icon '{icon_enum}' not found in {enum_class.__name__}")

        return self.get_icon(icon_enum.value)

_services: Dict[str, IconService] = {}

def _default_toolkit_root() -> str:
    # sli_ui_toolkit/ui/services/icon_service.py → sli_ui_toolkit/
    return str(Path(__file__).resolve().parents[2])


def get_icon_service(
    project_name: str,
    *,
    project_root: str | None = None,
    icons_relative_path: str = "resources/assets/icons",
) -> IconService:
    if project_name not in _services:
        if project_root is None:
            project_root = _default_toolkit_root()
        _services[project_name] = IconService(project_root, icons_relative_path)

    return _services[project_name]

def get_icon_by_name(
    icon_name: str,
    project_name: str = "Default",
    *,
    project_root: str | None = None,
    icons_relative_path: str = "resources/assets/icons",
) -> QIcon:
    service = get_icon_service(
        project_name,
        project_root=project_root,
        icons_relative_path=icons_relative_path,
    )
    return service.get_icon(icon_name)
