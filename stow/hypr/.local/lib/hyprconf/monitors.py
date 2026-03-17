"""hyprconf.monitors — read and write Hyprland monitor configuration.

Monitor lines live in monitors.conf (sourced from hyprland.conf).

Format:
    monitor = NAME, RESOLUTION@HZ, POSITION, SCALE[, extra_opts...]

Extra options (appended after scale, space-separated pairs):
    vrr, N            adaptive sync (0=off, 1=on, 2=fullscreen-only)
    bitdepth, N       bit depth (8, 10)
    cm, hdr|sdr       colour management mode
    sdrbrightness, F  HDR→SDR brightness multiplier
    sdrsaturation, F  HDR→SDR saturation multiplier
    transform, N      display transform (0-7, matching wlr transforms)
    mirror, NAME      mirror another monitor

Special resolution values:  preferred  highres  highrr  disable
Special position values:    auto  auto-right  auto-left  auto-up  auto-down
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .file_edit import read_lines, update_line, delete_line, append_block

# ─────────────────────────────────────────────────────────────────────────────
#  Paths
# ─────────────────────────────────────────────────────────────────────────────

_CFG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
MONITORS_FILE = _CFG / "hypr" / "monitors.conf"

# ─────────────────────────────────────────────────────────────────────────────
#  Data type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MonitorConfig:
    name:       str
    resolution: str          # e.g. "3840x2160@120" or "preferred" or "disable"
    position:   str          # e.g. "0x0" or "auto-right"
    scale:      str          # e.g. "1.5"
    extras:     str          # everything after scale on the original line
    file_path:  Path
    line_idx:   int
    raw_line:   str

    @property
    def is_disabled(self) -> bool:
        return self.resolution.strip().lower() == "disable"

    def to_line(self) -> str:
        """Regenerate the monitor = … line from current fields."""
        parts = f"monitor = {self.name}, {self.resolution}, {self.position}, {self.scale}"
        if self.extras:
            parts += f", {self.extras}"
        return parts


# ─────────────────────────────────────────────────────────────────────────────
#  Parsing
# ─────────────────────────────────────────────────────────────────────────────

_MONITOR_RE = re.compile(r"^monitor\s*=\s*(.+)$", re.IGNORECASE)


def read_monitor_configs(path: Optional[Path] = None) -> list[MonitorConfig]:
    """Parse monitor lines from *path* (default: monitors.conf).

    Returns a list of MonitorConfig objects.  Lines with fewer than 4
    comma-separated fields (e.g. ``monitor = DP-1, disable``) are included
    with empty position/scale/extras fields.
    """
    if path is None:
        path = MONITORS_FILE
    configs: list[MonitorConfig] = []
    lines = read_lines(path)
    for idx, raw in enumerate(lines):
        stripped = re.sub(r"(^|\s)#.*$", "", raw).strip()
        m = _MONITOR_RE.match(stripped)
        if not m:
            continue
        fields = [f.strip() for f in m.group(1).split(",")]
        name       = fields[0] if len(fields) > 0 else ""
        resolution = fields[1] if len(fields) > 1 else ""
        position   = fields[2] if len(fields) > 2 else ""
        scale      = fields[3] if len(fields) > 3 else ""
        extras     = ", ".join(fields[4:]) if len(fields) > 4 else ""
        configs.append(MonitorConfig(
            name=name, resolution=resolution, position=position,
            scale=scale, extras=extras,
            file_path=path, line_idx=idx, raw_line=raw,
        ))
    return configs


# ─────────────────────────────────────────────────────────────────────────────
#  Writers
# ─────────────────────────────────────────────────────────────────────────────

def upsert_monitor(name: str, resolution: str, position: str,
                   scale: str, extras: str = "",
                   file: Optional[Path] = None) -> bool:
    """Write or update a monitor line in *file* (default: monitors.conf).

    If a line for *name* already exists it is updated in-place; otherwise a
    new line is appended.  Returns True on success.
    """
    if file is None:
        file = MONITORS_FILE

    parts = f"monitor = {name}, {resolution}, {position}, {scale}"
    if extras.strip():
        parts += f", {extras.strip()}"

    existing = read_monitor_configs(file)
    for mc in existing:
        if mc.name == name:
            return update_line(file, mc.line_idx, parts)

    return append_block(file, parts)


def delete_monitor(file_path: Path, line_idx: int) -> bool:
    """Delete the monitor line at *line_idx* in *file_path*."""
    return delete_line(file_path, line_idx)


def enable_monitor(name: str, file: Optional[Path] = None) -> bool:
    """Switch a disabled monitor to ``preferred`` resolution."""
    if file is None:
        file = MONITORS_FILE
    existing = read_monitor_configs(file)
    for mc in existing:
        if mc.name == name and mc.is_disabled:
            return upsert_monitor(name, "preferred", "auto", "1", file=file)
    return False


def disable_monitor(name: str, file: Optional[Path] = None) -> bool:
    """Set a monitor to ``disable``."""
    if file is None:
        file = MONITORS_FILE
    existing = read_monitor_configs(file)
    for mc in existing:
        if mc.name == name:
            new_line = f"monitor = {name}, disable"
            return update_line(file, mc.line_idx, new_line)
    # Not found — append a disable line
    return append_block(file, f"monitor = {name}, disable")
