"""modules/terminal-kitty: kitty as the default terminal, plus one kitty include —
the module's own `install` against the root conftest's `box`, never install.sh."""

from pathlib import Path

import pytest

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
INCLUDE = "# hyprconf overlay\ninclude hyprconf.conf\n"
MARKER = ".local/state/hyprconf/terminal-applied"
CONF = ".config/kitty/kitty.conf"
MINE = ".config/kitty/hyprconf.conf"
# Omarchy's own: the theme include and omarchy-font-set:33-40's font_family in the user file,
# allow_remote_control and listen_on in /etc/xdg/kitty/kitty.conf, `shell` in shell-zsh's include.
OWNED = {"font_family", "font_size", "listen_on", "allow_remote_control", "include", "shell"}
# An upgraded box's user file: migrations/1788745941.sh:11-13 refreshes only one whose sha still matches stock.
UPGRADED = "include ~/.local/state/omarchy/current/theme/kitty.conf\nfont_family JetBrains Mono\n"
# --no-packages, what the post-update hook passes, and no terminal for the password prompt.
GATES = [({"tty": True, "env": {"HYPRCONF_NO_SUDO": "1"}}, "--no-packages"), ({}, "no terminal")]


def _kitty_missing(box) -> None:
    """omarchy-pkg-present (pacman -Q) answers no until omarchy-pkg-add has run."""
    box.stub("omarchy-pkg-present", f'[ -e "{box.tmp}/installed" ]\n')
    box.stub("omarchy-pkg-add", f'touch "{box.tmp}/installed"\n')


@pytest.fixture
def kitty(box):
    """A stock Omarchy: kitty installed, foot the default. box.terminal is what omarchy-default-terminal reports and what a set writes; box.set_status fails that write the way its closing notification does (bin/omarchy-default-terminal:37)."""
    box.terminal, box.set_status = box.tmp / "default-terminal", box.tmp / "set-status"
    box.terminal.write_text("foot")
    box.set_status.write_text("0")
    box.stub(
        "omarchy-default-terminal",
        f'(($#)) || {{ cat "{box.terminal}"; exit 0; }}\n'
        f'printf %s "$1" > "{box.terminal}"\nexit "$(cat "{box.set_status}")"\n',
    )
    return box


def test_a_first_run_installs_kitty_sets_the_terminal_and_lands_the_include(kitty) -> None:
    _kitty_missing(kitty)
    proc = kitty.run(INSTALL, tty=True)
    assert proc.returncode == 0, proc.stderr
    assert kitty.calls_of("omarchy-pkg-add") == [["omarchy-pkg-add", "kitty"]]  # the packages file
    assert kitty.terminal.read_text() == "kitty"
    mine = kitty.home / MINE
    assert mine.read_text() == (MODULE / "hyprconf.conf").read_text()
    assert mine.stat().st_mode & 0o777 == 0o644
    stub = (kitty.omarchy / "config/kitty/kitty.conf").read_text()  # seeded from Omarchy's own
    assert (kitty.home / CONF).read_text() == stub + INCLUDE
    assert (kitty.home / MARKER).exists()


def test_a_second_run_writes_nothing_and_never_takes_the_terminal_back(kitty) -> None:
    assert kitty.run(INSTALL).returncode == 0
    kitty.terminal.write_text("ghostty")  # the user moved on; the marker is set once
    before = kitty.snapshot()
    kitty.reset()
    proc = kitty.run(INSTALL)
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")
    assert kitty.snapshot() == before
    assert set(kitty.commands) == {"omarchy-pkg-present"}, kitty.calls


def test_a_setter_that_reports_failure_is_retried_then_recorded(kitty) -> None:
    """The setter's non-zero status arrives AFTER the list file is written (:31-37)."""
    kitty.set_status.write_text("1")
    assert kitty.run(INSTALL).returncode == 0
    assert not (kitty.home / MARKER).exists() and (kitty.home / MINE).exists()
    kitty.reset()
    assert kitty.run(INSTALL).returncode == 0  # kitty is current now, so it is only recorded
    assert (kitty.home / MARKER).exists() and kitty.commands.count("omarchy-default-terminal") == 1


