"""modules/font — the system monospace font, set once.

Every run is against the `box` fixture (repo-root conftest.py): a throwaway
$HOME and a PATH whose `omarchy-*` are recording fakes, so no test can reach
the developer's fontconfig, kitty.conf or package database.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
FAMILY = "GeistMono Nerd Font"
STOCK = "JetBrainsMono Nerd Font"  # default/fontconfig/conf.avail/50-omarchy.conf:22-29


def marker(box) -> Path:
    return box.home / ".local" / "state" / "hyprconf" / "font-applied"


def snapshot(box) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in box.files()}


def run(box, *args, **kwargs):
    """A run from a terminal — the ordinary first install. Without `tty` the
    package half takes its no-terminal path (stdin is /dev/null in a box)."""
    kwargs.setdefault("tty", True)
    return box.run(INSTALL, *args, **kwargs)


# bin/omarchy-font-set:33-40 (Omarchy 4.0.3-1), the kitty half transcribed:
# with kitty on PATH it creates the user file when absent, holding nothing
# but font_family.
FONT_SET_KITTY = (
    "if [[ -f ~/.config/kitty/kitty.conf ]] || omarchy-cmd-present kitty; then\n"
    "  mkdir -p ~/.config/kitty\n"
    "  if grep -qE '^[[:space:]]*font_family[[:space:]]+' ~/.config/kitty/kitty.conf 2>/dev/null; then\n"
    '    sed --follow-symlinks -i -E "s/^[[:space:]]*font_family[[:space:]]+.*/font_family $1/" ~/.config/kitty/kitty.conf\n'
    "  else\n"
    "    printf '\\nfont_family %s\\n' \"$1\" >>~/.config/kitty/kitty.conf\n"
    "  fi\n"
    "fi\n"
)


def kitty_conf(box) -> Path:
    return box.home / ".config" / "kitty" / "kitty.conf"


def stub_conf(box) -> str:
    return (box.omarchy / "config" / "kitty" / "kitty.conf").read_text()


# --------------------------------------------------------------------------
# The font itself
# --------------------------------------------------------------------------


def test_the_family_goes_to_omarchy_verbatim(box) -> None:
    """One call, the literal family: bin/omarchy-font-set:24-27 greps fc-list
    itself and exits 1 on a name it does not know, so a second copy of that
    check here could only disagree with it."""
    proc = run(box)
    assert proc.returncode == 0, proc.stderr
    assert box.calls_of("omarchy-font-set") == [["omarchy-font-set", FAMILY]]
    assert marker(box).exists()
    # No fc-list of our own: the setter's own check is the only one.
    assert "fc-list" not in box.commands


def test_a_second_run_writes_nothing_and_sets_no_font(box) -> None:
    """The post-update hook re-runs this after every omarchy-update: the
    marker is what keeps a font the user picked later (AGENTS rule 5)."""
    assert run(box).returncode == 0
    before = snapshot(box)
    box.reset()

    proc = run(box)
    assert proc.returncode == 0, proc.stderr
    assert snapshot(box) == before
    # omarchy-pkg-present only asks; nothing on this run changes the machine.
    assert box.commands == ["omarchy-pkg-present"]


def test_a_rejected_family_warns_writes_no_marker_and_is_retried(box) -> None:
    """A box without the font package is the ordinary first-run case: the
    setter exits 1, and a cosmetic module must not die under set -e."""
    box.stub("omarchy-font-set", "exit 1\n")
    proc = run(box)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-font-set" in box.commands
    assert FAMILY in proc.stderr
    assert not marker(box).exists()

    box.stub("omarchy-font-set", "exit 0\n")
    box.reset()
    assert run(box).returncode == 0
    assert box.calls_of("omarchy-font-set") == [["omarchy-font-set", FAMILY]]
    assert marker(box).exists()


def test_the_marker_follows_the_hyprconf_state_seam(box) -> None:
    """`${HYPRCONF_STATE:-$HOME/.local/state/hyprconf}` — the module contract's
    one marker per user choice, relocatable for a test."""
    state = box.tmp / "state"
    assert run(box, env={"HYPRCONF_STATE": str(state)}).returncode == 0
    assert (state / "font-applied").exists()
    assert not marker(box).exists()


# --------------------------------------------------------------------------
# The package
# --------------------------------------------------------------------------


def test_the_package_is_installed_only_when_it_is_missing(box) -> None:
    """bin/omarchy-pkg-add:8-14 asks sudo only when omarchy-pkg-missing says
    so, but the guard here is what keeps a re-run free of sudo entirely."""
    box.stub("omarchy-pkg-present", "exit 1\n")
    assert run(box).returncode == 0
    assert box.calls_of("omarchy-pkg-add") == [["omarchy-pkg-add", "otf-geist-mono-nerd"]]

    box.stub("omarchy-pkg-present", "exit 0\n")
    box.reset()
    assert run(box).returncode == 0
    assert "omarchy-pkg-add" not in box.commands


def test_a_failed_package_install_fails_the_module(box) -> None:
    """No font without the font: omarchy-pkg-add exits 1 when pacman could
    not register the package (bin/omarchy-pkg-add:16-22), and the core's
    module loop is what reports it."""
    box.stub("omarchy-pkg-present", "exit 1\n")
    box.stub("omarchy-pkg-add", "exit 1\n")
    proc = run(box)
    assert proc.returncode != 0
    assert "omarchy-font-set" not in box.commands
    assert not marker(box).exists()


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"tty": True, "env": {"HYPRCONF_NO_SUDO": "1"}}, id="no-sudo"),
        pytest.param({"tty": False}, id="no-terminal"),
    ],
)
def test_a_missing_package_without_sudo_points_and_exits_zero(box, kwargs) -> None:
    """What --no-packages and the post-update hook pass, and what an ssh run
    has: one pointer line, no sudo, nothing half-applied."""
    box.stub("omarchy-pkg-present", "exit 1\n")
    proc = box.run(INSTALL, **kwargs)
    assert proc.returncode == 0, proc.stderr
    assert "otf-geist-mono-nerd" in proc.stdout
    assert box.commands == ["omarchy-pkg-present"]
    assert not marker(box).exists()


def test_the_font_is_still_set_without_sudo_once_the_package_is_there(box) -> None:
    """The hook's own path on a machine that already has the font: nothing
    needs sudo, so nothing is skipped."""
    proc = box.run(INSTALL, env={"HYPRCONF_NO_SUDO": "1"})
    assert proc.returncode == 0, proc.stderr
    assert box.calls_of("omarchy-font-set") == [["omarchy-font-set", FAMILY]]


def test_the_packages_file_holds_plain_package_names(box) -> None:
    """One official-repo package per line, comments stripped — the shape the
    install's own reader assumes (AGENTS rule 3: no AUR, no pacman)."""
    names = []
    for line in (MODULE / "packages").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(line)
    assert names == ["otf-geist-mono-nerd"]
    assert all(name.replace("-", "").isalnum() for name in names)


