"""modules/bar: the bar back on the top edge, through Omarchy's own `omarchy bar position`,
on any run that finds it on another; a bar already on top (or nothing to read) and the undo
write and call nothing."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import Box

INSTALL = Path(__file__).parent / "install"
JSON = ".config/omarchy/shell.json"
# bin/omarchy-bar:198-205: `position <edge>` through omarchy-shell-config's commit (:53-62).
POSITION = """
json="$HOME/.config/omarchy/shell.json"
[[ $1 == position ]] || exit 1
jq -S -e --arg p "$2" '.bar.position = $p' "$json" > "$json.t" && mv "$json.t" "$json"
"""

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")


def write(box: Box, text: str) -> Path:
    path = box.home / JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.mark.parametrize("edge", ["bottom", "left", "right"])
def test_a_bar_on_another_edge_goes_back_to_top_and_a_second_run_writes_nothing(
    box: Box, edge: str
) -> None:
    box.stub("omarchy-bar", POSITION)
    path = write(box, json.dumps({"version": 1, "bar": {"position": edge, "transparent": False}}))
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert box.calls_of("omarchy-bar") == [["omarchy-bar", "position", "top"]]
    assert json.loads(path.read_text())["bar"] == {"position": "top", "transparent": False}
    assert f"on the {edge} edge" in result.stdout
    before = box.snapshot()
    box.reset()
    assert box.run(INSTALL).returncode == 0
    assert box.commands == [] and box.snapshot() == before


@pytest.mark.parametrize(
    "text",
    [
        None,  # no shell.json yet: the shipped defaults' top
        '{"version": 1, "bar": {"position": "top"}}',
        '{"version": 1, "bar": {}}',
        '{"version": 1, "bar": {"position": "middle"}}',  # read as top (BarModel.js:5-8)
        "{ not json",
    ],
)
def test_a_bar_on_top_or_nothing_to_read_is_left_alone(box: Box, text: str | None) -> None:
    if text is not None:
        write(box, text)
    before = box.snapshot()
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert box.commands == [] and box.snapshot() == before and result.stdout == ""


def test_a_failed_write_warns_and_does_not_fail_the_run(box: Box) -> None:
    box.stub("omarchy-bar", "exit 1\n")
    path = write(box, '{"bar": {"position": "right"}}')
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert "retried on the next run" in result.stdout
    assert json.loads(path.read_text())["bar"]["position"] == "right"


@pytest.mark.parametrize("installed", [False, True])
def test_undo_leaves_the_bar_where_it_is_and_calls_nothing(box: Box, installed: bool) -> None:
    box.stub("omarchy-bar", POSITION)
    path = write(box, '{"bar": {"position": "right"}}')
    if installed:
        box.run(INSTALL)
        box.reset()
    before = box.snapshot()
    assert box.undo("bar").returncode == 0
    assert box.commands == [] and box.snapshot() == before
    assert json.loads(path.read_text())["bar"]["position"] == ("top" if installed else "right")
