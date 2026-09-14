"""modules/terminal-kitty: kitty as the default terminal, and one include.

Every test runs the module's own `install` against a `box` (the root
conftest's throwaway machine) — never install.sh, never the developer's
desktop: `omarchy-pkg-present`, `omarchy-pkg-add` and `omarchy-default-terminal`
are recording fakes, and $HOME, /etc and $OMARCHY_PATH are all under tmp_path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
INCLUDE = "# hyprconf overlay\ninclude hyprconf.conf\n"

# ~/.config/kitty/kitty.conf on an UPGRADED Omarchy box: 4.0.3 moved the defaults to
# /etc/xdg/kitty/kitty.conf, but migrations/1788745941.sh:11-13 only refreshes a user
# file whose sha still matches the old stock one — and a hyprconf box's carries the
# include. These are the lines the module must leave intact, in order.
UPGRADED_KITTY_CONF = """include ~/.local/state/omarchy/current/theme/kitty.conf
# allow_remote_control yes
listen_on unix:${XDG_RUNTIME_DIR}/omarchy-kitty-{kitty_pid}
font_family JetBrainsMono Nerd Font
font_size 10
"""


def _terminal_stub(box, start: str = "foot", set_status: int = 0) -> None:
    """omarchy-default-terminal: reports `start` until something sets it, then what
    was set (bin/omarchy-default-terminal:7-18 reads, :20-37 writes). The write form
    lands first and exits `set_status` — the real one's status is its closing
    notification's (:37). The state file lives outside $HOME so box.files() stays
    a clean answer to "did this run write anything"."""
    state = box.tmp / "default-terminal"
    state.write_text(start)
    box.stub(
        "omarchy-default-terminal",
        f'if (($# == 0)); then cat "{state}"; exit 0; fi\n'
        f'printf "%s" "$1" > "{state}"\nexit {set_status}\n',
    )


def _kitty_missing(box) -> Path:
    """A box where kitty is not installed yet and omarchy-pkg-add installs it —
    the only way `omarchy-pkg-present` (pacman -Q) can answer no in the suite."""
    flag = box.tmp / "kitty-installed"
    box.stub("omarchy-pkg-present", f'[ -e "{flag}" ] || exit 1\nexit 0\n')
    box.stub("omarchy-pkg-add", f'touch "{flag}"\nexit 0\n')
    return flag


def _state(box) -> dict[Path, str]:
    return {p: p.read_text() for p in box.files()}


@pytest.fixture
def kitty(box):
    """A box with kitty installed and foot as the default — a stock Omarchy."""
    _terminal_stub(box)
    return box


# ---------------------------------------------------------------- applying


def test_a_first_run_sets_the_terminal_and_lands_the_include(kitty) -> None:
    proc = kitty.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    assert ["omarchy-default-terminal", "kitty"] in kitty.calls_of("omarchy-default-terminal")

    mine = kitty.home / ".config/kitty/hyprconf.conf"
    assert mine.read_text() == (MODULE / "hyprconf.conf").read_text()
    assert mine.stat().st_mode & 0o777 == 0o644
    # Seeded from Omarchy's own stub (config/kitty/kitty.conf), include appended last.
    conf = (kitty.home / ".config/kitty/kitty.conf").read_text()
    stub = (kitty.omarchy / "config/kitty/kitty.conf").read_text()
    assert conf == stub + INCLUDE
    assert (kitty.home / ".local/state/hyprconf/terminal-applied").exists()


def test_a_second_run_writes_nothing_and_asserts_nothing(kitty) -> None:
    """The post-update hook re-runs this after every omarchy-update."""
    assert kitty.run(INSTALL).returncode == 0
    before = _state(kitty)
    kitty.reset()

    proc = kitty.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    assert _state(kitty) == before
    # Nothing that changes the machine: the default is neither re-read nor re-set,
    # and with kitty already present no package command runs at all — every call the
    # run makes is Omarchy's own `pacman -Q` probe.
    assert set(kitty.commands) == {"omarchy-pkg-present"}, kitty.calls


def test_the_user_may_change_the_terminal_back(kitty) -> None:
    """Set-once (AGENTS › Hard rules, 5): the marker, not the current value, is
    what stops the next run re-asserting kitty."""
    assert kitty.run(INSTALL).returncode == 0
    _terminal_stub(kitty, start="ghostty")  # the user moved on
    kitty.reset()

    assert kitty.run(INSTALL).returncode == 0
    assert "omarchy-default-terminal" not in kitty.commands


def test_an_existing_kitty_conf_gains_only_the_include(kitty) -> None:
    conf = kitty.home / ".config/kitty/kitty.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(UPGRADED_KITTY_CONF)

    assert kitty.run(INSTALL).returncode == 0
    assert conf.read_text() == UPGRADED_KITTY_CONF + INCLUDE
    # And never a second copy, however often the module runs.
    assert kitty.run(INSTALL).returncode == 0
    assert conf.read_text().count("include hyprconf.conf") == 1


def test_the_shipped_include_file_restates_nothing_omarchy_owns(kitty) -> None:
    """It is included LAST, so a restatement would silently beat Omarchy: the user
    file's theme include and the font_family omarchy-font-set:33-40 appends, and
    /etc/xdg/kitty/kitty.conf's allow_remote_control and listen_on. `shell` belongs
    to the shell-zsh module's own include, not to this one."""
    body = "\n".join(
        ln for ln in (MODULE / "hyprconf.conf").read_text().splitlines() if not ln.startswith("#")
    )
    for owned in (
        "font_family",
        "font_size",
        "listen_on",
        "allow_remote_control",
        "include ",
        "shell ",
    ):
        assert owned not in body, owned


