"""modules/themes — the dracula user theme (linked, never activated) and the wallpapers beside it."""

import os
import tomllib
from pathlib import Path

import pytest

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
THEME = ".config/omarchy/themes/dracula"
WALL = ".config/omarchy/backgrounds/gruvbox/gruvbox.jpg"
SEED = MODULE / "backgrounds/gruvbox/gruvbox.jpg"

# omarchy-theme-remove:31-37 (Omarchy 4.0.3-1): `-d` follows the link, `rm -rf` on it unlinks; `exit 1` is the Omarchy that refuses.
THEME_REMOVE = '\np="$HOME/.config/omarchy/themes/$1"\n[ -d "$p" ] || exit 1\nrm -rf "$p"\n'


def snapshot(root: Path) -> dict[str, tuple]:
    """Every path under root as (mode, bytes or link target, mtime) — a symlink is read."""
    out = {}
    for p in sorted(root.rglob("*")):
        body = os.readlink(p) if p.is_symlink() else (p.read_bytes() if p.is_file() else b"")
        out[str(p.relative_to(root))] = (p.lstat().st_mode, body, p.lstat().st_mtime_ns)
    return out


def test_install_links_the_theme_and_seeds_the_wallpapers(box) -> None:
    """The link is the theme update (`git pull`); the wallpaper lands where the picker looks."""
    proc = box.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    link = box.home / THEME
    assert Path(os.readlink(link)) == MODULE / "dracula"
    assert (link / "colors.toml").is_file()
    assert (link / "backgrounds" / "dracula.png").is_file(), "its own wallpaper ships inside"
    assert (box.home / WALL).read_bytes() == SEED.read_bytes()
    assert box.commands == [], "never activated, no sudo, no Omarchy command at all"
    assert not (box.home / ".local/state/hyprconf").exists(), "no marker: the link is the gate"


def test_a_second_run_writes_nothing_and_calls_nothing(box) -> None:
    """The post-update hook re-runs every module: byte-stable, mtimes included."""
    box.run(INSTALL)
    before = snapshot(box.home)
    box.reset()
    proc = box.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    assert snapshot(box.home) == before
    assert box.commands == []


@pytest.mark.parametrize("shape", ("dir", "link"))
def test_a_theme_of_your_own_at_that_name_is_left_alone(box, shape) -> None:
    """`-e` catches a directory, `-L` a link of theirs; no `.stock` beside it either, because omarchy-theme-list:7 lists every dir and link there as a theme."""
    theirs = box.home / THEME
    theirs.parent.mkdir(parents=True)
    if shape == "dir":
        theirs.mkdir()
    else:
        theirs.symlink_to(box.home)
    before = snapshot(theirs.parent)
    proc = box.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    assert snapshot(theirs.parent) == before
    assert "left alone" in proc.stderr
    assert (box.home / WALL).is_file(), "the wallpapers are a separate seam"


def test_colors_toml_omits_what_omarchy_derives_to_the_same_value(box) -> None:
    """light_foreground is `${color7:-foreground}` and no colorN key is set; dark_background is not derivable — Omarchy would mix 25% black (omarchy-theme-color:223,236)."""
    colors = tomllib.loads((MODULE / "dracula" / "colors.toml").read_text())
    assert colors["mode"] == "dark"
    assert not any(k.startswith("color") for k in colors), "a colorN key would change :223"
    assert "light_foreground" not in colors
    assert colors["dark_background"] == colors["background"]


@pytest.mark.parametrize("remove", (THEME_REMOVE, "exit 1\n"))
def test_undo_unlinks_the_theme_and_takes_the_seeded_wallpaper_back(box, remove) -> None:
    """Through Omarchy's own command (rule 1), and through the `rm -f` after it when it refuses."""
    box.stub("omarchy-theme-remove", remove)
    box.run(INSTALL)
    box.reset()
    proc = box.undo("themes")
    assert proc.returncode == 0, proc.stderr
    assert box.calls_of("omarchy-theme-remove") == [["omarchy-theme-remove", "dracula"]]
    assert not (box.home / THEME).exists(follow_symlinks=False)
    assert (MODULE / "dracula" / "colors.toml").is_file(), "rm -rf must not follow the link"
    assert not (box.home / WALL).parent.exists()


def test_undo_leaves_what_is_not_ours_alone(box) -> None:
    """A theme of theirs at that name, and a wallpaper whose bytes are not ours, both stay."""
    box.stub("omarchy-theme-remove", THEME_REMOVE)
    theirs = box.home / THEME
    theirs.mkdir(parents=True)
    (theirs / "colors.toml").write_text("theirs\n")
    (box.home / WALL).parent.mkdir(parents=True)
    (box.home / WALL).write_bytes(b"my own wallpaper")
    before = snapshot(box.home)
    proc = box.undo("themes")
    assert proc.returncode == 0, proc.stderr
    assert snapshot(box.home) == before
    assert box.commands == [], "not ours: Omarchy is not asked either"


def test_undo_on_a_machine_that_never_installed_does_nothing(box) -> None:
    proc = box.undo("themes")
    assert proc.returncode == 0, proc.stderr
    assert box.files() == set() and box.commands == []
