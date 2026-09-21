"""modules/bar-resources: the facts about the payload it links that no other file can
carry. The install, the one enable and the undo are the shared mechanism's, pinned per
plugin folder in tests/test_plugins_contract.py."""

from __future__ import annotations

from pathlib import Path

PLUGIN = Path(__file__).parent / "plugin"
ID = "hyprconf.resources"


def test_the_feeders_run_once_for_the_session_not_once_per_monitor() -> None:
    """Bar.qml is `Variants { model: Quickshell.screens }`, so a Process the WIDGET
    owns runs once per bar surface; the service kind is loaded once a session
    (shell.qml:385-394, PluginShellApi.qml:30 — quickshell 0.3.1, one feeder pair
    over three surfaces)."""
    widget, service = (PLUGIN / "Widget.qml").read_text(), (PLUGIN / "Service.qml").read_text()
    assert "Process" not in widget, "a Process in the widget runs once per bar surface"
    assert f'root.bar?.shell?.serviceFor("{ID}")' in widget
    for feeder in ("bin/hyprconf-stats", "bin/hyprconf-gpu-info"):
        assert f'command: [root.pluginDir + "{feeder}"]' in service


def test_a_feeder_that_died_is_restarted_on_a_capped_doubling_backoff() -> None:
    """Service.qml's header rule, which only this shape keeps: 1 s doubled per
    attempt to 32 s and then parked, rearmed only by a line that parsed, and
    only for a feeder that ever produced one — a flat interval or an uncapped
    ladder respawns dead hardware forever (nvidia-smi --loop exits at once)."""
    service = (PLUGIN / "Service.qml").read_text()
    assert "readonly property int maxAttempts: 6" in service
    assert "if (restarter.attempt >= restarter.maxAttempts) return" in service
    assert "restarter.interval = 1000 * (1 << restarter.attempt)" in service
    assert service.count(".start()") == 1, "died() is the only thing that arms the timer"
    for feeder in ("stats", "gpu"):
        assert f"if (root.{feeder}Produced) {feeder}RestartTimer.died()" in service
        assert f"{feeder}RestartTimer.produced()" in service
    # Latched: it also decides what the GPU cells paint.
    assert "Produced = false" not in service


def test_the_feeders_emit_numbers_and_the_widget_owns_every_glyph() -> None:
    """Verified present in GeistMono Nerd Font, Omarchy's default bar font
    (fc-list ':charset=…'): nf-fa-microchip, nf-md-expansion_card,
    nf-md-memory, nf-md-thermometer."""
    widget = (PLUGIN / "Widget.qml").read_text()
    for cell, code in (("Cpu", "F2DB"), ("Gpu", "F08AE"), ("Mem", "F061A"), ("Thermo", "F050F")):
        assert f'property string glyph{cell}: "\\u{{{code}}}"' in widget
    assert 'root.glyphThermo + t + "° "' in widget, "the unit is the widget's too"
    service = (PLUGIN / "Service.qml").read_text()
    for prop, field in (
        ("cpuPct", "cpu"),
        ("cpuTemp", "temp"),
        ("memText", "mem"),
        ("netDown", "down"),
        ("netUp", "up"),
        ("gpuUtil", "util"),
        ("gpuTemp", "temp"),
        ("gpuVramUsed", "vram_used"),
        ("gpuVramTotal", "vram_total"),
        ("gpuTooltip", "tooltip"),
    ):
        assert f"root.{prop} = j.{field}\n" in service, "the feeder's own field, unreshaped"
    assert "j.text" not in service, "a feeder never hands over rendered text"
