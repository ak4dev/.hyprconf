"""Every command a shipped Hyprland config binds must ship.

Hyprland runs a bind whose target is missing as a silent no-op, so a bin/
tool deleted while bindings.lua still names it never surfaces as an error.
The hotkey tools are bound by command name, the way Omarchy binds its own
(install.sh puts bin/hyprconf-* on ~/.local/bin), so every hyprconf-* name a
hypr/*.lua file binds is mapped back to bin/. Omarchy's own commands are out
of scope: only what the overlay ships is validated.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HYPR = REPO_ROOT / "hypr"
# A hyprconf-* command named in a bind's dispatcher string.
TOOL_RE = re.compile(r'"(hyprconf-[\w-]+)(?:\s[^"]*)?"')


def _code(path: Path) -> str:
    return "\n".join(ln.split("--", 1)[0] for ln in path.read_text(encoding="utf-8").splitlines())


def test_every_hyprconf_command_bound_ships_in_bin() -> None:
    confs = sorted(HYPR.glob("*.lua"))
    assert confs, f"no .lua files under {HYPR}"
    missing = [
        f"{conf.name}: {tool}"
        for conf in confs
        for tool in TOOL_RE.findall(_code(conf))
        if not (REPO_ROOT / "bin" / tool).is_file()
    ]
    assert not missing, "config binds commands the overlay does not ship:\n" + "\n".join(missing)


def test_the_hotkey_tools_are_bound_by_name() -> None:
    """The preset and gaps keys run bin/ tools by command name, nothing under
    ~/.config/hypr/ (README › bin)."""
    code = _code(HYPR / "bindings.lua")
    assert '"hyprconf-monitor-preset bedroom"' in code
    assert '"hyprconf-monitor-preset kitchen"' in code
    assert '"hyprconf-gaps +"' in code and '"hyprconf-gaps -"' in code
    assert "~/.config/hypr" not in code
