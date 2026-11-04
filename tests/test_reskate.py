"""scripts/reskate: ReSkate's pinned release unpacked into ReSkate/ at the root of whichever Steam
library holds skate. — only once its sha256 matches, never over an install its own launcher keeps
updated, never at a path the launch option cannot carry — its download dir always cleaned up, a
missing tool named before anything is fetched, and the launch option printed, never written."""

from __future__ import annotations

import hashlib
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from conftest import REPO_ROOT, Box, code

SCRIPT = REPO_ROOT / "scripts" / "reskate"
PINNED = re.search(r"^sha256=([0-9a-f]{64})$", SCRIPT.read_text(), re.M).group(1)
URL = "https://github.com/Dingo-Shenanigans/ReSkate/releases/download/v2.1.4-2/ReSkate-2.1.4-2.zip"
LAUNCH = """bash -c 'exec "${{@/*EAAntiCheat.GameServiceLauncher.exe/{}/ReSkateLauncher.exe}}"' -- %command%"""
FILES = ["ReSkateLauncher.exe", "ReSkate.dll", "launcher.json", "LICENSE.txt", "licenses/zstd.txt"]
# `curl … -o <file> <url>`: the release zip from $ZIP.
CURL = 'while (($#)); do [[ $1 == -o ]] && { cp "$ZIP" "$2"; exit 0; }; shift; done; exit 1\n'
STEAMS = {
    "flatpak": ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    "native": ".local/share/Steam",
}
LIBRARY = "ext/Steam Library"  # a space, which the launch option carries


@pytest.fixture
def zipped(box: Box) -> Path:
    """A release zip with the real one's names, served by the curl fake; mktemp lands in the box."""
    path = box.tmp / "ReSkate.zip"
    with zipfile.ZipFile(path, "w") as z:
        for name in FILES:
            z.writestr(name, name)
    box.stub("curl", CURL)
    (box.tmp / "t").mkdir()
    box.env.update({"ZIP": str(path), "TMPDIR": str(box.tmp / "t")})
    return path


def skate(box: Box, steam: str = "flatpak", library: str = LIBRARY) -> Path:
    """skate. installed in a second library, which `steam`'s libraryfolders.vdf lists."""
    lib = box.tmp / library
    game = lib / "steamapps/common/Skate"
    game.mkdir(parents=True)
    (game / "Skate.exe").write_text("game")
    (lib / "steamapps/appmanifest_3354750.acf").write_text(
        '"AppState"\n{\n\t"installdir"\t\t"Skate"\n\t"buildid"\t\t"25414733"\n}\n'
    )
    root = box.home / STEAMS[steam]
    vdf = root / "steamapps/libraryfolders.vdf"
    vdf.parent.mkdir(parents=True)
    paths = "".join(
        f'\t"{i}"\n\t{{\n\t\t"path"\t\t"{p}"\n\t}}\n' for i, p in enumerate([root, lib])
    )
    vdf.write_text(f'"libraryfolders"\n{{\n{paths}}}\n')
    return game


def pinned_to(box: Box, zipped: Path) -> Path:
    """The script, its pin moved to this zip's digest."""
    copy = box.tmp / "reskate"
    digest = hashlib.sha256(zipped.read_bytes()).hexdigest()
    copy.write_text(SCRIPT.read_text().replace(PINNED, digest))
    return copy


@pytest.mark.parametrize("steam", list(STEAMS))
def test_the_release_is_unpacked_in_a_folder_of_its_own(box: Box, zipped: Path, steam: str) -> None:
    """Never under steamapps/common, where the launcher closes; Steam's skate. folder untouched."""
    game, reskate = skate(box, steam), box.tmp / LIBRARY / "ReSkate"
    result = box.run(pinned_to(box, zipped))
    assert result.returncode == 0, result.stderr
    assert all((reskate / name).read_text() == name for name in FILES)
    assert sorted(p.name for p in game.iterdir()) == ["Skate.exe"]
    ((_, *flags, out, url),) = box.calls_of("curl")
    assert flags == ["-fsSL", "--proto", "=https", "--proto-redir", "=https", "-o"]
    assert url == URL and not any((box.tmp / "t").iterdir()), "the download dir is cleaned up"
    assert f"ReSkate 2.1.4-2 is in {reskate}" in result.stdout
    assert LAUNCH.format(reskate) in result.stdout and "before 2.1" not in result.stdout


