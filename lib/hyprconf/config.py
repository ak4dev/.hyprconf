"""
hyprconf.config — unified config reader and writer.

Both the CLI and TUI use these functions exclusively for all persistent
storage.  The single canonical overrides file is:

    ~/.config/hypr/conf.d/local.lua

This file is individually ``require``d by ``hyprland.lua`` (via
``try_require`` — see there) and survives restarts. It is managed in a
two-zone format:

    [user-written content, preserved verbatim]

    -- hyprconf-managed
    hl.config({
        decoration = {
            blur = {
                enabled = true,
            },
        },
        general = {
            gaps_in = 8,
        },
    })

The managed block is entirely regenerated on each write; the user zone
above it is never touched. Unlike the hyprlang era (flat ``section:key =
value`` lines), the managed block is a single nested ``hl.config({...})``
call — values are typed (bool/int/float/str) using ``hyprconf.schema``'s
option metadata, since Lua (unlike hyprlang) distinguishes quoted strings
from bare numbers/booleans.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import lua_syntax
from .file_edit import atomic_write_text
from .paths import HYPR_DIR as _HYPR_DIR
from .paths import OVERRIDES_FILE
from .schema import OPTION_SCHEMA

# ── Paths ──────────────────────────────────────────────────────────────────────

LEGACY_OVERRIDES_FILE: Path = _HYPR_DIR / "hyprconf.local.conf"
_CONF_ERA_OVERRIDES_FILE: Path = _HYPR_DIR / "conf.d" / "99-hyprconf-local.conf"

MANAGED_MARKER: str = "-- hyprconf-managed"
# Markers written by older (hyprlang-era) hyprconf versions — recognised on
# read, replaced on write.
_LEGACY_MARKERS: tuple[str, ...] = ("# hyprconf-managed", "# hyprconf-tui managed")

# ── Key formatting ─────────────────────────────────────────────────────────────


def section_key_to_hyprctl(section: str, key: str) -> str:
    """Convert section + key to the colon-separated path hyprctl getoption uses.

    Examples:
        general, gaps_in          →  general:gaps_in
        decoration.blur, enabled  →  decoration:blur:enabled
    """
    return section.replace(".", ":") + ":" + key


def _flat_key(section: str, key: str) -> str:
    """The managed block's internal flat key: every path segment colon-joined.

    A dotted key nests exactly like a dotted section in the Lua API
    (``general.col.active_border`` is ``general = { col = { active_border
    = … } }`` — see Omarchy's default/hypr/looknfeel.lua), so the key's own
    dots become separators too: ``general:col:active_border``. That is also
    what :func:`_flatten_config_call` reads back from the nested table, so
    a merge never sees the same option under two spellings.
    """
    return (section + "." + key).replace(".", ":")


def _split_flat_key(hkey: str) -> tuple[str, str]:
    """Reverse of :func:`_flat_key`, schema-aware: ``general:col:active_border``
    → ``("general", "col.active_border")`` because that is the (section, key)
    pair ``OPTION_SCHEMA`` knows; an unknown path splits on its last segment."""
    parts = hkey.split(":")
    for i in range(len(parts) - 1, 0, -1):
        section, key = ".".join(parts[:i]), ".".join(parts[i:])
        if key in OPTION_SCHEMA.get(section, {}):
            return section, key
    return ".".join(parts[:-1]), parts[-1]


def _option_type(section: str, key: str) -> str:
    meta = OPTION_SCHEMA.get(section, {}).get(key)
    return meta[0] if meta else "str"


# ── Nested-table (de)serialization ─────────────────────────────────────────────


def _build_nested_config(managed: dict[str, str]) -> dict[str, object]:
    """Turn a flat ``{"general:gaps_in": "8", …}`` dict into a nested tree."""
    root: dict[str, object] = {}
    for hkey in sorted(managed):
        section, key = _split_flat_key(hkey)
        type_str = _option_type(section, key)
        *path, key = hkey.split(":")
        node = root
        for part in path:
            existing = node.setdefault(part, {})
            if not isinstance(existing, dict):
                existing = {}
                node[part] = existing
            node = existing
        raw = managed[hkey].strip()
        base = type_str.split(":", 1)[0]
        if base == "bool":
            node[key] = raw.lower() in ("1", "true", "yes", "on")
        elif base == "int":
            node[key] = int(raw) if _is_int(raw) else raw
        elif base == "float":
            node[key] = float(raw) if _is_float(raw) else raw
        else:
            node[key] = raw
    return root


def _is_int(s: str) -> bool:
    try:
        int(s)
        return True
    except ValueError:
        return False


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _stringify(value: object) -> str:
    """Render a Python value back to the lowercase-boolean string convention
    used everywhere else in this codebase (hyprctl/hyprlang-style tokens)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _parse_flat_lines(body: str) -> dict[str, str]:
    """Parse pre-Lua-migration flat ``section:key = value`` lines."""
    managed: dict[str, str] = {}
    for ln in body.splitlines():
        m = re.match(r"^([^#\s][^=]*?)\s*=\s*(.+)$", ln.strip())
        if m:
            managed[m.group(1).strip().replace(".", ":")] = m.group(2).strip()
    return managed


def _flatten_config_call(text: str) -> dict[str, str]:
    """Parse an ``hl.config({...})`` call's body back into flat ``section:key`` pairs.

    Only needs to handle what :func:`_build_nested_config` itself produces
    (arbitrarily nested tables of scalar leaves) — this is the read half of
    a format we fully own, not a general Lua table parser.
    """
    call = lua_syntax.parse_call(text.strip())
    if call is None or call[0] != "hl.config":
        return {}
    table_text = call[1]

    def _walk(body: str, prefix: list[str], out: dict[str, str]) -> None:
        inner = lua_syntax.strip_outer_braces(body)
        for part in lua_syntax.split_top_level(inner):
            key, sep, val = part.partition("=")
            if not sep:
                continue
            key = key.strip()
            val = val.strip()
            if val.startswith("{"):
                _walk(val, [*prefix, key], out)
            else:
                out[":".join([*prefix, key])] = _stringify(lua_syntax.lua_literal_to_py(val))

    result: dict[str, str] = {}
    _walk(table_text, [], result)
    return result


# ── Read ───────────────────────────────────────────────────────────────────────


def read_persisted(section: str, key: str) -> str | None:
    """Read a persisted value from the managed overrides file.

    Returns None if the key is not present.
    """
    path = _effective_overrides_path()
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")
    marker, _, body = _partition_marker(text)
    if marker is None:
        return None
    return _flatten_config_call(body).get(_flat_key(section, key))


# ── Write ──────────────────────────────────────────────────────────────────────


def save_pending(pending: dict[str, dict[str, str]]) -> tuple[bool, int]:
    """Write a dict of pending changes to the overrides file.

    pending is shaped as:  { section: { key: value } }

    Merges with existing managed entries.  Returns (success, num_written).
    """
    path = _effective_overrides_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""

        marker, pre, body = _partition_marker(existing)
        if marker is None:
            managed: dict[str, str] = {}
        elif marker == MANAGED_MARKER:
            managed = _flatten_config_call(body)
        else:
            # A legacy (pre-Lua-migration) marker: body is flat
            # `section:key = value` lines, not an hl.config({...}) call.
            managed = _parse_flat_lines(body)

        # Merge pending on top
        for sec, opts in pending.items():
            for k, v in opts.items():
                managed[_flat_key(sec, k)] = v

        nested = _build_nested_config(managed)
        block = "hl.config(" + lua_syntax.format_lua_literal(nested, indent=0) + ")"

        out = pre.rstrip()
        if out:
            out += "\n"
        out += f"\n{MANAGED_MARKER}\n{block}\n"

        atomic_write_text(path, out)
        return True, len(managed)
    except OSError:
        return False, 0


def _partition_marker(text: str) -> tuple[str | None, str, str]:
    """Split *text* at the managed-block marker (new or legacy). Returns (marker, pre, body)."""
    for m in (MANAGED_MARKER, *_LEGACY_MARKERS):
        if m in text:
            pre, _, body = text.partition(m)
            return m, pre, body
    return None, text, ""


# ── Legacy migration ───────────────────────────────────────────────────────────


def migrate_legacy() -> bool:
    """Migrate an older overrides file to the current location/format if needed.

    Handles two generations: the very old ``hyprconf.local.conf`` (pre-conf.d)
    and the hyprlang-era ``conf.d/99-hyprconf-local.conf`` (flat
    ``section:key = value`` lines). Both are converted to the current
    ``conf.d/local.lua``. Returns True if a migration was performed.
    """
    if OVERRIDES_FILE.exists():
        return False

    if LEGACY_OVERRIDES_FILE.exists():
        return _migrate_flat_conf(LEGACY_OVERRIDES_FILE)
    if _CONF_ERA_OVERRIDES_FILE.exists():
        return _migrate_flat_conf(_CONF_ERA_OVERRIDES_FILE)
    return False


def _migrate_flat_conf(source: Path) -> bool:
    """Convert a hyprlang-era overrides file (flat ``key = value`` lines,
    ``# hyprconf-managed`` marker) into the current Lua format."""
    OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8")
    marker, pre, body = _partition_marker(text)
    if marker is None or marker == MANAGED_MARKER:
        # Nothing recognisable to convert — carry the file over verbatim so
        # user-written content isn't lost.
        atomic_write_text(OVERRIDES_FILE, text)
        return True

    managed = _parse_flat_lines(body)
    nested = _build_nested_config(managed)
    block = "hl.config(" + lua_syntax.format_lua_literal(nested, indent=0) + ")"
    out = pre.rstrip()
    if out:
        out += "\n"
    out += f"\n{MANAGED_MARKER}\n{block}\n"
    atomic_write_text(OVERRIDES_FILE, out)
    return True


# ── Internal helpers ───────────────────────────────────────────────────────────


def _effective_overrides_path() -> Path:
    """Return the active overrides file path, migrating an older one if needed."""
    migrate_legacy()
    return OVERRIDES_FILE
