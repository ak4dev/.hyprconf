"""The hypr module: three ~/.config/hypr override files, the seeded monitor
presets, and the two tools the hotkeys run.

The Lua is checked statically, because these files ARE the running config:
every one must parse, may state only deltas over Omarchy's defaults, and may
name only a command the module ships — Hyprland runs a missing target as a
silent no-op. The install script is checked on a `box`: the overrides land as
copies, a second run writes nothing at all, a seeded preset is never
overwritten, and `undo` hands each override back to Omarchy's own restore.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).parent
# A hyprconf-* command named in a bind's dispatcher string.
TOOL_RE = re.compile(r'"(hyprconf-[\w-]+)(?:\s[^"]*)?"')
OVERRIDES = ("bindings", "input", "looknfeel")
# omarchy-refresh-config, faithful to bin/omarchy-refresh-config:29,41-43: it
# creates the directory, then copies the shipped template over whatever is
# there (with no .bak when the user file is absent, which undo relies on).
REFRESH = (
    'mkdir -p "$(dirname "$HOME/.config/$1")"\ncp "$OMARCHY_PATH/config/$1" "$HOME/.config/$1"\n'
)
TOOLS = ("hyprconf-gaps", "hyprconf-monitor-preset")


def _code(path: Path) -> str:
    return "\n".join(
        ln
        for ln in path.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("--")
    )


# ---------------------------------------------------------------------------
# The shipped Lua
# ---------------------------------------------------------------------------


def test_hypr_overrides_parse_as_lua() -> None:
    """A syntax error here is a broken desktop, not a failed test run."""
    luac = shutil.which("luac") or shutil.which("luac5.4")
    if luac is None:
        pytest.skip("no luac available to parse the Hyprland Lua config")
    for lua in sorted(MODULE.glob("*.lua")):
        proc = subprocess.run([luac, "-p", str(lua)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


def test_every_hyprconf_command_bound_ships_in_the_module() -> None:
    """Hyprland runs a bind whose target is missing as a silent no-op, so a
    tool deleted while bindings.lua still names it never surfaces as an error.
    Omarchy's own commands are out of scope: only what the module ships."""
    confs = sorted(MODULE.glob("*.lua"))
    assert confs, f"no .lua files under {MODULE}"
    missing = [
        f"{conf.name}: {tool}"
        for conf in confs
        for tool in TOOL_RE.findall(_code(conf))
        if not (MODULE / "bin" / tool).is_file()
    ]
    assert not missing, "config binds commands the module does not ship:\n" + "\n".join(missing)


def test_looknfeel_states_only_deltas_over_the_theme() -> None:
    """looknfeel.lua loads after Omarchy's defaults, which load after the
    active theme's hyprland.lua — so a shadow key set here restates Hyprland's
    default OVER the theme's own (lumon ships one). Enabling the shadow is the
    delta; its range, colour and render_power are the theme's."""
    looknfeel = _code(MODULE / "looknfeel.lua")
    assert re.search(r"shadow\s*=\s*\{[^}]*\benabled\s*=\s*true", looknfeel)
    assert not re.search(r"shadow\s*=\s*\{[^}]*\b(range|color|render_power)\b", looknfeel), (
        "the shadow's range, colour and render_power are Hyprland's, or the theme's"
    )
    # The gestures.* tuning in input.lua is inert without a gesture bound to it.
    assert "hl.gesture(" in _code(MODULE / "input.lua")


def test_steam_is_tiled_like_everything_else() -> None:
    """The class-wide tile rule, then the Friends-List float, in that order
    (why: looknfeel.lua's own comment above the rules)."""
    code = _code(MODULE / "looknfeel.lua")
    tile = re.search(r'o\.window\("steam".*\btile = true', code)
    assert tile, 'looknfeel.lua must tile class steam: o.window("steam", { tile = true })'
    friends = re.search(r'o\.window\(.*"Friends List".*\bfloat = true', code)
    assert friends, "the Friends List popup must be re-floated after the tile rule"
    assert tile.start() < friends.start(), "the class-wide tile rule must come first"
    # Nothing floats the class back afterwards (window rules apply in order).
    assert not re.search(r'o\.window\("steam".*\bfloat = true', code)


