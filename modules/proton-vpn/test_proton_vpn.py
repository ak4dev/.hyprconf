"""modules/proton-vpn: the two packages through the sudo gate, then one guarded line in Omarchy's
autostart.lua that starts the app minimized at login — only once the app is installed, never twice,
put back after Omarchy rewrites the file, Lua that still parses, and removed alone by the undo."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import Box

INSTALL = Path(__file__).parent / "install"
LINE = 'o.launch_on_start("protonvpn-app --start-minimized") -- hyprconf/proton-vpn'
# Omarchy's seed, config/hypr/autostart.lua (4.0.4-1).
SEED = '-- Extra autostart processes.\n-- o.launch_on_start("my-service")\n'
PACKAGES = ["proton-vpn-gtk-app", "proton-vpn-cli"]
GATES = [({"tty": True, "env": {"HYPRCONF_NO_SUDO": "1"}}, "--no-packages"), ({}, "no terminal")]


@pytest.fixture
def vpn(box: Box) -> Box:
    """Omarchy's seed autostart.lua; the packages absent until omarchy-pkg-add installs them."""
    box.stub("omarchy-pkg-present", f'[ -e "{box.tmp}/installed" ]\n')
    box.stub("omarchy-pkg-add", f'touch "{box.tmp}/installed"\n')
    path = box.home / ".config/hypr/autostart.lua"
    path.parent.mkdir(parents=True)
    path.write_text(SEED)
    return box


def autostart(box: Box) -> Path:
    return box.home / ".config/hypr/autostart.lua"


def test_a_first_run_installs_both_packages_and_adds_the_one_line(vpn: Box) -> None:
    proc = vpn.run(INSTALL, tty=True)
    assert proc.returncode == 0, proc.stderr
    assert vpn.calls_of("omarchy-pkg-add") == [["omarchy-pkg-add", *PACKAGES]]
    assert autostart(vpn).read_text() == SEED + LINE + "\n"


@pytest.mark.skipif(shutil.which("luac") is None, reason="luac is not installed")
def test_the_file_still_parses_as_lua(vpn: Box) -> None:
    vpn.run(INSTALL, tty=True)
    assert subprocess.run(["luac", "-p", str(autostart(vpn))]).returncode == 0


def test_a_second_run_writes_nothing_and_a_rewritten_file_gets_the_line_back(vpn: Box) -> None:
    vpn.run(INSTALL, tty=True)
    before = vpn.snapshot()
    vpn.reset()
    proc = vpn.run(INSTALL, tty=True)
    assert proc.returncode == 0 and proc.stdout == ""
    assert set(vpn.commands) == {"omarchy-pkg-present"} and vpn.snapshot() == before
    autostart(vpn).write_text(SEED)  # what `omarchy refresh hyprland` leaves
    vpn.run(INSTALL, tty=True)
    assert autostart(vpn).read_text() == SEED + LINE + "\n"


@pytest.mark.parametrize(("kwargs", "pointer"), GATES)
def test_the_package_step_bows_out_of_sudo_and_no_line_lands(
    vpn: Box, kwargs: dict, pointer: str
) -> None:
    proc = vpn.run(INSTALL, **kwargs)
    assert proc.returncode == 0, proc.stderr
    assert pointer in proc.stdout and "omarchy-pkg-add" not in vpn.commands
    assert autostart(vpn).read_text() == SEED


def test_a_failed_package_install_fails_the_module(vpn: Box) -> None:
    vpn.stub("omarchy-pkg-add", "exit 1\n")
    proc = vpn.run(INSTALL, tty=True)
    assert proc.returncode != 0 and "package install failed" in proc.stderr
    assert autostart(vpn).read_text() == SEED


@pytest.mark.parametrize(
    ("before", "after_undo"),
    [(SEED, SEED), ("", ""), ("-- mine, no newline", "-- mine, no newline\n")],
    ids=["seed", "empty", "no-final-newline"],
)
def test_undo_takes_back_only_the_line(vpn: Box, before: str, after_undo: str) -> None:
    autostart(vpn).write_text(before)
    vpn.run(INSTALL, tty=True)
    assert autostart(vpn).read_text().endswith("\n" + LINE + "\n") or before == ""
    assert vpn.undo("proton-vpn").returncode == 0
    assert autostart(vpn).read_text() == after_undo


def test_undo_on_a_box_that_never_installed_writes_nothing(vpn: Box) -> None:
    before = vpn.snapshot()
    assert vpn.undo("proton-vpn").returncode == 0
    assert vpn.calls == [] and vpn.snapshot() == before
