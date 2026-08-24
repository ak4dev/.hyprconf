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
