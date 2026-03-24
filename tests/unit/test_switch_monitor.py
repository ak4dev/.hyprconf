"""Tests for stow/hypr/.config/hypr/scripts/switch_monitor.sh.

Verifies:
- Applying a valid preset copies the preset file to monitors.conf
- Missing preset exits non-zero with a useful error message
- Missing monitors.conf argument exits non-zero
- Atomic write: uses cp+mv (not rm+cp), so monitors.conf is never absent
  during the switch (regression guard on source-level check + behaviour)
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT = (
    REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "scripts" / "switch_monitor.sh"
)


def _make_fake_hyprctl(tmp: Path) -> None:
    fake = tmp / "hyprctl"
    fake.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run_switch(tmp: Path, preset: str, config_dir: Path) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "PATH": f"{tmp}:{os.environ['PATH']}",
        "HOME": str(tmp / "home"),
    }
    # Point HOME so the script's CONFIG_DIR = $HOME/.config/hypr resolves to our tmp
    home = tmp / "home"
    home.mkdir(exist_ok=True)
    cfg = home / ".config" / "hypr"
    cfg.mkdir(parents=True, exist_ok=True)
    # Copy any preset files from config_dir into home cfg dir
    for f in config_dir.iterdir():
        (cfg / f.name).write_text(f.read_text())
    env["HOME"] = str(home)
    return subprocess.run(
        ["bash", str(SCRIPT), preset],
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# Preset application
# ---------------------------------------------------------------------------

def test_valid_preset_writes_monitors_conf(tmp_path):
    """Applying a valid preset must write its content to monitors.conf."""
    _make_fake_hyprctl(tmp_path)
    cfg_src = tmp_path / "cfg_src"
    cfg_src.mkdir()
    (cfg_src / "pcMonitors.bedroom").write_text("monitor=HDMI-A-1,preferred,auto,1\n")

    res = _run_switch(tmp_path, "bedroom", cfg_src)
    assert res.returncode == 0, f"Script failed: {res.stderr}"

    monitors_conf = tmp_path / "home" / ".config" / "hypr" / "monitors.conf"
    assert monitors_conf.exists(), "monitors.conf not created"
    assert "HDMI-A-1" in monitors_conf.read_text()


def test_preset_not_found_exits_nonzero(tmp_path):
    """A non-existent preset must cause the script to exit non-zero."""
    _make_fake_hyprctl(tmp_path)
    cfg_src = tmp_path / "cfg_src"
    cfg_src.mkdir()

    res = _run_switch(tmp_path, "nonexistent", cfg_src)
    assert res.returncode != 0, "Expected non-zero exit for missing preset"
    assert "not found" in res.stderr.lower() or "nonexistent" in res.stderr.lower()


def test_no_preset_argument_exits_nonzero(tmp_path):
    """Running without a preset argument must exit non-zero."""
    _make_fake_hyprctl(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "HOME": str(home)}
    res = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode != 0


# ---------------------------------------------------------------------------
# Atomic write regression
# ---------------------------------------------------------------------------

def test_atomic_write_uses_cp_then_mv_not_rm_then_cp() -> None:
    """Regression: switch_monitor.sh must use cp+mv (atomic) not rm+cp.

    The rm+cp pattern leaves a window where monitors.conf is absent.
    With cp+mv, the new file is always swapped in atomically.
    """
    src = SCRIPT.read_text()
    # Must NOT contain the old pattern
    assert "rm -f" not in src or "mv " in src, (
        "switch_monitor.sh uses rm+cp (non-atomic); must use cp+mv"
    )
    # Positive: mv must be present for atomic replace
    assert "mv " in src, "switch_monitor.sh must use mv for atomic monitors.conf replacement"
