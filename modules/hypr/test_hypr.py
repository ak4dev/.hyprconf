"""The hypr module: the three ~/.config/hypr override copies, the seeded
monitor presets and the two tools the hotkeys run. The Lua is checked
statically because these files ARE the running config."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
OVERRIDES = ("bindings", "input", "looknfeel")
TOOLS = ("hyprconf-gaps", "hyprconf-monitor-preset")
# A hyprconf-* command named in a bind's dispatcher string.
TOOL_RE = re.compile(r'"(hyprconf-[\w-]+)(?:\s[^"]*)?"')
# omarchy-refresh-config, faithful to bin/omarchy-refresh-config:29,41-43: the
# shipped template over whatever is there, and no .bak when nothing is — the
# branch undo relies on.
REFRESH = 'mkdir -p "$HOME/.config/${1%/*}"\ncp "$OMARCHY_PATH/config/$1" "$HOME/.config/$1"\n'
# Keys Omarchy already binds to exactly what hyprconf wanted (pseudo, focus,
# workspace scroll, drag move/resize — default/hypr/bindings/tiling.lua): a
# restatement is drift the moment Omarchy retunes one.
OMARCHY_BINDS = (
    '" + P"|" + left"|" + right"|" + up"|" + down"|mouse_down|mouse_up|mouse:272|mouse:273'.split(
        "|"
    )
)
# Omarchy's media keys end by calling omarchy-osd (bin/omarchy-audio-output-
# volume:86, bin/omarchy-brightness-display:87), so a rebind — or an unbind,
# hence matching all code, not just binds — moves the level with no indicator.
OSD_KEYS = "XF86AudioRaiseVolume XF86AudioLowerVolume XF86AudioMute XF86AudioMicMute XF86MonBrightnessUp XF86MonBrightnessDown XF86AudioNext XF86AudioPrev XF86AudioPlay XF86AudioPause".split()


def _code(path: Path) -> str:
    return "\n".join(ln for ln in path.read_text().splitlines() if not ln.lstrip().startswith("--"))


def _binds(path: Path) -> list[str]:
    return [ln for ln in _code(path).splitlines() if re.search(r"\b(rebind|o\.bind)\s*\(", ln)]


def _stock_omarchy(box) -> Path:
    """Omarchy's own template at each override path, as every box carries it."""
    for name in OVERRIDES:
        box.omarchy_write(f"config/hypr/{name}.lua", f"-- omarchy stock {name}\n")
    (box.home / ".config" / "hypr").mkdir(parents=True, exist_ok=True)
    return box.home / ".config" / "hypr"


# --- the shipped Lua -------------------------------------------------------