def _binds(path: Path) -> list[str]:
    return [ln for ln in _code(path).splitlines() if re.search(r"\b(rebind|o\.bind)\s*\(", ln)]


@pytest.mark.parametrize(
    "scope,forbidden",
    [
        # The nine keys Omarchy already binds to exactly what hyprconf wanted:
        # SUPER+P (pseudo), SUPER+arrows (focus), SUPER+mouse (workspace
        # scroll, drag move/resize) — default/hypr/bindings/tiling.lua. A
        # restatement is drift the moment Omarchy retunes one. The five second
        # keys hyprconf keeps on purpose (SUPER+D, SUPER+L, SUPER+SHIFT+V,
        # SUPER+SHIFT+Escape, SUPER+SHIFT+BACKSPACE) are not here: hypr.0#7's
        # trim is the user's call, and it was declined.
        (
            "binds",
            (
                '" + P"',
                '" + left"',
                '" + right"',
                '" + up"',
                '" + down"',
                "mouse_down",
                "mouse_up",
                "mouse:272",
                "mouse:273",
            ),
        ),
        # Volume, brightness and media keys stay on Omarchy's own binds
        # (default/hypr/bindings/media.lua:2-9,24-29): its commands end by
        # calling omarchy-osd (bin/omarchy-audio-output-volume:86,
        # bin/omarchy-brightness-display:87), so a rebind — or an unbind —
        # changes the level with no on-screen indicator.
        # Matched over all code, not just binds, so an unbind is caught too.
        (
            "code",
            (
                "XF86AudioRaiseVolume",
                "XF86AudioLowerVolume",
                "XF86AudioMute",
                "XF86AudioMicMute",
                "XF86MonBrightnessUp",
                "XF86MonBrightnessDown",
                "XF86AudioNext",
                "XF86AudioPrev",
                "XF86AudioPlay",
                "XF86AudioPause",
            ),
        ),
    ],
    ids=["omarchys-own-binds", "osd-keys"],
)
def test_bindings_leave_omarchys_own_keys_alone(scope: str, forbidden: tuple[str, ...]) -> None:
    bindings = MODULE / "bindings.lua"
    text = "\n".join(_binds(bindings)) if scope == "binds" else _code(bindings)
    for key in forbidden:
        assert key not in text, (
            f"{key} is Omarchy's own (tiling.lua/utilities.lua, or the OSD keys)"
        )
    # The resize keys are SHIFT+arrows — those stay: Omarchy swaps windows there.
    assert '" + SHIFT + left"' in "\n".join(_binds(bindings))


def test_every_binding_carries_a_description() -> None:
    """A description is what puts a key in Omarchy's SUPER+K keybindings menu:
    hl.bind records none, o.bind (and the rebind helper over it) does. Every
    bind's second argument must be a string — the helper's own forwarding call
    passes the parameter through and is excluded by name."""
    code = _code(MODULE / "bindings.lua")
    assert not re.search(r"\bhl\.bind\s*\(", code), "use rebind()/o.bind: the menu lists those"
    calls = [
        ln.strip()
        for ln in code.splitlines()
        if re.match(r"(rebind|o\.bind)\(", ln.strip()) and not ln.strip().startswith("o.bind(keys")
    ]
    assert calls
    for ln in calls:
        assert re.match(r'(rebind|o\.bind)\(.*?,\s*"', ln), f"no description: {ln}"


