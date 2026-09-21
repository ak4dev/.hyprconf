"""modules/keychron — the root write of one udev rule, the gates around it, the undo."""

import re
from pathlib import Path

import pytest

from conftest import SUDO_RUNS, Box

INSTALL, RULE = (Path(__file__).parent / f for f in ("install", "70-keychron.rules"))
VENDOR_LINE = re.compile(r'SUBSYSTEM=="hidraw", ATTRS\{idVendor\}=="(\w+)", TAG\+="uaccess"')
NO_SUDO = {"HYPRCONF_NO_SUDO": "1"}
GATES = [({"tty": False}, "no terminal for sudo"), ({"env": NO_SUDO}, "--no-packages")]


def installed(box: Box) -> Path:
    return box.etc / "udev" / "rules.d" / "70-keychron.rules"


def run(box: Box, *args: str, tty: bool = True, env: dict | None = None):
    proc = box.run(INSTALL, *args, tty=tty, env=env)
    assert proc.returncode == 0, proc.stderr
    return proc


def test_rule_is_installed_through_sudo_and_applied_to_connected_devices(box: Box) -> None:
    box.stub("sudo", SUDO_RUNS)
    run(box)
    dst = installed(box)
    assert dst.read_bytes() == RULE.read_bytes()
    assert dst.stat().st_mode & 0o777 == 0o644, "install -Dm644"
    assert ["sudo", "install", "-Dm644", "--", str(RULE), str(dst)] in box.calls_of("sudo")
    assert ["udevadm", "control", "--reload-rules"] in box.calls_of("udevadm")
    assert ["udevadm", "trigger", "--subsystem-match=hidraw"] in box.calls_of("udevadm")


def test_a_second_run_writes_nothing_and_asks_for_no_sudo(box: Box) -> None:
    box.stub("sudo", SUDO_RUNS)
    run(box)
    before = box.snapshot()
    box.reset()
    run(box)
    assert box.commands == [], box.calls
    assert box.snapshot() == before
    assert box.files() == set(), "the module writes nothing into $HOME"


def test_a_hand_edited_rule_is_repaired(box: Box) -> None:
    box.stub("sudo", SUDO_RUNS)
    run(box)
    installed(box).write_text("# hand-edited\n")
    box.reset()
    run(box)
    assert installed(box).read_bytes() == RULE.read_bytes()


@pytest.mark.parametrize(("kw", "pointer"), GATES)
def test_without_a_password_prompt_it_says_so_and_touches_nothing(box, kw, pointer) -> None:
    assert pointer in run(box, **kw).stdout
    assert box.commands == [], box.calls
    assert not installed(box).exists()


def test_a_refused_sudo_is_a_warning_not_a_failure(box: Box) -> None:
    box.stub("sudo", "exit 1\n")
    assert "could not install" in run(box).stdout
    assert not installed(box).exists()
    assert box.calls_of("udevadm") == []


def test_undo_removes_the_rule_and_reloads_then_is_a_silent_no_op(box: Box) -> None:
    box.stub("sudo", SUDO_RUNS)
    run(box)
    dst = installed(box)
    box.reset()
    run(box, "undo")
    assert not dst.exists()
    assert ["sudo", "rm", "-f", "--", str(dst)] in box.calls_of("sudo")
    assert box.calls_of("udevadm") == [["udevadm", "control", "--reload-rules"]], "no trigger"
    box.reset()
    run(box, "undo")
    assert box.commands == [], box.calls


@pytest.mark.parametrize(("kw", "pointer"), GATES)
def test_undo_behind_a_gate_points_at_undo_and_leaves_the_rule(box, kw, pointer) -> None:
    box.stub("sudo", SUDO_RUNS)
    run(box)
    box.reset()
    out = run(box, "undo", **kw).stdout
    assert pointer in out and "install undo`" in out
    assert box.commands == [], box.calls
    assert installed(box).exists()


def test_rule_sorts_before_seat_late_matches_vendor_only_and_sets_no_mode() -> None:
    assert int(RULE.name.split("-", 1)[0]) < 73, "must sort before 73-seat-late.rules"
    rules = [ln for ln in RULE.read_text().splitlines() if ln and not ln.startswith("#")]
    # fullmatch is the whole shape (no MODE=, GROUP=, idProduct); the set is rule 8's pin — a new vendor moves it.
    assert [m and m[1] for m in map(VENDOR_LINE.fullmatch, rules)] == ["3434", "362d"]
