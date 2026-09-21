"""modules/font — GeistMono Nerd Font as the system monospace, set once."""

from pathlib import Path

import pytest

INSTALL = Path(__file__).parent / "install"
FAMILY = "GeistMono Nerd Font"
MARKER = ".local/state/hyprconf/font-applied"
KITTY = ".config/kitty/kitty.conf"


def run(box, **kw):
    kw.setdefault("tty", True)
    return box.run(INSTALL, **kw)


# HYPRCONF_NO_SUDO (--no-packages) gates the package step alone: the package is already there, so the set-once still runs.
@pytest.mark.parametrize("env", [{}, {"HYPRCONF_NO_SUDO": "1"}])
def test_install_hands_the_family_to_omarchy_verbatim(box, env) -> None:
    proc = run(box, env=env)
    assert proc.returncode == 0, proc.stderr
    assert box.calls_of("omarchy-font-set") == [["omarchy-font-set", FAMILY]]
    assert (box.home / MARKER).exists()
    assert "fc-list" not in box.commands  # bin/omarchy-font-set:24-27 checks the name itself


def test_a_second_run_writes_nothing_and_sets_no_font(box) -> None:
    assert run(box).returncode == 0
    before = box.snapshot()
    box.reset()
    proc = run(box)
    assert proc.returncode == 0, proc.stderr
    assert box.snapshot() == before
    assert box.commands == ["omarchy-pkg-present"]


def test_undo_drops_the_marker_and_names_omarchys_own_font(box) -> None:
    assert run(box).returncode == 0
    box.reset()
    proc = box.undo("font")
    assert proc.returncode == 0, proc.stderr
    assert not (box.home / MARKER).exists()
    assert "omarchy font set 'JetBrainsMono Nerd Font'" in proc.stdout
    assert box.commands == []


@pytest.mark.parametrize("kw", [{"env": {"HYPRCONF_NO_SUDO": "1"}}, {"tty": False}])
def test_a_missing_package_without_sudo_points_and_exits_zero(box, kw) -> None:
    box.stub("omarchy-pkg-present", "exit 1\n")
    proc = run(box, **kw)
    assert proc.returncode == 0, proc.stderr
    assert "otf-geist-mono-nerd" in proc.stdout
    assert box.commands == ["omarchy-pkg-present"]
    assert not (box.home / MARKER).exists()


# rc=1 is rule 6: a failed `omarchy-pkg-add` still fails the module.
@pytest.mark.parametrize("rc", [0, 1])
def test_a_missing_package_goes_to_omarchy_pkg_add_and_a_failure_fails_the_module(box, rc) -> None:
    box.stub("omarchy-pkg-present", "exit 1\n")
    box.stub("omarchy-pkg-add", f"exit {rc}\n")
    assert run(box).returncode == rc
    assert box.calls_of("omarchy-pkg-add") == [["omarchy-pkg-add", "otf-geist-mono-nerd"]]
    assert ("omarchy-font-set" in box.commands) == (box.home / MARKER).exists() == (rc == 0)


def test_a_rejected_family_warns_and_writes_no_marker(box) -> None:
    box.stub("omarchy-font-set", "exit 1\n")
    proc = run(box)
    assert proc.returncode == 0, proc.stderr
    assert FAMILY in proc.stderr
    assert not (box.home / MARKER).exists()


def test_an_absent_kitty_conf_is_seeded_from_omarchys_stub_first(box) -> None:
    # bin/omarchy-font-set:33-40 creates it itself, holding font_family alone.
    box.stub("omarchy-font-set", 'printf "\\nfont_family %s\\n" "$1" >>~/' + KITTY)
    assert run(box).returncode == 0
    stub = (box.omarchy / "config/kitty/kitty.conf").read_text()
    assert (box.home / KITTY).read_text() == stub + f"\nfont_family {FAMILY}\n"
    assert (box.home / KITTY).stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize("case", ["no-kitty", "already-there"])
def test_the_seed_covers_only_an_absent_kitty_conf(box, case) -> None:
    before = None
    if case == "no-kitty":
        box.stub("omarchy-cmd-present", "exit 1\n")
    else:
        (box.home / KITTY).parent.mkdir(parents=True)
        before = "include theme.conf\nfont_family Mine\n"
        (box.home / KITTY).write_text(before)
    assert run(box).returncode == 0
    assert ((box.home / KITTY).read_text() if (box.home / KITTY).exists() else None) == before
