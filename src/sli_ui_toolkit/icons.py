import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtGui import QIcon

logger = logging.getLogger(__name__)

from sli_ui_toolkit.ui.services.icon_service import (
    IconService,
    get_icon_by_name,
    get_icon_service,
)
from sli_ui_toolkit.ui.managers.icon_manager import get_icon_by_path, get_themed_icon

_icon_resolver: Callable[[Any], QIcon] | None = None
_named_icons: dict[str, Any] = {}

def configure_icon_resolver(
    resolver: Callable[[Any], QIcon] | None,
    *,
    named_icons: dict[str, Any] | None = None,
) -> None:
    global _icon_resolver, _named_icons
    _icon_resolver = resolver
    _named_icons = dict(named_icons or {})

def resolve_icon(icon: Any) -> QIcon:
    if icon is None:
        return QIcon()
    if isinstance(icon, QIcon):
        return icon
    if isinstance(icon, str):
        mapped = _named_icons.get(icon)
        if mapped is not None:
            if _icon_resolver is not None:
                try:
                    mapped_result = _icon_resolver(mapped)
                    if mapped_result.isNull():
                        logger.warning("icon resolver returned blank icon for mapped %r", icon)
                    else:
                        return mapped_result
                except Exception:
                    logger.warning("icon resolver raised for mapped %r; falling back to default", icon, exc_info=True)
            mapped_name = getattr(mapped, "value", mapped)
            mapped_fallback = get_icon_by_name(mapped_name)
            if mapped_fallback.isNull():
                logger.warning("icon resolution returned blank icon for mapped %r (%r)", icon, mapped_name)
            return mapped_fallback
        # Try app resolver first for plain strings like "magnifier.svg"
        # (Improve-ImgSLI's PanelVisibility uses this) before falling back
        # to the toolkit's default icon service which has no such file.
        if _icon_resolver is not None:
            try:
                result = _icon_resolver(icon)
                if not result.isNull():
                    return result
                logger.warning("icon resolver returned blank icon for %r; falling back to default", icon)
            except Exception:
                logger.warning("icon resolver raised for %r; falling back to default", icon, exc_info=True)
        icon_result = get_icon_by_name(icon)
        if icon_result.isNull():
            logger.warning("icon resolution returned blank icon for %r", icon)
        return icon_result
    if _icon_resolver is not None:
        try:
            res = _icon_resolver(icon)
            if res.isNull():
                logger.warning("icon resolver returned blank icon for %r", icon)
            return res
        except Exception:
            logger.warning("icon resolver raised for %r; returning blank icon", icon, exc_info=True)
            return QIcon()
    value = getattr(icon, "value", None)
    if isinstance(value, str):
        value_result = get_icon_by_name(value)
        if value_result.isNull():
            logger.warning("icon resolution returned blank icon for %r", icon)
        return value_result
    logger.warning("icon resolution returned blank icon for %r", icon)
    return QIcon()

def get_named_icon(name: str) -> Any:
    return _named_icons.get(name)

__all__ = [
    "IconService",
    "configure_icon_resolver",
    "get_icon_by_name",
    "get_icon_by_path",
    "get_icon_service",
    "get_named_icon",
    "get_themed_icon",
    "resolve_icon",
]
