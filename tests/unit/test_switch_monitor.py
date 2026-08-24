"""Tests for hypr/scripts/switch_monitor.sh.

Verifies:
- Applying a valid preset symlinks monitors.lua to the preset file
  (`pcMonitors.<name>.lua`, or `<name>Monitors.lua` for `pc` / `laptop`)
- A pre-migration extension-less hyprlang `pcMonitors.<name>` is refused with a
  message that says how to convert it — linked over monitors.lua it would be a
  Lua parse error that takes every later `require` in Omarchy's hyprland.lua
  down with it
- A missing preset exits non-zero with a useful error, reported through
  Omarchy's notification command (the script is reached from a hotkey, where
  stderr goes nowhere a human can see)
- Missing preset argument exits non-zero
- Atomic write: ln -sf (not rm+cp), so monitors.lua is never absent mid-switch

HERMETIC: the script talks to hyprctl, omarchy-notification-send and
omarchy-osd. Every one of them is a recording stub on a fake-bins dir put
FIRST on PATH — the real ones would reload the developer's compositor, move
their workspaces, and put a critical "Preset not found" notification on their
desktop every time the suite runs (which is exactly what happened once).
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT = REPO_ROOT / "hypr" / "scripts" / "switch_monitor.sh"

# Every external command the script may call. The self-check below derives
# the same set from the script's text, so a new call cannot slip past the
# fakes unnoticed.
EXTERNALS = ("hyprctl", "omarchy-notification-send", "omarchy-osd")


def _make_fake_bins(tmp: Path) -> Path:
    """Recording stubs for every external; each appends its argv to calls.txt."""
    bins = tmp / "bins"
    bins.mkdir(exist_ok=True)
    calls = tmp / "calls.txt"
    for name in EXTERNALS:
        fake = bins / name
        fake.write_text(f'#!/usr/bin/env bash\nprintf \'%s\\n\' "{name} $*" >> "{calls}"\nexit 0\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bins


def _calls(tmp: Path) -> list[str]:
    f = tmp / "calls.txt"
    return f.read_text().splitlines() if f.exists() else []


def _run_switch(tmp: Path, preset: str, config_dir: Path) -> subprocess.CompletedProcess:
    bins = _make_fake_bins(tmp)
    home = tmp / "home"
    cfg = home / ".config" / "hypr"
    cfg.mkdir(parents=True, exist_ok=True)
    for f in config_dir.iterdir():
        (cfg / f.name).write_text(f.read_text())
    env = {**os.environ, "PATH": f"{bins}:{os.environ['PATH']}", "HOME": str(home)}
    return subprocess.run(
        ["bash", str(SCRIPT), preset], capture_output=True, text=True, env=env, timeout=60
    )


# ---------------------------------------------------------------------------
# Hermeticity self-check
# ---------------------------------------------------------------------------


def test_every_external_the_script_calls_has_a_fake() -> None:
    """If switch_monitor.sh grows a new omarchy-*/hyprctl call, this fails
    before that call can reach the developer's real desktop from a test."""
    code = "\n".join(
        ln for ln in SCRIPT.read_text().splitlines() if not ln.lstrip().startswith("#")
    )
    called = set(re.findall(r"\b(hyprctl|omarchy-[a-z-]+)\b", code))
    assert called, "no external calls found — the scan regex is broken"
    assert called <= set(EXTERNALS), f"unstubbed externals: {called - set(EXTERNALS)}"


# ---------------------------------------------------------------------------
# Preset application
# ---------------------------------------------------------------------------


def test_valid_preset_writes_monitors_lua(tmp_path: Path) -> None:
    """Applying a valid Lua preset symlinks it over monitors.lua and reloads."""
    cfg_src = tmp_path / "cfg_src"
    cfg_src.mkdir()
    (cfg_src / "pcMonitors.bedroom.lua").write_text(
        'hl.monitor({ output = "HDMI-A-1", mode = "preferred" })\n'
    )

    res = _run_switch(tmp_path, "bedroom", cfg_src)
    assert res.returncode == 0, f"Script failed: {res.stderr}"

    monitors_lua = tmp_path / "home" / ".config" / "hypr" / "monitors.lua"
    assert monitors_lua.is_symlink()
    assert "HDMI-A-1" in monitors_lua.read_text()
    calls = _calls(tmp_path)
    assert "hyprctl reload" in calls
    assert any(c.startswith("omarchy-osd") and "bedroom" in c for c in calls)


