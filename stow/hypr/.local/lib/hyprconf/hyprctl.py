"""
hyprconf.hyprctl — thin wrapper around hyprctl IPC.

All runtime communication with the Hyprland compositor goes through this
module.  Both the CLI and TUI import from here; neither calls hyprctl
directly.
"""

from __future__ import annotations

import json
import os
import subprocess

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
        # str field: gradients, paths, and string options come through here
        s = d.get("str")
        if s is not None and str(s).strip():
            return str(s)
        # col field: ARGB integer → hex string
        col = d.get("col")
        if col is not None and int(col) != 0:
            return f"0x{int(col) & 0xFFFFFFFF:08x}"
        # Prefer float when it has a meaningful fractional component
        f = d.get("float", 0.0)
        i = d.get("int", 0)
        if f != 0.0 and f != float(i):
            return str(f)
        # Fall back to int (covers bools, pure ints, and floats like 1.0)
        for field in ("int", "float"):
            v = d.get(field)
            if v is not None:
                return str(v)
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        pass

    return None


# ── Option write ───────────────────────────────────────────────────────────────


def set_option(section: str, key: str, value: str) -> bool:
    """Apply a Hyprland option at runtime via hyprctl keyword.

    Returns True on success, False if compositor is not running or the
    keyword was rejected.
    """
    if not is_active():
        return False
    hkey = section.replace(".", ":") + ":" + key
    return _run(["hyprctl", "keyword", hkey, value]) is not None


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


def set_monitor(keyword: str) -> bool:
    """Apply a monitor= keyword at runtime.

    keyword should be in the format:  NAME,RESxRES@HZ,XxY,SCALE[,vrr,N]
    """
    if not is_active():
        return False
    return _run(["hyprctl", "keyword", "monitor", keyword]) is not None


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
