"""bin/hyprconf-gaps (SUPER+SHIFT+= / SUPER+SHIFT+-): reads general:gaps_in /
gaps_out with `hyprctl getoption -j` and applies the stepped values with
`hyprctl eval`, against a hyprctl stubbed to serve canned JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "bin" / "hyprconf-gaps"
# getoption answers from a file per option; eval answers "ok" unless a test says otherwise.
HYPRCTL = (
    'case "${1:-}" in\n'
    '  getoption) f="$HOME/${2#general:}.json"; [[ -f $f ]] && cat "$f" ;;\n'
    '  eval) cat "$HOME/eval_reply" 2>/dev/null || echo ok ;;\n'
    "esac\n"
)


def _gap(value: int) -> str:
    """CCssGapData as Hyprland 0.56.2 reports it: the four-sided value is in "css" alone."""
    return json.dumps({"int": 0, "float": 0.0, "str": "", "css": f"{value} " * 3 + str(value)})


def _run(box, direction: str | None, gaps_in: str, gaps_out: str, eval_reply: str = "ok"):
    box.stub("hyprctl", HYPRCTL)
    (box.home / "gaps_in.json").write_text(gaps_in)
    (box.home / "gaps_out.json").write_text(gaps_out)
    (box.home / "eval_reply").write_text(eval_reply + "\n")
    proc = box.run(SCRIPT, *([] if direction is None else [direction]))
    return proc, [c[2] for c in box.calls_of("hyprctl") if len(c) > 2 and c[1] == "eval"]


def _expected(gaps_in: int, gaps_out: int) -> str:
    return f"hl.config({{ general = {{ gaps_in = {gaps_in}, gaps_out = {gaps_out} }} }})"


@pytest.mark.parametrize(
    ("direction", "gaps_in", "gaps_out", "exp_in", "exp_out"),
    [("+", 10, 20, 12, 22), ("-", 15, 25, 13, 23), ("-", 1, 1, 0, 0)],
    ids=["up", "down", "floors-at-zero"],
)
def test_steps_both_gaps_together(box, direction, gaps_in, gaps_out, exp_in, exp_out) -> None:
    proc, evals = _run(box, direction, _gap(gaps_in), _gap(gaps_out))
    assert proc.returncode == 0, proc.stderr
    assert evals == [_expected(exp_in, exp_out)]


@pytest.mark.parametrize(
    ("gaps_in", "gaps_out"),
    # Plain-text getoption output fails jq and takes the `|| echo 0` fallback;
    # no output at all (hyprctl cannot reach the compositor) reads as 0 too.
    [("option: general:gaps_in = 10", "option: general:gaps_out = 10"), ("", "")],
    ids=["non-json", "empty"],
)
def test_an_unreadable_gap_reads_as_zero(box, gaps_in: str, gaps_out: str) -> None:
    proc, evals = _run(box, "+", gaps_in, gaps_out)
    assert proc.returncode == 0, proc.stderr
    assert evals == [_expected(2, 2)]


def test_a_rejected_eval_is_reported(box) -> None:
    """`hyprctl keyword` answers "use eval" and still exits 0: anything but "ok" back is a failed apply."""
    proc, evals = _run(box, "+", _gap(4), _gap(8), "error: unknown config key 'general.gaps_in'")
    assert proc.returncode == 1
    assert "unknown config key" in proc.stderr
    assert evals == [_expected(6, 10)]


@pytest.mark.parametrize("direction", ["sideways", None], ids=["bad", "bare"])
def test_a_run_that_is_not_a_step_is_a_usage_error_and_touches_nothing(box, direction) -> None:
    """No argument must never default to `+` — the bare command was silently widening the gaps."""
    proc, evals = _run(box, direction, _gap(4), _gap(8))
    assert proc.returncode == 1
    assert "Usage" in proc.stderr
    assert evals == []
