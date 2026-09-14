"""modules/shell-zsh: zsh + powerlevel10k in the terminal, on the `box` fixture."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import GIT_FAKE

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
SOURCE_LINE = f'[ -r "{MODULE}/zshrc" ] && source "{MODULE}/zshrc"'
PIN = re.search(r"p10k_pin=([0-9a-f]{40})", INSTALL.read_text()).group(1)
PKGS = ["zsh", "zsh-autosuggestions", "zsh-syntax-highlighting"]
# Installed for everything but the plugin package: the three-package question is
# then a miss and the `zsh` one a hit.
PLUGINS_MISSING = 'case " $* " in *zsh-autosuggestions*) exit 1 ;; esac\nexit 0\n'
THEIRS = "# theirs\ninclude ~/.local/state/omarchy/current/theme/kitty.conf\n"
BLOCK = "# above\n# >>> hyprconf >>>\nsource $ZSH/oh-my-zsh.sh\n# <<< hyprconf <<<\n# below\n"
LONE = "# >>> hyprconf >>>\nsource $ZSH/oh-my-zsh.sh\n# mine\n"
STALE = '[ -r "/old/modules/shell-zsh/zshrc" ] && source "/old/modules/shell-zsh/zshrc"'


def apply(box, **kwargs) -> subprocess.CompletedProcess:
    box.stub("git", GIT_FAKE)
    return box.run(INSTALL, **kwargs)


def snapshot(home: Path) -> dict:
    """Bytes or link target, and mtime, for every path under HOME."""
    paths = (p for p in sorted(home.rglob("*")) if p.is_symlink() or p.is_file())
    return {
        str(p): (p.lstat().st_mtime_ns, p.readlink() if p.is_symlink() else p.read_bytes())
        for p in paths
    }


def zshrc_lines(box) -> list[str]:
    return (box.home / ".zshrc").read_text().splitlines()


# theirs: the include is appended. stub: an absent kitty.conf is seeded from
# Omarchy's own first (config/kitty/kitty.conf:1-2 is where the theme include
# lives). none: no kitty at all, and nothing under ~/.config/kitty.
@pytest.mark.parametrize("kitty", ["theirs", "stub", "none"])
def test_a_first_run_lands_the_prompt_the_rc_line_and_the_kitty_shell(box, kitty) -> None:
    conf = box.home / ".config/kitty/kitty.conf"
    if kitty == "theirs":
        conf.parent.mkdir(parents=True)
        conf.write_text(THEIRS)
    if kitty == "none":
        box.stub("omarchy-cmd-present", "exit 1\n")
    proc = apply(box)
    assert proc.returncode == 0, proc.stderr
    clone = " ".join([c for c in box.calls_of("git") if "clone" in c][0])
    assert f"--revision={PIN}" in clone and "romkatv/powerlevel10k.git" in clone
    assert (box.home / ".local/share/powerlevel10k/.git/head").read_text() == PIN
    assert (box.home / ".p10k.zsh").readlink() == MODULE / ".p10k.zsh"
    assert zshrc_lines(box) == [SOURCE_LINE]
    if kitty == "none":
        assert not conf.parent.exists()
        return
    base = THEIRS if kitty == "theirs" else (box.omarchy / "config/kitty/kitty.conf").read_text()
    assert conf.read_text() == base + "include hyprconf-zsh.conf\n"  # no separator: undo is exact
    ours = MODULE / "hyprconf-zsh.conf"
    assert (conf.parent / ours.name).read_bytes() == ours.read_bytes()


def test_a_second_run_writes_nothing_and_calls_no_mutating_command(box) -> None:
    apply(box)
    before = snapshot(box.home)
    box.reset()
    proc = apply(box)
    assert proc.returncode == 0, proc.stderr
    assert snapshot(box.home) == before
    assert "omarchy-pkg-add" not in box.commands
    assert not [c for c in box.calls_of("git") if {"clone", "fetch", "checkout", "pull"} & set(c)]


@pytest.mark.parametrize("mine", [None, False, True])
def test_undo_restores_what_it_found(box, mine) -> None:
    stub = (box.omarchy / "config/kitty/kitty.conf").read_text()
    if mine is None:  # never installed: `hyprconf --undo` runs every module's undo
        assert box.undo("shell-zsh").returncode == 0
        assert box.files() == set()
        return
    if mine:
        (box.home / ".zshrc").write_text("# mine\n\n# below\n")
        (box.home / ".p10k.zsh").write_text("# my own prompt\n")
    apply(box)
    proc = box.undo("shell-zsh")
    assert proc.returncode == 0, proc.stderr
    assert not (box.home / ".local").exists()  # the clone, its marker, their dirs
    assert (box.home / ".config/kitty/kitty.conf").read_text() == stub
    assert not (box.home / ".config/kitty/hyprconf-zsh.conf").exists()
    if mine:  # the blank line too: the drop mode compares against an empty `want`
        assert zshrc_lines(box) == ["# mine", "", "# below"]
        assert (box.home / ".p10k.zsh").read_text() == "# my own prompt\n"
        assert not (box.home / ".p10k.zsh.stock").exists()
    else:
        assert not (box.home / ".zshrc").exists()  # stock Omarchy ships none
        assert not (box.home / ".p10k.zsh").is_symlink()


@pytest.mark.parametrize(
    "before,after",
    [
        (BLOCK, ["# above", "# below", SOURCE_LINE]),  # the 7.x block, cut once
        (LONE, [*LONE.splitlines(), SOURCE_LINE]),  # one marker gone: nothing is cut
        (f"# mine\n{STALE}\n", ["# mine", SOURCE_LINE]),  # a checkout that moved
        (f"# a\n{SOURCE_LINE}\n# b\n", ["# a", SOURCE_LINE, "# b"]),  # keeps its place
        (f"# a\n{SOURCE_LINE}\n# b\n{SOURCE_LINE}\n", ["# a", SOURCE_LINE, "# b"]),  # deduped
    ],
)
def test_the_zshrc_source_line_lands_once_and_moves_nothing_else(box, before, after) -> None:
    (box.home / ".zshrc").write_text(before)
    assert apply(box).returncode == 0
    assert zshrc_lines(box) == after


@pytest.mark.parametrize("kind,stock", [("file", "file"), ("link", "link"), ("legacy", None)])
def test_a_p10k_zsh_of_the_users_is_backed_up_once_and_replaced(box, tmp_path, kind, stock) -> None:
    """`cp -P` keeps a dotfiles link a link; a link into the checkout is 7.x's own."""
    p10krc = box.home / ".p10k.zsh"
    for n in (1, 2):  # they put theirs back and re-run: the FIRST backup is kept
        p10krc.unlink(missing_ok=True)
        if kind == "file":
            p10krc.write_text(f"# theirs {n}\n")
        else:
            legacy = MODULE.parent.parent / "zsh" / ".p10k.zsh"
            p10krc.symlink_to(tmp_path / f"theirs{n}" if kind == "link" else legacy)
        apply(box)
    backup = box.home / ".p10k.zsh.stock"
    assert p10krc.readlink() == MODULE / ".p10k.zsh"
    if stock == "file":
        assert backup.read_text() == "# theirs 1\n"
    elif stock == "link":
        assert backup.readlink() == tmp_path / "theirs1"
    else:
        assert not backup.exists(follow_symlinks=False)


