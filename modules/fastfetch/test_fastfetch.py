"""modules/fastfetch — the shell greeting's layout.

The module is one copy, so the contract is small and the interesting half is
what it must NOT do: nothing may land in ~/.config/fastfetch/, the single
user slot fastfetch reads (`fastfetch --list-config-paths`, first hit wins),
because a file there replaces the layout Omarchy's About screen renders with
bare `fastfetch` (bin/omarchy-launch-about:161) and switches off that
window's fit measurement (:16-18, used at :61 and :95). Releases before the
module split did exactly that, so install also clears its own old link once.

HERMETIC: the `box` fixture (conftest.py) only — a tmp $HOME and a PATH whose
omarchy-* commands are recording fakes. This module calls none of them, and
one test pins that.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from conftest import Box

REPO_ROOT = Path(__file__).parent.parent.parent
MODULE = REPO_ROOT / "modules" / "fastfetch"
INSTALL = MODULE / "install"
SRC = MODULE / "config.jsonc"


def run(box: Box, *args: str):
    return box.run(INSTALL, *args)


def target(box: Box) -> Path:
    return box.home / ".config" / "hyprconf" / "fastfetch.jsonc"


def about_slot(box: Box) -> Path:
    """Omarchy's own user config slot — the path this module must never take."""
    return box.home / ".config" / "fastfetch" / "config.jsonc"


def snapshot(box: Box) -> dict[Path, tuple[int, bytes]]:
    """Every file under HOME as (mtime_ns, bytes) — the byte-stability probe."""
    return {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in box.files()}


# ------------------------------------------------------------------ install


def test_copies_the_layout_to_hyprconfs_own_path(box: Box) -> None:
    r = run(box)
    assert r.returncode == 0, r.stderr
    assert target(box).read_bytes() == SRC.read_bytes()
    assert target(box).stat().st_mode & 0o777 == 0o644


def test_leaves_omarchys_about_slot_and_every_omarchy_command_alone(box: Box) -> None:
    assert run(box).returncode == 0
    assert not (box.home / ".config" / "fastfetch").exists()
    assert box.commands == []
    assert box.files() == {target(box)}


def test_second_run_writes_nothing(box: Box) -> None:
    assert run(box).returncode == 0
    before = snapshot(box)
    box.reset()
    r = run(box)
    assert r.returncode == 0
    assert r.stdout == ""
    assert snapshot(box) == before
    assert box.commands == []


def test_a_changed_layout_is_copied_again(box: Box) -> None:
    assert run(box).returncode == 0
    target(box).write_text("{}\n")
    assert run(box).returncode == 0
    assert target(box).read_bytes() == SRC.read_bytes()


# --------------------------------------------------------------------- undo


def test_undo_removes_the_layout_and_its_empty_directory(box: Box) -> None:
    assert run(box).returncode == 0
    assert box.undo("fastfetch").returncode == 0
    assert not target(box).exists()
    assert not target(box).parent.exists()
    assert box.files() == set()


def test_undo_keeps_a_directory_another_module_shares(box: Box) -> None:
    assert run(box).returncode == 0
    neighbour = target(box).parent / "kept-by-someone-else.conf"
    neighbour.write_text("x\n")
    assert box.undo("fastfetch").returncode == 0
    assert box.files() == {neighbour}


def test_undo_with_nothing_installed_is_a_no_op(box: Box) -> None:
    r = box.undo("fastfetch")
    assert r.returncode == 0
    assert box.files() == set()


# ---------------------------------------------- the pre-module symlink, once


def legacy_link(box: Box, points_at: Path) -> Path:
    link = about_slot(box)
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(points_at)
    return link


def test_the_old_releases_link_into_the_about_slot_is_cleared(box: Box) -> None:
    # What install.sh linked before the split: <checkout>/fastfetch/config.jsonc.
    link = legacy_link(box, REPO_ROOT / "fastfetch" / "config.jsonc")
    assert run(box).returncode == 0
    assert not link.exists() and not link.is_symlink()
    assert target(box).read_bytes() == SRC.read_bytes()


