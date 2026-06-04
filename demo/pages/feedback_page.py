"""Feedback & Indicators page."""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import (
    Button,
    Label,
    LoadingSpinner,
    OverlayScrollArea,
    ToastManager,
    ToastAction,
)

from demo.components import GalleryPage


class FeedbackPage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Feedback & Indicators",
            subtitle="Спиннеры, тосты, тонкие скроллбары.",
            source_file=__file__,
            parent=parent,
        )

        spinner = LoadingSpinner()
        spinner.setMinimumHeight(48)

        controls_holder = QWidget()
        controls = QHBoxLayout(controls_holder)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.addWidget(spinner)
        start = Button(text="Start", variant="surface")
        stop = Button(text="Stop", variant="surface")
        start.clicked.connect(spinner.start)
        stop.clicked.connect(spinner.stop)
        controls.addWidget(start)
        controls.addWidget(stop)
        controls.addStretch()
        self.add_card("LoadingSpinner", controls_holder)

        scroll_demo_host = QWidget()
        scroll_demo_host.setFixedHeight(160)
        scroll_demo_layout = QVBoxLayout(scroll_demo_host)
        scroll_demo_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = OverlayScrollArea()
        scroll_area.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(12, 12, 18, 12)
        il.setSpacing(12)
        for title, body in (
            ("Build output", "The overlay scrollbar is drawn above the viewport and does not reserve a native gutter."),
            ("Theme aware", "Idle, hover, and drag states resolve through the toolkit theme manager."),
            ("Dense content", "This demo uses paragraphs instead of repeated rows so the surface reads like scrollable content, not a list widget."),
            ("Pointer behavior", "Drag the thin thumb or click the track. The native QScrollArea range stays synchronized behind the overlay."),
            ("Resize behavior", "The thumb height follows the viewport/content ratio after resize and content layout changes."),
            ("Usage", "Use OverlayScrollArea directly; do not replace its vertical scrollbar manually."),
        ):
            il.addWidget(Label(title, pixel_size=12, bold=True))
            il.addWidget(Label(body, pixel_size=11, word_wrap=True))
        il.addStretch()
        scroll_area.setWidget(inner)
        scroll_demo_layout.addWidget(scroll_area)
        self.add_card("OverlayScrollArea", scroll_demo_host, "Встроенный overlay thumb поверх обычного QScrollArea.")

        tip_btn = Button(text="Hover me", variant="surface")
        tip_btn.setToolTip("Tooltip via setToolTip() — стилизуется toolkit'ом.")
        self.add_card("Tooltips", tip_btn)

        toast_holder = QWidget()
        tl = QHBoxLayout(toast_holder)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)
        self._toast_manager: ToastManager | None = None
        self._toast_progress_id: int | None = None
        self._toast_progress_value = 0
        info_btn = Button(text="Show toast", variant="surface")
        info_btn.clicked.connect(self._show_info_toast)
        action_btn = Button(text="Toast with action", variant="surface")
        action_btn.clicked.connect(self._show_action_toast)
        progress_btn = Button(text="Progress toast", variant="surface")
        progress_btn.clicked.connect(self._show_progress_toast)
        tl.addWidget(info_btn)
        tl.addWidget(action_btn)
        tl.addWidget(progress_btn)
        tl.addStretch()
        self.add_card(
            "ToastManager",
            toast_holder,
            "Тосты позиционируются в левом верхнем углу окна. ",
        )

        self.add_stretch()

    def _ensure_toast_manager(self) -> ToastManager:
        if self._toast_manager is None:
            self._toast_manager = ToastManager(self.window())
        return self._toast_manager

    def _show_info_toast(self) -> None:
        self._ensure_toast_manager().show_toast("Файл сохранён", duration=2500)

    def _show_action_toast(self) -> None:
        mgr = self._ensure_toast_manager()
        mgr.show_toast(
            "Удалено 3 элемента",
            duration=5000,
            actions=[ToastAction("Undo", self._show_info_toast)],
        )

    def _show_progress_toast(self) -> None:
        from PyQt6.QtCore import QTimer
        mgr = self._ensure_toast_manager()
        self._toast_progress_value = 0
        self._toast_progress_id = mgr.show_toast(
            "Загрузка…",
            duration=0,
            progress=0,
        )
        timer = QTimer(self)
        timer.setInterval(150)

        def tick():
            self._toast_progress_value += 7
            if self._toast_progress_id is None:
                timer.stop()
                return
            if self._toast_progress_value >= 100:
                mgr.update_toast(
                    self._toast_progress_id,
                    "Готово",
                    success=True,
                    duration=2000,
                    progress=None,
                )
                self._toast_progress_id = None
                timer.stop()
                return
            mgr.update_toast(
                self._toast_progress_id,
                f"Загрузка… {self._toast_progress_value}%",
                success=False,
                duration=0,
                progress=self._toast_progress_value,
            )
        timer.timeout.connect(tick)
        timer.start()
