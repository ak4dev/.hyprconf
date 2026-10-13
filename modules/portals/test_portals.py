"""modules/portals: input capture off through xdg-desktop-portal's per-user config — hyprland's
packaged file plus one line, rebuilt when that file changes, never over a config of the user's
own — and Omarchy's allow_token_by_default = true turned false; the portals restarted once per
run that changed something, a second run writing and calling nothing, and an undo that puts
Omarchy's seed value back."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import Box

INSTALL = Path(__file__).parent / "install"
PACKAGED = "[preferred]\ndefault=hyprland;gtk\n"
OFF = "org.freedesktop.impl.portal.InputCapture=none"
# Omarchy's seed, config/hypr/xdph.conf (4.0.4-1).
SEED = (
    "screencopy {\n"
    "    allow_token_by_default = true\n"
    "    custom_picker_binary = hyprland-preview-share-picker\n"
    "}\n"
)
RESTART = [
    "systemctl",
    "--user",
    "try-restart",
    "xdg-desktop-portal-hyprland.service",
    "xdg-desktop-portal.service",
]


def conf(box: Box) -> Path:
    return box.home / ".config/xdg-desktop-portal/hyprland-portals.conf"


def setup(box: Box, xdph: str | None = SEED, packaged: str | None = PACKAGED) -> Path:
    """Omarchy's seed in its tree and, as `xdph`, in ~/.config/hypr; the packaged portal config."""
    box.omarchy_write("config/hypr/xdph.conf", SEED)
    if packaged is not None:
        path = Path(box.env["_HYPRCONF_PORTALS"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(packaged)
    path = box.home / ".config/hypr/xdph.conf"
    if xdph is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(xdph)
    return path


def test_install_closes_both_and_restarts_the_portals_once(box: Box) -> None:
    xdph = setup(box)
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    header, *body = conf(box).read_text().splitlines()
    assert header.startswith("# hyprconf/portals: ") and "install undo" in header
    assert body == [*PACKAGED.splitlines(), OFF]
    assert xdph.read_text() == SEED.replace("= true", "= false")
    assert box.calls_of("systemctl") == [RESTART]


def test_a_second_run_writes_and_calls_nothing(box: Box) -> None:
    setup(box)
    box.run(INSTALL)
    before = box.snapshot()
    box.reset()
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert box.commands == [] and box.snapshot() == before and result.stdout == ""


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("    allow_token_by_default = 1", "    allow_token_by_default = false"),
        ("    allow_token_by_default=yes", "    allow_token_by_default=false"),
        ("    allow_token_by_default = on  ", "    allow_token_by_default = false"),
        ("screencopy:allow_token_by_default = true", "screencopy:allow_token_by_default = false"),
    ],
)
def test_every_spelling_of_true_turns_false_and_nothing_else_moves(
    box: Box, line: str, expected: str
) -> None:
    xdph = setup(box, xdph=f"# mine\n{line}\nscreencopy:max_fps = 60\n", packaged=None)
    assert box.run(INSTALL).returncode == 0
    assert xdph.read_text() == f"# mine\n{expected}\nscreencopy:max_fps = 60\n"
    assert box.calls_of("systemctl") == [RESTART]


@pytest.mark.parametrize(
    "text",
    [None, SEED.replace("= true", "= false"), "screencopy {\n    max_fps = 60\n}\n"],
    ids=["no-file", "already-false", "no-key"],
)
def test_an_xdph_conf_with_no_true_is_left_alone(box: Box, text: str | None) -> None:
    xdph = setup(box, xdph=text, packaged=None)
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert (xdph.read_text() if xdph.exists() else None) == text
    assert box.calls == [] and box.files() == ({xdph} if text is not None else set())


def test_a_changed_packaged_config_rebuilds_ours(box: Box) -> None:
    setup(box)
    box.run(INSTALL)
    Path(box.env["_HYPRCONF_PORTALS"]).write_text("[preferred]\ndefault=hyprland;gtk;kde\n")
    box.reset()
    assert box.run(INSTALL).returncode == 0
    assert conf(box).read_text().splitlines()[1:] == [
        "[preferred]",
        "default=hyprland;gtk;kde",
        OFF,
    ]
    assert box.calls_of("systemctl") == [RESTART]


@pytest.mark.parametrize("name", ["hyprland-portals.conf", "portals.conf"])
def test_a_portal_config_of_the_users_own_is_left_alone(box: Box, name: str) -> None:
    setup(box)
    theirs = box.home / ".config/xdg-desktop-portal" / name
    theirs.parent.mkdir(parents=True)
    theirs.write_text("[preferred]\ndefault=gtk\n")
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert theirs.read_text() == "[preferred]\ndefault=gtk\n" and "left alone" in result.stdout
    assert sorted(p.name for p in theirs.parent.iterdir()) == [name]
    assert box.run(INSTALL, "undo").returncode == 0
    assert theirs.read_text() == "[preferred]\ndefault=gtk\n"


def test_undo_puts_omarchys_seed_value_back_and_restarts_once(box: Box) -> None:
    xdph = setup(box)
    box.run(INSTALL)
    box.reset()
    result = box.undo("portals")
    assert result.returncode == 0, result.stderr
    assert not conf(box).parent.exists() and xdph.read_text() == SEED
    assert box.calls_of("systemctl") == [RESTART]


def test_undo_on_a_stock_box_that_never_installed_does_nothing(box: Box) -> None:
    setup(box)
    before = box.snapshot()
    assert box.undo("portals").returncode == 0
    assert box.calls == [] and box.snapshot() == before


def test_undo_leaves_false_when_omarchys_seed_has_no_true(box: Box) -> None:
    xdph = setup(box)
    box.run(INSTALL)
    box.omarchy_write("config/hypr/xdph.conf", "screencopy {\n}\n")
    assert box.undo("portals").returncode == 0
    assert xdph.read_text() == SEED.replace("= true", "= false")


def test_a_failed_restart_says_so_and_does_not_fail_the_run(box: Box) -> None:
    setup(box)
    box.stub("systemctl", "exit 1\n")
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert "log in again" in result.stdout
