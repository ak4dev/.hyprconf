"""modules/keychron — the udev rule that makes Keychron / Lemokey boards reachable.

The module's whole job is one file outside $HOME, so the tests are about the
root write and the gates around it: it lands only when the bytes differ, only
with a password prompt to answer, always through `sudo install -Dm644 --`,
and it repairs a hand-edited copy (nothing else can catch that — a $HOME
byte-stability probe never looks at /etc).

HERMETIC: the `box` fixture (conftest.py) only. `sudo` and `udevadm` are
recording fakes there; the tests that need the write to really happen give
`sudo` a body that execs its arguments, into the box's own /etc.
"""

from __future__ import annotations

import re
from pathlib import Path

from conftest import Box

REPO_ROOT = Path(__file__).parent.parent.parent
MODULE = REPO_ROOT / "modules" / "keychron"
INSTALL = MODULE / "install"
RULE = MODULE / "70-keychron.rules"


def rules_dir(box: Box) -> Path:
    """Where the box's udev rules live — the _HYPRCONF_UDEV_RULES seam."""
    return box.etc / "udev" / "rules.d"


def run(box: Box, *args: str, tty: bool = True, env: dict[str, str] | None = None):
    child = {"_HYPRCONF_UDEV_RULES": str(rules_dir(box)), **(env or {})}
    return box.run(INSTALL, *args, tty=tty, env=child)


def real_sudo(box: Box) -> None:
    """A sudo that records and then runs what it was handed, so `install` and
    `rm` really touch the box's /etc."""
    box.stub("sudo", 'exec "$@"\n')


def installed(box: Box) -> Path:
    return rules_dir(box) / "70-keychron.rules"


# ------------------------------------------------------------------ installing


def test_rule_is_installed_through_sudo_and_applied_to_connected_devices(box: Box) -> None:
    """The shipped rule lands byte-for-byte at 0644, then udev is reloaded AND
    retriggered — without the trigger the ACL would arrive only on the next
    re-plug."""
    real_sudo(box)
    proc = run(box)
    assert proc.returncode == 0, proc.stderr

    assert installed(box).read_bytes() == RULE.read_bytes()
    assert installed(box).stat().st_mode & 0o777 == 0o644, "install -Dm644"
    assert ["sudo", "install", "-Dm644", "--", str(RULE), str(installed(box))] in box.calls_of(
        "sudo"
    )
    assert ["udevadm", "control", "--reload-rules"] in box.calls_of("udevadm")
    assert ["udevadm", "trigger", "--subsystem-match=hidraw"] in box.calls_of("udevadm")


def test_a_second_run_writes_nothing_and_asks_for_no_sudo(box: Box) -> None:
    """Byte-stable: a matching rule is compared and the run ends before the
    sudo gate — nothing under $HOME either, ever."""
    real_sudo(box)
    run(box)
    before = (installed(box).stat().st_mtime_ns, installed(box).read_bytes())
    box.reset()

    proc = run(box)
    assert proc.returncode == 0, proc.stderr
    assert box.commands == [], box.calls
    assert (installed(box).stat().st_mtime_ns, installed(box).read_bytes()) == before
    assert box.files() == set(), "the module writes nothing into $HOME"


def test_a_hand_edited_rule_is_repaired(box: Box) -> None:
    """Drift repair: the comparison is of bytes, not of existence."""
    real_sudo(box)
    run(box)
    installed(box).write_text("# hand-edited\n")
    box.reset()

    proc = run(box)
    assert proc.returncode == 0, proc.stderr
    assert installed(box).read_bytes() == RULE.read_bytes()
    assert "sudo" in box.commands


# ------------------------------------------------------------------- the gates


def test_without_a_terminal_it_says_so_and_touches_nothing(box: Box) -> None:
    """The post-update hook runs non-interactively inside omarchy-update, where
    a sudo password prompt would stall the whole update."""
    proc = run(box, tty=False)
    assert proc.returncode == 0, proc.stderr
    assert "no terminal for sudo" in proc.stdout
    assert box.commands == [], box.calls
    assert not installed(box).exists()