def test_whole_machine_presets_resolve_by_short_name(tmp_path: Path) -> None:
    """`pc` -> pcMonitors.lua, `laptop` -> laptopMonitors.lua."""
    cfg_src = tmp_path / "cfg_src"
    cfg_src.mkdir()
    (cfg_src / "laptopMonitors.lua").write_text(
        'hl.monitor({ output = "eDP-1", mode = "preferred" })\n'
    )
    res = _run_switch(tmp_path, "laptop", cfg_src)
    assert res.returncode == 0, res.stderr
    assert "eDP-1" in (tmp_path / "home" / ".config" / "hypr" / "monitors.lua").read_text()


def test_extensionless_hyprlang_preset_is_refused(tmp_path: Path) -> None:
    """Omarchy's hyprland.lua `require`s monitors.lua as Lua; a hyprlang file
    linked there is a parse error that stops every later require. The script
    must refuse it and say how to convert, rather than link it."""
    cfg_src = tmp_path / "cfg_src"
    cfg_src.mkdir()
    (cfg_src / "pcMonitors.bedroom").write_text("monitor=HDMI-A-1,preferred,auto,1\n")

    res = _run_switch(tmp_path, "bedroom", cfg_src)
    assert res.returncode != 0
    assert "hyprlang" in res.stderr and "pcMonitors.bedroom.lua" in res.stderr
    assert not (tmp_path / "home" / ".config" / "hypr" / "monitors.lua").exists()
    assert "hyprctl reload" not in _calls(tmp_path)


def test_preset_not_found_exits_nonzero_and_notifies(tmp_path: Path) -> None:
    """A missing preset fails, and the failure is a desktop notification —
    the hotkey path has no terminal to read stderr from."""
    cfg_src = tmp_path / "cfg_src"
    cfg_src.mkdir()

    res = _run_switch(tmp_path, "nonexistent", cfg_src)
    assert res.returncode != 0, "Expected non-zero exit for missing preset"
    assert "Preset not found: pcMonitors.nonexistent.lua" in res.stderr
    assert any(
        c.startswith("omarchy-notification-send") and "nonexistent" in c for c in _calls(tmp_path)
    )
    assert "hyprctl reload" not in _calls(tmp_path)


def test_no_preset_argument_exits_nonzero(tmp_path: Path) -> None:
    bins = _make_fake_bins(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "PATH": f"{bins}:{os.environ['PATH']}", "HOME": str(home)}
    res = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env, timeout=60)
    assert res.returncode != 0
    assert "Usage" in res.stderr


def test_preset_name_is_whitelisted(tmp_path: Path) -> None:
    """`$1` is a path component; anything outside [A-Za-z0-9_-] is refused."""
    cfg_src = tmp_path / "cfg_src"
    cfg_src.mkdir()
    res = _run_switch(tmp_path, "../evil", cfg_src)
    assert res.returncode != 0
    assert "Invalid preset name" in res.stderr


# ---------------------------------------------------------------------------
# Atomic write regression
# ---------------------------------------------------------------------------


def test_atomic_write_uses_ln_sf_not_rm_cp() -> None:
    """Regression: switch_monitor.sh must use ln -sf (atomic symlink) not rm+cp.

    The rm+cp pattern leaves a window where monitors.lua is absent. ln -sf is
    a single syscall that atomically replaces the symlink. It is also what lets
    edits to monitors.lua land on the tracked preset file.
    """
    src = SCRIPT.read_text()
    assert "ln -sf" in src, (
        "switch_monitor.sh must use 'ln -sf' for atomic monitors.lua replacement"
    )
    assert not ("rm -f" in src and "cp " in src and "mv " not in src), (
        "switch_monitor.sh uses rm+cp (non-atomic); must use ln -sf"
    )
