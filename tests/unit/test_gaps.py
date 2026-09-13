"""Tests for bin/hyprconf-gaps (SUPER+SHIFT+= / SUPER+SHIFT+-).

The tool reads general:gaps_in / gaps_out with `hyprctl getoption -j` and
applies the stepped values with `hyprctl eval "hl.config({ general = { … } })"`.
It is `eval`, not `keyword`, on purpose (AGENTS.md > Known quirks; the why sits
beside the call in bin/hyprconf-gaps).

Everything runs against a fake hyprctl on PATH that serves canned getoption
JSON and records every `eval` program it is handed.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "bin" / "hyprconf-gaps"


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
        fi
    """)


def _gap_json(option: str, value: int) -> str:
    """CCssGapData as `hyprctl getoption -j` reports it. Hyprland 0.56 names
    the four-sided field "css"; the "custom" older builds used is covered by
    the empty-css case of test_reads_every_hyprctl_json_shape."""
    return json.dumps(
        {
            "option": option,
            "int": 0,
            "float": 0.0,
            "str": "",
            "css": f"{value} {value} {value} {value}",
            "set": True,
        }
    )


def _run(
    tmp_path: Path,
    direction: str | None,
    *,
    json_in: str,
    json_out: str,
    eval_reply: str = "ok",
) -> tuple[subprocess.CompletedProcess, list[str]]:
    """Run hyprconf-gaps against the fake hyprctl; return (process, eval programs)."""
    fake_dir = tmp_path / "bins"
    fake_dir.mkdir(exist_ok=True)
    calls_file = tmp_path / "evals.txt"
    fake = fake_dir / "hyprctl"
    fake.write_text(_fake_hyprctl(calls_file, json_in, json_out, eval_reply=eval_reply))
    fake.chmod(0o755)

    # The fake first, then only /usr/bin and /bin (jq lives there) — never the
    # host's PATH, where /usr/share/omarchy/bin would answer.
    env = {"PATH": f"{fake_dir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    args = [direction] if direction is not None else []  # None: the bare, zero-argument run
    proc = subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=30
    )
    calls = calls_file.read_text().splitlines() if calls_file.exists() else []
    return proc, [c.strip() for c in calls if c.strip()]


def _expected(gaps_in: int, gaps_out: int) -> str:
    return f"hl.config({{ general = {{ gaps_in = {gaps_in}, gaps_out = {gaps_out} }} }})"


def _step(tmp_path: Path, direction: str, gaps_in: int, gaps_out: int):
    return _run(
        tmp_path,
        direction,
        json_in=_gap_json("general:gaps_in", gaps_in),
        json_out=_gap_json("general:gaps_out", gaps_out),
    )


@pytest.mark.parametrize(
    ("direction", "gaps_in", "gaps_out", "exp_in", "exp_out"),
    [
        ("+", 10, 20, 12, 22),
        ("+", 0, 0, 2, 2),
        ("-", 15, 25, 13, 23),
        ("-", 1, 1, 0, 0),  # floors at 0, never negative
    ],
)
def test_steps_both_gaps_together(
    tmp_path: Path,
    direction: str,
    gaps_in: int,
    gaps_out: int,
    exp_in: int,
    exp_out: int,
) -> None:
    proc, calls = _step(tmp_path, direction, gaps_in, gaps_out)
    assert proc.returncode == 0, proc.stderr
    assert calls == [_expected(exp_in, exp_out)]


@pytest.mark.parametrize(
    ("json_in", "json_out", "expected"),
    [
        # A populated int field and no four-sided field: read the int.
        (
            json.dumps({"option": "general:gaps_in", "int": 8, "str": "", "set": True}),
            json.dumps({"option": "general:gaps_out", "int": 15, "str": "", "set": True}),
            _expected(10, 17),
        ),
        # An empty "css" string counts as absent, so a populated "custom" still wins.
        (
            json.dumps({"option": "general:gaps_in", "int": 0, "css": "", "custom": "5 5 5 5"}),
            json.dumps({"option": "general:gaps_out", "int": 0, "css": "", "custom": "9 9 9 9"}),
            _expected(7, 11),
        ),
        # Non-JSON getoption output (the plain-text format) must not crash: jq
        # fails to parse it and the `|| echo 0` fallback wins.
        ("option: general:gaps_in = 10", "option: general:gaps_out = 10", _expected(2, 2)),
        # No output at all (hyprctl cannot reach the compositor) reads as 0.
        ("", "", _expected(2, 2)),
    ],
    ids=["int-fallback", "empty-css", "non-json", "empty"],
)
def test_reads_every_hyprctl_json_shape(
    tmp_path: Path, json_in: str, json_out: str, expected: str
) -> None:
    proc, calls = _run(tmp_path, "+", json_in=json_in, json_out=json_out)
    assert proc.returncode == 0, proc.stderr
    assert calls == [expected]


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


@pytest.mark.parametrize("direction", ["sideways", None], ids=["bad", "bare"])
def test_a_run_that_is_not_a_step_is_a_usage_error_and_touches_nothing(
    tmp_path: Path, direction: str | None
) -> None:
    """No argument must never default to `+`: a user typing the bare command
    to learn its shape was silently widening their gaps."""
    proc, evals = _run(
        tmp_path,
        direction,
        json_in=_gap_json("general:gaps_in", 4),
        json_out=_gap_json("general:gaps_out", 8),
    )
    assert proc.returncode == 1
    assert "Usage" in proc.stderr
    assert evals == []
