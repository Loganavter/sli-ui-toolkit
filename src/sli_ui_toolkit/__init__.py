"""Reusable PyQt toolkit primitives."""

from sli_ui_toolkit._version import __version__
from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit
from sli_ui_toolkit.palettes import FLUENT_LIGHT, FLUENT_DARK
from sli_ui_toolkit.core.logging import (
    get_log_directory,
    setup_logging,
    setup_simple_logging,
)
from sli_ui_toolkit.i18n import (
    I18nStateError,
    ToolkitTranslationEvents,
    TranslationManager,
    configure_i18n,
    emit_language_changed,
    get_current_language,
    tr,
    translation_events,
)
from sli_ui_toolkit.utils.file_utils import get_unique_filepath
from sli_ui_toolkit.utils.paths import resource_path
from sli_ui_toolkit.workers.generic_worker import GenericWorker, WorkerSignals
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import (
    DEFER_CLICK_AWAIT_RIPPLE,
    Label,
    LabelConfig,
    LabelVariantSpec,
    application_tooltips_enabled,
    get_default_defer_click,
    get_label_variant,
    get_ripple_duration_ms,
    install_application_tooltips,
    popup_context_menu_for_anchor,
    register_label_variant,
    set_application_tooltips_enabled,
    set_default_defer_click,
    set_ripple_duration_ms,
)
from sli_ui_toolkit.style import (
    WidgetStyleTokens,
    read_widget_style,
    update_widget_style,
)
from sli_ui_toolkit.ui.windows import (
    CustomTitleBar,
    TitleBarMenu,
    TitleBarMenuStrip,
    TitleBarPresets,
    WindowChrome,
    WindowChromeConfig,
    WindowControlsConfig,
    apply_frameless,
    decorate_dialog,
    remove_frameless,
    set_frameless_runtime,
    set_window_bg_color,
)

__all__ = [
    "__version__",
    "GenericWorker",
    "WorkerSignals",
    "ThemeManager",
    "Label",
    "LabelConfig",
    "LabelVariantSpec",
    "get_label_variant",
    "register_label_variant",
    "application_tooltips_enabled",
    "install_application_tooltips",
    "set_application_tooltips_enabled",
    "WidgetStyleTokens",
    "read_widget_style",
    "update_widget_style",
    "FlyoutTimingConfig",
    "I18nStateError",
    "ToolkitTranslationEvents",
    "TranslationManager",
    "configure_i18n",
    "configure_toolkit",
    "DEFER_CLICK_AWAIT_RIPPLE",
    "emit_language_changed",
    "get_default_defer_click",
    "get_log_directory",
    "get_current_language",
    "get_ripple_duration_ms",
    "get_unique_filepath",
    "resource_path",
    "set_default_defer_click",
    "set_ripple_duration_ms",
    "setup_logging",
    "setup_simple_logging",
    "tr",
    "translation_events",
    "FLUENT_LIGHT",
    "FLUENT_DARK",
    "CustomTitleBar",
    "TitleBarMenu",
    "TitleBarMenuStrip",
    "TitleBarPresets",
    "WindowChrome",
    "WindowChromeConfig",
    "WindowControlsConfig",
    "apply_frameless",
    "remove_frameless",
    "set_frameless_runtime",
    "decorate_dialog",
    "popup_context_menu_for_anchor",
    "set_window_bg_color",
]