def test_app_keys_use_omarchys_launcher_idiom() -> None:
    """`{ omarchy = "terminal" }` is how Omarchy's own bindings name
    omarchy-launch-terminal (default/hypr/helpers.lua `command_from`): the app
    keys use it — never the launcher spelled out, never an app binary, which
    would pin a choice Omarchy's own `omarchy default <kind>` cannot move and
    skip uwsm-app scoping."""
    binds = _binds(MODULE / "bindings.lua")
    joined = "\n".join(binds)
    for launcher in ("terminal", "browser", "editor", "nautilus"):
        assert f'{{ omarchy = "{launcher}" }}' in joined, launcher
    rest = re.sub(r'\{ omarchy = "[a-z-]+" \}', "", joined)
    assert "omarchy-launch-" not in rest
    for binary in ('"firefox"', '"nautilus"', '"code"', '"kitty"', '"dolphin"'):
        assert binary not in rest, f"{binary} is an Omarchy default, not a keymap constant"


def test_rebind_itself_clears_omarchys_keycode_form() -> None:
    """Omarchy binds the digits and -/= by KEYCODE (`SUPER + SHIFT + code:20`,
    default/hypr/bindings/tiling.lua:20-25,52-55), which an unbind of the
    keysym does not match — both would fire. rebind() does that unbind itself,
    so the pairing cannot be forgotten on a new key; nothing outside it may
    hand-roll one."""
    text = (MODULE / "bindings.lua").read_text(encoding="utf-8")
    helper = re.search(r"local function rebind\(.*?\nend\n", text, re.S)
    assert helper, "rebind() not found in bindings.lua"
    body = helper.group(0)
    assert "KEYCODE[" in body and 'code:"' in body, "rebind() no longer unbinds the keycode form"
    table = re.search(r"local KEYCODE = \{(.*?)\}", text, re.S)
    assert table, "KEYCODE table not found"
    keys = set(re.findall(r'\["([a-z0-9]+)"\]\s*=\s*\d+', table.group(1)))
    keys |= set(re.findall(r"\b([a-z]+)\s*=\s*\d+", table.group(1)))
    assert {"minus", "equal"} | {str(d) for d in range(10)} <= keys, sorted(keys)
    assert "unbind_keycode" not in text, "the fold into rebind() replaced the helper"


DESK_PRESETS = ("pcMonitors.bedroom.lua", "pcMonitors.kitchen.lua")


@pytest.mark.parametrize("name", DESK_PRESETS)
def test_desk_presets_are_description_keyed_serial_free_and_end_in_the_catch_all(
    name: str,
) -> None:
    """The three properties a desk preset has to have: displays named by
    `desc:` and never by a connector (which renumbers when a cable moves
    between GPUs), no serial in that description (PII, rule 4 — `desc:`
    prefix-matches "<make> <model> <serial>", so make + model is enough), and
    the `output = ""` catch-all last, so an unrecognised display comes up at
    its preferred mode instead of staying dark. `laptop` is not a desk preset:
    it describes no particular hardware, only "an external is plugged in"."""
    code = _code(MODULE / name)
    outputs = re.findall(r'output = "([^"]*)"', code)
    assert outputs, f"{name} declares no hl.monitor outputs"
    for out in outputs:
        assert out == "" or out.startswith("desc:"), f"{name}: connector-keyed output {out!r}"
    monitors = re.findall(r'monitor = "([^"]+)"', code)
    assert monitors, f"{name} carries no workspace rules"
    for mon in monitors:
        assert mon.startswith("desc:"), f"{name}: connector-keyed workspace rule {mon!r}"
    assert 'hl.monitor({ output = "", mode = "preferred"' in code, f"{name} has no catch-all"
    # Serials on this desk look like `HCPW500583` and `0x14821A42`.
    for desc in re.findall(r'"desc:([^"]+)"', code):
        tail = desc.split()[-1]
        assert not re.fullmatch(r"0x[0-9A-Fa-f]{4,}", tail), f"{name}: serial in {desc!r}"
        assert not re.fullmatch(r"[A-Z]{2,}[0-9]{4,}[A-Z0-9]*", tail), f"{name}: serial in {desc!r}"


