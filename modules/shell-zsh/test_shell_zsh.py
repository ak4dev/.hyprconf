"""modules/shell-zsh: zsh + powerlevel10k in the terminal, on the `box` fixture.

Hermetic: the pinned clone is a fake `git` that writes marker files instead of
reaching GitHub, and every omarchy-* the module calls is a recording stub.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
SOURCE_LINE = f'[ -r "{MODULE}/zshrc" ] && source "{MODULE}/zshrc"'
PIN = re.search(r"p10k_pin=([0-9a-f]{40})", INSTALL.read_text()).group(1)

# A git that never reaches the network: a clone records the sha it was asked
# for, `rev-parse HEAD` reads it back, and fetch+checkout move it — the shapes
# clone_p10k drives.
GIT = """\
case "$1" in
  clone)
    rev=""
    for a in "$@"; do case $a in --revision=*) rev=${a#--revision=} ;; esac; d=$a; done
    mkdir -p "$d/.git" "$d/config"; printf '%s' "$rev" > "$d/.git/head"; exit 0 ;;
  -C)
    d=$2; shift 2
    case "$1" in
      rev-parse) cat "$d/.git/head" 2>/dev/null || echo unborn ;;
      fetch)     for a in "$@"; do last=$a; done; printf '%s' "$last" > "$d/.git/fetched" ;;
      checkout)  cat "$d/.git/fetched" > "$d/.git/head" 2>/dev/null ;;
    esac
    exit 0 ;;
