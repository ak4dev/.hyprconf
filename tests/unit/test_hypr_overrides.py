"""Static checks over the shipped ~/.config/hypr override files (hypr/*.lua).

These files are symlinked over Omarchy's own override points and loaded after
its defaults, so they can only ever STATE deltas — and each delta this repo
promises must actually be in the file it says it is in. They are also the
live config (AGENTS.md › Live files): every one must parse, and every command
a bind names must ship, since Hyprland runs a missing target as a no-op.
What each delta IS belongs to README › hypr/*.lua, not here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HYPR = REPO_ROOT / "hypr"
# A hyprconf-* command named in a bind's dispatcher string.
TOOL_RE = re.compile(r'"(hyprconf-[\w-]+)(?:\s[^"]*)?"')


def _code(path: Path) -> str:
    return "\n".join(
        ln
        for ln in path.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("--")
    )


def test_hypr_overrides_parse_as_lua() -> None:
    """A syntax error here is a broken desktop, not a failed test run."""
    luac = shutil.which("luac") or shutil.which("luac5.4")
    if luac is None:
        pytest.skip("no luac available to parse the Hyprland Lua config")
    for lua in sorted(HYPR.glob("*.lua")):
        proc = subprocess.run([luac, "-p", str(lua)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


def test_every_hyprconf_command_bound_ships_in_bin() -> None:
    """Hyprland runs a bind whose target is missing as a silent no-op, so a
    bin/ tool deleted while bindings.lua still names it never surfaces as an
    error. Omarchy's own commands are out of scope: only what the overlay
    ships is validated."""
    confs = sorted(HYPR.glob("*.lua"))
    assert confs, f"no .lua files under {HYPR}"
    missing = [
        f"{conf.name}: {tool}"
        for conf in confs
        for tool in TOOL_RE.findall(_code(conf))
        if not (REPO_ROOT / "bin" / tool).is_file()
    ]
    assert not missing, "config binds commands the overlay does not ship:\n" + "\n".join(missing)


def test_looknfeel_states_only_deltas_over_the_theme() -> None:
    """looknfeel.lua loads after Omarchy's defaults, which load after the
    active theme's hyprland.conf — so a shadow key set here restates
    Hyprland's default OVER the theme's own (lumon ships one). Enabling the
    shadow is the delta; its range, colour and render_power are the theme's.
    The tuned values themselves are README › hypr/*.lua's to record."""
    looknfeel = _code(HYPR / "looknfeel.lua")
    assert re.search(r"shadow\s*=\s*\{[^}]*\benabled\s*=\s*true", looknfeel)
    assert not re.search(r"shadow\s*=\s*\{[^}]*\b(range|color|render_power)\b", looknfeel), (
        "the shadow's range, colour and render_power are Hyprland's, or the theme's"
    )
    # The gestures.* tuning in input.lua is inert without a gesture bound to it.
    assert "hl.gesture(" in _code(HYPR / "input.lua")


def test_steam_is_tiled_like_everything_else() -> None:
    """The class-wide tile rule, then the Friends-List float, in that order
    (why: looknfeel.lua's own comment above the rules)."""
    code = _code(HYPR / "looknfeel.lua")
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
        # Omarchy's default/hypr/bindings/tiling.lua (4.0.0-1) already binds
        # these to exactly what hyprconf wanted: SUPER+P (pseudo), SUPER+arrows
        # (focus), SUPER+mouse_down/up (workspace scroll) and SUPER+mouse:272/273
        # (drag move/resize). A restatement is drift the moment Omarchy retunes
        # one — both were in this file once and were removed.
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
        # Volume, brightness and media keys stay on Omarchy's own binds: its
        # commands end by calling omarchy-osd, so a rebind — or an unbind —
        # changes the level with no on-screen indicator (README › Hotkeys).
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
    bindings = HYPR / "bindings.lua"
    text = "\n".join(_binds(bindings)) if scope == "binds" else _code(bindings)
    for key in forbidden:
        assert key not in text, f"{key} is Omarchy's own (tiling.lua, or the OSD keys)"
    # The resize keys are SHIFT+arrows — those stay: Omarchy swaps windows there.
    assert '" + SHIFT + left"' in "\n".join(_binds(bindings))


def test_every_binding_carries_a_description() -> None:
    """A description is what puts a key in Omarchy's SUPER+K keybindings
    menu: hl.bind records none, o.bind (and the rebind helper over it) does.
    The description is a literal string, so a top-level bind call whose
    second argument is not one has dropped it (the helper's own forwarding
    call is indented)."""
    code = _code(HYPR / "bindings.lua")
    assert not re.search(r"\bhl\.bind\s*\(", code), "use rebind()/o.bind: the menu lists those"
    calls = [ln for ln in code.splitlines() if re.match(r"(rebind|o\.bind)\(", ln)]
    assert calls
    for ln in calls:
        assert re.match(r'(rebind|o\.bind)\(.*?,\s*"[^"]+"\s*,', ln), f"no description: {ln}"


def test_app_keys_use_omarchys_launcher_idiom() -> None:
    """`{ omarchy = "terminal" }` is how Omarchy's own bindings name
    omarchy-launch-terminal (default/hypr/helpers.lua `command_from`): the app
    keys use it — never the launcher spelled out, never an app binary, which
    would pin a choice Omarchy's own `omarchy default <kind>` cannot move and
    skip uwsm-app scoping. Which key opens what is README › Hotkeys'."""
    binds = _binds(HYPR / "bindings.lua")
    joined = "\n".join(binds)
    for launcher in ("terminal", "browser", "editor", "nautilus"):
        assert f'{{ omarchy = "{launcher}" }}' in joined, launcher
    rest = re.sub(r'\{ omarchy = "[a-z-]+" \}', "", "\n".join(binds))
    assert "omarchy-launch-" not in rest
    for binary in ('"firefox"', '"nautilus"', '"code"', '"kitty"', '"dolphin"'):
        assert binary not in rest, f"{binary} is an Omarchy default, not a keymap constant"


def test_every_keycode_key_rebind_is_paired_with_its_unbind() -> None:
    """Omarchy binds digits and -/= by KEYCODE (`SUPER + SHIFT + code:20`),
    which `hl.unbind` of the keysym does not match — so a rebind of such a
    key without its `unbind_keycode(mods, key)` leaves Omarchy's bind live
    and both fire on every press (AGENTS › Known quirks calls the pairing
    load-bearing; nothing pinned it). Parsed textually: one bind per line is
    the file's own stated discipline."""
    text = (REPO_ROOT / "hypr" / "bindings.lua").read_text(encoding="utf-8")
    table = re.search(r"local KEYCODE = \{(.*?)\}", text, re.S)
    assert table, "KEYCODE table not found in bindings.lua"
    # Both spellings Lua allows: bracket-quoted digits and bare identifiers
    # (minus/equal) — missing the bare ones silently skipped exactly the
    # -/= rebinds this test exists for.
    keys = set(re.findall(r'\["([a-z0-9]+)"\]\s*=\s*\d+', table.group(1)))
    keys |= set(re.findall(r"\b([a-z]+)\s*=\s*\d+", table.group(1)))
    assert {"1", "minus", "equal"} <= keys, f"KEYCODE parse incomplete: {sorted(keys)}"
    checked = 0
    for m in re.finditer(r'rebind\(mainMod \.\. " \+ ([^"]+)"', text):
        tokens = m.group(1).split(" + ")
        key = tokens[-1]
        if key not in keys:
            continue
        mods = "mainMod" if len(tokens) == 1 else 'mainMod .. " + ' + " + ".join(tokens[:-1]) + '"'
        expected = f'unbind_keycode({mods}, "{key}")'
        assert expected in text, f"missing {expected} for rebind of {m.group(1)}"
        assert text.index(expected) < m.start(), f"{expected} must come before its rebind"
        checked += 1
    assert checked >= 4, "the digit/-/= rebinds the pairing exists for were not found"


# ---------------------------------------------------------------------------
# Monitor presets — the desc: convention
# ---------------------------------------------------------------------------

DESK_PRESETS = ("pcMonitors.bedroom.lua", "pcMonitors.kitchen.lua")


@pytest.mark.parametrize("name", DESK_PRESETS)
def test_desk_presets_are_description_keyed_serial_free_and_end_in_the_catch_all(
    name: str,
) -> None:
    """The three properties a desk preset has to have, all three of them
    written up in README › Monitor presets and in the preset's own header:
    displays named by `desc:` and never by a connector (which renumbers when a
    cable moves between GPUs), no serial in that description (PII, rule 4 —
    `desc:` prefix-matches "<make> <model> <serial>", so make + model is
    enough), and the `output = ""` catch-all last, so an unrecognised display
    comes up at its preferred mode instead of staying dark. `laptop` is not a
    desk preset: it describes no particular hardware."""
    code = _code(HYPR / name)
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
