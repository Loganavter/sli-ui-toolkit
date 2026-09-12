import sys
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(tuple)
    result = Signal(object)
    progress = Signal(int)
    partial_result = Signal(object)

# Pins live workers so their WorkerSignals QObjects outlive the queued
# cross-thread slot delivery. Without this, PySide6 GCs the Python wrapper
# after QThreadPool auto-deletes the QRunnable, the unparented signals object
# disappears, and queued slot calls to result/error/finished are silently
# dropped on the main thread.
_LIVE_WORKERS: set["GenericWorker"] = set()

class GenericWorker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(False)
        _LIVE_WORKERS.add(self)
        self.signals.finished.connect(self._release_self)

    def _release_self(self) -> None:
        _LIVE_WORKERS.discard(self)

    def _safe_emit(self, signal_name: str, *args: Any) -> None:
        try:
            signal = getattr(self.signals, signal_name, None)
            if signal is not None:
                signal.emit(*args)
        except RuntimeError as exc:
            if "wrapped C/C++ object of type WorkerSignals has been deleted" not in str(
                exc
            ):
                raise

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:
            if not (isinstance(exc, RuntimeError) and str(exc) == "Save canceled by user"):
                traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self._safe_emit("error", (exctype, value, traceback.format_exc()))
        else:
            if result is not None:
                self._safe_emit("result", result)
        finally:
            self._safe_emit("finished")

