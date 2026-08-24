"""
hyprconf.hyprctl — thin wrapper around hyprctl IPC.

All runtime communication with the Hyprland compositor goes through this
module; the TUI never calls hyprctl directly.

Live changes go through ``hyprctl eval <lua>``, never the legacy
``keyword`` subcommand: on Hyprland 0.56 (Lua config parser — the one Omarchy
4.0 runs) that subcommand prints "keyword can't work with non-legacy parsers.
Use eval." and exits 0, i.e. it is a silent no-op that *looks* successful.
``eval`` runs a Lua chunk against the live config API: ``hl.config({ … })``
sets options, ``hl.monitor({ … })`` (re)configures an output. Verified on this
host (Hyprland 0.56.2): a good chunk prints ``ok`` and exits 0; an unknown key
(``error: … unknown config key 'general.no_such_option_xyz'``) or a syntax
error exits 7.
"""

from __future__ import annotations

import json
import os
import subprocess

from . import lua_syntax
from .config import _option_type

# ── Session detection ──────────────────────────────────────────────────────────


def is_active() -> bool:
    """Return True if a Hyprland session is currently running."""
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))


# ── Low-level runner ───────────────────────────────────────────────────────────


def _run(args: list[str], timeout: float = 3.0) -> str | None:
    """Run a command, return stdout on success or None on failure."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


# ── Lua eval ───────────────────────────────────────────────────────────────────


def eval_lua(code: str) -> bool:
    """Run a Lua chunk against the live compositor via ``hyprctl eval``.

    Returns True when Hyprland accepted it (exit 0 and no ``error:`` reply),
    False when the compositor is not running or rejected the chunk.
    """
    if not is_active():
        return False
    out = _run(["hyprctl", "eval", code])
    if out is None:
        return False
    return not out.lstrip().lower().startswith("error")


# ── Option read ────────────────────────────────────────────────────────────────


def get_option(section: str, key: str) -> str | None:
    """Read the current live value of a Hyprland option via hyprctl getoption.

    Returns the most human-readable field from the JSON response, or None if
    the compositor is not running or the option is unknown.

    hyprctl key format uses colons:  decoration:blur:enabled
    """
    if not is_active():
        return None

    hkey = section.replace(".", ":") + ":" + key
    raw = _run(["hyprctl", "getoption", hkey, "-j"])
    if not raw:
        return None

    try:
        d = json.loads(raw)
        # Priority order: str > custom > col > float(if meaningful) > int/float fallback
        s = d.get("str")
        if s is not None and str(s).strip():
            return str(s)
        c = d.get("custom")
        if c is not None and str(c).strip():
            return str(c)
        col = d.get("col")
        if col is not None and int(col) != 0:
            return f"0x{int(col) & 0xFFFFFFFF:08x}"
        # Prefer float when it has a meaningful fractional component
        f = d.get("float", 0.0)
        i = d.get("int", 0)
        if f != 0.0 and f != float(i):
            return str(f)
        for field in ("int", "float"):
            v = d.get(field)
            if v is not None:
                return str(v)
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        pass

    return None


# ── Option write ───────────────────────────────────────────────────────────────


def config_call(section: str, key: str, value: str) -> str:
    """Build the ``hl.config({ … })`` chunk that sets one option live.

    A dotted section nests: ``("decoration.blur", "enabled", "true")`` →
    ``hl.config({ decoration = { blur = { enabled = true } } })``; so does a
    dotted key — ``col.active_border`` is ``col = { active_border = … }`` to
    the Lua API (see Omarchy's default/hypr/looknfeel.lua). The value is
    typed from the option schema (``hyprconf.schema``) so bools and numbers
    are bare Lua literals and everything else is a quoted string — the same
    rule ``hyprconf.config`` uses for the persisted overrides.
    """
    literal = lua_syntax.format_lua_value(value, _option_type(section, key))
    parts = section.split(".") + key.split(".")
    body = f"{parts[-1]} = {literal}"
    for part in reversed(parts[:-1]):
        body = f"{part} = {{ {body} }}"
    return f"hl.config({{ {body} }})"


def set_option(section: str, key: str, value: str) -> bool:
    """Apply a Hyprland option at runtime via ``hyprctl eval``.

    Returns True on success, False if compositor is not running or the
    option was rejected.
    """
    if not is_active():
        return False
    return eval_lua(config_call(section, key, value))


# ── Monitors ───────────────────────────────────────────────────────────────────


def get_monitors() -> list[dict]:
    """Return the current monitor list as parsed JSON, or [] on failure."""
    raw = _run(["hyprctl", "monitors", "-j"])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def apply_monitor(name: str, resolution: str, position: str, scale: str, extras: str = "") -> bool:
    """(Re)configure an output live: ``hyprctl eval 'hl.monitor({ … })'``.

    The table is the same one :mod:`hyprconf.monitors` persists to
    ``monitors.lua``, so what the compositor runs and what the file says
    never drift apart. ``resolution == "disable"`` turns the output off.
    """
    if not is_active():
        return False
    from .monitors import monitor_call

    return eval_lua(monitor_call(name, resolution, position, scale, extras))


def disable_monitor(name: str) -> bool:
    """Turn an output off live (``hl.monitor({ output = NAME, disabled = true })``)."""
    return apply_monitor(name, "disable", "", "")


# ── Reload ─────────────────────────────────────────────────────────────────────


def reload() -> bool:
    """Signal Hyprland to reload its configuration."""
    if not is_active():
        return False
    return _run(["hyprctl", "reload"]) is not None


# ── Generic dispatch ───────────────────────────────────────────────────────────


def dispatch(action: str, *args: str) -> bool:
    """Send a hyprctl dispatch command."""
    if not is_active():
        return False
    return _run(["hyprctl", "dispatch", action, *args]) is not None
