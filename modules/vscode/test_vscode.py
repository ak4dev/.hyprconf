"""modules/vscode — VS Code through Omarchy's installer, `code` as the default editor.

Every Omarchy command is a recording fake from the root conftest's `box`; the
two that have to answer (`omarchy-pkg-present`, `omarchy-default-editor`) are
modelled here in the shape the real ones have on Omarchy 4.0.3-1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MODULE = Path(__file__).parent / "install"

# bin/omarchy-default-editor: no argument reads ~/.local/state/omarchy/defaults/
# editor and falls back to "nvim" (:9-15); an argument writes the file (:33-34)
# and the LAST thing the script runs is omarchy-notification-send (:36), whose
# status is the script's — so a TTY or SSH run exits non-zero with the value
# already on disk. $EDITOR_SET_STATUS models exactly that.
EDITOR = """\
state=${EDITOR_STATE:?}
if (($# == 0)); then { [ -r "$state" ] && cat "$state"; } || echo nvim; exit 0; fi
mkdir -p "$(dirname "$state")"
printf '%s\\n' "$1" > "$state"
exit ${EDITOR_SET_STATUS:-0}
"""
# The same setter with a live session to notify but nothing written — the
# failure the marker has to wait for.
EDITOR_DEAF = """\
state=${EDITOR_STATE:?}
if (($# == 0)); then { [ -r "$state" ] && cat "$state"; } || echo nvim; exit 0; fi
exit 0
"""
# bin/omarchy-pkg-present:6-8 is `pacman -Q` per name: present iff the flag file
# the installer stub touches is there.
PKG_PRESENT = 'test -e "${VSCODE_FLAG:?}"\n'


def machine(box, *, present: bool, delivers: bool = True, editor: str = EDITOR):
    """A box with VS Code present or absent, an installer that does or does not
    deliver the package, and a default-editor state file."""
    flag = box.tmp / "visual-studio-code-bin"
    box.env["VSCODE_FLAG"] = str(flag)
    box.env["EDITOR_STATE"] = str(box.home / ".local/state/omarchy/defaults/editor")
    if present:
        flag.touch()
    box.stub("omarchy-pkg-present", PKG_PRESENT)
    box.stub("omarchy-install-editor-vscode", f'touch "{flag}"\n' if delivers else "exit 0\n")
    box.stub("omarchy-default-editor", editor)
    return box


def marker(box) -> Path:
    return box.home / ".local/state/hyprconf/editor-applied"


def default_editor(box) -> str:
    state = Path(box.env["EDITOR_STATE"])
    return state.read_text().strip() if state.exists() else "nvim"


def snapshot(box) -> dict:
    return {p: p.read_bytes() for p in box.files()}


# -- the package --------------------------------------------------------------


def test_absent_vscode_goes_through_omarchys_installer_and_is_read_back(box) -> None:
    """omarchy-install-editor-vscode exits 0 whatever happened (no `set -e`,
    unguarded omarchy-pkg-add, backgrounded launch), so the result is read back
    with omarchy-pkg-present rather than taken from its status."""
    machine(box, present=False)
    proc = box.run(MODULE, tty=True)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-install-editor-vscode" in box.commands
    assert box.commands.count("omarchy-pkg-present") >= 2  # asked again afterwards
    assert default_editor(box) == "code"


def test_present_vscode_is_never_reinstalled(box) -> None:
    machine(box, present=True)
    assert box.run(MODULE, tty=True).returncode == 0
    assert "omarchy-install-editor-vscode" not in box.commands


def test_an_installer_that_did_not_deliver_warns_with_omarchys_retry(box) -> None:
    """A conflict (Arch's `code`) fails inside omarchy-pkg-add and the installer
    carries on to exit 0: the run says how to retry and does not fail."""
    machine(box, present=False, delivers=False)
    proc = box.run(MODULE, tty=True)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy install editor vscode" in proc.stdout
    assert not marker(box).exists()  # no package, no editor default either


def test_nothing_removes_a_package_or_reaches_pacman(box) -> None:
    machine(box, present=False)
    box.run(MODULE, tty=True)
    assert "pacman" not in box.commands
    assert not any(c.startswith("omarchy-pkg-drop") for c in box.calls)
    assert not any(c.startswith("omarchy-pkg-add") for c in box.calls)
    code = [ln for ln in MODULE.read_text().splitlines() if not ln.lstrip().startswith("#")]
    for forbidden in ("pacman", "yay", "paru", "makepkg", "omarchy-pkg-drop", "omarchy-pkg-aur"):
        assert not any(forbidden in ln for ln in code), forbidden


# -- the sudo gates -----------------------------------------------------------


@pytest.mark.parametrize("gate", ["no-sudo", "no-tty"])
def test_the_install_half_bows_out_behind_both_gates(box, gate: str) -> None:
    """--no-packages (the post-update hook's flag) and a run with no terminal
    for the password prompt: a pointer line, exit 0, no installer."""
    machine(box, present=False)
    env = {"HYPRCONF_NO_SUDO": "1"} if gate == "no-sudo" else {}
    proc = box.run(MODULE, tty=(gate == "no-sudo"), env=env)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-install-editor-vscode" not in box.commands
    assert "VS Code" in proc.stdout


def test_the_editor_default_is_not_seeded_while_vscode_is_absent(box) -> None:
    """A --no-packages first run must never point the editor at a VS Code that
    is not installed; the next run with a terminal seeds it."""
    machine(box, present=False)
    assert box.run(MODULE, tty=True, env={"HYPRCONF_NO_SUDO": "1"}).returncode == 0
    assert not any(c[1:] for c in box.calls_of("omarchy-default-editor"))
    assert not marker(box).exists()

    box.reset()
    assert box.run(MODULE, tty=True).returncode == 0
    assert default_editor(box) == "code"
    assert marker(box).exists()


# -- the editor default, set once ---------------------------------------------


def test_editor_is_seeded_once_on_the_value_read_back_not_the_setters_status(box) -> None:
    """The setter's exit status is its closing notification's: a TTY run seeds
    the value and still exits 1. Trusting it left the marker unwritten on
    exactly the runs that had succeeded, and the next run re-asserted `code`
    over an editor chosen in between."""
    machine(box, present=True)
    proc = box.run(MODULE, tty=True, env={"EDITOR_SET_STATUS": "1"})
    assert proc.returncode == 0, proc.stderr
    assert default_editor(box) == "code"
    assert marker(box).exists()

    Path(box.env["EDITOR_STATE"]).write_text("helix\n")  # the user's later pick
    box.reset()
    assert box.run(MODULE, tty=True).returncode == 0
    assert not any(c[1:] for c in box.calls_of("omarchy-default-editor"))
    assert default_editor(box) == "helix"


def test_the_marker_waits_for_the_value_to_land(box) -> None:
    """A setter that records the call and leaves the default where it was: no
    marker, a pointer line, and the next run tries again."""
    machine(box, present=True, editor=EDITOR_DEAF)
    proc = box.run(MODULE, tty=True)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy default editor code" in proc.stdout
    assert not marker(box).exists()

    box.stub("omarchy-default-editor", EDITOR)
    box.reset()
    box.run(MODULE, tty=True)
    assert marker(box).exists()
    assert default_editor(box) == "code"


def test_the_pre_module_defaults_marker_counts_as_applied(box) -> None:
    """~/.local/state/hyprconf/defaults-applied is the one marker the browser
    and the editor shared before the split: honoured for one release, and left
    on disk because the browser module reads it too."""
    machine(box, present=True)
    legacy = box.home / ".local/state/hyprconf/defaults-applied"
    legacy.parent.mkdir(parents=True)
    legacy.touch()
    assert box.run(MODULE, tty=True).returncode == 0
    assert not any(c[1:] for c in box.calls_of("omarchy-default-editor"))
    assert default_editor(box) == "nvim"
    assert marker(box).exists() and legacy.exists()


# -- idempotence and undo -----------------------------------------------------


def test_a_second_run_writes_nothing_and_calls_nothing_that_mutates(box) -> None:
    machine(box, present=True)
    assert box.run(MODULE, tty=True).returncode == 0
    before = snapshot(box)

    box.reset()
    proc = box.run(MODULE, tty=True)
    assert proc.returncode == 0, proc.stderr
    assert snapshot(box) == before
    assert box.commands == ["omarchy-pkg-present"]


def test_undo_puts_the_stock_editor_back_and_leaves_the_package(box) -> None:
    """Stock is Omarchy's own fallback, nvim (bin/omarchy-default-editor:14).
    Nothing is uninstalled — no removals, ever."""
    machine(box, present=True)
    box.run(MODULE, tty=True)
    box.reset()

    proc = box.undo("vscode")
    assert proc.returncode == 0, proc.stderr
    assert default_editor(box) == "nvim"
    assert not marker(box).exists()
    assert not any(c.startswith("omarchy-pkg-drop") for c in box.calls)
    assert "omarchy-install-editor-vscode" not in box.commands


def test_undo_leaves_an_editor_chosen_after_the_install_alone(box) -> None:
    machine(box, present=True)
    box.run(MODULE, tty=True)
    Path(box.env["EDITOR_STATE"]).write_text("helix\n")
    box.reset()

    assert box.undo("vscode").returncode == 0
    assert default_editor(box) == "helix"
    assert not any(c[1:] for c in box.calls_of("omarchy-default-editor"))
    assert not marker(box).exists()


def test_undo_on_a_box_that_never_ran_the_module_is_a_no_op(box) -> None:
    machine(box, present=False)
    proc = box.undo("vscode")
    assert proc.returncode == 0, proc.stderr
    assert box.files() == set()