def test_the_laptop_preset_states_only_what_stock_does_not() -> None:
    """`laptop` is a delta over Omarchy's own monitors.lua, which ends in
    `hl.monitor({ output = "", ... })` (config/hypr/monitors.lua:8) and is
    loaded before this toggle: restating that line, or the internal panel it
    already covers, would be the same layout `hyprconf-monitor-preset stock`
    gives. What is left is the one thing stock cannot do — an external at a
    forced scale."""
    code = _code(MODULE / "laptopMonitors.lua")
    outputs = re.findall(r'output = "([^"]*)"', code)
    assert outputs, "laptopMonitors.lua declares no hl.monitor outputs"
    assert "" not in outputs, "the catch-all is Omarchy's own monitors.lua line"
    assert not any(o.startswith("eDP") for o in outputs), "the internal panel is stock's"
    assert all(re.search(r"scale = \d", ln) for ln in code.splitlines() if "hl.monitor(" in ln)


# ---------------------------------------------------------------------------
# install / undo
# ---------------------------------------------------------------------------

INSTALL = MODULE / "install"


def _snapshot(home: Path) -> dict[str, tuple]:
    """Every path under $HOME with its inode, mtime, size and link target —
    `==` across two runs is "the second run wrote nothing at all". The inode
    matters: `ln -sfn` over a correct link recreates it with a new one."""
    out = {}
    for p in sorted(home.rglob("*")):
        st = p.lstat()
        target = os.readlink(p) if p.is_symlink() else None
        out[str(p.relative_to(home))] = (st.st_ino, st.st_mtime_ns, st.st_size, target)
    return out


def test_the_overrides_land_as_copies_and_the_presets_and_tools_follow(box) -> None:
    res = box.run(INSTALL)
    assert res.returncode == 0, res.stderr
    hypr = box.home / ".config" / "hypr"
    for name in OVERRIDES:
        landed = hypr / f"{name}.lua"
        assert landed.is_file() and not landed.is_symlink(), f"{name}.lua is not a copy"
        assert landed.read_bytes() == (MODULE / f"{name}.lua").read_bytes()
        assert landed.stat().st_mode & 0o777 == 0o644
    presets = sorted(MODULE.glob("*Monitors*.lua"))
    assert presets, "the module ships no monitor presets"
    for preset in presets:
        assert (hypr / preset.name).read_bytes() == preset.read_bytes()
    for tool in TOOLS:
        link = box.home / ".local" / "bin" / tool
        assert link.is_symlink() and link.resolve() == MODULE / "bin" / tool
    # The copies are only live after a reload; nothing else is called.
    assert box.commands == ["hyprctl"], box.calls
    assert not (hypr / "monitors.lua").exists(), "Omarchy's own monitors.lua is not this module's"


def test_a_second_run_writes_nothing_and_calls_nothing(box) -> None:
    """The post-update hook re-runs every module after every omarchy-update."""
    assert box.run(INSTALL).returncode == 0
    before = _snapshot(box.home)
    box.reset()

    res = box.run(INSTALL)
    assert res.returncode == 0, res.stderr
    assert _snapshot(box.home) == before
    assert box.commands == [], box.calls


def test_a_pre_module_symlink_is_replaced_by_a_file(box) -> None:
    """Before the module split these three paths were symlinks into the
    checkout, which is what made `omarchy refresh` write through them."""
    hypr = box.home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    checkout = box.tmp / "checkout"
    checkout.mkdir()
    (checkout / "bindings.lua").write_text("-- the pre-module checkout\n")
    (hypr / "bindings.lua").symlink_to(checkout / "bindings.lua")

    assert box.run(INSTALL).returncode == 0
    landed = hypr / "bindings.lua"
    assert not landed.is_symlink()
    assert landed.read_bytes() == (MODULE / "bindings.lua").read_bytes()
    assert (checkout / "bindings.lua").read_text() == "-- the pre-module checkout\n"