GATES = [  # a terminal, then each gate's pointer line (box.run closes stdin: no terminal)
    ({}, True, None),
    ({"HYPRCONF_NO_SUDO": "1"}, False, "packages left to a run without --no-packages"),
    ({}, False, "no terminal for sudo"),
]


@pytest.mark.parametrize("env,tty,pointer", GATES)
def test_the_packages_land_from_a_terminal_and_each_gate_skips_them(box, env, tty, pointer) -> None:
    box.stub("omarchy-pkg-present", PLUGINS_MISSING)
    proc = apply(box, tty=tty, env=env)
    assert proc.returncode == 0, proc.stderr
    if pointer is None:
        assert box.calls_of("omarchy-pkg-add") == [["omarchy-pkg-add", *PKGS]]
    else:
        assert pointer in proc.stdout
        assert "omarchy-pkg-add" not in box.commands
    assert zshrc_lines(box) == [SOURCE_LINE]


@pytest.mark.parametrize("rc,says", [(0, "zsh is not installed"), (1, "omarchy-pkg-add failed")])
def test_the_module_writes_nothing_when_it_cannot_configure(box, rc, says) -> None:
    """kitty cannot start on an absent shell; omarchy-pkg-add:16-22 exits 1 on pacman's."""
    box.stub("omarchy-pkg-present", "exit 1\n" if rc == 0 else PLUGINS_MISSING)
    box.stub("omarchy-pkg-add", "exit 1\n")
    proc = apply(box, tty=True, env={"HYPRCONF_NO_SUDO": "1"} if rc == 0 else {})
    assert proc.returncode == rc
    assert says in proc.stdout + proc.stderr
    assert box.files() == set()


@pytest.mark.parametrize("checkout", [False, True])
def test_a_powerlevel10k_already_there_is_adopted_or_left_never_deleted(box, checkout) -> None:
    """Only a clone this module made carries the marker `undo` deletes on."""
    theirs = box.home / ".local/share/powerlevel10k"
    mark = theirs / (".git/head" if checkout else "powerlevel10k.zsh-theme")
    mark.parent.mkdir(parents=True)
    mark.write_text("0" * 40)
    proc = apply(box)
    assert proc.returncode == 0, proc.stderr
    assert not [c for c in box.calls_of("git") if "clone" in c]
    assert mark.read_text() == (PIN if checkout else "0" * 40)  # moved to the pin, or left
    assert checkout or "not a git checkout" in proc.stdout
    assert box.undo("shell-zsh").returncode == 0
    assert mark.exists()


def test_the_third_party_pin_is_a_reviewed_sha_fetched_over_https(box) -> None:
    """The only third-party code this module installs, run by every zsh (AGENTS rule 8)."""
    text = INSTALL.read_text()
    assert re.search(r"^p10k_url=https://", text, re.M)
    assert re.search(r"^p10k_pin=[0-9a-f]{40}$", text, re.M)
    assert "git pull" not in text
    assert "--revision=" in text and "--depth=1" in text
    assert "oh-my-zsh" not in text.lower()


def test_the_shipped_zsh_files_parse(box) -> None:
    if shutil.which("zsh") is None:
        pytest.skip("no zsh on this box")
    for name in ("zshrc", ".p10k.zsh"):
        assert subprocess.run(["zsh", "-n", MODULE / name], capture_output=True).returncode == 0
