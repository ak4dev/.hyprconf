"""scripts/steam-flatpak: Flathub's Steam, per-user, its sandbox tightened past Flathub's own —
the overrides reset and applied whole on every run, each library native Steam lists that is
mounted (never native Steam's own root), and the NVIDIA GL extension checked on Flathub before
anything is installed. Native Steam is never touched."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import REPO_ROOT, Box, code

SCRIPT = REPO_ROOT / "scripts" / "steam-flatpak"
APP = "com.valvesoftware.Steam"
GL = "org.freedesktop.Platform.GL.nvidia-610-57-04"
# `flatpak remote-ls --runtime --columns=application`: one id a line.
FLATPAK = f"""
[[ $1 == remote-ls ]] && printf '%s\\n' org.freedesktop.Platform {GL}
exit 0
"""
HARDENING = [
    "--nodevice=all",
    "--device=dri",
    "--device=input",
    "--nofilesystem=/mnt",
    "--nofilesystem=/media",
    "--nofilesystem=/run/media",
    "--nofilesystem=xdg-music",
    "--nofilesystem=xdg-pictures",
    "--system-no-talk-name=org.freedesktop.UDisks2",
    "--disallow=bluetooth",
]
REMOTE_ADD = [
    "flatpak",
    "remote-add",
    "--user",
    "--if-not-exists",
    "flathub",
    "https://dl.flathub.org/repo/flathub.flatpakrepo",
]
REMOTE_LS = ["flatpak", "remote-ls", "--user", "--runtime", "--columns=application", "flathub"]
INSTALL = ["flatpak", "install", "--user", "--noninteractive", "--or-update", "flathub", APP]
RESET = ["flatpak", "override", "--user", "--reset", APP]


@pytest.fixture(autouse=True)
def _box(box: Box) -> None:
    """No NVIDIA driver unless a test loads one: the seam never reads the real /sys."""
    box.env["_HYPRCONF_NVIDIA_VERSION"] = str(box.tmp / "sys/module/nvidia/version")
    box.stub("flatpak", FLATPAK)


def load_nvidia(box: Box, version: str) -> None:
    path = Path(box.env["_HYPRCONF_NVIDIA_VERSION"])
    path.parent.mkdir(parents=True)
    path.write_text(f"{version}\n")


def native_libraries(box: Box, *paths: Path) -> None:
    """Native Steam's libraryfolders.vdf: its own root first, as Steam writes it."""
    root = box.home / ".local/share/Steam"
    vdf = root / "steamapps/libraryfolders.vdf"
    vdf.parent.mkdir(parents=True)
    entries = "".join(
        f'\t"{i}"\n\t{{\n\t\t"path"\t\t"{p}"\n\t\t"label"\t\t""\n\t}}\n'
        for i, p in enumerate([root, *paths])
    )
    vdf.write_text(f'"libraryfolders"\n{{\n{entries}}}\n')


def test_a_run_installs_per_user_grants_the_mounted_libraries_and_reruns_the_same(
    box: Box,
) -> None:
    load_nvidia(box, "610.57.04")
    library, unmounted = box.tmp / "ext/SteamLibrary", box.tmp / "media/drive/SteamLibrary"
    library.mkdir(parents=True)
    native_libraries(box, library, unmounted)
    before = box.snapshot()
    first = box.run(SCRIPT)
    assert first.returncode == 0, first.stderr
    assert box.calls_of("omarchy-pkg-add") == [["omarchy-pkg-add", "flatpak"]]
    override = ["flatpak", "override", "--user", APP, *HARDENING, f"--filesystem={library}"]
    assert box.calls_of("flatpak") == [REMOTE_ADD, REMOTE_LS, RESET, override, INSTALL]
    assert f"library {unmounted} is not mounted" in first.stdout
    assert str(library) in first.stdout
    assert box.snapshot() == before, "native Steam and the box are left as they were"
    calls = box.calls
    box.reset()
    assert box.run(SCRIPT).stdout == first.stdout
    assert box.calls == calls


def test_no_gl_extension_for_the_loaded_driver_stops_before_the_install(box: Box) -> None:
    load_nvidia(box, "611.0.1")
    result = box.run(SCRIPT)
    assert result.returncode != 0
    assert "no org.freedesktop.Platform.GL.nvidia-611-0-1" in result.stderr
    assert box.calls_of("flatpak") == [REMOTE_ADD, REMOTE_LS]


def test_with_no_nvidia_driver_and_no_native_steam_the_hardening_still_applies(box: Box) -> None:
    result = box.run(SCRIPT)
    assert result.returncode == 0, result.stderr
    override = ["flatpak", "override", "--user", APP, *HARDENING]
    assert box.calls_of("flatpak") == [REMOTE_ADD, RESET, override, INSTALL]
    assert "none found" in result.stdout


def test_a_rejected_override_stops_before_the_app_exists(box: Box) -> None:
    """Fail closed: an install left on Flathub's own --device=all is the state to avoid."""
    box.stub("flatpak", "[[ $1 == override && $3 != --reset ]] && exit 1\nexit 0\n")
    assert box.run(SCRIPT).returncode != 0
    assert INSTALL not in box.calls_of("flatpak")


def test_a_failed_flatpak_install_stops_before_flathub(box: Box) -> None:
    box.stub("omarchy-pkg-add", "exit 1\n")
    assert box.run(SCRIPT).returncode != 0
    assert box.calls_of("flatpak") == []


def test_refuses_to_run_as_root() -> None:
    """Pinned as text, as install.sh's is (tests/test_core.py): the suite is unprivileged."""
    assert re.search(r"^\(\(EUID\)\) \|\| die", code(SCRIPT.read_text()), re.M)


def test_an_argument_is_refused_before_anything_runs(box: Box) -> None:
    result = box.run(SCRIPT, "--system")
    assert result.returncode != 0 and "takes no arguments" in result.stderr
    assert box.calls == []