def test_hypr_overrides_parse_as_lua() -> None:
    """A syntax error here is a broken desktop, not a failed test run."""
    luac = shutil.which("luac") or shutil.which("luac5.4")
    if luac is None:
        pytest.skip("no luac available to parse the Hyprland Lua config")
    for lua in sorted(MODULE.glob("*.lua")):
        proc = subprocess.run([luac, "-p", str(lua)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


def test_every_hyprconf_command_bound_ships_in_the_module() -> None:
    """Hyprland runs a bind whose target is missing as a silent no-op."""
    confs = sorted(MODULE.glob("*.lua"))
    assert confs, f"no .lua files under {MODULE}"
    missing = [
        f"{conf.name}: {tool}"
        for conf in confs
        for tool in TOOL_RE.findall(_code(conf))
        if not (MODULE / "bin" / tool).is_file()
    ]
    assert not missing, f"config binds commands the module does not ship: {missing}"


def test_looknfeel_and_input_state_only_deltas() -> None:
    """looknfeel loads after the theme's hyprland.lua: a shadow range, colour or render_power here would restate a default over the theme's own."""
    looknfeel = _code(MODULE / "looknfeel.lua")
    assert re.search(r"shadow\s*=\s*\{[^}]*\benabled\s*=\s*true", looknfeel)
    assert not re.search(r"shadow\s*=\s*\{[^}]*\b(range|color|render_power)\b", looknfeel)
    # The gestures.* tuning in input.lua is inert without a gesture bound to it.
    assert "hl.gesture(" in _code(MODULE / "input.lua")


def test_steam_is_tiled_and_only_the_friends_list_floats() -> None:
    """Window rules apply in order: the class-wide tile, then the popup."""
    code = _code(MODULE / "looknfeel.lua")
    tile = re.search(r'o\.window\("steam".*\btile = true', code)
    friends = re.search(r'o\.window\(.*"Friends List".*\bfloat = true', code)
    assert tile and friends and tile.start() < friends.start(), code
    assert not re.search(r'o\.window\("steam".*\bfloat = true', code)


@pytest.mark.parametrize("scope,forbidden", [("binds", OMARCHY_BINDS), ("code", OSD_KEYS)])
def test_bindings_leave_omarchys_own_keys_alone(scope: str, forbidden: list[str]) -> None:
    bindings = MODULE / "bindings.lua"
    text = "\n".join(_binds(bindings)) if scope == "binds" else _code(bindings)
    for key in forbidden:
        assert key not in text, f"{key} is Omarchy's own"
    # The resize keys are SHIFT+arrows — those stay: Omarchy swaps windows there.
    assert '" + SHIFT + left"' in "\n".join(_binds(bindings))


def test_every_binding_carries_a_description() -> None:
    """A description is what puts a key in the SUPER+K menu: hl.bind records none, o.bind does."""
    code = _code(MODULE / "bindings.lua")
    assert not re.search(r"\bhl\.bind\s*\(", code), "use rebind()/o.bind: the menu lists those"
    # rebind()'s own forwarding call (o.bind(keys, ...)) passes the parameter through.
    calls = [ln.strip() for ln in code.splitlines() if re.match(r"(rebind|o\.bind)\(", ln.strip())]
    calls = [ln for ln in calls if not ln.startswith("o.bind(keys")]
    assert calls
    for ln in calls:
        assert re.match(r'(rebind|o\.bind)\(.*?,\s*"', ln), f"no description: {ln}"


def test_app_keys_use_omarchys_launcher_idiom() -> None:
    """`{ omarchy = "terminal" }` is how Omarchy names omarchy-launch-terminal (default/hypr/helpers.lua `command_from`); a binary would pin what `omarchy default <kind>` moves."""
    joined = "\n".join(_binds(MODULE / "bindings.lua"))
    for launcher in ("terminal", "browser", "editor", "nautilus"):
        assert f'{{ omarchy = "{launcher}" }}' in joined, launcher
    rest = re.sub(r'\{ omarchy = "[a-z-]+" \}', "", joined)
    assert "omarchy-launch-" not in rest
    for binary in ('"firefox"', '"nautilus"', '"code"', '"kitty"', '"dolphin"'):
        assert binary not in rest, f"{binary} is an Omarchy default, not a keymap constant"


def test_rebind_itself_clears_omarchys_keycode_form() -> None:
    """Omarchy binds the digits and -/= by KEYCODE (default/hypr/bindings/tiling.lua:20-25,52-55), which an unbind of the keysym does not match — both would fire."""
    text = (MODULE / "bindings.lua").read_text()
    helper = re.search(r"local function rebind\(.*?\nend\n", text, re.S)
    assert helper, "rebind() not found in bindings.lua"
    assert "KEYCODE[" in helper.group(0) and 'code:"' in helper.group(0)
    table = re.search(r"local KEYCODE = \{(.*?)\}", text, re.S)
    assert table, "KEYCODE table not found"
    keys = set(re.findall(r'\["([a-z0-9]+)"\]\s*=\s*\d+', table.group(1)))
    keys |= set(re.findall(r"\b([a-z]+)\s*=\s*\d+", table.group(1)))
    assert {"minus", "equal"} | {str(d) for d in range(10)} <= keys, sorted(keys)


def test_desk_presets_are_description_keyed_serial_free_and_end_in_the_catch_all() -> None:
    """Never a connector (it renumbers when a cable moves between GPUs), never a serial (rule 4), catch-all last."""
    for name in ("pcMonitors.bedroom.lua", "pcMonitors.kitchen.lua"):
        code = _code(MODULE / name)
        outputs = re.findall(r'output = "([^"]*)"', code)
        monitors = re.findall(r'monitor = "([^"]+)"', code)
        assert outputs and monitors, f"{name}: no hl.monitor outputs or no workspace rules"
        for out in outputs:
            assert out == "" or out.startswith("desc:"), f"{name}: connector-keyed {out!r}"
        for mon in monitors:
            assert mon.startswith("desc:"), f"{name}: connector-keyed workspace rule {mon!r}"
        assert 'hl.monitor({ output = "", mode = "preferred"' in code, f"{name} has no catch-all"
        for desc in re.findall(r'"desc:([^"]+)"', code):  # serials: HCPW500583, 0x14821A42
            tail = desc.split()[-1]
            assert not re.fullmatch(r"0x[0-9A-Fa-f]{4,}", tail), f"{name}: serial in {desc!r}"
            assert not re.fullmatch(r"[A-Z]{2,}[0-9]{4,}[A-Z0-9]*", tail), f"{name}: {desc!r}"


def test_the_laptop_preset_states_only_what_stock_does_not() -> None:
    """Omarchy's monitors.lua ends in the `output = ""` catch-all (config/hypr/monitors.lua:8) and loads first."""
    code = _code(MODULE / "laptopMonitors.lua")
    outputs = re.findall(r'output = "([^"]*)"', code)
    assert outputs, "laptopMonitors.lua declares no hl.monitor outputs"
    assert "" not in outputs and not any(o.startswith("eDP") for o in outputs)
    assert all(re.search(r"scale = \d", ln) for ln in code.splitlines() if "hl.monitor(" in ln)


# --- install / undo --------------------------------------------------------


def _snapshot(home: Path) -> dict[str, tuple]:
    """`==` across two runs is "wrote nothing at all"; the inode matters — `ln -sfn` recreates a correct link."""
    out = {}
    for p in sorted(home.rglob("*")):
        st = p.lstat()
        out[str(p)] = (st.st_ino, st.st_mtime_ns, st.st_size, p.is_symlink() and os.readlink(p))
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


@pytest.mark.parametrize("kind", ["mine", "mine-link", "omarchy-template", "hyprconf-link"])
def test_only_a_file_of_the_users_own_is_kept_once_as_stock(box, kind: str) -> None:
    """Omarchy's template is what undo restores anyway and hyprconf's own link is ours; the user's file, or their dotfiles link (kept AS a link by cp -P), is what an overwrite would lose."""
    hypr = box.home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    dst, stock = hypr / "bindings.lua", hypr / "bindings.lua.stock"
    theirs = box.tmp / "dotfiles-bindings.lua"
    theirs.write_text("-- from my dotfiles\n")
    if kind == "mine":
        dst.write_text("-- my own bindings\n")
    elif kind == "mine-link":
        dst.symlink_to(theirs)
    elif kind == "omarchy-template":
        _stock_omarchy(box)
        dst.write_text("-- omarchy stock bindings\n")
    else:
        dst.symlink_to(MODULE.parent.parent / "hypr" / "bindings.lua")

    res = box.run(INSTALL)
    assert res.returncode == 0, res.stderr
    assert not dst.is_symlink() and dst.read_bytes() == (MODULE / "bindings.lua").read_bytes()
    if kind == "mine-link":
        assert stock.is_symlink() and stock.readlink() == theirs
        assert theirs.read_text() == "-- from my dotfiles\n"
    elif kind == "mine":
        assert stock.read_text() == "-- my own bindings\n"
        dst.write_text("-- edited on the copy\n")  # once: an edit costs no backup
        assert box.run(INSTALL).returncode == 0
        assert stock.read_text() == "-- my own bindings\n"
    else:
        assert not stock.exists() and not stock.is_symlink()
    assert not (hypr / "input.lua.stock").exists(), "nothing was there to keep"


def test_a_folder_with_no_preset_installs_the_rest(box) -> None:
    """nullglob is unset: without the `[[ -f ]]` guard the literal pattern fails the run half-applied."""
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
    """A preset describes one machine's desk: an edit survives every later run."""
    hypr = box.home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    mine = '-- this desk\nhl.monitor({ output = "DP-3", mode = "preferred" })\n'
    (hypr / "pcMonitors.bedroom.lua").write_text(mine)
    assert box.run(INSTALL).returncode == 0
    assert (hypr / "pcMonitors.bedroom.lua").read_text() == mine
    kitchen = MODULE / "pcMonitors.kitchen.lua"
    assert (hypr / kitchen.name).read_bytes() == kitchen.read_bytes()


def test_a_shipped_preset_that_moves_is_reported_once_and_still_never_applied(box) -> None:
    """A seeded preset is the machine's, so an improvement made here would otherwise
    stop at the checkout in silence — the bedroom TV lost its hl.monitor line that way.
    Only a change made HERE speaks, once per shipped version: an edit of your own never nags."""
    folder = box.tmp / "hypr-shipped"
    shutil.copytree(MODULE, folder, ignore=shutil.ignore_patterns("__pycache__"))
    shipped = folder / "pcMonitors.bedroom.lua"
    assert box.run(folder / "install").returncode == 0
    seeded = box.home / ".config" / "hypr" / shipped.name

    # An edit of your own: nothing here moved, so nothing is said about it.
    mine = seeded.read_text() + 'hl.monitor({ output = "desc:My Panel", mode = "preferred" })\n'
    seeded.write_text(mine)
    res = box.run(folder / "install")
    assert res.returncode == 0, res.stderr
    assert shipped.name not in res.stdout, f"an edit of your own nagged: {res.stdout}"

    # The shipped one moves: said once, and yours is left byte for byte.
    shipped.write_text(shipped.read_text() + "-- a better preset\n")
    res = box.run(folder / "install")
    assert res.returncode == 0, res.stderr
    assert f"{shipped.name} here has changed" in res.stdout, res.stdout
    assert seeded.read_text() == mine, "a seeded preset was overwritten"
    res = box.run(folder / "install")
    assert shipped.name not in res.stdout, f"said twice for one shipped version: {res.stdout}"
    assert seeded.read_text() == mine


def test_undo_puts_back_what_was_there_stock_files_first(box) -> None:
    """The .stock kept on the way in wins; otherwise the copy goes first, so omarchy-refresh-config takes its no-backup branch (:41-43) and leaves no .bak."""
    box.stub("omarchy-refresh-config", REFRESH)
    hypr = _stock_omarchy(box)
    (hypr / "bindings.lua").write_text("-- my own bindings\n")
    theirs = box.tmp / "dotfiles-input.lua"
    theirs.write_text("-- my own input\n")
    (hypr / "input.lua").symlink_to(theirs)
    assert box.run(INSTALL).returncode == 0
    box.reset()

    res = box.undo("hypr")
    assert res.returncode == 0, res.stderr
    assert (hypr / "bindings.lua").read_text() == "-- my own bindings\n"
    assert (hypr / "input.lua").is_symlink() and (hypr / "input.lua").readlink() == theirs
    assert (hypr / "looknfeel.lua").read_text() == "-- omarchy stock looknfeel\n"
    assert box.calls_of("omarchy-refresh-config") == [
        ["omarchy-refresh-config", "hypr/looknfeel.lua"]
    ]
    assert not sorted(hypr.glob("*.stock")), "a .stock survived the restore"
    assert not sorted(hypr.glob("*.bak.*")), "Omarchy backed up a file the overlay wrote"
    assert not sorted(hypr.glob("*Monitors*.lua")), "a seeded preset survived undo"
    marks = box.home / ".local" / "state" / "hyprconf"
    assert not sorted(marks.glob("*.shipped")), "a .shipped marker survived undo"
    for tool in TOOLS:
        assert not (box.home / ".local" / "bin" / tool).is_symlink()
    assert ["omarchy-hyprland-toggle", "hyprconf-monitor-preset", "off"] in box.calls_of(
        "omarchy-hyprland-toggle"
    )


def test_undo_on_a_machine_that_never_installed_is_a_no_op(box) -> None:
    """`hyprconf --undo` runs every module's undo, installed or not."""
    box.stub("omarchy-refresh-config", REFRESH)
    hypr = _stock_omarchy(box)
    res = box.undo("hypr")
    assert res.returncode == 0, res.stderr
    assert not list((box.home / ".local" / "bin").glob("*"))
    assert not list(hypr.glob("*Monitors*.lua"))
