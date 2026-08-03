"""hyprconf.monitors — read and write Hyprland monitor configuration.

Monitor lines live in ``monitors.lua`` (a symlink to the active preset,
``require``d from ``hyprland.lua``). Hyprland 0.55+ replaced the positional
``monitor = NAME, RES@HZ, POS, SCALE[, extras...]`` line with a single
``hl.monitor({ output=, mode=, position=, scale=, … })`` table call — one
call per line (matching the official example config's style), so entries
stay addressable by ``(file_path, line_idx)`` exactly as before.

The public :class:`MonitorConfig` shape (name/resolution/position/scale/extras
as flat strings) is kept unchanged from the hyprlang-era API so the TUI's
field-level get/set code (used by the "configure monitor" screen) needs no
changes — only the on-disk read/write format underneath it changed.

Format:
    hl.monitor({ output = NAME, mode = "RESOLUTION@HZ", position = "POSITION",
                 scale = SCALE[, vrr = N, bitdepth = N, cm = "…",
                 sdrbrightness = F, sdrsaturation = F, transform = N,
                 mirror = "…"] })
    A disabled output uses ``disabled = true`` instead of ``mode`` — exposed
    here as ``resolution == "disable"`` for API compatibility.

Special resolution values:  preferred  highres  highrr  disable
Special position values:    auto  auto-right  auto-left  auto-up  auto-down
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import lua_syntax
from .file_edit import append_block, delete_line, read_lines, strip_comment, update_line
from .paths import MONITORS_FILE

# ─────────────────────────────────────────────────────────────────────────────
#  Data type
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class MonitorConfig:
    name: str
    resolution: str  # e.g. "3840x2160@120" or "preferred" or "disable"
    position: str  # e.g. "0x0" or "auto-right"
    scale: str  # e.g. "1.5"
    extras: str  # flat "key, value, key, value" text — same shape as the hyprlang era
    file_path: Path
    line_idx: int
    raw_line: str

    @property
    def is_disabled(self) -> bool:
        return self.resolution.strip().lower() == "disable"

    def to_line(self) -> str:
        """Regenerate the ``hl.monitor({ … })`` line from current fields."""
        table = _fields_to_table(self.name, self.resolution, self.position, self.scale, self.extras)
        return "hl.monitor(" + lua_syntax.format_lua_literal(table) + ")"


# ─────────────────────────────────────────────────────────────────────────────
#  Parsing — permissive reader: legacy hyprlang OR new Lua form
# ─────────────────────────────────────────────────────────────────────────────

_LEGACY_MONITOR_RE = re.compile(r"^monitor\s*=\s*(.+)$", re.IGNORECASE)
_LUA_MONITOR_RE = re.compile(r"^(?:local\s+\w+\s*=\s*)?hl\.monitor\((.*)\)\s*$")

_EXTRAS_FIELDS = frozenset(
    {"vrr", "bitdepth", "cm", "sdrbrightness", "sdrsaturation", "transform", "mirror"}
)
_MONITOR_FIELDS = ("res", "pos", "scale") + tuple(sorted(_EXTRAS_FIELDS))


def _table_to_fields(table: dict[str, object]) -> tuple[str, str, str, str, str]:
    name = str(table.get("output", ""))
    resolution = "disable" if table.get("disabled") is True else str(table.get("mode", ""))
    position = str(table.get("position", ""))
    scale = str(table.get("scale", ""))
    extras_raw = {k: str(v) for k, v in table.items() if k in _EXTRAS_FIELDS}
    extras = _build_extras(extras_raw)
    return name, resolution, position, scale, extras


def read_monitor_configs(path: Path | None = None) -> list[MonitorConfig]:
    """Parse monitor entries from *path* (default: monitors.lua).

    Returns a list of MonitorConfig objects.
    """
    if path is None:
        path = MONITORS_FILE
    configs: list[MonitorConfig] = []
    strip_fn = lua_syntax.strip_lua_comment if path.suffix == ".lua" else strip_comment
    lines = read_lines(path)
    for idx, raw in enumerate(lines):
        stripped = strip_fn(raw)
        if not stripped:
            continue

        m_lua = _LUA_MONITOR_RE.match(stripped)
        if m_lua:
            table = {
                k: lua_syntax.lua_literal_to_py(v)
                for k, v in lua_syntax.parse_flat_table(m_lua.group(1)).items()
            }
            name, resolution, position, scale, extras = _table_to_fields(table)
            configs.append(
                MonitorConfig(
                    name=name,
                    resolution=resolution,
                    position=position,
                    scale=scale,
                    extras=extras,
                    file_path=path,
                    line_idx=idx,
                    raw_line=raw,
                )
            )
            continue

        m_legacy = _LEGACY_MONITOR_RE.match(stripped)
        if m_legacy:
            fields = [f.strip() for f in m_legacy.group(1).split(",")]
            configs.append(
                MonitorConfig(
                    name=fields[0] if len(fields) > 0 else "",
                    resolution=fields[1] if len(fields) > 1 else "",
                    position=fields[2] if len(fields) > 2 else "",
                    scale=fields[3] if len(fields) > 3 else "",
                    extras=", ".join(fields[4:]) if len(fields) > 4 else "",
                    file_path=path,
                    line_idx=idx,
                    raw_line=raw,
                )
            )
    return configs


# ─────────────────────────────────────────────────────────────────────────────
#  Writers
# ─────────────────────────────────────────────────────────────────────────────

_EXTRAS_INT_FIELDS = {"vrr", "bitdepth", "transform"}
_EXTRAS_FLOAT_FIELDS = {"sdrbrightness", "sdrsaturation"}


def _coerce_extra_value(key: str, value: str) -> object:
    if key in _EXTRAS_INT_FIELDS:
        try:
            return int(value)
        except ValueError:
            return value
    if key in _EXTRAS_FLOAT_FIELDS:
        try:
            return float(value)
        except ValueError:
            return value
    return value  # cm / mirror stay strings


def _coerce_scale(value: str) -> object:
    if value.strip().lower() == "auto":
        return value.strip()
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def _fields_to_table(name: str, resolution: str, position: str, scale: str, extras: str) -> dict[str, object]:
    table: dict[str, object] = {"output": name}
    if resolution.strip().lower() == "disable":
        table["disabled"] = True
    elif resolution.strip():
        table["mode"] = resolution.strip()
    if position.strip():
        table["position"] = position.strip()
    if scale.strip():
        table["scale"] = _coerce_scale(scale.strip())
    for k, v in _parse_extras_dict(extras).items():
        table[k] = _coerce_extra_value(k, v)
    return table


def upsert_monitor(
    name: str,
    resolution: str,
    position: str,
    scale: str,
    extras: str = "",
    file: Path | None = None,
) -> bool:
    """Write or update a monitor entry in *file* (default: monitors.lua).

    If an entry for *name* already exists it is updated in-place; otherwise a
    new entry is appended. Returns True on success.
    """
    if file is None:
        file = MONITORS_FILE

    line = "hl.monitor(" + lua_syntax.format_lua_literal(
        _fields_to_table(name, resolution, position, scale, extras)
    ) + ")"

    existing = read_monitor_configs(file)
    for mc in existing:
        if mc.name == name:
            return update_line(file, mc.line_idx, line)

    return append_block(file, line)


def delete_monitor(file_path: Path, line_idx: int) -> bool:
    """Delete the monitor entry at *line_idx* in *file_path*."""
    return delete_line(file_path, line_idx)


# ─────────────────────────────────────────────────────────────────────────────
#  Field-level get / set  (used by CLI configure interface)
# ─────────────────────────────────────────────────────────────────────────────


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
