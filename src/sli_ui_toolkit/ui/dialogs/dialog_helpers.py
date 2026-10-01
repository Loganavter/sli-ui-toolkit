import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.layout_settle import settle_layout
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.utils import resource_path

class BaseDialog(QDialog):
    def __init__(self, parent=None, title="", min_width=0, min_height=0):
        super().__init__(parent)
        self.setObjectName(f"{self.__class__.__name__}")
        self.theme_manager = ThemeManager.get_instance()
        self._surface_color = QColor("#000000")
        self._read_surface_color()

        self._setup_window(title, min_width, min_height)
        self._setup_icon()
        self._setup_theme()

    def _read_surface_color(self) -> None:
        """Re-read the ``dialog.background`` token into ``_surface_color``.

        Re-read on every ``theme_changed`` (never cached forever): hosts may
        override the token via ``ThemeManager.set_color``. ThemeManager may
        be uninitialized in some test contexts — fall back to the palette
        Window role as a last resort.
        """
        try:
            color = QColor(
                ThemeManager.get_instance().get_color("surface.background")
            )
        except Exception:
            color = QColor(self.palette().window().color())
        self._surface_color = color

    def paintEvent(self, event) -> None:  # noqa: N802
        """Fill the dialog surface with the ``dialog.background`` token.

        Top-level QDialog QSS surface paint dies with host QSS: with no
        stylesheet the dialog paints the QPalette Window role, which hosts
        keep darker than the dialog surface token — the explicit paint keeps
        the surface consistent with the toolkit's other painted surfaces.
        """
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._surface_color)
        painter.end()

    def _setup_window(self, title, min_width, min_height):
        if title:
            self.setWindowTitle(title)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)

        if min_width > 0:
            self.setMinimumWidth(min_width)
        if min_height > 0:
            self.setMinimumHeight(min_height)

    def _setup_icon(self):
        setup_dialog_icon(self)

    def _setup_theme(self):
        self.theme_manager.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self):
        self._read_surface_color()
        self.update()

def setup_dialog_scaffold(
    dialog: QDialog,
    main_layout: QVBoxLayout,
    ok_text: str,
    cancel_text: str = "Cancel",
    show_cancel_button: bool = True,
):
    action_bar = QWidget(dialog)
    action_layout = QHBoxLayout(action_bar)
    action_layout.setContentsMargins(0, 0, 0, 0)
    action_layout.setSpacing(8)
    action_layout.addStretch()

    ok_button = Button(text=ok_text, variant="surface", parent=action_bar)
    ok_button.setProperty("class", "primary")

    cancel_button = Button(text=cancel_text, variant="surface", parent=action_bar)

    ok_button.clicked.connect(dialog.accept)
    cancel_button.clicked.connect(dialog.reject)

    if not show_cancel_button:
        cancel_button.hide()

    action_layout.addWidget(ok_button)
    action_layout.addWidget(cancel_button)
    main_layout.addWidget(action_bar)

    # Public API: host code (and this toolkit's own tests) read
    # dialog.ok_button / dialog.cancel_button after calling this helper.
    dialog.ok_button = ok_button  # type: ignore[attr-defined]
    dialog.cancel_button = cancel_button  # type: ignore[attr-defined]

def setup_dialog_icon(dialog: QDialog, icon_path: str | None = None):
    if icon_path is None:
        try:
            icon_path = resource_path("resources/icons/icon.png")
        except Exception:
            return

    if icon_path and os.path.exists(icon_path):
        dialog.setWindowIcon(QIcon(icon_path))

def _dialog_layout_children(dialog: QDialog) -> list[QWidget]:
    """Direct layout children of ``dialog`` (for ``settle_layout``)."""
    layout = dialog.layout()
    if layout is None:
        return []
    children: list[QWidget] = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        widget = item.widget() if item is not None else None
        if widget is not None:
            children.append(widget)
    return children


def apply_auto_size(dialog: QDialog, min_width: int = 0, min_height: int = 0) -> None:
    """Resize ``dialog`` to its content synchronously (no event-loop wait).

    The synchronous core behind ``auto_size_dialog``: refreshes child hints
    first (so ``adjustSize()``/``sizeHint()`` below see current child state
    instead of a stale cache), resizes from the fresh hint, re-syncs group
    frames, then settles the dialog layout in the same call — the widget
    and its contents agree in the first painted frame (see
    ``ui.layout_settle``). A dialog without a layout still resizes; the
    settle is a no-op there.
    """
    children = _dialog_layout_children(dialog)
    settle_layout(dialog, *children)
    dialog.ensurePolished()
    dialog.adjustSize()

    content_size = dialog.sizeHint()

    final_width = max(min_width, content_size.width() + 50)
    final_height = max(min_height, content_size.height() + 30)

    dialog.resize(final_width, final_height)

    _update_group_sizes(dialog)
    settle_layout(dialog, *children)


def auto_size_dialog(dialog: QDialog, min_width: int = 0, min_height: int = 0):
    """Size ``dialog`` to its content (deferred when still hidden).

    A hidden dialog has no valid hints yet, so the sizing is posted to the
    next loop turn (as before). A dialog that is already visible/polished
    is sized synchronously in the same call — its hints are valid and
    there is no reason to show one frame at the old size. Either leg ends
    in ``apply_auto_size``'s synchronous settle.
    """
    if dialog.isVisible():
        apply_auto_size(dialog, min_width, min_height)
        return

    def _recalculate_sizes():
        try:
            apply_auto_size(dialog, min_width, min_height)
        except RuntimeError:
            pass  # dialog torn down before the deferred pass ran

    QTimer.singleShot(0, _recalculate_sizes)

def _update_group_sizes(dialog: QDialog):
    for child in dialog.findChildren(QWidget):
        if child.objectName() == "StyledGroupFrame":
            parent_group = child.parent()
            if isinstance(parent_group, QWidget):
                content_width = child.sizeHint().width()
                min_width = content_width + 30

                for title_child in parent_group.findChildren(QLabel):
                    if title_child.objectName() == "StyledGroupTitle":
                        title_width = title_child.width() + 40
                        min_width = max(min_width, title_width)
                        break

                parent_group.resize(max(parent_group.width(), min_width), parent_group.height())
                # The resize above derives the host's size from a child's
                # hint while a layout may place its children: settle now so
                # the group and its contents agree in the same call (a group
                # without a layout is a no-op for the settle, not an error).
                settle_layout(parent_group, child)
                parent_group.updateGeometry()
