import os
import time
from enum import Enum
from pathlib import Path
from typing import Dict, Type, TypeVar, Union

from PySide6.QtGui import QIcon

from sli_ui_toolkit.theme import ThemeManager

T = TypeVar("T", bound=Enum)

#: How long a filesystem miss stays cached. Misses are re-probed after this
#: so icons installed after the first lookup (host asset unpack, lazy theme
#: download) still resolve without a process restart. The primary (first)
#: candidate root is additionally re-checked on every lookup — see
#: :meth:`IconService.get_icon` — so the common "icon lands in the theme
#: dir" case recovers immediately instead of waiting out the TTL.
NEGATIVE_CACHE_TTL_S = 30.0

class IconService:
    def __init__(
        self, project_root: str, icons_relative_path: str = "resources/assets/icons",
        negative_ttl_s: float = NEGATIVE_CACHE_TTL_S,
    ):
        self.project_root = Path(project_root)
        self.icons_path = self.project_root / icons_relative_path
        self._md_cache: Dict[str, Dict[str, QIcon]] = {}
        self._icon_cache: Dict[tuple[str, bool], QIcon] = {}
        # Negative cache: key -> monotonic timestamp of the miss. Bounds the
        # os.path.exists stat storm when a name is looked up repeatedly but
        # ships in no root (e.g. per-frame toolbar rebuilds with a typo'd id).
        self._miss_cache: Dict[tuple[str, bool], float] = {}
        self._negative_ttl_s = float(negative_ttl_s)

    def get_icon(self, icon_name: str, is_dark: bool | None = None) -> QIcon:
        if is_dark is None:
            theme_manager = ThemeManager.get_instance()
            is_dark = theme_manager.is_dark()

        # Allow callers to pass either "name" or "name.svg".
        if not os.path.splitext(icon_name)[1]:
            icon_name_with_ext = icon_name + ".svg"
        else:
            icon_name_with_ext = icon_name

        cache_key = (icon_name_with_ext, bool(is_dark))

        candidates = []
        if is_dark:
            candidates.append(self.icons_path / "dark" / icon_name_with_ext)
        candidates.append(self.icons_path / "light" / icon_name_with_ext)
        candidates.append(self.icons_path / icon_name_with_ext)

        missed_at = self._miss_cache.get(cache_key)
        if missed_at is not None:
            if time.monotonic() - missed_at < self._negative_ttl_s:
                # Fresh miss: skip the stat storm, but always revisit the
                # first (primary-theme) root — a single cheap exists() — so
                # an icon dropped into the theme dir resolves immediately
                # instead of waiting out the TTL.
                try:
                    first_now_exists = os.path.exists(str(candidates[0]))
                except (AttributeError, RecursionError):
                    first_now_exists = False
                if not first_now_exists:
                    return self._fallback_icon(icon_name_with_ext, cache_key)
                del self._miss_cache[cache_key]
                self._icon_cache.pop(cache_key, None)
            else:
                del self._miss_cache[cache_key]
                self._icon_cache.pop(cache_key, None)

        cached = self._icon_cache.get(cache_key)
        if cached is not None:
            return cached

        for path in candidates:
            try:
                if os.path.exists(str(path)):
                    icon = QIcon(str(path))
                    self._icon_cache[cache_key] = icon
                    self._miss_cache.pop(cache_key, None)
                    return icon
            except (AttributeError, RecursionError):
                continue

        # Last resort — return the (likely empty) QIcon constructed from light path.
        self._miss_cache[cache_key] = time.monotonic()
        return self._fallback_icon(icon_name_with_ext, cache_key)

    def _fallback_icon(self, icon_name_with_ext: str, cache_key: tuple[str, bool]) -> QIcon:
        icon = QIcon(str(self.icons_path / "light" / icon_name_with_ext))
        self._icon_cache[cache_key] = icon
        return icon

    def invalidate(self, icon_name: str | None = None, is_dark: bool | None = None) -> None:
        """Drop cached hits (and misses): ``None`` name clears everything."""
        if icon_name is None:
            self._icon_cache.clear()
            self._miss_cache.clear()
            return
        keys = [icon_name, icon_name + ".svg"] if not os.path.splitext(icon_name)[1] else [icon_name]
        for key in keys:
            for dark in (True, False) if is_dark is None else (bool(is_dark),):
                self._icon_cache.pop((key, dark), None)
                self._miss_cache.pop((key, dark), None)

    def get_enum_icon(
        self, icon_enum: Union[str, T], enum_class: Type[T]
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
    existing = _services.get(project_name)
    if existing is not None:
        # First-root revisit: the first caller's root used to pin the entry
        # forever, so a later explicit root (tests, asset relocation, second
        # host in one process) was silently ignored and kept resolving
        # against the stale tree. An explicit, differing root rebuilds.
        if (
            project_root is not None
            and Path(project_root) != existing.project_root
        ):
            existing = None
        else:
            return existing
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
