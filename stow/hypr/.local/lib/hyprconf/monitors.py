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

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .file_edit import read_lines, update_line, delete_line, append_block, strip_comment
from .paths import MONITORS_FILE

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
        stripped = strip_comment(raw)
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


# ─────────────────────────────────────────────────────────────────────────────
#  Field-level get / set  (used by CLI configure interface)
# ─────────────────────────────────────────────────────────────────────────────

_EXTRAS_FIELDS = frozenset(
    {"vrr", "bitdepth", "cm", "sdrbrightness", "sdrsaturation", "transform", "mirror"}
)

_MONITOR_FIELDS = ("res", "pos", "scale") + tuple(sorted(_EXTRAS_FIELDS))


def _parse_extras_dict(extras: str) -> dict[str, str]:
    """Parse ``'vrr, 2, bitdepth, 10'`` → ``{'vrr': '2', 'bitdepth': '10'}``."""
    tokens = [t.strip() for t in extras.split(",") if t.strip()]
    result: dict[str, str] = {}
    i = 0
    while i + 1 < len(tokens):
        result[tokens[i].lower()] = tokens[i + 1]
        i += 2
    return result


def _build_extras(d: dict[str, str]) -> str:
    """Rebuild an extras string from a dict, preserving the canonical field order."""
    pairs: list[str] = []
    for key in sorted(_EXTRAS_FIELDS):  # stable output order
        if key in d:
            pairs.append(f"{key}, {d[key]}")
    return ", ".join(pairs)


def get_monitor_fields(name: Optional[str] = None,
                       file: Optional[Path] = None) -> str:
    """Return a formatted table of configured monitors (or a single monitor).

    Output is a human-readable string suitable for terminal display.
    """
    configs = read_monitor_configs(file)
    if name:
        configs = [c for c in configs if c.name == name]
        if not configs:
            return f"  Monitor '{name}' not found in monitors.conf."

    if not configs:
        return "  No monitor configs found."

    lines: list[str] = []
    for mc in configs:
        ex = _parse_extras_dict(mc.extras)
        lines.append(f"\n  {mc.name}")
        lines.append(f"    {'res':<16} {mc.resolution}")
        lines.append(f"    {'pos':<16} {mc.position}")
        lines.append(f"    {'scale':<16} {mc.scale}")
        for f in sorted(_EXTRAS_FIELDS):
            val = ex.get(f, "")
            if val or name:  # always show all fields when querying one monitor
                lines.append(f"    {f:<16} {val or '(unset)'}")
    return "\n".join(lines)


def update_monitor_field(name: str, field: str, value: str,
                         file: Optional[Path] = None) -> bool:
    """Update a single field of an existing monitor config.

    Handles the three basic positional fields (res, pos, scale) directly and
    routes all other fields through the extras string.  If the monitor is not
    yet in monitors.conf, a new entry is created with sensible defaults for
    the fields that are not being set.

    Returns True on success.
    """
    field = field.lower()
    if field not in _MONITOR_FIELDS:
        raise ValueError(
            f"Unknown monitor field '{field}'. Valid: {', '.join(sorted(_MONITOR_FIELDS))}"
        )

    configs = read_monitor_configs(file)
    mc = next((c for c in configs if c.name == name), None)

    if mc is None:
        # No existing entry — create a minimal one first
        res   = value if field == "res"   else "preferred"
        pos   = value if field == "pos"   else "auto"
        scale = value if field == "scale" else "1"
        extras = ""
        if field in _EXTRAS_FIELDS:
            extras = f"{field}, {value}"
        return upsert_monitor(name, res, pos, scale, extras, file=file)

    # Update in-place
    res, pos, scale = mc.resolution, mc.position, mc.scale
    ex = _parse_extras_dict(mc.extras)

    if field == "res":
        res = value
    elif field == "pos":
        pos = value
    elif field == "scale":
        scale = value
    else:
        ex[field] = value

    return upsert_monitor(name, res, pos, scale, _build_extras(ex), file=file)