def test_a_folder_with_no_preset_installs_the_rest(box) -> None:
    """The seed list is a glob and nullglob is unset, so with no
    *Monitors*.lua beside the install the pattern comes back as itself:
    without the `[[ -f ]]` guard `install -m 644 '<dir>/*Monitors*.lua'` fails
    the run half-applied — the overrides written, the tools not yet linked."""
    folder = box.tmp / "no-presets"
    shutil.copytree(MODULE, folder, ignore=shutil.ignore_patterns("*Monitors*.lua", "__pycache__"))
    res = box.run(folder / "install")
    assert res.returncode == 0, res.stderr
    hypr = box.home / ".config" / "hypr"
    assert not sorted(hypr.glob("*Monitors*.lua")), "a preset appeared from nowhere"
    for name in OVERRIDES:
        assert (hypr / f"{name}.lua").is_file()
    for tool in TOOLS:
        assert (box.home / ".local" / "bin" / tool).is_symlink(), f"{tool} never got linked"


def test_a_seeded_preset_is_never_overwritten(box) -> None:
    """A preset describes one machine's desk, so once it exists it is that
    machine's — the hotkey tool promises an edit survives re-selecting it."""
    hypr = box.home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    mine = '-- this desk\nhl.monitor({ output = "DP-3", mode = "preferred" })\n'
    (hypr / "pcMonitors.bedroom.lua").write_text(mine)

    assert box.run(INSTALL).returncode == 0
    assert (hypr / "pcMonitors.bedroom.lua").read_text() == mine
    assert (hypr / "pcMonitors.kitchen.lua").read_bytes() == (
        MODULE / "pcMonitors.kitchen.lua"
    ).read_bytes()


def test_undo_hands_each_override_back_to_omarchys_own_restore(box) -> None:
    """Undo is Omarchy's own restore command, not a backup this module kept:
    the copy is removed first so omarchy-refresh-config takes its no-backup
    branch (bin/omarchy-refresh-config:41-43) and leaves no .bak behind."""
    box.stub("omarchy-refresh-config", REFRESH)
    for name in OVERRIDES:
        box.omarchy_write(f"config/hypr/{name}.lua", f"-- omarchy stock {name}\n")
    assert box.run(INSTALL).returncode == 0
    box.reset()

    res = box.undo("hypr")
    assert res.returncode == 0, res.stderr
    hypr = box.home / ".config" / "hypr"
    for name in OVERRIDES:
        assert (hypr / f"{name}.lua").read_text() == f"-- omarchy stock {name}\n"
    assert not sorted(hypr.glob("*.bak.*")), "Omarchy backed up a file the overlay wrote"
    assert not sorted(hypr.glob("*Monitors*.lua")), "a seeded preset survived undo"
    for tool in TOOLS:
        assert not (box.home / ".local" / "bin" / tool).is_symlink()
    assert box.commands.count("omarchy-refresh-config") == len(OVERRIDES)
    # The preset toggle goes through Omarchy's own off, not an rm here.
    assert ["omarchy-hyprland-toggle", "hyprconf-monitor-preset", "off"] in box.calls_of(
        "omarchy-hyprland-toggle"
    )


def test_undo_on_a_machine_that_never_installed_is_a_no_op(box) -> None:
    """`install undo` from the core runs for every module, installed or not."""
    box.stub("omarchy-refresh-config", REFRESH)
    for name in OVERRIDES:
        box.omarchy_write(f"config/hypr/{name}.lua", f"-- omarchy stock {name}\n")
    res = box.undo("hypr")
    assert res.returncode == 0, res.stderr
    assert not list((box.home / ".local" / "bin").glob("*"))
    assert not list((box.home / ".config" / "hypr").glob("*Monitors*.lua"))
