"""modules/themes — the dracula user theme (linked, never activated) and the
wallpapers filed under the Omarchy theme each belongs to.

Everything the module does happens inside $HOME with coreutils, so the box's
recording fakes are here to prove a negative: no run of this module calls an
Omarchy command at all, except the one `omarchy-theme-remove` that undo uses.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
# Code only: the header explains what the module does NOT do, so a scan for a
# forbidden command has to read past the comments.
CODE = "\n".join(ln for ln in INSTALL.read_text().splitlines() if not ln.lstrip().startswith("#"))

# What omarchy-theme-remove does to the name it is given: the `-d` gate follows
# the link, and `rm -rf` on a symlink unlinks it (omarchy-theme-remove:31-37,
# Omarchy 4.0.3-1). The shared fake only records, so a test that wants the
# effect asks for this body.
THEME_REMOVE = """
p="$HOME/.config/omarchy/themes/$1"
[ -d "$p" ] || exit 1
rm -rf "$p"
"""


def snapshot(root: Path) -> dict[str, tuple]:
    """Every path under root as (kind, content, mtime_ns) — what "a second run
    wrote nothing" is compared on. A symlink is read, never followed."""
    out = {}
    for p in sorted(root.rglob("*")):
        st = p.lstat()
        body = os.readlink(p) if p.is_symlink() else (p.read_bytes() if p.is_file() else b"")
        out[str(p.relative_to(root))] = (st.st_mode, body, st.st_mtime_ns)
    return out


def themes_dir(box) -> Path:
    return box.home / ".config" / "omarchy" / "themes"


def gruvbox(box) -> Path:
    return box.home / ".config" / "omarchy" / "backgrounds" / "gruvbox" / "gruvbox.jpg"


# ---------------------------------------------------------------------------
# The theme
# ---------------------------------------------------------------------------


def test_the_theme_is_linked_into_omarchys_user_theme_dir(box) -> None:
    """A symlink, so a `git pull` is the theme update — and Omarchy blesses the
    shape: theme_came_from_a_repo is `[[ ! -L $source && -d $source/.git ]]`
    (omarchy-theme-set:204-208), so a linked user theme takes the plain `cp -r`
    branch (:275), and `omarchy theme update` skips it via omarchy-theme-extras:12
    (read by omarchy-theme-update:5) rather than pulling into the checkout."""
    proc = box.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    link = themes_dir(box) / "dracula"
    assert link.is_symlink()
    assert Path(os.readlink(link)) == MODULE / "dracula"
    assert (link / "colors.toml").is_file()


def test_installing_never_activates_a_theme(box) -> None:
    """Which theme is active is the user's, and this module re-runs after every
    Omarchy update (the post-update hook). Asserted twice: no omarchy-theme-set
    anywhere in the code — which covers every branch, not the one a run takes —
    and a full run that calls no command at all."""
    assert "omarchy-theme-set" not in CODE
    box.run(INSTALL)
    assert box.commands == []


def test_a_theme_directory_of_your_own_is_left_alone(box) -> None:
    """A real ~/.config/omarchy/themes/dracula is a theme they installed
    themselves (`omarchy theme install` clones one, omarchy-theme-install:56):
    `ln -sfn` over a directory would only drop a stray link inside it, so the
    module says so and carries on with the wallpapers."""
    theirs = themes_dir(box) / "dracula"
    theirs.mkdir(parents=True)
    (theirs / "colors.toml").write_text("theirs\n")

    proc = box.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    assert not theirs.is_symlink()
    assert sorted(p.name for p in theirs.iterdir()) == ["colors.toml"]
    assert "left alone" in proc.stderr
    assert gruvbox(box).is_file(), "the wallpapers are a separate seam"


def test_the_theme_carries_its_own_background(box) -> None:
    """Omarchy's picker scans the active theme's own backgrounds/ as well as the
    user folder (omarchy-theme-bg-next:7-12), so dracula's wallpaper ships
    inside the theme and never goes through the seeding loop."""
    inside = sorted(p.name for p in (MODULE / "dracula" / "backgrounds").iterdir())
    assert inside == ["dracula.png"]
    assert not (MODULE / "backgrounds" / "dracula").exists()


def test_colors_toml_omits_what_omarchy_derives_to_the_same_value(box) -> None:
    """light_foreground is `${color7:-foreground}` when absent
    (omarchy-theme-color:223) and the theme defines no colorN key, so writing it
    was a no-op line. dark_background is NOT derivable — Omarchy would mix
    background with 25% black (:236) — so it stays, named in the header."""
    text = (MODULE / "dracula" / "colors.toml").read_text()
    colors = tomllib.loads(text)
    assert colors["mode"] == "dark"
    assert not any(k.startswith("color") for k in colors), "a colorN key would change :223"
    assert "light_foreground" not in colors
    assert colors["dark_background"] == colors["background"]
    header = text.split("accent", 1)[0]
    assert "dark_background" in header and "light_foreground" in header


# ---------------------------------------------------------------------------
# The wallpapers
# ---------------------------------------------------------------------------