esac
exit 0
"""

# omarchy-pkg-present answers "installed" for anything but the plugin package:
# the three-package question is then a miss and the `zsh` question a hit.
PLUGINS_MISSING = 'case " $* " in *zsh-autosuggestions*) exit 1 ;; esac\nexit 0\n'
KITTY_CONF = (
    "# Remove the include below to disconnect Kitty from Omarchy's theming system.\n"
    "include ~/.local/state/omarchy/current/theme/kitty.conf\n"
)


def apply(box, **kwargs) -> subprocess.CompletedProcess:
    """One run of the module against the box, with the fake git in place."""
    box.stub("git", GIT)
    return box.run(INSTALL, **kwargs)


def snapshot(home: Path) -> dict[str, tuple]:
    """Every path under HOME with its bytes, mtime and link target — what a
    second run has to leave untouched."""
    out: dict[str, tuple] = {}
    for path in sorted(home.rglob("*")):
        if path.is_symlink():
            out[str(path)] = ("link", str(path.readlink()), path.lstat().st_mtime_ns)
        elif path.is_file():
            out[str(path)] = ("file", path.read_bytes(), path.stat().st_mtime_ns)
    return out


def zshrc_lines(box) -> list[str]:
    return (box.home / ".zshrc").read_text().splitlines()


def test_a_first_run_lands_the_prompt_the_rc_line_and_the_kitty_shell(box) -> None:
    (box.home / ".config" / "kitty").mkdir(parents=True)
    (box.home / ".config" / "kitty" / "kitty.conf").write_text(KITTY_CONF)

    proc = apply(box)
    assert proc.returncode == 0, proc.stderr

    # the prompt: one clone, at the pin, and ~/.p10k.zsh pointing into the module
    clone = [c for c in box.calls_of("git") if "clone" in c][0]
    assert f"--revision={PIN}" in clone
    assert "https://github.com/romkatv/powerlevel10k.git" in clone
    assert (box.home / ".local/share/powerlevel10k/.git/head").read_text() == PIN
    assert (box.home / ".p10k.zsh").readlink() == MODULE / ".p10k.zsh"

    # ~/.zshrc: exactly one line, and it is a source of this module's zshrc
    assert zshrc_lines(box) == [SOURCE_LINE]

    # kitty: the module's own include, beside Omarchy's theme include, and
    # nothing else — one line, no separator, so `undo` is byte-exact
    conf = (box.home / ".config/kitty/kitty.conf").read_text()
    assert conf == KITTY_CONF + "include hyprconf-zsh.conf\n"
    assert (box.home / ".config/kitty/hyprconf-zsh.conf").read_text() == (
        MODULE / "hyprconf-zsh.conf"
    ).read_text()


def test_a_second_run_writes_nothing_and_calls_no_mutating_command(box) -> None:
    (box.home / ".config" / "kitty").mkdir(parents=True)
    (box.home / ".config" / "kitty" / "kitty.conf").write_text(KITTY_CONF)
    apply(box)
    before = snapshot(box.home)
    box.reset()

    proc = apply(box)

    assert proc.returncode == 0, proc.stderr
    assert snapshot(box.home) == before
    assert "omarchy-pkg-add" not in box.commands
    mutating = {"clone", "fetch", "checkout", "pull"}
    assert not [c for c in box.calls_of("git") if mutating & set(c)]


def test_undo_restores_the_files_it_found(box) -> None:
    (box.home / ".config" / "kitty").mkdir(parents=True)
    (box.home / ".config" / "kitty" / "kitty.conf").write_text(KITTY_CONF)
    (box.home / ".zshrc").write_text("# mine\nexport EDITOR=vi\n")
    (box.home / ".p10k.zsh").write_text("# my own prompt\n")

    apply(box)
    assert (box.home / ".p10k.zsh.stock").read_text() == "# my own prompt\n"

    proc = box.undo("shell-zsh")

    assert proc.returncode == 0, proc.stderr
    assert zshrc_lines(box) == ["# mine", "export EDITOR=vi"]
    assert (box.home / ".config/kitty/kitty.conf").read_text() == KITTY_CONF
    assert not (box.home / ".config/kitty/hyprconf-zsh.conf").exists()
    # the clone, its marker and every directory they created
    assert not (box.home / ".local").exists()
    assert (box.home / ".p10k.zsh").read_text() == "# my own prompt\n"
    assert not (box.home / ".p10k.zsh.stock").exists()


def test_the_pre_module_managed_block_is_cut_once_and_the_rest_kept_in_place(box) -> None:
    (box.home / ".zshrc").write_text(
        "# mine, above\n"
        "# >>> hyprconf >>>\n"
        "export ZSH=$HOME/.oh-my-zsh\n"
        "source $ZSH/oh-my-zsh.sh\n"
        "# <<< hyprconf <<<\n"
        "# mine, below\n"
    )

    apply(box)

    assert zshrc_lines(box) == ["# mine, above", "# mine, below", SOURCE_LINE]
    assert "oh-my-zsh" not in (box.home / ".zshrc").read_text()


def test_a_marker_pair_that_is_not_a_pair_leaves_the_file_alone(box) -> None:
    """One marker line lost to a hand revert: a begin-to-EOF cut would eat
    everything the user wrote below it, so nothing is cut."""
    (box.home / ".zshrc").write_text("# >>> hyprconf >>>\nsource $ZSH/oh-my-zsh.sh\n# mine\n")

    apply(box)

    assert zshrc_lines(box) == [
        "# >>> hyprconf >>>",
        "source $ZSH/oh-my-zsh.sh",
        "# mine",
        SOURCE_LINE,
    ]


def test_a_source_line_from_a_checkout_that_moved_is_replaced_not_doubled(box) -> None:
    stale = (
        '[ -r "/old/place/modules/shell-zsh/zshrc" ] && source "/old/place/modules/shell-zsh/zshrc"'
    )
    (box.home / ".zshrc").write_text(f"# mine\n{stale}\n")

    apply(box)

    assert zshrc_lines(box) == ["# mine", SOURCE_LINE]


def test_an_existing_source_line_keeps_its_place_in_the_file(box) -> None:
    (box.home / ".zshrc").write_text(f"# above\n{SOURCE_LINE}\n# below\n")

    apply(box)

    assert zshrc_lines(box) == ["# above", SOURCE_LINE, "# below"]


def test_a_hand_duplicated_source_line_is_collapsed_to_one(box) -> None:
    """ "Exactly one source line, never two" holds over a file that already
    carries two identical copies — sourcing `zshrc` twice would run every
    `compinit`, plugin and greeting in it twice."""
    (box.home / ".zshrc").write_text(f"# above\n{SOURCE_LINE}\n# middle\n{SOURCE_LINE}\n")

    apply(box)

    assert zshrc_lines(box) == ["# above", SOURCE_LINE, "# middle"]


def test_blank_lines_in_the_users_zshrc_survive_the_drop(box) -> None:
    """The dedupe rule compares against an empty `want` in undo's drop mode —
    the guard that keeps it from eating every blank line the user wrote."""
    (box.home / ".zshrc").write_text(f"# above\n\n\n{SOURCE_LINE}\n\n# below\n")
    apply(box)

    assert box.undo("shell-zsh").returncode == 0
    assert zshrc_lines(box) == ["# above", "", "", "", "# below"]


def test_a_dotfiles_link_at_p10k_zsh_is_backed_up_as_a_link_once(box, tmp_path) -> None:
    """A stow-style link there is somebody's own arrangement: `cp -P` keeps it
    a link, so the README's restore hands it back pointing where it pointed —
    and the FIRST backup is the one that matters, so a user who re-creates
    their link and re-runs does not lose it."""
    theirs = tmp_path / "dotfiles" / "p10k.zsh"
    theirs.parent.mkdir()
    theirs.write_text("# their own prompt\n")
    (box.home / ".p10k.zsh").symlink_to(theirs)

    apply(box)
    backup = box.home / ".p10k.zsh.stock"
    assert backup.is_symlink() and backup.readlink() == theirs
    assert (box.home / ".p10k.zsh").readlink() == MODULE / ".p10k.zsh"

    # They put their link back, then re-run: the first backup stays theirs.
    (box.home / ".p10k.zsh").unlink()
    (box.home / ".p10k.zsh").symlink_to(theirs)
    apply(box)
    assert backup.is_symlink() and backup.readlink() == theirs

    # And the restore line puts it back, still a link to their file.
    assert box.undo("shell-zsh").returncode == 0
    assert (box.home / ".p10k.zsh").readlink() == theirs


def test_missing_packages_are_installed_from_a_terminal(box) -> None:
    box.stub("omarchy-pkg-present", PLUGINS_MISSING)

    proc = apply(box, tty=True)

    assert proc.returncode == 0, proc.stderr
    assert box.calls_of("omarchy-pkg-add") == [
        ["omarchy-pkg-add", "zsh", "zsh-autosuggestions", "zsh-syntax-highlighting"]
    ]


def test_no_sudo_and_no_terminal_both_skip_the_packages_and_still_configure(box) -> None:
    box.stub("omarchy-pkg-present", PLUGINS_MISSING)

    no_sudo = apply(box, env={"HYPRCONF_NO_SUDO": "1"})
    assert no_sudo.returncode == 0, no_sudo.stderr
    assert "omarchy-pkg-add" not in box.commands
    assert zshrc_lines(box) == [SOURCE_LINE]

    box.reset()
    (box.home / ".zshrc").unlink()
    no_tty = apply(box)  # box.run closes stdin: the no-terminal path
    assert no_tty.returncode == 0, no_tty.stderr
    assert "omarchy-pkg-add" not in box.commands
    assert "no terminal for sudo" in no_tty.stdout
    assert zshrc_lines(box) == [SOURCE_LINE]


def test_without_zsh_the_module_configures_nothing_and_does_not_fail(box) -> None:
    """kitty pointed at a shell that is not installed cannot start at all."""
    box.stub("omarchy-pkg-present", "exit 1\n")

    proc = apply(box, env={"HYPRCONF_NO_SUDO": "1"})

    assert proc.returncode == 0, proc.stderr
    assert box.files() == set()
    assert "zsh is not installed" in proc.stdout


def test_without_kitty_the_rest_still_lands(box) -> None:
    box.stub("omarchy-cmd-present", "exit 1\n")

    proc = apply(box)

    assert proc.returncode == 0, proc.stderr
    assert not (box.home / ".config/kitty").exists()
    assert zshrc_lines(box) == [SOURCE_LINE]
    assert (box.home / ".p10k.zsh").is_symlink()


def test_a_powerlevel10k_directory_that_is_not_a_checkout_is_left_alone(box) -> None:
    theirs = box.home / ".local/share/powerlevel10k"
    theirs.mkdir(parents=True)
    (theirs / "powerlevel10k.zsh-theme").write_text("# theirs\n")

    proc = apply(box)

    assert proc.returncode == 0, proc.stderr
    assert (theirs / "powerlevel10k.zsh-theme").read_text() == "# theirs\n"
    assert not [c for c in box.calls_of("git") if "clone" in c]
    assert "not a git checkout" in proc.stdout


def test_a_checkout_at_another_commit_moves_to_the_pin(box) -> None:
    apply(box)
    head = box.home / ".local/share/powerlevel10k/.git/head"
    head.write_text("0" * 40)
    box.reset()

    apply(box)

    assert head.read_text() == PIN
    assert [c[3] for c in box.calls_of("git") if "fetch" in c] == ["fetch"]


def test_the_third_party_pin_is_a_reviewed_sha_fetched_over_https(box) -> None:
    """The prompt is the only third-party code this module installs, and it
    runs in every interactive zsh (AGENTS rule 8)."""
    text = INSTALL.read_text()
    assert re.search(r"^p10k_url=https://", text, re.M)
    assert re.search(r"^p10k_pin=[0-9a-f]{40}$", text, re.M)
    assert "git pull" not in text
    assert "--revision=" in text and "--depth=1" in text
    assert "oh-my-zsh" not in text.lower()


def test_the_payload_names_no_framework_and_no_checkout_path(box) -> None:
    zshrc = (MODULE / "zshrc").read_text()
    p10k = (MODULE / ".p10k.zsh").read_text()
    assert "oh-my-zsh" not in (zshrc + p10k).lower()
    assert "ZSH_THEME" not in zshrc
    # the alias runs the ~/.local/bin link the core makes, so no path is baked in
    assert "alias hyprsync='hyprconf --sync'" in zshrc
    assert ".hyprconf" not in zshrc
    # the greeting: the fastfetch module's config when it is there, plain when not
    assert 'fastfetch -c "$HOME/.config/hyprconf/fastfetch.jsonc"' in zshrc
    assert "powerlevel10k.zsh-theme" in zshrc


def test_every_omarchy_command_the_module_calls_has_a_fake(box) -> None:
    named = set(re.findall(r"\bomarchy(?:-[a-z0-9]+)+\b", INSTALL.read_text()))
    assert named <= box.fakes, named - box.fakes


def test_the_shipped_zsh_files_parse(box) -> None:
    if shutil.which("zsh") is None:
        pytest.skip("no zsh on this box")
    for name in ("zshrc", ".p10k.zsh"):
        proc = subprocess.run(
            ["zsh", "-n", str(MODULE / name)], capture_output=True, text=True, timeout=30
        )
        assert proc.returncode == 0, proc.stderr


def test_the_pre_module_p10k_link_is_replaced_without_a_dangling_backup(box) -> None:
    """~/.p10k.zsh already points at <checkout>/zsh/.p10k.zsh on every box that
    ran hyprconf <= 7.x; saving that as .stock would preserve a link to a file
    the module split deletes."""
    checkout = MODULE.parent.parent
    (box.home / ".p10k.zsh").symlink_to(checkout / "zsh" / ".p10k.zsh")

    apply(box)

    assert (box.home / ".p10k.zsh").readlink() == MODULE / ".p10k.zsh"
    assert not (box.home / ".p10k.zsh.stock").exists(follow_symlinks=False)


def test_undo_leaves_a_powerlevel10k_directory_it_never_made(box) -> None:
    theirs = box.home / ".local/share/powerlevel10k"
    theirs.mkdir(parents=True)
    (theirs / "powerlevel10k.zsh-theme").write_text("# theirs\n")
    apply(box)

    proc = box.undo("shell-zsh")

    assert proc.returncode == 0, proc.stderr
    assert (theirs / "powerlevel10k.zsh-theme").read_text() == "# theirs\n"


def test_a_kitty_conf_that_is_not_there_is_seeded_from_omarchys_own_stub(box) -> None:
    """The theme include lives only in Omarchy's stub (config/kitty/kitty.conf:1-2),
    and the user file is optional from 4.0.3: creating one with just this
    module's include would cost kitty its theming for good."""
    stub = (box.omarchy / "config/kitty/kitty.conf").read_text()

    proc = apply(box)

    assert proc.returncode == 0, proc.stderr
    conf = (box.home / ".config/kitty/kitty.conf").read_text()
    assert conf == stub + "include hyprconf-zsh.conf\n"
    assert "include ~/.local/state/omarchy/current/theme/kitty.conf" in conf.splitlines()