# --------------------------------------------------------------------------
# kitty.conf: the setter must not be the one to create it
# --------------------------------------------------------------------------


def test_an_absent_kitty_conf_is_seeded_from_omarchys_stub_before_the_setter(box) -> None:
    """omarchy-font-set creates ~/.config/kitty/kitty.conf itself when kitty
    is installed and the file is absent (:33-40) — holding only font_family,
    no theme include, which lives only in Omarchy's stub. Seeded first, so
    what the setter appends lands beside the include, not instead of it."""
    box.stub("omarchy-font-set", FONT_SET_KITTY)
    proc = run(box)
    assert proc.returncode == 0, proc.stderr
    assert kitty_conf(box).read_text() == stub_conf(box) + f"\nfont_family {FAMILY}\n"
    assert kitty_conf(box).stat().st_mode & 0o777 == 0o644


def test_without_kitty_no_kitty_conf_is_made(box) -> None:
    """The setter's own condition (`omarchy-cmd-present kitty`, :33): no
    kitty, no file — the module must not seed one either."""
    box.stub("omarchy-cmd-present", "exit 1\n")
    box.stub("omarchy-font-set", FONT_SET_KITTY)
    proc = run(box)
    assert proc.returncode == 0, proc.stderr
    assert not kitty_conf(box).exists()


def test_a_kitty_conf_already_there_is_left_to_the_setter(box) -> None:
    """The seed covers the absent file only: a file of the user's own is the
    setter's to edit (it rewrites or appends font_family, :35-39), never ours."""
    kitty_conf(box).parent.mkdir(parents=True)
    kitty_conf(box).write_text("include theme.conf\nfont_family Mine\n")
    proc = run(box)
    assert proc.returncode == 0, proc.stderr
    assert kitty_conf(box).read_text() == "include theme.conf\nfont_family Mine\n"


# --------------------------------------------------------------------------
# Undo
# --------------------------------------------------------------------------


def test_undo_drops_the_marker_and_names_omarchys_own_font(box) -> None:
    """The setter restarts the shell (bin/omarchy-font-set:74), so the revert
    is the user's command to run; the module only stops claiming the choice."""
    assert run(box).returncode == 0
    assert marker(box).exists()
    box.reset()

    proc = box.undo("font")
    assert proc.returncode == 0, proc.stderr
    assert not marker(box).exists()
    assert f"omarchy font set '{STOCK}'" in proc.stdout
    assert box.commands == []


def test_undo_on_a_machine_that_never_ran_the_module_is_a_no_op(box) -> None:
    proc = box.undo("font")
    assert proc.returncode == 0, proc.stderr
    assert box.files() == set()
    assert box.commands == []


def test_every_command_the_module_names_has_a_fake(box) -> None:
    """A call the box does not fake would reach the real machine."""
    import re

    named = set(re.findall(r"\bomarchy(?:-[a-z0-9]+)+\b", INSTALL.read_text()))
    assert named
    assert named <= box.fakes
