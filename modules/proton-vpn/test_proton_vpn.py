"""modules/proton-vpn: the two packages through the sudo gate, then one guarded line in Omarchy's
autostart.lua that starts the app minimized at login — only once the app is installed, never twice,
put back after Omarchy rewrites the file, Lua that still parses, and removed alone by the undo — and
the app's Auto connect set once to FASTEST, never re-asserted, taken back by the undo only if unchanged."""

from __future__ import annotations

import json
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
CONFIG = ".config/Proton/VPN/app-config.json"
MARKER = ".local/state/hyprconf/autoconnect-applied"
# The app's own file (proton-vpn-gtk-app 4.18.6) after "On" was typed into its Auto connect field.
REST = {"tray_pinned_servers": [], "start_app_minimized": False}
TYPED_ON = {**REST, "connect_at_app_startup": "ON"}

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")


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


def write_config(box: Box, text: str) -> None:
    (box.home / CONFIG).parent.mkdir(parents=True, exist_ok=True)
    (box.home / CONFIG).write_text(text)


def config(box: Box) -> dict:
    return json.loads((box.home / CONFIG).read_text())


def test_a_first_run_installs_both_packages_and_adds_the_one_line(vpn: Box) -> None:
    proc = vpn.run(INSTALL, tty=True)
    assert proc.returncode == 0, proc.stderr
    assert vpn.calls_of("omarchy-pkg-add") == [["omarchy-pkg-add", *PACKAGES]]
    assert autostart(vpn).read_text() == SEED + LINE + "\n"
    assert config(vpn) == {"connect_at_app_startup": "FASTEST"} and (vpn.home / MARKER).exists()


def test_auto_connect_becomes_fastest_and_the_apps_other_settings_stay(vpn: Box) -> None:
    write_config(vpn, json.dumps(TYPED_ON, indent=4) + "\n")  # "ON": no country, every start failed
    vpn.run(INSTALL, tty=True)
    assert config(vpn) == {**TYPED_ON, "connect_at_app_startup": "FASTEST"}


def test_a_config_that_is_not_json_is_left_alone_and_retried(vpn: Box) -> None:
    write_config(vpn, "{ not json")
    proc = vpn.run(INSTALL, tty=True)
    assert proc.returncode == 0 and "will retry on the next run" in proc.stdout
    assert (vpn.home / CONFIG).read_text() == "{ not json" and not (vpn.home / MARKER).exists()


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
    write_config(vpn, json.dumps({"connect_at_app_startup": "NL#42"}))  # set in the app since
    vpn.run(INSTALL, tty=True)
    assert autostart(vpn).read_text() == SEED + LINE + "\n"
    assert config(vpn) == {"connect_at_app_startup": "NL#42"}


@pytest.mark.parametrize(("kwargs", "pointer"), GATES)
def test_the_package_step_bows_out_of_sudo_and_no_line_lands(
    vpn: Box, kwargs: dict, pointer: str
) -> None:
    proc = vpn.run(INSTALL, **kwargs)
    assert proc.returncode == 0, proc.stderr
    assert pointer in proc.stdout and "omarchy-pkg-add" not in vpn.commands
    assert autostart(vpn).read_text() == SEED and not (vpn.home / CONFIG).exists()


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


@pytest.mark.parametrize(
    ("since", "after_undo"),
    [("FASTEST", REST), ("US", {**REST, "connect_at_app_startup": "US"})],
    ids=["unchanged", "set-in-the-app-since"],
)
def test_undo_takes_back_auto_connect_only_while_it_is_still_hyprconfs(
    vpn: Box, since: str, after_undo: dict
) -> None:
    write_config(vpn, json.dumps(TYPED_ON))
    vpn.run(INSTALL, tty=True)
    write_config(vpn, json.dumps({**REST, "connect_at_app_startup": since}))
    assert vpn.undo("proton-vpn").returncode == 0
    assert config(vpn) == after_undo and not (vpn.home / MARKER).exists()


def test_undo_on_a_box_that_never_installed_writes_nothing(vpn: Box) -> None:
    before = vpn.snapshot()
    assert vpn.undo("proton-vpn").returncode == 0
    assert vpn.calls == [] and vpn.snapshot() == before
