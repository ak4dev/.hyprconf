"""modules/boot-text — the root write of one Limine drop-in, the rebuild after it, the gates, the undo."""

from pathlib import Path

import pytest

from conftest import SUDO_RUNS, Box

INSTALL, DROPIN = (Path(__file__).parent / f for f in ("install", "zz-hyprconf-boot-text.conf"))
NO_SUDO = {"HYPRCONF_NO_SUDO": "1"}
GATES = [({"tty": False}, "no terminal for sudo"), ({"env": NO_SUDO}, "--no-packages")]
# limine-mkinitcpio-install's error_msg when a build fails, which still exits 0 (:230, :315).
BUILD_FAILED = "echo 'ERROR: mkinitcpio failed for kernel 7.2.15-1-omarchy, skipping.'\n"


def installed(box: Box) -> Path:
    return box.etc / "limine-entry-tool.d" / DROPIN.name


def run(box: Box, *args: str, tty: bool = True, env: dict | None = None):
    proc = box.run(INSTALL, *args, tty=tty, env=env)
    assert proc.returncode == 0, proc.stderr
    return proc


def test_drop_in_is_installed_through_sudo_and_the_boot_images_rebuilt(box: Box) -> None:
    box.stub("sudo", SUDO_RUNS)
    out = run(box).stdout
    dst = installed(box)
    assert dst.read_bytes() == DROPIN.read_bytes()
    assert dst.stat().st_mode & 0o777 == 0o644, "install -Dm644"
    assert ["sudo", "install", "-Dm644", "--", str(DROPIN), str(dst)] in box.calls_of("sudo")
    assert box.calls_of("limine-mkinitcpio") == [["limine-mkinitcpio"]]
    assert "boot images rebuilt" in out


def test_a_second_run_writes_nothing_and_asks_for_no_sudo(box: Box) -> None:
    box.stub("sudo", SUDO_RUNS)
    run(box)
    before = box.snapshot()
    box.reset()
    run(box)
    assert box.commands == [], box.calls
    assert box.snapshot() == before
    assert box.files() == set(), "the module writes nothing into $HOME"


def test_a_hand_edited_drop_in_is_repaired_and_rebuilt(box: Box) -> None:
    box.stub("sudo", SUDO_RUNS)
    run(box)
    installed(box).write_text("# hand-edited\n")
    box.reset()
    run(box)
    assert installed(box).read_bytes() == DROPIN.read_bytes()
    assert box.calls_of("limine-mkinitcpio") == [["limine-mkinitcpio"]]


@pytest.mark.parametrize(("kw", "pointer"), GATES)
def test_without_a_password_prompt_it_says_so_and_touches_nothing(box, kw, pointer) -> None:
    assert pointer in run(box, **kw).stdout
    assert box.commands == ["omarchy-cmd-present"], box.calls
    assert not installed(box).exists()


def test_a_box_that_does_not_boot_through_limine_is_skipped(box: Box) -> None:
    box.stub("omarchy-cmd-present", "exit 1\n")
    assert "does not boot through Limine" in run(box).stdout
    assert box.commands == ["omarchy-cmd-present"], box.calls
    assert not installed(box).exists()


def test_a_refused_sudo_is_a_warning_not_a_failure(box: Box) -> None:
    box.stub("sudo", "exit 1\n")
    assert "could not install" in run(box).stdout
    assert not installed(box).exists()
    assert box.calls_of("limine-mkinitcpio") == []


@pytest.mark.parametrize("body", [BUILD_FAILED, "exit 1\n"], ids=["error-line", "exit-status"])
def test_a_failed_rebuild_says_how_to_finish_it(box: Box, body: str) -> None:
    box.stub("sudo", SUDO_RUNS)
    box.stub("limine-mkinitcpio", body)
    out = run(box).stdout
    assert "not rebuilt" in out and "sudo limine-mkinitcpio" in out
    assert "boot images rebuilt" not in out


def test_undo_removes_the_drop_in_and_rebuilds_then_is_a_silent_no_op(box: Box) -> None:
    box.stub("sudo", SUDO_RUNS)
    run(box)
    dst = installed(box)
    box.reset()
    run(box, "undo")
    assert not dst.exists()
    assert ["sudo", "rm", "-f", "--", str(dst)] in box.calls_of("sudo")
    assert box.calls_of("limine-mkinitcpio") == [["limine-mkinitcpio"]]
    box.reset()
    run(box, "undo")
    assert box.commands == [], box.calls


@pytest.mark.parametrize(("kw", "pointer"), GATES)
def test_undo_behind_a_gate_points_at_undo_and_leaves_the_drop_in(box, kw, pointer) -> None:
    box.stub("sudo", SUDO_RUNS)
    run(box)
    box.reset()
    out = run(box, "undo", **kw).stdout
    assert pointer in out and "install undo`" in out
    assert box.commands == [], box.calls
    assert installed(box).exists()


def test_drop_in_only_appends_the_three_parameters_and_sorts_after_omarchys() -> None:
    # The whole of the root surface's content, rule 8's pin: a new parameter moves it here.
    lines = [ln for ln in DROPIN.read_text().splitlines() if ln and not ln.startswith("#")]
    assert lines == [
        'KERNEL_CMDLINE[default]+=" splash=verbose loglevel=4 systemd.show_status=true"'
    ]
    assert DROPIN.name > "omarchy-defaults.conf", "a later value wins only from a later file"