# ------------------------------------------------------------- bowing out


def test_a_box_without_kitty_is_left_alone(box) -> None:
    """Warn and skip, never die: this runs on every omarchy-update (which
    passes --no-packages), and pointing omarchy-default-terminal (which checks
    nothing) at an absent kitty would leave SUPER+RETURN with no terminal."""
    _terminal_stub(box)
    box.stub("omarchy-pkg-present", "exit 1\n")

    proc = box.run(INSTALL, tty=True, env={"HYPRCONF_NO_SUDO": "1"})
    assert proc.returncode == 0, proc.stderr
    assert "kitty is not installed" in proc.stderr
    assert not any(len(c) > 1 for c in box.calls_of("omarchy-default-terminal"))
    assert box.files() == set()


def test_a_failed_package_install_fails_the_module(box) -> None:
    """omarchy-pkg-add exits 1 when pacman could not register the package
    (bin/omarchy-pkg-add:16-22): the module fails — the core's loop names it
    at the end of the run (AGENTS rule 6) — and nothing else happens."""
    _terminal_stub(box)
    box.stub("omarchy-pkg-present", "exit 1\n")
    box.stub("omarchy-pkg-add", "exit 1\n")  # the package really is unavailable

    proc = box.run(INSTALL, tty=True)
    assert proc.returncode != 0
    assert "package install failed" in proc.stderr
    assert not any(len(c) > 1 for c in box.calls_of("omarchy-default-terminal"))
    assert box.files() == set()


def test_a_missing_package_is_installed_from_the_modules_own_packages_file(box) -> None:
    _terminal_stub(box)
    _kitty_missing(box)

    proc = box.run(INSTALL, tty=True)
    assert proc.returncode == 0, proc.stderr
    assert ["omarchy-pkg-add", "kitty"] in box.calls_of("omarchy-pkg-add")
    assert (box.home / ".config/kitty/hyprconf.conf").exists()


@pytest.mark.parametrize(
    ("kwargs", "pointer"),
    [
        ({"tty": True, "env": {"HYPRCONF_NO_SUDO": "1"}}, "--no-packages"),
        ({}, "no terminal for the sudo prompt"),  # box.run closes stdin
    ],
)
def test_the_package_step_bows_out_of_sudo(box, kwargs, pointer) -> None:
    """Both gates of the module contract: --no-packages (what the post-update hook
    passes) and no terminal for the password prompt. Neither is a failure."""
    _terminal_stub(box)
    _kitty_missing(box)

    proc = box.run(INSTALL, **kwargs)
    assert proc.returncode == 0, proc.stderr
    assert pointer in proc.stdout
    assert "omarchy-pkg-add" not in box.commands
    assert box.files() == set()  # kitty absent, so nothing further happens either


