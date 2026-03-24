"""Tests for stow/hypr/.config/hypr/scripts/toggle-native-display.

Verifies:
- Disabling eDP-1 sends `hyprctl keyword monitor eDP-1,disable`
- Enabling  eDP-1 sends `hyprctl keyword monitor eDP-1,preferred,auto,1`
  (regression: must NOT use a hardcoded resolution like 1920x1200)
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT = (
    REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "scripts" / "toggle-native-display"
)


def _make_fake_hyprctl(tmp: Path, monitors_output: str, calls_log: Path) -> Path:
    """Create a fake hyprctl that records `keyword` calls and returns canned output."""
    fake = tmp / "hyprctl"
    fake.write_text(
        f"""#!/usr/bin/env bash
if [[ "$1" == "monitors" ]]; then
    printf '%s' '{monitors_output}'
elif [[ "$1" == "keyword" ]]; then
    echo "$2 $3 $4" >> "{calls_log}"
fi
"""
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return fake


def _run_toggle(tmp: Path, monitors_text: str) -> tuple[int, list[str]]:
    calls_log = tmp / "hyprctl_calls.log"
    _make_fake_hyprctl(tmp, monitors_text, calls_log)
    env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}"}
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    calls = calls_log.read_text().splitlines() if calls_log.exists() else []
    return result.returncode, calls


# ---------------------------------------------------------------------------
# Disable path
# ---------------------------------------------------------------------------

def test_disable_sends_disable_keyword(tmp_path):
    """When eDP-1 is enabled (disabled: false), the script disables it."""
    monitors_text = "Monitor eDP-1 (ID 0):\n\tdisabled: false\n"
    rc, calls = _run_toggle(tmp_path, monitors_text)
    assert rc == 0
    assert any("eDP-1,disable" in c for c in calls), \
        f"Expected disable call, got: {calls}"


# ---------------------------------------------------------------------------
# Enable path — regression: must use 'preferred', not hardcoded resolution
# ---------------------------------------------------------------------------

def test_enable_uses_preferred_not_hardcoded_resolution(tmp_path):
    """Regression: re-enabling eDP-1 must use 'preferred', not a hardcoded
    resolution (e.g. 1920x1200) that breaks on displays with other native res."""
    monitors_text = "Monitor eDP-1 (ID 0):\n\tdisabled: true\n"
    rc, calls = _run_toggle(tmp_path, monitors_text)
    assert rc == 0
    enable_calls = [c for c in calls if "eDP-1" in c and "disable" not in c]
    assert enable_calls, f"No enable call found; got: {calls}"
    # Must use 'preferred', not a fixed resolution
    assert any("preferred" in c for c in enable_calls), (
        f"Enable call must use 'preferred' — got: {enable_calls}"
    )
    assert not any(
        any(token[0].isdigit() and "x" in token for token in c.split(","))
        for c in enable_calls
    ), f"Enable call must not contain a hardcoded resolution, got: {enable_calls}"


def test_script_source_uses_preferred() -> None:
    """Regression guard: verify 'preferred' appears in the script and
    '1920x1200' does not (belt-and-suspenders check on the source)."""
    src = SCRIPT.read_text()
    assert "1920x1200" not in src, \
        "toggle-native-display still contains hardcoded 1920x1200"
    assert "preferred" in src, \
        "toggle-native-display must use 'preferred' when re-enabling eDP-1"
