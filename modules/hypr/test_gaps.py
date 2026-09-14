"""bin/hyprconf-gaps (SUPER+SHIFT+= / SUPER+SHIFT+-).

The tool reads general:gaps_in / gaps_out with `hyprctl getoption -j` and
applies the stepped values with `hyprctl eval "hl.config({ general = { … } })"`.
It is `eval`, not `keyword`, on purpose — the why sits beside the call in the
tool. Everything runs against the box's hyprctl, stubbed to serve canned
getoption JSON and to record every `eval` program it is handed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "bin" / "hyprconf-gaps"

# getoption answers from a file per option; eval answers "ok" unless the test
# says otherwise.
HYPRCTL = (
    'case "${1:-}" in\n'
    '  getoption) f="$HOME/${2#general:}.json"; [[ -f $f ]] && cat "$f" ;;\n'
    '  eval) cat "$HOME/eval_reply" 2>/dev/null || echo ok ;;\n'
    "esac\n"
)


def _gap_json(option: str, value: int) -> str:
    """CCssGapData as `hyprctl getoption -j` reports it on Hyprland 0.56.2:
    the four-sided value is in "css" and in no other populated field (verified
    live for both gaps options)."""
    return json.dumps(
        {"option": option, "int": 0, "float": 0.0, "str": "", "css": f"{value} " * 3 + str(value)}
    )


def _run(box, direction: str | None, *, gaps_in: str, gaps_out: str, eval_reply: str = "ok"):
    box.stub("hyprctl", HYPRCTL)
    (box.home / "gaps_in.json").write_text(gaps_in)
    (box.home / "gaps_out.json").write_text(gaps_out)
    (box.home / "eval_reply").write_text(eval_reply + "\n")
    args = [] if direction is None else [direction]  # None: the bare, zero-argument run
    proc = box.run(SCRIPT, *args)
    evals = [c[2] for c in box.calls_of("hyprctl") if len(c) > 2 and c[1] == "eval"]
    return proc, evals


def _expected(gaps_in: int, gaps_out: int) -> str:
    return f"hl.config({{ general = {{ gaps_in = {gaps_in}, gaps_out = {gaps_out} }} }})"


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
    box, direction: str, gaps_in: int, gaps_out: int, exp_in: int, exp_out: int
) -> None:
    proc, evals = _run(
        box,
        direction,
        gaps_in=_gap_json("general:gaps_in", gaps_in),
        gaps_out=_gap_json("general:gaps_out", gaps_out),
    )
    assert proc.returncode == 0, proc.stderr
    assert evals == [_expected(exp_in, exp_out)]


@pytest.mark.parametrize(
    ("gaps_in", "gaps_out"),
    [
        # Non-JSON getoption output (the plain-text format) must not crash: jq
        # fails to parse it and the `|| echo 0` fallback wins.
        ("option: general:gaps_in = 10", "option: general:gaps_out = 10"),
        # No output at all (hyprctl cannot reach the compositor) reads as 0.
        ("", ""),
    ],
    ids=["non-json", "empty"],
)
def test_an_unreadable_gap_reads_as_zero(box, gaps_in: str, gaps_out: str) -> None:
    proc, evals = _run(box, "+", gaps_in=gaps_in, gaps_out=gaps_out)
    assert proc.returncode == 0, proc.stderr
    assert evals == [_expected(2, 2)]


def test_a_rejected_eval_is_reported(box) -> None:
    """Anything but "ok" from eval is a failed apply, and the hotkey must say
    so: `hyprctl keyword` answers "use eval" and still exits 0, which is the
    silent no-op this check exists for."""
    proc, evals = _run(
        box,
        "+",
        gaps_in=_gap_json("general:gaps_in", 4),
        gaps_out=_gap_json("general:gaps_out", 8),
        eval_reply="error: unknown config key 'general.gaps_in'",
    )
    assert proc.returncode == 1
    assert "unknown config key" in proc.stderr
    assert evals == [_expected(6, 10)]


@pytest.mark.parametrize("direction", ["sideways", None], ids=["bad", "bare"])
def test_a_run_that_is_not_a_step_is_a_usage_error_and_touches_nothing(
    box, direction: str | None
) -> None:
    """No argument must never default to `+`: a user typing the bare command
    to learn its shape was silently widening their gaps."""
    proc, evals = _run(
        box,
        direction,
        gaps_in=_gap_json("general:gaps_in", 4),
        gaps_out=_gap_json("general:gaps_out", 8),
    )
    assert proc.returncode == 1
    assert "Usage" in proc.stderr
    assert evals == []
