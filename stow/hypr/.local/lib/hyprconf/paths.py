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
HYPRLAND_CONF:  Path = HYPR_DIR / "hyprland.conf"
KEYBINDS_FILE:  Path = HYPR_DIR / "keybinds.conf"
MONITORS_FILE:  Path = HYPR_DIR / "monitors.conf"
HYPRLOCK_FILE:  Path = HYPR_DIR / "hyprlock.conf"
HYPRIDLE_FILE:  Path = HYPR_DIR / "hypridle.conf"
HYPRPAPER_FILE: Path = HYPR_DIR / "hyprpaper.conf"

# Files written at runtime by hyprconf (conf.d glob)
OVERRIDES_FILE: Path = HYPR_DIR / "conf.d" / "99-hyprconf-local.conf"
WINRULES_FILE:  Path = HYPR_DIR / "conf.d" / "50-windowrules.conf"
WKSPRULES_FILE: Path = HYPR_DIR / "conf.d" / "50-workspacerules.conf"