def test_wallpapers_are_seeded_where_omarchy_looks_and_then_left_alone(box) -> None:
    """The destination is the directory name under backgrounds/ — no table:
    Omarchy's picker scans ~/.config/omarchy/backgrounds/<active theme>/
    (omarchy-theme-bg-next:8, omarchy-theme-bg-switcher:14), so a file filed
    anywhere else never appears. Seeded, not synced: the folder is the user's."""
    box.run(INSTALL)
    assert (
        gruvbox(box).read_bytes()
        == (MODULE / "backgrounds" / "gruvbox" / "gruvbox.jpg").read_bytes()
    )

    gruvbox(box).write_bytes(b"my own wallpaper")
    proc = box.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    assert gruvbox(box).read_bytes() == b"my own wallpaper"


def test_a_deleted_wallpaper_comes_back(box) -> None:
    """Copied when absent: deleting one and re-running brings it back. To stop
    that for good the file leaves the module."""
    box.run(INSTALL)
    gruvbox(box).unlink()
    box.run(INSTALL)
    assert gruvbox(box).is_file()


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------


def test_a_second_run_writes_nothing_and_calls_nothing(box) -> None:
    """The post-update hook re-runs every module after every Omarchy update:
    byte-stable, mtimes included (the link is not re-made), and no command."""
    box.run(INSTALL)
    before = snapshot(box.home)
    box.reset()

    proc = box.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    assert snapshot(box.home) == before
    assert box.commands == []
    assert proc.stdout == ""


def test_nothing_leaves_home_and_no_user_choice_is_recorded(box) -> None:
    """No package, no root write, no prompt — so no HYPRCONF_NO_SUDO or TTY gate
    to get wrong; and no set-once marker, because linking a theme and seeding a
    file are their own gates (the link target, and `[[ -e $dest ]]`)."""
    assert "sudo" not in CODE
    assert "HYPRCONF_STATE" not in CODE
    box.run(INSTALL)
    assert not (box.home / ".local" / "state" / "hyprconf").exists()
    assert box.etc.is_dir() and list(box.etc.iterdir()) == []


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------


def test_undo_removes_the_link_through_omarchys_own_command(box) -> None:
    """`omarchy theme remove dracula` is the Omarchy tool for this (rule 1); on a
    symlink its `rm -rf` unlinks and never reaches the checkout
    (omarchy-theme-remove:31-37)."""
    box.stub("omarchy-theme-remove", THEME_REMOVE)
    box.run(INSTALL)
    box.reset()

    proc = box.undo("themes")
    assert proc.returncode == 0, proc.stderr
    assert box.calls_of("omarchy-theme-remove") == [["omarchy-theme-remove", "dracula"]]
    assert not (themes_dir(box) / "dracula").exists(follow_symlinks=False)
    assert (MODULE / "dracula" / "colors.toml").is_file(), "rm -rf must not follow the link"


def test_undo_removes_the_link_even_when_omarchy_cannot(box) -> None:
    """The shared fake answers nothing, standing in for an Omarchy that refuses:
    undo still ends with the link gone."""
    box.run(INSTALL)
    proc = box.undo("themes")
    assert proc.returncode == 0, proc.stderr
    assert box.calls_of("omarchy-theme-remove") == [["omarchy-theme-remove", "dracula"]]
    assert not (themes_dir(box) / "dracula").exists(follow_symlinks=False)


def test_undo_leaves_a_theme_that_is_not_ours_alone(box) -> None:
    """A directory of their own, and a link they pointed at a working copy of
    their own, are both theirs — undo touches neither, and asks Omarchy nothing."""
    box.stub("omarchy-theme-remove", THEME_REMOVE)
    theirs = themes_dir(box) / "dracula"
    theirs.mkdir(parents=True)
    (theirs / "colors.toml").write_text("theirs\n")
    box.undo("themes")
    assert (theirs / "colors.toml").read_text() == "theirs\n"

    theirs.rename(box.home / "their-dracula")
    theirs.symlink_to(box.home / "their-dracula")
    proc = box.undo("themes")
    assert proc.returncode == 0, proc.stderr
    assert theirs.is_symlink()
    assert box.commands == []


def test_undo_takes_the_seeded_wallpaper_back_but_not_your_own(box) -> None:
    """Ours by bytes: the seeded file goes and the folder with it when empty; a
    file the user put at that path, or their other wallpapers, stay."""
    box.run(INSTALL)
    proc = box.undo("themes")
    assert proc.returncode == 0, proc.stderr
    assert not gruvbox(box).parent.exists()

    box.run(INSTALL)
    gruvbox(box).write_bytes(b"my own wallpaper")
    mine = gruvbox(box).with_name("mine.jpg")
    mine.write_bytes(b"another of mine")
    box.undo("themes")
    assert gruvbox(box).read_bytes() == b"my own wallpaper"
    assert mine.is_file()


def test_undo_on_a_machine_that_never_installed_does_nothing(box) -> None:
    """The module loop runs `install undo` for every module: a clean exit and no
    files on a box that never had it."""
    proc = box.undo("themes")
    assert proc.returncode == 0, proc.stderr
    assert box.files() == set()
    assert box.commands == []
