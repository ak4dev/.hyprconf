"""modules/vscode — VS Code through Omarchy's installer, `code` as the default editor."""

from pathlib import Path

import pytest

MODULE = Path(__file__).parent / "install"
MARKER = ".local/state/hyprconf/editor-applied"
LEGACY = ".local/state/hyprconf/defaults-applied"
STATE = ".local/state/omarchy/defaults/editor"

# bin/omarchy-default-editor: no argument reads the state file, else "nvim" (:9-15); an argument writes it (:33-34), then returns the notification's status (:36).
EDITOR = """\
state=${EDITOR_STATE:?}
(($#)) || { { [ -r "$state" ] && cat "$state"; } || echo nvim; exit 0; }
[[ -n ${EDITOR_DEAF:-} ]] || { mkdir -p "${state%/*}"; printf '%s\\n' "$1" > "$state"; }
exit ${EDITOR_SET_STATUS:-0}
"""


def machine(box, *, present: bool, delivers: bool = True) -> None:
    flag = box.tmp / "visual-studio-code-bin"
    box.env |= {"VSCODE_FLAG": str(flag), "EDITOR_STATE": str(box.home / STATE)}
    box.stub("omarchy-pkg-present", 'test -e "${VSCODE_FLAG:?}"\n')  # :6-8 is `pacman -Q`
    box.stub("omarchy-install-editor-vscode", f'touch "{flag}"\n' if delivers else "exit 0\n")
    box.stub("omarchy-default-editor", EDITOR)
    if present:
        flag.touch()


def seeded(box) -> tuple[bool, str, bool]:
    """(the marker is written, the default editor, the setter was called)."""
    editor = (box.home / STATE).read_text().strip() if (box.home / STATE).exists() else "nvim"
    called = any(c[1:] for c in box.calls_of("omarchy-default-editor"))
    return (box.home / MARKER).exists(), editor, called


@pytest.mark.parametrize("delivers", [True, False])
def test_install_reads_the_installer_result_back(box, delivers: bool) -> None:
    """omarchy-install-editor-vscode exits 0 whatever happened (:6,27,29)."""
    machine(box, present=False, delivers=delivers)
    assert (proc := box.run(MODULE, tty=True)).returncode == 0, proc.stderr
    assert "omarchy-install-editor-vscode" in box.commands
    assert box.commands.count("omarchy-pkg-present") >= 2
    assert seeded(box) == ((True, "code", True) if delivers else (False, "nvim", False))
    assert ("omarchy install editor vscode" in proc.stdout) is not delivers


@pytest.mark.parametrize("tty,env", [(True, {"HYPRCONF_NO_SUDO": "1"}), (False, {})])
def test_the_install_half_bows_out_behind_both_gates(box, tty: bool, env: dict) -> None:
    machine(box, present=False)
    proc = box.run(MODULE, tty=tty, env=env)
    assert proc.returncode == 0 and "VS Code" in proc.stdout, proc.stderr
    assert "omarchy-install-editor-vscode" not in box.commands and "sudo" not in box.commands


def test_the_editor_marker_is_set_once_and_the_legacy_marker_counts(box) -> None:
    """A --no-packages run on a box that has VS Code still seeds — once, off the value read back."""
    machine(box, present=True)
    assert box.run(MODULE, env={"HYPRCONF_NO_SUDO": "1", "EDITOR_SET_STATUS": "1"}).returncode == 0
    assert "omarchy-install-editor-vscode" not in box.commands
    assert seeded(box) == (True, "code", True)
    (box.home / MARKER).unlink()
    (box.home / STATE).write_text("helix\n")  # a pick of the user's, from before the split
    (box.home / LEGACY).touch()
    box.reset()
    assert box.run(MODULE, tty=True).returncode == 0
    assert seeded(box) == (True, "helix", False)


def test_the_marker_waits_for_the_value_to_land(box) -> None:
    machine(box, present=True)
    proc = box.run(MODULE, tty=True, env={"EDITOR_DEAF": "1"})
    assert proc.returncode == 0 and "omarchy default editor code" in proc.stdout, proc.stderr
    assert seeded(box) == (False, "nvim", True)
    assert box.run(MODULE, tty=True).returncode == 0
    assert seeded(box) == (True, "code", True)


def test_a_second_run_writes_nothing_and_calls_nothing_that_mutates(box) -> None:
    machine(box, present=True)
    assert box.run(MODULE, tty=True).returncode == 0
    before = {p: p.read_bytes() for p in box.files()}
    box.reset()
    assert (proc := box.run(MODULE, tty=True)).returncode == 0, proc.stderr
    assert {p: p.read_bytes() for p in box.files()} == before
    assert box.commands == ["omarchy-pkg-present"] and proc.stdout == ""


def test_undo_restores_the_stock_editor_and_keeps_a_later_pick(box) -> None:
    """Stock is Omarchy's own fallback, nvim (bin/omarchy-default-editor:14)."""
    machine(box, present=True)
    box.run(MODULE, tty=True)
    (box.home / LEGACY).touch()
    box.reset()
    assert box.undo("vscode").returncode == 0
    assert seeded(box) == (False, "nvim", True) and (box.home / LEGACY).exists()
    (box.home / STATE).write_text("helix\n")  # a pick made after the install
    box.reset()
    assert box.undo("vscode").returncode == 0 and seeded(box) == (False, "helix", False)