@pytest.mark.parametrize("body", [UPGRADED, "include theme.conf"])  # with, without a last newline
def test_an_existing_kitty_conf_gains_only_the_include(kitty, body) -> None:
    conf = kitty.home / CONF
    conf.parent.mkdir(parents=True)
    conf.write_text(body)
    assert kitty.run(INSTALL).returncode == 0
    assert kitty.run(INSTALL).returncode == 0  # and never a second copy
    assert conf.read_text() == body.rstrip("\n") + "\n" + INCLUDE


def test_the_shipped_include_restates_nothing_omarchy_owns() -> None:
    """It is included LAST, so a restatement would silently beat Omarchy."""
    conf = (MODULE / "hyprconf.conf").read_text().splitlines()
    assert not {ln.split()[0] for ln in conf if ln[:1].isalpha()} & OWNED, conf


def test_a_failed_package_install_fails_the_module(kitty) -> None:
    """omarchy-pkg-add exits 1 when pacman could not register the package (bin/omarchy-pkg-add:16-22); the core's loop names the module (AGENTS rule 6)."""
    kitty.stub("omarchy-pkg-present", "exit 1\n")
    kitty.stub("omarchy-pkg-add", "exit 1\n")
    proc = kitty.run(INSTALL, tty=True)
    assert proc.returncode != 0 and "package install failed" in proc.stderr
    assert kitty.terminal.read_text() == "foot" and kitty.files() == set()


@pytest.mark.parametrize(("kwargs", "pointer"), GATES)
def test_the_package_step_bows_out_of_sudo_and_kitty_stays_absent(kitty, kwargs, pointer) -> None:
    _kitty_missing(kitty)
    proc = kitty.run(INSTALL, **kwargs)
    assert proc.returncode == 0, proc.stderr
    assert pointer in proc.stdout and "omarchy-pkg-add" not in kitty.commands
    # And with kitty still absent the setter — which checks nothing — is never pointed at it.
    assert "kitty is not installed" in proc.stderr
    assert kitty.terminal.read_text() == "foot" and kitty.files() == set()


def test_a_symlinked_kitty_conf_keeps_its_link_through_install_and_undo(kitty, tmp_path) -> None:
    """undo's `sed --follow-symlinks`: a dotfiles kitty.conf comes back a link, not a copy."""
    conf = kitty.home / CONF
    conf.parent.mkdir(parents=True)
    (tmp_path / "theirs.conf").write_text(UPGRADED)
    conf.symlink_to(tmp_path / "theirs.conf")
    assert kitty.run(INSTALL).returncode == 0 and conf.read_text() == UPGRADED + INCLUDE
    assert kitty.undo("terminal-kitty").returncode == 0
    assert conf.is_symlink() and conf.read_text() == UPGRADED


# The last row: foot removed — the setter checks nothing, so undo never points it there (AGENTS rule 6).
UNDO = [("kitty", "", "foot"), ("ghostty", "", "ghostty"), ("kitty", "foot", "kitty")]


@pytest.mark.parametrize(("since", "absent", "back"), UNDO)
def test_undo_restores_stock(kitty, since, absent, back) -> None:
    """foot: /usr/share/xdg-terminal-exec/hyprland-xdg-terminals.list (omarchy-settings 4.0.3-1), and only while kitty is still what we set."""
    assert kitty.run(INSTALL).returncode == 0
    kitty.terminal.write_text(since)
    kitty.stub("omarchy-pkg-present", f'[[ "$*" != "{absent}" ]]\n')
    assert kitty.undo("terminal-kitty").returncode == 0
    stock = (kitty.omarchy / "config/kitty/kitty.conf").read_text()  # every added line gone
    assert (kitty.home / CONF).read_text() == stock
    assert not (kitty.home / MINE).exists() and not (kitty.home / MARKER).exists()
    assert kitty.terminal.read_text() == back
