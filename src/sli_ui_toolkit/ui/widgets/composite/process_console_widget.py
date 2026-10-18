from __future__ import annotations

import os

from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_SCALE, connect_ui_metrics
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.composite.console_view import ConsoleLine, ConsoleView


def _qt_enum_value(value) -> int:
    return int(getattr(value, "value", value))


class ProcessConsoleWidget(QWidget):
    """Interactive process console backed by the painted :class:`ConsoleView`.

    Signals, the input row, and the ``output`` semantics are unchanged.
    """

    outputReceived = Signal(str)
    errorReceived = Signal(str)
    commandSubmitted = Signal(str)
    processStarted = Signal()
    processFinished = Signal(int, int)
    processStateChanged = Signal(int)

    def __init__(self, parent=None, *, max_entries: int = 2000):
        super().__init__(parent)
        self._max_entries = max(1, int(max_entries))
        self._entries: list[tuple[str, str]] = []
        self.theme_manager = ThemeManager.get_instance()
        self._surface_color = QColor("#000000")
        self._info_color = QColor("#ffffff")
        self._error_color = QColor("#FF0000")
        self._status_color = QColor("#9E9E9E")
        self._command_color = QColor("#4A90D9")
        self.process = QProcess(self)
        self._fixed_font = QFont()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.output = ConsoleView(self, max_lines=self._max_entries)
        self.output.setObjectName("ProcessConsoleOutput")
        self._apply_fixed_font()
        # The monospace size is the system FixedFont × the scale factor.
        connect_ui_metrics(self, self._apply_fixed_font, axes=frozenset({AXIS_SCALE}))

        self.input_row = QWidget(self)
        input_layout = QHBoxLayout(self.input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        self.input_edit = CustomLineEdit(self.input_row)
        self.input_edit.setObjectName("ProcessConsoleInput")
        self.input_edit.setPlaceholderText("Enter command")
        self.input_edit.setFont(self._fixed_font)

        self.send_button = Button(text="Send", variant="surface", parent=self.input_row)
        self.send_button.clicked.connect(self.submit_current_input)
        self.input_edit.returnPressed.connect(self.submit_current_input)

        input_layout.addWidget(self.input_edit, 1)
        input_layout.addWidget(self.send_button)

        layout.addWidget(self.output, 1)
        layout.addWidget(self.input_row)

        self.process.readyReadStandardOutput.connect(self._on_stdout_ready)
        self.process.readyReadStandardError.connect(self._on_stderr_ready)
        self.process.started.connect(self._on_started)
        self.process.finished.connect(self._on_finished)
        self.process.stateChanged.connect(self._on_state_changed)

        self._apply_styles()
        self.theme_manager.theme_changed.connect(self._apply_styles)

    def _apply_fixed_font(self) -> None:
        """Resize the console's monospace font with the UI scale.

        The system FixedFont is design-sized; UiScale multiplies its size so
        the console text grows with the interface like every other label
        (the monospace family is kept). Applies to both the output view and
        the input line.
        """
        base = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        factor = UiScale.get_instance().factor()
        font = QFont(base)
        if base.pointSizeF() > 0:
            font.setPointSizeF(base.pointSizeF() * factor)
        elif base.pixelSize() > 0:
            font.setPixelSize(max(1, int(round(base.pixelSize() * factor))))
        self._fixed_font = font
        self.output.set_font(font)
        input_edit = getattr(self, "input_edit", None)
        if input_edit is not None:
            input_edit.setFont(font)

    def set_max_entries(self, max_entries: int) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries = self._entries[-self._max_entries :]
        self.output.set_max_lines(self._max_entries)
        self._rebuild()

    def clear_output(self) -> None:
        self._entries.clear()
        self.output.clear()

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def start_process(
        self,
        program: str,
        args: list[str] | None = None,
        *,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        if self.is_running():
            self.stop_process(force=True)

        self.clear_output()
        self.process.setProgram(program)
        self.process.setArguments(list(args or []))
        if workdir:
            self.process.setWorkingDirectory(workdir)
        if env:
            process_env = self.process.processEnvironment()
            for key, value in env.items():
                process_env.insert(str(key), str(value))
            self.process.setProcessEnvironment(process_env)
        self.process.start()

    def start_shell(self, *, workdir: str | None = None) -> None:
        if os.name == "nt":
            self.start_process("cmd.exe", workdir=workdir)
            return
        shell = os.environ.get("SHELL") or "/bin/bash"
        args = ["-i"] if os.path.basename(shell) in {"bash", "zsh", "sh"} else []
        self.start_process(shell, args, workdir=workdir)

    def send_input(self, text: str, *, add_newline: bool = True, echo: bool = True) -> None:
        if not self.is_running():
            if echo and text:
                self._append_entry("command", f"> {text}")
            self._append_entry("status", "No process running. Call start_process() or start_shell() first.")
            return
        payload = str(text)
        if echo and payload:
            self._append_entry("command", f"> {payload}")
        if add_newline:
            payload += "\n"
        self.process.write(payload.encode("utf-8", errors="replace"))
        self.commandSubmitted.emit(str(text))

    def submit_current_input(self) -> None:
        text = self.input_edit.text().strip()
        if not text:
            return
        self.send_input(text)
        self.input_edit.clear()

    def stop_process(self, *, force: bool = False) -> None:
        if not self.is_running():
            return
        if force:
            self.process.kill()
        else:
            self.process.terminate()

    def _append_entry(self, level: str, text: str) -> None:
        safe_level = (
            level if level in {"info", "error", "status", "command"} else "info"
        )
        message = str(text)
        self._entries.append((safe_level, message))
        self._entries = self._entries[-self._max_entries :]
        color, bold = self._level_style(safe_level)
        self.output.append(message, color=color, bold=bold)

    def _level_style(self, level: str) -> tuple[QColor, bool]:
        if level == "error":
            return (QColor(self._error_color), True)
        if level == "status":
            return (QColor(self._status_color), False)
        if level == "command":
            return (QColor(self._command_color), True)
        return (QColor(self._info_color), False)

    def _entry_to_console_line(self, level: str, message: str) -> ConsoleLine:
        color, bold = self._level_style(level)
        return ConsoleLine(message, color, bold, False)

    def _rebuild(self) -> None:
        self.output.set_lines(
            self._entry_to_console_line(level, message)
            for level, message in self._entries
        )

    def _on_stdout_ready(self) -> None:
        text = bytes(self.process.readAllStandardOutput().data()).decode(
            "utf-8", errors="replace"
        )
        if not text:
            return
        for line in text.splitlines():
            self._append_entry("info", line)
        self.outputReceived.emit(text)

    def _on_stderr_ready(self) -> None:
        text = bytes(self.process.readAllStandardError().data()).decode(
            "utf-8", errors="replace"
        )
        if not text:
            return
        for line in text.splitlines():
            self._append_entry("error", line)
        self.errorReceived.emit(text)

    def _on_started(self) -> None:
        self._append_entry("status", "Process started")
        self.processStarted.emit()

    def _on_finished(self, exit_code: int, exit_status) -> None:
        self._append_entry(
            "status",
            f"Process finished with exit code {exit_code}",
        )
        self.processFinished.emit(exit_code, _qt_enum_value(exit_status))

    def _on_state_changed(self, state) -> None:
        self.processStateChanged.emit(_qt_enum_value(state))

    def _apply_styles(self) -> None:
        try:
            self._surface_color = QColor(
                self.theme_manager.get_color("surface.background")
            )
        except Exception:
            self._surface_color = QColor(self.palette().window().color())
        self._info_color = QColor(self.theme_manager.get_color("dialog.text"))
        self._error_color = QColor("#D70000" if self.theme_manager.is_dark() else "#FF0000")
        self._status_color = QColor("#9E9E9E")
        self._command_color = QColor(self.theme_manager.get_color("accent"))
        self._rebuild()

    def paintEvent(self, event) -> None:  # noqa: N802
        """Fill the widget surface from the ``dialog.background`` token.

        A plain QWidget would otherwise fall back to the QPalette Window
        role, which hosts keep darker than the dialog surface token — the
        gaps around the output/input rows then read darker than the rest of
        the dialog surface. Re-read in ``_apply_styles`` (theme_changed).
        """
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._surface_color)
        painter.end()