def test_a_link_to_this_modules_own_file_is_cleared_too(box: Box) -> None:
    link = legacy_link(box, SRC)
    assert run(box).returncode == 0
    assert not link.is_symlink()


def test_a_dangling_old_link_is_cleared_from_a_copy_of_the_folder(box: Box) -> None:
    """Two contracts at once: the module runs from wherever the folder was
    dropped, and the link text is matched raw — the checkout it names may
    already be gone, and a dangling link at that path is still ours."""
    elsewhere = box.tmp / "checkout" / "modules" / "fastfetch"
    shutil.copytree(MODULE, elsewhere)
    link = legacy_link(box, box.tmp / "checkout" / "fastfetch" / "config.jsonc")
    assert not link.exists() and link.is_symlink()
    assert box.run(elsewhere / "install").returncode == 0
    assert not link.is_symlink()
    assert target(box).read_bytes() == SRC.read_bytes()


def test_the_backup_the_old_stage_took_is_restored(box: Box) -> None:
    link = legacy_link(box, REPO_ROOT / "fastfetch" / "config.jsonc")
    Path(f"{link}.stock").write_text('{"mine": true}\n')
    assert run(box).returncode == 0
    assert link.is_file() and not link.is_symlink()
    assert link.read_text() == '{"mine": true}\n'
    assert not Path(f"{link}.stock").exists()


def test_a_link_of_the_users_own_is_left_alone(box: Box) -> None:
    mine = box.home / "my-fastfetch.jsonc"
    mine.write_text("{}\n")
    link = legacy_link(box, mine)
    assert run(box).returncode == 0
    assert link.is_symlink() and link.resolve() == mine
    box.reset()
    assert box.undo("fastfetch").returncode == 0
    assert link.is_symlink()


def test_a_real_file_of_the_users_own_is_left_alone(box: Box) -> None:
    slot = about_slot(box)
    slot.parent.mkdir(parents=True)
    slot.write_text('{"theirs": true}\n')
    assert run(box).returncode == 0
    assert slot.read_text() == '{"theirs": true}\n'


def test_undo_clears_the_old_link_as_well(box: Box) -> None:
    link = legacy_link(box, REPO_ROOT / "fastfetch" / "config.jsonc")
    assert box.undo("fastfetch").returncode == 0
    assert not link.is_symlink()


# ------------------------------------------------------------- the layout


def test_layout_is_json_and_carries_the_logo_flags_the_greeting_dropped(box: Box) -> None:
    """`--logo arch2 --logo-color-1 green --logo-color-2 green` moved out of the
    greeting command into the config, so `fastfetch -c <file>` renders it whole."""
    conf = json.loads(SRC.read_text())
    assert conf["logo"] == {"source": "arch2", "color": {"1": "green", "2": "green"}}
    assert conf["display"]["separator"] == " : "


def test_every_format_names_its_variables(box: Box) -> None:
    """Positional `{2}` needs the fastfetch wiki to read; the names are in
    `fastfetch --help <module>-format` (2.68.1)."""
    for module in json.loads(SRC.read_text())["modules"]:
        if isinstance(module, str) or module["type"] == "custom":
            continue
        for placeholder in re.findall(r"\{([^}]*)\}", module.get("format", "")):
            assert not placeholder.isdigit(), f"{module['type']}: positional {{{placeholder}}}"


def test_keys_and_indentation_render_once(box: Box) -> None:
    """A key ending in a space renders the separator with a double gap; a tab
    or an odd indent is invisible until someone edits the file."""
    for n, line in enumerate(SRC.read_text().splitlines(), start=1):
        assert line == line.rstrip(), f"line {n}: trailing whitespace"
        assert "\t" not in line, f"line {n}: tab"
        indent = len(line) - len(line.lstrip(" "))
        assert indent % 2 == 0, f"line {n}: odd indent"
    for module in json.loads(SRC.read_text())["modules"]:
        if isinstance(module, str):
            continue
        assert module.get("key", "x") == module.get("key", "x").rstrip()
