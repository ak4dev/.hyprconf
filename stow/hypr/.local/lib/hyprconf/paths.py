"""hyprconf.paths — single source of truth for all XDG path constants.

Every module that needs a path to a Hyprland config file should import from
here rather than re-computing ``XDG_CONFIG_HOME`` locally.
"""

from __future__ import annotations

import os
from pathlib import Path

CFG_HOME: Path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
HYPR_DIR: Path = CFG_HOME / "hypr"

# User-managed config files (stow tree → ~/.config/hypr/)
# Hyprland's own compositor config: Lua as of 0.55+ (hyprlang `.conf` is
# deprecated since 0.56 and slated for removal ~0.57 — see
# docs/hyprland-reference.md). hypridle/hyprlock/hyprpaper are separate
# programs that are staying on hyprlang and keep their `.conf` constants.
HYPRLAND_CONF: Path = HYPR_DIR / "hyprland.lua"
KEYBINDS_FILE: Path = HYPR_DIR / "keybinds.lua"
MONITORS_FILE: Path = HYPR_DIR / "monitors.lua"
HYPRLOCK_FILE: Path = HYPR_DIR / "hyprlock.conf"
HYPRIDLE_FILE: Path = HYPR_DIR / "hypridle.conf"
HYPRPAPER_FILE: Path = HYPR_DIR / "hyprpaper.conf"

# Files written at runtime by hyprconf (each individually `pcall(require, …)`d
# from hyprland.lua — see try_require() there — so a missing one is a no-op,
# unlike hyprlang's "glob must match >=1 file" restriction)
OVERRIDES_FILE: Path = HYPR_DIR / "conf.d" / "local.lua"
WINRULES_FILE: Path = HYPR_DIR / "conf.d" / "windowrules.lua"
WKSPRULES_FILE: Path = HYPR_DIR / "conf.d" / "workspacerules.lua"