def test_no_packages_skips_the_root_write(box: Box) -> None:
    """HYPRCONF_NO_SUDO — what `--no-packages` exports, and the hook passes."""
    proc = run(box, env={"HYPRCONF_NO_SUDO": "1"})
    assert proc.returncode == 0, proc.stderr
    assert "--no-packages" in proc.stdout
    assert box.commands == [], box.calls
    assert not installed(box).exists()


def test_a_refused_sudo_is_a_warning_not_a_failure(box: Box) -> None:
    """The module never fails the loop: a declined password leaves the run at 0
    with the rule simply not installed."""
    box.stub("sudo", "exit 1\n")
    proc = run(box)
    assert proc.returncode == 0, proc.stderr
    assert "could not install" in proc.stdout
    assert not installed(box).exists()
    assert box.calls_of("udevadm") == []


# ------------------------------------------------------------------------ undo


def test_undo_removes_the_rule_and_reloads(box: Box) -> None:
    real_sudo(box)
    run(box)
    box.reset()

    proc = box.run(INSTALL, "undo", tty=True, env={"_HYPRCONF_UDEV_RULES": str(rules_dir(box))})
    assert proc.returncode == 0, proc.stderr
    assert not installed(box).exists()
    assert ["sudo", "rm", "-f", "--", str(installed(box))] in box.calls_of("sudo")
    assert ["udevadm", "control", "--reload-rules"] in box.calls_of("udevadm")
    # No trigger: 73-seat-late.rules only ever adds an ACL, so one already
    # granted lasts until the board is re-plugged or the session ends.
    assert not [c for c in box.calls_of("udevadm") if c[1:2] == ["trigger"]]


def test_undo_with_nothing_installed_is_a_silent_exit_zero(box: Box) -> None:
    proc = box.run(INSTALL, "undo", tty=True, env={"_HYPRCONF_UDEV_RULES": str(rules_dir(box))})
    assert proc.returncode == 0, proc.stderr
    assert box.commands == [], box.calls


def test_undo_without_a_terminal_leaves_the_rule_alone(box: Box) -> None:
    real_sudo(box)
    run(box)
    box.reset()

    proc = box.run(INSTALL, "undo", env={"_HYPRCONF_UDEV_RULES": str(rules_dir(box))})
    assert proc.returncode == 0, proc.stderr
    assert installed(box).exists()
    assert box.commands == [], box.calls


# ------------------------------------------------------------------ the payload


def test_rule_sorts_before_seat_late_matches_vendor_only_and_sets_no_mode() -> None:
    """The three properties the rule is worthless without — see README.md."""
    assert int(RULE.name.split("-", 1)[0]) < 73, "must sort before 73-seat-late.rules"
    rules = [ln for ln in RULE.read_text().splitlines() if ln and not ln.startswith("#")]
    assert rules
    for rule in rules:
        assert re.fullmatch(r'SUBSYSTEM=="hidraw", ATTRS\{idVendor\}=="\w+", TAG\+="uaccess"', rule)
    for forbidden in ("MODE=", "GROUP=", "idProduct"):
        assert forbidden not in "\n".join(rules), forbidden


def test_every_root_call_carries_the_end_of_options_marker() -> None:
    """AGENTS.md rule 8: a path handed to a root coreutils call is never
    readable as an option. `sudo udevadm …` takes no path, hence the exemption
    for it alone."""
    root_calls = [
        ln.strip()
        for ln in INSTALL.read_text().splitlines()
        if re.search(r"(?:^|;|&&|\|\||\bif )\s*sudo\s", ln) and not ln.lstrip().startswith("#")
    ]
    assert root_calls
    for call in root_calls:
        assert " udevadm " in call or " -- " in call, call
