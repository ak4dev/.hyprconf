"""modules/fastfetch — the greeting layout, at a path only the greeting reads: never
~/.config/fastfetch/config.jsonc, Omarchy's About screen (bin/omarchy-launch-about:161)."""

import json
import re
from pathlib import Path

import pytest

from conftest import Box

MODULE = Path(__file__).parent
INSTALL, SRC = MODULE / "install", MODULE / "config.jsonc"
TARGET, ABOUT_SLOT = ".config/hyprconf/fastfetch.jsonc", ".config/fastfetch/config.jsonc"
# Gone from the checkout: a link to it dangles, and the install matches text, not file.
PRE_SPLIT = MODULE.parent.parent / "fastfetch" / "config.jsonc"


def old_link(box: Box, points_at: Path) -> Path:
    slot = box.home / ABOUT_SLOT
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.symlink_to(points_at)
    return slot


def test_install_copies_the_layout_and_writes_nothing_else(box: Box) -> None:
    assert (r := box.run(INSTALL)).returncode == 0, r.stderr
    target = box.home / TARGET
    assert target.read_bytes() == SRC.read_bytes() and target.stat().st_mode & 0o777 == 0o644
    assert box.files() == {target} and box.commands == []


def test_a_second_run_writes_nothing_and_a_stale_copy_is_refreshed(box: Box) -> None:
    assert box.run(INSTALL).returncode == 0
    before = box.snapshot()
    box.reset()
    r = box.run(INSTALL)
    assert r.returncode == 0 and r.stdout == ""
    assert box.snapshot() == before
    assert box.commands == []
    # README > Settings, the other half: the gate is cmp, not existence, so
    # "edit config.jsonc here and re-run" writes a copy that has drifted again.
    (target := box.home / TARGET).write_text("{}\n")
    assert box.run(INSTALL).returncode == 0
    assert target.read_bytes() == SRC.read_bytes() and target.stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize("shared", [False, True])
def test_undo_removes_the_copy_and_its_directory_only_while_empty(box: Box, shared: bool) -> None:
    assert box.run(INSTALL).returncode == 0
    neighbour = (box.home / TARGET).parent / "another-module.conf"
    if shared:
        neighbour.write_text("x\n")
    assert box.undo("fastfetch").returncode == 0
    assert box.files() == ({neighbour} if shared else set())
    assert (box.home / TARGET).parent.exists() is shared


@pytest.mark.parametrize("args", [(), ("undo",)], ids=["install", "undo"])
def test_a_link_of_ours_in_the_about_slot_is_cleared(box: Box, args) -> None:
    link = old_link(box, PRE_SPLIT)
    assert box.run(INSTALL, *args).returncode == 0
    assert not link.is_symlink() and not link.exists()


def test_the_file_that_link_displaced_is_put_back(box: Box) -> None:
    link = old_link(box, PRE_SPLIT)
    Path(f"{link}.stock").write_text('{"mine": true}\n')
    assert box.run(INSTALL).returncode == 0
    assert not link.is_symlink() and link.read_text() == '{"mine": true}\n'
    assert not Path(f"{link}.stock").exists()


@pytest.mark.parametrize("theirs", [True, False], ids=["a link of theirs", "a real file"])
def test_anything_else_in_the_about_slot_is_left_alone(box: Box, theirs: bool) -> None:
    """A link to THIS checkout's config.jsonc is theirs too: no release ever wrote one."""
    slot = old_link(box, SRC)
    if not theirs:
        slot.unlink()
        slot.write_text('{"theirs": true}\n')
    before = box.snapshot(slot.parent)
    assert box.run(INSTALL).returncode == 0
    assert box.undo("fastfetch").returncode == 0
    assert box.snapshot(slot.parent) == before


def test_the_layout_is_a_self_contained_fastfetch_config() -> None:
    """`-c <file>` is the whole command: the logo is in it, and no format is positional."""
    conf = json.loads(SRC.read_text())
    assert conf["logo"] == {"source": "arch2", "color": {"1": "green", "2": "green"}}
    for module in conf["modules"]:
        if isinstance(module, str) or module["type"] == "custom":
            continue
        for name in re.findall(r"\{([^}]*)\}", module.get("format", "")):
            assert not name.isdigit(), f"{module['type']}: positional {{{name}}}"