def test_a_zip_that_misses_its_pin_is_never_unpacked(box: Box, zipped: Path) -> None:
    game = skate(box)
    result = box.run(SCRIPT)
    assert result.returncode != 0 and "does not match its pinned sha256" in result.stderr
    assert not (box.tmp / LIBRARY / "ReSkate").exists()
    assert sorted(p.name for p in game.iterdir()) == ["Skate.exe"]
    assert not any((box.tmp / "t").iterdir())


def test_an_installed_reskate_is_left_to_its_own_updater(box: Box, zipped: Path) -> None:
    skate(box)
    reskate = box.tmp / LIBRARY / "ReSkate"
    reskate.mkdir()
    (reskate / "ReSkateLauncher.exe").write_text("updated by itself")
    result = box.run(pinned_to(box, zipped))
    assert result.returncode == 0, result.stderr
    assert box.calls_of("curl") == [] and "already in" in result.stdout
    assert [p.name for p in reskate.iterdir()] == ["ReSkateLauncher.exe"]
    assert (reskate / "ReSkateLauncher.exe").read_text() == "updated by itself"
    assert LAUNCH.format(reskate) in result.stdout


def test_a_reskate_left_beside_skate_exe_is_named_never_moved(box: Box, zipped: Path) -> None:
    """Before 2.1 it went beside Skate.exe, where its launcher now closes: the way out is printed."""
    game = skate(box)
    (game / "Mods").mkdir()
    (game / "ReSkateLauncher.exe").write_text("closes here")
    result = box.run(pinned_to(box, zipped))
    assert result.returncode == 0, result.stderr
    assert (box.tmp / LIBRARY / "ReSkate/ReSkateLauncher.exe").read_text() == "ReSkateLauncher.exe"
    assert sorted(p.name for p in game.iterdir()) == ["Mods", "ReSkateLauncher.exe", "Skate.exe"]
    assert (
        "before 2.1 is still beside Skate.exe" in result.stdout
        and f"\n     {game}\n" in result.stdout
    )


@pytest.mark.parametrize("library", ["ext/Games & Co", "ext/Jeux Vidéo", "ext/it's", "ext/$HOME"])
def test_a_path_the_launch_option_cannot_carry_stops_before_the_download(
    box: Box, zipped: Path, library: str
) -> None:
    """bash 5.2+ reads a & in the replacement as the match; quotes and $ end or expand it."""
    skate(box, library=library)
    result = box.run(pinned_to(box, zipped))
    assert result.returncode != 0 and "the launch option can carry only" in result.stderr
    assert box.calls_of("curl") == [] and not (box.tmp / library / "ReSkate").exists()


def test_no_skate_install_stops_before_the_download(box: Box, zipped: Path) -> None:
    result = box.run(pinned_to(box, zipped))
    assert result.returncode != 0 and "no skate. found" in result.stderr
    assert box.calls_of("curl") == []


def test_a_missing_tool_is_named_before_anything_is_fetched(box: Box, zipped: Path) -> None:
    """Off Arch, libarchive's bsdtar may be missing: named before the download."""
    skate(box)
    bare = box.tmp / "bare"
    bare.mkdir()
    for tool in ("bash", "sha256sum"):
        (bare / tool).symlink_to(shutil.which(tool))
    (bare / "curl").symlink_to(box.bins / "curl")
    result = box.run(pinned_to(box, zipped), env={"PATH": str(bare)})
    assert result.returncode != 0 and "needs bsdtar" in result.stderr
    assert box.calls_of("curl") == []


def test_refuses_to_run_as_root() -> None:
    """Pinned as text, as install.sh's is (tests/test_core.py): the suite is unprivileged."""
    assert re.search(r"^\(\(EUID\)\) \|\| die", code(SCRIPT.read_text()), re.M)
