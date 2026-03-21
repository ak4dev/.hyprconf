"""Tests for stow/hypr/.config/hypr/scripts/adjust-gaps."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parent.parent.parent
    / "stow" / "hypr" / ".config" / "hypr" / "scripts" / "adjust-gaps"
)


def _run(direction: str, gaps_in: int, gaps_out: int) -> tuple[int, list[str]]:
    """Run adjust-gaps with a fake hyprctl in PATH; return (rc, keyword_calls)."""
    fake_dir = Path(__file__).parent / "_fake_bins_adjust_gaps"
    fake_dir.mkdir(exist_ok=True)
    fake_hyprctl = fake_dir / "hyprctl"

    # getoption returns the current value; keyword calls are recorded to a file
    calls_file = fake_dir / "calls.txt"
    calls_file.unlink(missing_ok=True)

    fake_hyprctl.write_text(
        f"""#!/usr/bin/env bash
if [[ "$1" == "getoption" ]]; then
    case "$2" in
        general:gaps_in)  echo "int: {gaps_in}" ;;
        general:gaps_out) echo "int: {gaps_out}" ;;
    esac
elif [[ "$1" == "keyword" ]]; then
    echo "$2 $3" >> "{calls_file}"
fi
"""
    )
    fake_hyprctl.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_dir}:{env['PATH']}"

    result = subprocess.run(
        ["bash", str(SCRIPT), direction],
        env=env,
        capture_output=True,
        text=True,
    )

    calls: list[str] = []
    if calls_file.exists():
        calls = [line.strip() for line in calls_file.read_text().splitlines() if line.strip()]

    return result.returncode, calls


# ---------------------------------------------------------------------------
# Increase
# ---------------------------------------------------------------------------

def test_increase_by_step():
    rc, calls = _run("+", gaps_in=10, gaps_out=20)
    assert rc == 0
    assert "general:gaps_in 15" in calls
    assert "general:gaps_out 25" in calls


def test_increase_from_zero():
    rc, calls = _run("+", gaps_in=0, gaps_out=0)
    assert rc == 0
    assert "general:gaps_in 5" in calls
    assert "general:gaps_out 5" in calls


def test_increase_large_values():
    """No upper cap — can grow well beyond typical values."""
    rc, calls = _run("+", gaps_in=200, gaps_out=300)
    assert rc == 0
    assert "general:gaps_in 205" in calls
    assert "general:gaps_out 305" in calls


# ---------------------------------------------------------------------------
# Decrease
# ---------------------------------------------------------------------------

def test_decrease_by_step():
    rc, calls = _run("-", gaps_in=15, gaps_out=25)
    assert rc == 0
    assert "general:gaps_in 10" in calls
    assert "general:gaps_out 20" in calls


def test_decrease_clamps_at_zero():
    """Decreasing below zero should floor at 0, not go negative."""
    rc, calls = _run("-", gaps_in=3, gaps_out=2)
    assert rc == 0
    assert "general:gaps_in 0" in calls
    assert "general:gaps_out 0" in calls


def test_decrease_from_zero_stays_at_zero():
    """Decreasing when already at zero must stay at zero (no negative gaps)."""
    rc, calls = _run("-", gaps_in=0, gaps_out=0)
    assert rc == 0
    assert "general:gaps_in 0" in calls
    assert "general:gaps_out 0" in calls


def test_decrease_exactly_step():
    """Decreasing when value equals STEP should land exactly on zero."""
    rc, calls = _run("-", gaps_in=5, gaps_out=5)
    assert rc == 0
    assert "general:gaps_in 0" in calls
    assert "general:gaps_out 0" in calls


def test_decrease_positive_result_does_not_abort():
    """
    Regression: (( new_in < 0 )) && new_in=0 with set -e aborted the script
    when new_in was already positive (expression false → exit 1 → set -e).
    Verify hyprctl keyword is always called on a valid decrease.
    """
    rc, calls = _run("-", gaps_in=20, gaps_out=30)
    assert rc == 0, "Script must not abort on a positive post-decrement value"
    assert "general:gaps_in 15" in calls
    assert "general:gaps_out 25" in calls
