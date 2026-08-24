"""Tests for hypr/scripts/adjust-gaps.

The script reads general:gaps_in / gaps_out with `hyprctl getoption -j` and
applies the stepped values with `hyprctl eval "hl.config({ general = { … } })"`.
It is `eval`, not `keyword`, on purpose: under Hyprland 0.56's Lua parser
`hyprctl keyword` answers "keyword can't work with non-legacy parsers. Use
eval." and still exits 0, so the old form failed silently. `eval` answers "ok"
on success and reports a real failure (exit 7), which the script surfaces.

Everything runs against a fake hyprctl on PATH that serves canned getoption
JSON and records every `eval` program it is handed.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

SCRIPT = Path(__file__).parent.parent.parent / "hypr" / "scripts" / "adjust-gaps"


def _fake_hyprctl(calls_file: Path, json_in: str, json_out: str, *, eval_reply: str = "ok") -> str:
    """A fake hyprctl: getoption serves canned JSON, eval records its program."""
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [[ "$1" == "getoption" ]]; then
            case "$2" in
                general:gaps_in)  echo '{json_in}' ;;
                general:gaps_out) echo '{json_out}' ;;
            esac
        elif [[ "$1" == "eval" ]]; then
            printf '%s\\n' "$2" >> "{calls_file}"
            echo "{eval_reply}"
        elif [[ "$1" == "keyword" ]]; then
            # What Hyprland 0.56 really says — and it exits 0 while doing nothing.
            echo "keyword can't work with non-legacy parsers. Use eval."
        fi
    """)


def _gap_json(option: str, value: int, *, field: str = "css") -> str:
    """CCssGapData as `hyprctl getoption -j` reports it.

    Hyprland 0.56 names the four-sided field "css"; older builds used "custom".
    """
    return json.dumps(
        {
            "option": option,
            "int": 0,
            "float": 0.0,
            "str": "",
            field: f"{value} {value} {value} {value}",
            "set": True,
        }
    )


def _run(
    tmp_path: Path,
    direction: str,
    *,
    json_in: str,
    json_out: str,
    eval_reply: str = "ok",
) -> tuple[subprocess.CompletedProcess, list[str]]:
    """Run adjust-gaps against the fake hyprctl; return (process, eval programs)."""
    fake_dir = tmp_path / "bins"
    fake_dir.mkdir(exist_ok=True)
    calls_file = tmp_path / "evals.txt"
    fake = fake_dir / "hyprctl"
    fake.write_text(_fake_hyprctl(calls_file, json_in, json_out, eval_reply=eval_reply))
    fake.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_dir}:{env['PATH']}"
    proc = subprocess.run(
        ["bash", str(SCRIPT), direction], env=env, capture_output=True, text=True, timeout=30
    )
    calls = calls_file.read_text().splitlines() if calls_file.exists() else []
    return proc, [c.strip() for c in calls if c.strip()]


def _expected(gaps_in: int, gaps_out: int) -> str:
    return f"hl.config({{ general = {{ gaps_in = {gaps_in}, gaps_out = {gaps_out} }} }})"


def _step(tmp_path: Path, direction: str, gaps_in: int, gaps_out: int, *, field: str = "css"):
    return _run(
        tmp_path,
        direction,
        json_in=_gap_json("general:gaps_in", gaps_in, field=field),
        json_out=_gap_json("general:gaps_out", gaps_out, field=field),
    )


# ---------------------------------------------------------------------------
# Increase
# ---------------------------------------------------------------------------


def test_increase_by_step(tmp_path: Path) -> None:
    proc, calls = _step(tmp_path, "+", 10, 20)
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(12, 22)]


def test_increase_from_zero(tmp_path: Path) -> None:
    proc, calls = _step(tmp_path, "+", 0, 0)
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(2, 2)]


def test_increase_large_values(tmp_path: Path) -> None:
    """No upper cap — can grow well beyond typical values."""
    proc, calls = _step(tmp_path, "+", 200, 300)
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(202, 302)]


# ---------------------------------------------------------------------------
# Decrease
# ---------------------------------------------------------------------------


def test_decrease_by_step(tmp_path: Path) -> None:
    proc, calls = _step(tmp_path, "-", 15, 25)
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(13, 23)]


def test_decrease_clamps_at_zero(tmp_path: Path) -> None:
    """Decreasing below zero floors at 0, never negative."""
    proc, calls = _step(tmp_path, "-", 1, 1)
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(0, 0)]


