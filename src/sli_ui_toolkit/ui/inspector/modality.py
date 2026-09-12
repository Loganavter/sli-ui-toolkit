"""Modal-window lifting for the inspector — split out of ``InspectorController``
to keep that class down to event dispatch + selection state, mirroring the
thin-owner pattern already used in ``code/apply.py``. Functions here take the
controller as their first argument and read/write its ``_lifted_modal`` state
directly, same calling convention as ``code/apply.py``.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QWidget

logger = logging.getLogger("sli_ui_toolkit.inspector")


def lift_modality_for(controller, window: QWidget) -> None:
    try:
        modality = window.windowModality()
    except RuntimeError:
        return
    logger.debug(
        "modality lift: window=%s#%s modality=%s",
        type(window).__name__,
        window.objectName(),
        modality,
    )
    restore_modality(controller)
    if modality == Qt.WindowModality.NonModal:
        return
    # setParent(parent, flags) *replaces* the widget's window flags with
    # the passed ones — hand the original flags back, or the inspector's
    # CSD/frameless setup (InspectorWindow is a decorated QDialog) breaks.
    flags = controller._window.windowFlags()
    controller._lifted_modal = (window, flags)
    # Qt's modal input filter blocks every top-level except the modal
    # window and its descendants. Reparenting the inspector window as a
    # *child window* of the modal makes it fully interactive without any
    # hide/show — hiding the modal would visibly close and reopen it (the
    # modal stack only pops on hide).
    try:
        global_pos = controller._window.mapToGlobal(QPoint(0, 0))
        controller._window.setParent(window, flags)
        controller._window.move(window.mapFromGlobal(global_pos))
        controller._window.show()
    except RuntimeError:
        controller._lifted_modal = None
    logger.debug(
        "modal lift via child-window: inspector parent=%s#%s flags=0x%x",
        type(window).__name__,
        window.objectName(),
        int(flags.value) if hasattr(flags, "value") else 0,
    )


def restore_modality(controller) -> None:
    if controller._lifted_modal is None:
        return
    window, flags = controller._lifted_modal
    controller._lifted_modal = None
    logger.debug(
        "modality restore: inspector parent=%s#%s",
        type(window).__name__,
        window.objectName(),
    )
    try:
        # Put the inspector window back as an independent top-level with
        # its original flags (CSD/frameless must survive the round trip).
        global_pos = controller._window.mapToGlobal(QPoint(0, 0))
        controller._window.setParent(None, flags)
        controller._window.move(global_pos)
        controller._window.show()
    except RuntimeError:
        pass
