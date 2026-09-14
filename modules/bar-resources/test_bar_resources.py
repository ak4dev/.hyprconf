"""modules/bar-resources: the install (link, rescan, enable once, undo), and the
facts about the payload it links that no other file can carry."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import Box

MODULE = Path(__file__).parent
PLUGIN = MODULE / "plugin"
ID = "hyprconf.resources"
# The one real omarchy-* command the suite runs (AGENTS.md › Tests); absent in
# CI, which carries no Omarchy.
PLUGIN_VALIDATE = (
    Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "bin/omarchy-plugin-validate"
)
# omarchy-plugin-list answering with this plugin: what the discovery loop waits
# for before the enable (bin/omarchy-plugin-add:164-171 does the same).
LISTED = f'printf \'[{{"id":"{ID}"}}]\\n\'\n'


def _link(box: Box) -> Path:
    return box.home / ".config/omarchy/plugins" / ID


def _marker(box: Box) -> Path:
    return box.home / ".local/state/hyprconf/resources-applied"


def _install(box: Box, *args: str, listed: bool = True):
    if listed:
        box.stub("omarchy-plugin-list", LISTED)
    return box.run(MODULE / "install", *args)


def _snapshot(box: Box) -> dict[str, tuple]:
    """Everything under $HOME: content or link target, and mtime."""
    out: dict[str, tuple] = {}
    for p in sorted(box.home.rglob("*")):
        rel = str(p.relative_to(box.home))
        if p.is_symlink():
            out[rel] = ("link", os.readlink(p), p.lstat().st_mtime_ns)
        elif p.is_dir():
            out[rel] = ("dir",)
        else:
            out[rel] = ("file", p.read_bytes(), p.stat().st_mtime_ns)
    return out


def test_links_the_plugin_rescans_and_enables_it(box: Box) -> None:
    r = _install(box)
    assert r.returncode == 0, r.stderr
    assert os.readlink(_link(box)) == str(PLUGIN)
    assert _marker(box).exists()
    assert box.calls_of("omarchy-shell") == [["omarchy-shell", "shell", "rescanPlugins"]]
    # No --section: placement comes from the manifest's barWidget.defaultSection
    # (shell/services/PluginRegistry.qml:194-196).
    assert box.calls_of("omarchy-plugin-enable") == [["omarchy-plugin-enable", ID]]


def test_a_second_run_writes_nothing_and_re_enables_nothing(box: Box) -> None:
    _install(box)
    before = _snapshot(box)
    box.reset()
    r = _install(box)
    assert r.returncode == 0, r.stderr
    assert _snapshot(box) == before
    assert "omarchy-plugin-enable" not in box.commands


def test_undo_disables_unlinks_and_forgets_the_marker(box: Box) -> None:
    _install(box)
    box.reset()
    r = box.undo("bar-resources")
    assert r.returncode == 0, r.stderr
    assert box.calls_of("omarchy-plugin-disable") == [["omarchy-plugin-disable", ID]]
    assert not _link(box).is_symlink() and not _link(box).exists()
    assert not _marker(box).exists()
    assert "omarchy-shell" in box.commands


def test_undo_touches_nothing_it_did_not_install(box: Box) -> None:
    """Only ever its own link, and an uninstalled box writes nothing."""
    assert box.undo("bar-resources").returncode == 0
    assert box.files() == set()
    foreign = _link(box)
    foreign.mkdir(parents=True)
    (foreign / "manifest.json").write_text("{}\n")
    assert box.undo("bar-resources").returncode == 0
    assert (foreign / "manifest.json").read_text() == "{}\n"


def test_no_shell_leaves_the_marker_unwritten_and_retries(box: Box) -> None:
    """The enable needs the running shell (bin/omarchy-plugin-enable:85-87)."""
    box.stub("omarchy-plugin-enable", "exit 1\n")
    r = _install(box, listed=False)
    assert r.returncode == 0
    assert not _marker(box).exists()
    assert os.readlink(_link(box)) == str(PLUGIN)  # the link lands either way
    box.stub("omarchy-plugin-enable", "exit 0\n")
    _install(box)
    assert _marker(box).exists()


def test_a_link_pointing_somewhere_else_is_repaired(box: Box) -> None:
    stale = box.tmp / "somewhere-else"
    stale.mkdir()
    _link(box).parent.mkdir(parents=True)
    _link(box).symlink_to(stale)
    _install(box)
    assert os.readlink(_link(box)) == str(PLUGIN)


def test_an_omarchy_plugin_add_checkout_is_left_alone(box: Box) -> None:
    """A same-id git checkout is Omarchy's to manage (omarchy plugin update)."""
    checkout = _link(box)
    (checkout / ".git").mkdir(parents=True)
    r = _install(box)
    assert r.returncode == 0
    assert checkout.is_dir() and not checkout.is_symlink()
    assert not _marker(box).exists()
    assert "omarchy-plugin-enable" not in box.commands


def test_a_real_folder_is_moved_aside_before_linking(box: Box) -> None:
    """Moved aside under bin/omarchy-plugin-remove:106's name, never deleted."""
    old = _link(box)
    old.mkdir(parents=True)
    (old / "manifest.json").write_text("{}\n")
    _install(box)
    assert os.readlink(_link(box)) == str(PLUGIN)
    backups = list(old.parent.glob(f".{ID}.bak.*"))
    assert len(backups) == 1
    assert (backups[0] / "manifest.json").read_text() == "{}\n"


def test_the_installed_folder_passes_omarchy_plugin_validate(box: Box) -> None:
    """It refuses a symlink inside a plugin folder (bin/omarchy-plugin-validate:115),
    and what lands in ~/.config/omarchy/plugins/ IS one — hence the trailing slash
    that makes its `find` descend it, the line both READMEs give a by-hand user."""
    if not PLUGIN_VALIDATE.is_file():
        pytest.skip("no installed omarchy-plugin-validate")
    _install(box)

    def validate(path: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(PLUGIN_VALIDATE), path],
            capture_output=True,
            text=True,
            timeout=30,
            env={"PATH": "/usr/bin:/bin", "HOME": str(box.home)},
        )

    passed = validate(f"{_link(box)}/")
    assert passed.returncode == 0, passed.stderr
    assert validate(str(_link(box))).returncode != 0, "the trailing slash is no longer load-bearing"


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


def test_the_feeders_ship_executable() -> None:
    """The folder is linked, not copied: the checkout's mode is what execs."""
    for feeder in ("hyprconf-stats", "hyprconf-gpu-info"):
        assert os.access(PLUGIN / "bin" / feeder, os.X_OK), feeder


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
    assert 'root.glyphThermo + t + "\u00b0 "' in widget, "the unit is the widget's too"
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