def test_decrease_from_zero_stays_at_zero(tmp_path: Path) -> None:
    proc, calls = _step(tmp_path, "-", 0, 0)
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(0, 0)]


def test_decrease_exactly_step(tmp_path: Path) -> None:
    """A value equal to STEP lands exactly on zero."""
    proc, calls = _step(tmp_path, "-", 2, 2)
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(0, 0)]


def test_decrease_positive_result_does_not_abort(tmp_path: Path) -> None:
    """Regression: `(( new < 0 )) && new=0` under set -e aborted the script
    whenever the value was already positive (false expression -> exit 1)."""
    proc, calls = _step(tmp_path, "-", 20, 30)
    assert proc.returncode == 0, "Script must not abort on a positive post-decrement value"
    assert calls == [_expected(18, 28)]


# ---------------------------------------------------------------------------
# Reading the current value across hyprctl JSON shapes
# ---------------------------------------------------------------------------


def test_reads_the_pre_0_56_custom_field_too(tmp_path: Path) -> None:
    """Older builds report the four-sided gap under "custom", not "css"."""
    proc, calls = _step(tmp_path, "+", 10, 20, field="custom")
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(12, 22)]


def test_increase_with_int_field_fallback(tmp_path: Path) -> None:
    """A populated int field and no four-sided field: read the int."""
    proc, calls = _run(
        tmp_path,
        "+",
        json_in=json.dumps({"option": "general:gaps_in", "int": 8, "str": "", "set": True}),
        json_out=json.dumps({"option": "general:gaps_out", "int": 15, "str": "", "set": True}),
    )
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(10, 17)]


def test_reads_custom_when_css_is_empty(tmp_path: Path) -> None:
    """An empty "css" string counts as absent, so a populated "custom" still wins."""
    proc, calls = _run(
        tmp_path,
        "+",
        json_in=json.dumps({"option": "general:gaps_in", "int": 0, "css": "", "custom": "5 5 5 5"}),
        json_out=json.dumps(
            {"option": "general:gaps_out", "int": 0, "css": "", "custom": "9 9 9 9"}
        ),
    )
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(7, 11)]


def test_increase_with_broken_hyprctl_output_defaults_to_zero(tmp_path: Path) -> None:
    """Non-JSON getoption output (the plain-text format) must not crash: jq
    fails to parse it and the `|| echo 0` fallback wins."""
    proc, calls = _run(
        tmp_path,
        "+",
        json_in="option: general:gaps_in = 10",
        json_out="option: general:gaps_out = 10",
    )
    assert proc.returncode == 0, f"Script crashed on broken hyprctl output.\nstderr: {proc.stderr}"
    assert calls == [_expected(2, 2)]


def test_increase_with_empty_hyprctl_output_defaults_to_zero(tmp_path: Path) -> None:
    """No output at all (hyprctl cannot reach the compositor) reads as 0."""
    proc, calls = _run(tmp_path, "+", json_in="", json_out="")
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(2, 2)]


def test_no_inline_python() -> None:
    """The JSON is parsed with jq, the tool Omarchy uses for `hyprctl getoption -j`."""
    code = "\n".join(
        ln for ln in SCRIPT.read_text().splitlines() if not ln.lstrip().startswith("#")
    )
    assert "python" not in code
    assert "jq " in code


# ---------------------------------------------------------------------------
# The apply path
# ---------------------------------------------------------------------------


def test_never_uses_hyprctl_keyword() -> None:
    """`hyprctl keyword` is a silent no-op under the Lua parser (exit 0)."""
    code = "\n".join(
        ln for ln in SCRIPT.read_text().splitlines() if not ln.lstrip().startswith("#")
    )
    assert "hyprctl keyword" not in code
    assert "hyprctl eval" in code


def test_a_rejected_eval_is_reported(tmp_path: Path) -> None:
    """Anything but "ok" from eval is a failed apply, and the hotkey must say so."""
    proc, calls = _run(
        tmp_path,
        "+",
        json_in=_gap_json("general:gaps_in", 4),
        json_out=_gap_json("general:gaps_out", 8),
        eval_reply="error: unknown config key 'general.gaps_in'",
    )
    assert proc.returncode == 1
    assert "unknown config key" in proc.stderr
    assert calls == [_expected(6, 10)]


def test_usage_on_bad_direction(tmp_path: Path) -> None:
    proc, calls = _step(tmp_path, "sideways", 4, 8)
    assert proc.returncode == 1
    assert "Usage" in proc.stderr
    assert calls == []