def test_a_setter_that_reports_failure_is_retried_then_recorded(kitty) -> None:
    """omarchy-default-terminal has no `set -e` and exits with its closing
    omarchy-notification-send's status (:37), which fails with no shell to notify —
    after the list file is already written."""
    _terminal_stub(kitty, set_status=1)
    proc = kitty.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    assert not (kitty.home / ".local/state/hyprconf/terminal-applied").exists()
    assert (kitty.home / ".config/kitty/hyprconf.conf").exists()  # the run went on

    kitty.reset()
    assert kitty.run(INSTALL).returncode == 0
    assert (kitty.home / ".local/state/hyprconf/terminal-applied").exists()
    # It was already kitty, so the setter is never called a second time.
    assert not any(len(c) > 1 for c in kitty.calls_of("omarchy-default-terminal"))


# ------------------------------------------------------------------- undo


def test_undo_restores_stock(kitty) -> None:
    conf = kitty.home / ".config/kitty/kitty.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(UPGRADED_KITTY_CONF)
    assert kitty.run(INSTALL).returncode == 0
    kitty.reset()

    proc = kitty.undo("terminal-kitty")
    assert proc.returncode == 0, proc.stderr
    assert conf.read_text() == UPGRADED_KITTY_CONF
    assert not (kitty.home / ".config/kitty/hyprconf.conf").exists()
    assert not (kitty.home / ".local/state/hyprconf/terminal-applied").exists()
    # Back to Omarchy's stock terminal: /usr/share/xdg-terminal-exec/
    # hyprland-xdg-terminals.list names foot.desktop (omarchy-settings 4.0.3-1).
    assert ["omarchy-default-terminal", "foot"] in kitty.calls_of("omarchy-default-terminal")


def test_undo_of_a_kitty_conf_with_no_final_newline_leaves_that_one_byte(kitty) -> None:
    """The documented exception to "undo puts the file back as it was": the
    install has to terminate the last line before appending, and undo cannot
    tell that newline from one the user wrote. Everything else comes back, and
    Omarchy's own stub ends in a newline, so a stock box never reaches this."""
    conf = kitty.home / ".config/kitty/kitty.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("include theme.conf")  # no trailing newline

    assert kitty.run(INSTALL).returncode == 0
    assert conf.read_text() == "include theme.conf\n" + INCLUDE
    assert kitty.undo("terminal-kitty").returncode == 0
    assert conf.read_text() == "include theme.conf\n"


def test_undo_on_a_seeded_kitty_conf_leaves_omarchys_own_stub(kitty) -> None:
    assert kitty.run(INSTALL).returncode == 0
    assert kitty.undo("terminal-kitty").returncode == 0
    conf = kitty.home / ".config/kitty/kitty.conf"
    assert conf.read_text() == (kitty.omarchy / "config/kitty/kitty.conf").read_text()


def test_undo_leaves_a_terminal_the_user_chose_themselves(kitty) -> None:
    assert kitty.run(INSTALL).returncode == 0
    _terminal_stub(kitty, start="ghostty")
    kitty.reset()

    assert kitty.undo("terminal-kitty").returncode == 0
    assert not any(len(c) > 1 for c in kitty.calls_of("omarchy-default-terminal"))


def test_undo_is_safe_before_any_install(box) -> None:
    _terminal_stub(box)
    proc = box.undo("terminal-kitty")
    assert proc.returncode == 0, proc.stderr
    assert box.files() == set()


# ------------------------------------------------------------ the payload


def test_the_packages_file_is_plain_package_names(kitty) -> None:
    for line in (MODULE / "packages").read_text().splitlines():
        name = line.split("#", 1)[0].strip()
        if name:
            assert name.replace("-", "").isalnum(), line


def test_every_command_the_module_names_has_a_fake(kitty) -> None:
    """A command with no fake would reach the developer's real machine."""
    import re

    text = INSTALL.read_text()
    for name in sorted(set(re.findall(r"\bomarchy(?:-[a-z0-9]+)+\b", text))):
        assert name in kitty.fakes, name