def test_a_backslash_in_the_checkout_path_keeps_the_source_line_in_place(box, tmp_path) -> None:
    """awk escape-processes a `-v` assignment, so the line to keep goes to it as
    a file: a checkout under a path with a backslash in it must still recognise
    the line already in ~/.zshrc instead of dropping and re-appending it."""
    weird = tmp_path / "back\\slash" / "modules" / "shell-zsh"
    weird.parent.mkdir(parents=True)
    shutil.copytree(MODULE, weird, ignore=shutil.ignore_patterns("__pycache__"))
    line = f'[ -r "{weird}/zshrc" ] && source "{weird}/zshrc"'
    (box.home / ".zshrc").write_text(f"# above\n{line}\n# below\n")
    box.stub("git", GIT)

    first = box.run(weird / "install")
    before = (box.home / ".zshrc").read_bytes()
    second = box.run(weird / "install")

    assert (first.returncode, second.returncode) == (0, 0), first.stderr + second.stderr
    assert zshrc_lines(box) == ["# above", line, "# below"]
    assert (box.home / ".zshrc").read_bytes() == before


def test_undo_leaves_a_checkout_the_install_only_moved_to_the_pin(box) -> None:
    """Adopting a powerlevel10k the user cloned themselves does not make it
    ours: only a clone this module made carries the marker undo deletes on."""
    theirs = box.home / ".local/share/powerlevel10k"
    (theirs / ".git").mkdir(parents=True)
    (theirs / ".git" / "head").write_text("0" * 40)
    apply(box)
    assert (theirs / ".git" / "head").read_text() == PIN

    proc = box.undo("shell-zsh")

    assert proc.returncode == 0, proc.stderr
    assert (theirs / ".git" / "head").read_text() == PIN


def test_undo_leaves_nothing_behind_on_a_home_that_had_none_of_it(box) -> None:
    """Every file here is the module's own: undo takes the lot, and kitty.conf
    goes back to Omarchy's stub byte for byte."""
    apply(box)
    assert (box.home / ".zshrc").exists()

    proc = box.undo("shell-zsh")

    assert proc.returncode == 0, proc.stderr
    assert not (box.home / ".zshrc").exists()
    assert not (box.home / ".p10k.zsh").is_symlink()
    assert not (box.home / ".local").exists()
    assert (box.home / ".config/kitty/kitty.conf").read_text() == (
        box.omarchy / "config/kitty/kitty.conf"
    ).read_text()


def test_undo_before_any_install_writes_nothing_and_exits_zero(box) -> None:
    proc = box.undo("shell-zsh")

    assert proc.returncode == 0, proc.stderr
    assert box.files() == set()
