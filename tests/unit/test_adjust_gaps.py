"""Tests for stow/hypr/.config/hypr/scripts/adjust-gaps."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parent.parent.parent
    / "stow" / "hypr" / ".config" / "hypr" / "scripts" / "adjust-gaps"
)


def _fake_hyprctl_script(
    calls_file: Path,
    json_in: str,
    json_out: str,
) -> str:
    """Return a fake hyprctl bash script body.

    getoption returns CCssGapData JSON; --batch records keyword calls.
    """
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [[ "$1" == "getoption" ]]; then
            case "$2" in
                general:gaps_in)  echo '{json_in}' ;;
                general:gaps_out) echo '{json_out}' ;;
            esac
        elif [[ "$1" == "--batch" ]]; then
            IFS=';' read -ra CMDS <<< "$2"
            for cmd in "${{CMDS[@]}}"; do
                cmd="$(echo "$cmd" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
                if [[ "$cmd" == keyword\\ * ]]; then
                    echo "${{cmd#keyword }}" >> "{calls_file}"
                fi
            done
        fi
    """)


def _run(direction: str, gaps_in: int, gaps_out: int) -> tuple[int, list[str]]:
    """Run adjust-gaps with a fake hyprctl in PATH; return (rc, keyword_calls).

    The fake hyprctl returns JSON with a ``custom`` field (CCssGapData format)
    for getoption calls, and records keyword calls from --batch to a file.
    """
    fake_dir = Path(tempfile.mkdtemp())
    try:
        fake_hyprctl = fake_dir / "hyprctl"
        calls_file = fake_dir / "calls.txt"

        json_in = json.dumps({
            "option": "general:gaps_in", "int": 0, "float": 0.0,
            "str": "", "custom": f"{gaps_in} {gaps_in} {gaps_in} {gaps_in}",
            "set": True,
        })
        json_out = json.dumps({
            "option": "general:gaps_out", "int": 0, "float": 0.0,
            "str": "", "custom": f"{gaps_out} {gaps_out} {gaps_out} {gaps_out}",
            "set": True,
        })

        fake_hyprctl.write_text(
            _fake_hyprctl_script(calls_file, json_in, json_out)
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
    finally:
        shutil.rmtree(fake_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Increase
# ---------------------------------------------------------------------------

def test_increase_by_step():
    rc, calls = _run("+", gaps_in=10, gaps_out=20)
    assert rc == 0
    assert "general:gaps_in 12" in calls
    assert "general:gaps_out 22" in calls


def test_increase_from_zero():
    rc, calls = _run("+", gaps_in=0, gaps_out=0)
    assert rc == 0
    assert "general:gaps_in 2" in calls
    assert "general:gaps_out 2" in calls


def test_increase_large_values():
    """No upper cap — can grow well beyond typical values."""
    rc, calls = _run("+", gaps_in=200, gaps_out=300)
    assert rc == 0
    assert "general:gaps_in 202" in calls
    assert "general:gaps_out 302" in calls


# ---------------------------------------------------------------------------
# Decrease
# ---------------------------------------------------------------------------

def test_decrease_by_step():
    rc, calls = _run("-", gaps_in=15, gaps_out=25)
    assert rc == 0
    assert "general:gaps_in 13" in calls
    assert "general:gaps_out 23" in calls


def test_decrease_clamps_at_zero():
    """Decreasing below zero should floor at 0, not go negative."""
    rc, calls = _run("-", gaps_in=1, gaps_out=1)
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
    rc, calls = _run("-", gaps_in=2, gaps_out=2)
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
    assert "general:gaps_in 18" in calls
    assert "general:gaps_out 28" in calls


# ---------------------------------------------------------------------------
# Regression: broken/empty hyprctl output must not crash
# ---------------------------------------------------------------------------

def test_increase_with_broken_hyprctl_output_defaults_to_zero(tmp_path):
    """Regression: if hyprctl getoption returns non-JSON output, python3
    json.load raises and the '|| echo 0' fallback must kick in."""
    fake_hyprctl = tmp_path / "hyprctl"
    calls_file = tmp_path / "calls.txt"

    fake_hyprctl.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [[ "$1" == "getoption" ]]; then
            echo "option: general:gaps_in = 10"
        elif [[ "$1" == "--batch" ]]; then
            IFS=';' read -ra CMDS <<< "$2"
            for cmd in "${{CMDS[@]}}"; do
                cmd="$(echo "$cmd" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
                if [[ "$cmd" == keyword\\ * ]]; then
                    echo "${{cmd#keyword }}" >> "{calls_file}"
                fi
            done
        fi
    """))
    fake_hyprctl.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"

    result = subprocess.run(
        ["bash", str(SCRIPT), "+"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Script crashed on broken hyprctl output.\nstderr: {result.stderr}"
    )
    # Gaps_in was 0 (fallback) + STEP=2 → 2
    calls = calls_file.read_text().splitlines() if calls_file.exists() else []
    assert any("general:gaps_in 2" in c for c in calls), (
        f"Expected gaps_in=2 (0+2) but calls were: {calls}"
    )


def test_increase_with_int_field_fallback():
    """When the JSON has a populated int field but no custom field (e.g. older
    Hyprland or non-CSS option), the script should read the int value."""
    fake_dir = Path(tempfile.mkdtemp())
    try:
        fake_hyprctl = fake_dir / "hyprctl"
        calls_file = fake_dir / "calls.txt"

        json_in = json.dumps({
            "option": "general:gaps_in", "int": 8, "float": 0.0,
            "str": "", "set": True,
        })
        json_out = json.dumps({
            "option": "general:gaps_out", "int": 15, "float": 0.0,
            "str": "", "set": True,
        })

        fake_hyprctl.write_text(
            _fake_hyprctl_script(calls_file, json_in, json_out)
        )
        fake_hyprctl.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{fake_dir}:{env['PATH']}"

        result = subprocess.run(
            ["bash", str(SCRIPT), "+"],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        calls = [l.strip() for l in calls_file.read_text().splitlines() if l.strip()]
        assert "general:gaps_in 10" in calls
        assert "general:gaps_out 17" in calls
    finally:
        shutil.rmtree(fake_dir, ignore_errors=True)
