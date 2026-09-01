"""Static checks over the shipped ~/.config/hypr override files (hypr/*.lua).

These files are symlinked over Omarchy's own override points and loaded after
its defaults, so they can only ever STATE deltas — and each delta this repo
promises must actually be in the file it says it is in. They are also the
live config (AGENTS.md › Live files): every one must parse.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HYPR = REPO_ROOT / "hypr"


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


def test_natural_scroll_is_the_default() -> None:
    """Omarchy ships natural_scroll off for the mouse and off for the touchpad;
    input.lua turns both on (README › input.lua)."""
    assert _code(HYPR / "input.lua").count("natural_scroll = true") == 2


def test_steam_is_tiled_like_everything_else() -> None:
    """Omarchy floats every window of class "steam" (default/hypr/apps/steam.lua).
    looknfeel.lua is loaded after Omarchy's defaults and Hyprland applies rules
    in order, so its `tile = true` for the class wins; the Friends List, which
    Omarchy sizes as a floating panel, is re-floated after that. Shipped
    unconditionally — installed or not, Steam tiles from its first window."""
    code = _code(HYPR / "looknfeel.lua")
    tile = re.search(r'o\.window\(\s*"steam"\s*,\s*\{\s*tile\s*=\s*true\s*\}\s*\)', code)
    assert tile, 'looknfeel.lua must tile class steam with o.window("steam", { tile = true })'
    friends = re.search(
        r'o\.window\(\s*\{\s*class\s*=\s*"steam"\s*,\s*title\s*=\s*"Friends List"\s*\}\s*,\s*\{\s*float\s*=\s*true\s*\}\s*\)',
        code,
    )
    assert friends, "the Friends List popup must be re-floated after the tile rule"
    assert tile.start() < friends.start(), "the class-wide tile rule must come first"
    # Nothing else in the overlay floats Steam back.
    for lua in HYPR.glob("*.lua"):
        assert not re.search(r'o\.window\(\s*"steam"\s*,\s*\{[^}]*float\s*=\s*true', _code(lua)), (
            lua.name
        )


def _binds(path: Path) -> list[str]:
    return [ln for ln in _code(path).splitlines() if re.search(r"\b(rebind|o\.bind)\s*\(", ln)]


def test_bindings_never_restate_omarchys_own_binds() -> None:
    """Omarchy's default/hypr/bindings/tiling.lua (4.0.0-1) already binds
    SUPER+P (pseudo), SUPER+arrows (focus), SUPER+mouse_down/up (workspace
    scroll) and SUPER+mouse:272/273 (drag move/resize) to exactly what
    hyprconf wanted there. A restatement is drift the moment Omarchy retunes
    one, so bindings.lua carries only its deltas."""
    binds = "\n".join(_binds(HYPR / "bindings.lua"))
    for key in (
        '" + P"',
        '" + left"',
        '" + right"',
        '" + up"',
        '" + down"',
        "mouse_down",
        "mouse_up",
        "mouse:272",
        "mouse:273",
    ):
        assert key not in binds, f"{key} is Omarchy's own bind already (tiling.lua)"
    # The resize keys are SHIFT+arrows — those stay: Omarchy swaps windows there.
    assert '" + SHIFT + left"' in binds


def test_osd_keys_are_left_to_omarchy() -> None:
    """Volume, brightness and media keys stay on Omarchy's own binds: its
    commands end by calling omarchy-osd, so a rebind — or an unbind — changes
    the level with no on-screen indicator. Matched on code, not on the
    comments that name the keys."""
    code = _code(HYPR / "bindings.lua")
    for key in (
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
    ):
        assert key not in code, f"{key} must be left to Omarchy (it drives the OSD)"


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
    omarchy-launch-terminal (default/hypr/helpers.lua command_from,
    bindings/applications.lua): the four app keys use it — never the launcher
    spelled out, never an app binary, which would pin a choice Omarchy's own
    `omarchy default <kind>` cannot move and skip uwsm-app scoping."""
    binds = _binds(HYPR / "bindings.lua")
    for key, launcher in (("T", "terminal"), ("F", "browser"), ("C", "editor"), ("E", "nautilus")):
        line = next(ln for ln in binds if f'" + {key}"' in ln)
        assert f'{{ omarchy = "{launcher}" }}' in line, line
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
