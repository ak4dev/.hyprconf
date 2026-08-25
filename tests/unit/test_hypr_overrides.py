"""Static checks over the shipped ~/.config/hypr override files (hypr/*.lua).

These files are symlinked over Omarchy's own override points and loaded after
its defaults, so they can only ever STATE deltas — and each delta this repo
promises must actually be in the file it says it is in.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HYPR = REPO_ROOT / "hypr"


def _code(path: Path) -> str:
    return "\n".join(
        ln
        for ln in path.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("--")
    )


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


def test_launchers_use_omarchys_own_idiom() -> None:
    """`{ omarchy = "terminal" }` is how Omarchy's own bindings name
    omarchy-launch-terminal (default/hypr/helpers.lua command_from,
    bindings/applications.lua); the four app keys use it rather than
    spelling the launcher out."""
    binds = _binds(HYPR / "bindings.lua")
    for key, launcher in (("T", "terminal"), ("F", "browser"), ("C", "editor"), ("E", "nautilus")):
        line = next(ln for ln in binds if f'" + {key}"' in ln)
        assert f'{{ omarchy = "{launcher}" }}' in line, line
    assert not any("omarchy-launch-" in ln for ln in binds)
