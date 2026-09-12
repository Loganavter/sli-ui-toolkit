from __future__ import annotations

from sli_ui_toolkit.ui.managers.settle_gate import SettleGate


def test_settle_gate_pulse_each_ping_settle_once(qapp):
    pulses: list[int] = []
    settles: list[int] = []

    gate = SettleGate(
        on_settle=lambda: settles.append(1),
        on_pulse=lambda: pulses.append(1),
        interval_ms=50,
        parent=None,
    )

    gate.ping()
    gate.ping()
    gate.ping()

    assert pulses == [1, 1, 1]
    assert settles == []
    assert gate.is_pending()

    gate.flush()
    assert settles == [1]
    assert not gate.is_pending()


def test_settle_gate_cancel_skips_settle(qapp):
    settles: list[int] = []
    gate = SettleGate(
        on_settle=lambda: settles.append(1),
        interval_ms=50,
    )
    gate.ping()
    assert gate.is_pending()
    gate.cancel()
    assert not gate.is_pending()
    assert settles == []


def test_settle_gate_flush_noop_when_idle(qapp):
    settles: list[int] = []
    gate = SettleGate(on_settle=lambda: settles.append(1), interval_ms=50)
    gate.flush()
    assert settles == []
