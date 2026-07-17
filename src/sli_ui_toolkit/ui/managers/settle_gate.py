from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer


class SettleGate(QObject):
    """Restartable quiet-period gate with optional per-pulse work.

    Typical resize pattern::

        gate.ping()  # every resizeEvent
        # on_pulse: cheap refit / mark busy
        # on_settle: expensive prepare / full render
    """

    DEFAULT_INTERVAL_MS = 120

    def __init__(
        self,
        on_settle: Callable[[], None],
        *,
        on_pulse: Callable[[], None] | None = None,
        interval_ms: int = DEFAULT_INTERVAL_MS,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._on_settle = on_settle
        self._on_pulse = on_pulse
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(0, int(interval_ms)))
        self._timer.timeout.connect(self._fire_settle)

    def ping(self) -> None:
        if self._on_pulse is not None:
            self._on_pulse()
        self._timer.start()

    def cancel(self) -> None:
        self._timer.stop()

    def flush(self) -> None:
        if not self._timer.isActive():
            return
        self._timer.stop()
        self._fire_settle()

    def is_pending(self) -> bool:
        return self._timer.isActive()

    def interval(self) -> int:
        return self._timer.interval()

    def set_interval(self, ms: int) -> None:
        self._timer.setInterval(max(0, int(ms)))

    def _fire_settle(self) -> None:
        self._on_settle()
