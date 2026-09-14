"""modules/idle: the screensaver timeout, set once through Omarchy's own shell.json helper
(conftest's SHELL_CONFIG stands in for the sourced bin/omarchy-shell-config)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import SHELL_CONFIG

INSTALL = Path(__file__).parent / "install"
JSON = ".config/omarchy/shell.json"
MARKER = ".local/state/hyprconf/idle-applied"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")


@pytest.fixture(autouse=True)
def _helper(box) -> None:
    """Make `source omarchy-shell-config` work, and `omarchy-shell` answer."""
    box.stub("omarchy-shell-config", SHELL_CONFIG)
    box.stub("omarchy-shell")


def write(box, text: str) -> None:
    (box.home / JSON).parent.mkdir(parents=True, exist_ok=True)
    (box.home / JSON).write_text(text)


def config(box) -> dict:
    return json.loads((box.home / JSON).read_text())


def test_the_screensaver_is_set_to_900_through_omarchys_own_helper(box):
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert config(box)["idle"] == {"screensaver": 900, "lock": 300}  # .idle.lock left alone
    assert config(box)["bar"]["centerAnchor"] == "omarchy.clock"  # from the shipped defaults
    assert "omarchy-shell-config" in box.commands
    assert ["omarchy-shell", "shell", "reloadConfig"] in box.calls_of("omarchy-shell")
    assert (box.home / MARKER).exists()


def test_an_existing_shell_json_is_edited_not_replaced(box):
    write(box, json.dumps({"version": 1, "idle": {"lock": 60}, "bar": {"position": "bottom"}}))
    box.run(INSTALL)
    assert config(box)["idle"] == {"lock": 60, "screensaver": 900}
    assert config(box)["bar"] == {"position": "bottom"}


def test_a_second_run_writes_nothing_and_calls_nothing(box):
    box.run(INSTALL)
    before = {p: p.read_bytes() for p in box.files()}
    box.reset()
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert box.commands == []
    assert {p: p.read_bytes() for p in box.files()} == before


def test_the_marker_is_honoured_so_a_later_hand_edit_is_never_re_asserted(box):
    box.run(INSTALL)
    write(box, json.dumps({"idle": {"screensaver": 60}}))
    box.reset()
    box.run(INSTALL)
    assert config(box)["idle"]["screensaver"] == 60
    assert box.commands == []


@pytest.mark.parametrize("case", ["no-helper", "commit-fails"])
def test_a_failure_warns_leaves_no_marker_and_does_not_fail_the_run(box, case):
    env = {}
    if case == "no-helper":  # a PATH with no omarchy-*: `command -v` fails
        (box.tmp / "bare").mkdir()
        for tool in ("bash", "readlink", "dirname"):
            (box.tmp / "bare" / tool).symlink_to(shutil.which(tool))
        env["PATH"] = str(box.tmp / "bare")
    else:
        write(box, "{ not json")  # jq -S -e fails, so commit()'s fail() exits the subshell 1
    before = box.files()
    result = box.run(INSTALL, env=env)
    assert result.returncode == 0
    assert "retry" in result.stdout
    assert box.files() == before, "a failed run leaves nothing behind, the marker included"


def test_undo_drops_the_key_and_the_marker(box):
    box.run(INSTALL)
    box.reset()
    result = box.undo("idle")
    assert result.returncode == 0, result.stderr
    assert config(box)["idle"] == {"lock": 300}  # Omarchy's own 150 s applies again
    assert "omarchy-shell-config" in box.commands
    assert not (box.home / MARKER).exists()


@pytest.mark.parametrize("text", [None, '{"version": 1, "idle": {"lock": 300}}', "{ not json"])
def test_undo_leaves_a_shell_json_that_never_carried_the_key_alone(box, text):
    if text is not None:
        write(box, text)
    (box.home / MARKER).parent.mkdir(parents=True)
    (box.home / MARKER).touch()
    assert box.undo("idle").returncode == 0
    path = box.home / JSON
    assert (path.read_text() if path.exists() else None) == text
    assert not (box.home / MARKER).exists()
    assert box.commands == []
