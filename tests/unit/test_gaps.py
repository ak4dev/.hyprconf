"""Tests for bin/hyprconf-gaps (SUPER+SHIFT+= / SUPER+SHIFT+-).

The tool reads general:gaps_in / gaps_out with `hyprctl getoption -j` and
applies the stepped values with `hyprctl eval "hl.config({ general = { … } })"`.
It is `eval`, not `keyword`, on purpose: under Hyprland 0.56's Lua parser
`hyprctl keyword` answers "keyword can't work with non-legacy parsers. Use
eval." and still exits 0 — a silent no-op. `eval` answers "ok" on success and
reports a real failure (exit 7), which the script surfaces.

Everything runs against a fake hyprctl on PATH that serves canned getoption
JSON and records every `eval` program it is handed — a `keyword` call records
nothing, so it can never satisfy the expected-program assertions.
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


def _step(tmp_path: Path, direction: str, gaps_in: int, gaps_out: int, *, field: str = "css"):
    return _run(
        tmp_path,
        direction,
        json_in=_gap_json("general:gaps_in", gaps_in, field=field),
        json_out=_gap_json("general:gaps_out", gaps_out, field=field),
    )


@pytest.mark.parametrize(
    ("direction", "gaps_in", "gaps_out", "exp_in", "exp_out", "field"),
    [
        ("+", 10, 20, 12, 22, "css"),
        ("+", 0, 0, 2, 2, "css"),
        ("+", 200, 300, 202, 302, "css"),  # no upper cap
        ("-", 15, 25, 13, 23, "css"),
        ("-", 1, 1, 0, 0, "css"),  # floors at 0, never negative
        ("-", 0, 0, 0, 0, "css"),
        ("-", 2, 2, 0, 0, "css"),  # a value equal to STEP lands exactly on zero
        # Older builds report the four-sided gap under "custom", not "css".
        ("+", 10, 20, 12, 22, "custom"),
    ],
)
def test_steps_both_gaps_together(
    tmp_path: Path,
    direction: str,
    gaps_in: int,
    gaps_out: int,
    exp_in: int,
    exp_out: int,
    field: str,
) -> None:
    proc, calls = _step(tmp_path, direction, gaps_in, gaps_out, field=field)
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


def test_no_inline_python() -> None:
    """The JSON is parsed with jq, the tool Omarchy uses for `hyprctl getoption -j`."""
    code = "\n".join(
        ln for ln in SCRIPT.read_text().splitlines() if not ln.lstrip().startswith("#")
    )
    assert "python" not in code
    assert "jq " in code


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


def test_bare_run_is_a_usage_error_and_touches_nothing(tmp_path: Path) -> None:
    """No argument must never default to `+`: a user typing the bare command
    to learn its shape was silently widening their gaps."""
    proc, evals = _run(
        tmp_path,
        None,
        json_in=_gap_json("general:gaps_in", 4),
        json_out=_gap_json("general:gaps_out", 8),
    )
    assert proc.returncode == 1
    assert "Usage:" in proc.stderr
    assert evals == []
