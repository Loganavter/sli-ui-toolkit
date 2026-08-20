"""Shared contract-test helper: the trial-dispatch arrow-key contract.

Every widget with its own ``keyPressEvent`` override must, while idle (not
in whatever transient state makes it want to consume the key itself, e.g.
an open ComboBox dropdown or focused text-edit mode), leave Up/Down
*unaccepted* so ``NavigationManager``/``ToolbarRowsSection`` can route them
for row/section navigation instead (see
``sli-ui-toolkit/docs/dev/NAVIGATION.md``). ``SpinBox`` silently broke this
rule for years (unconditional ``setValue()`` + ``event.accept()`` on
Up/Down) before this helper existed — nothing caught it because no test
ever asserted the *absence* of acceptance. Wire this into any widget's test
module that overrides ``keyPressEvent`` and touches arrow keys.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QWidget


def assert_yields_arrows_when_idle(make_widget: Callable[[], QWidget]) -> None:
    """Construct a fresh widget via *make_widget* and assert Up/Down are
    left unaccepted in its idle state (``event.isAccepted()`` is ``False``
    after a direct ``keyPressEvent()`` trial-dispatch — the same technique
    ``ToolbarRowsSection._widget_handles`` uses to probe a widget before
    claiming a key for row navigation).
    """
    for key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
        widget = make_widget()
        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        widget.keyPressEvent(event)
        assert not event.isAccepted(), (
            f"{type(widget).__name__}.keyPressEvent accepted {key!r} while idle -- "
            "Up/Down must stay available for NavigationManager routing "
            "(see docs/dev/NAVIGATION.md)"
        )
