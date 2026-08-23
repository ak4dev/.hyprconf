"""Autostart must not spawn Wayland clients while the config is being parsed.

Regression guard for the hyprlang → Lua migration. A top-level
``hl.exec_cmd()`` runs *during config parsing*, and on the very first parse
Hyprland has not created its Wayland socket yet: children inherit an empty
``WAYLAND_DISPLAY``, fail to connect and die instantly — so the wallpaper and
the bar never appeared until a manual ``hyprctl reload``. hyprlang's
``exec =`` never behaved that way (Hyprland queued those commands and
dispatched them after startup), so the migration silently changed the
semantics of the autostart block.

The contract enforced here:

* every launch that must happen at login lives in
  ``hl.on("hyprland.start", …)``, which fires once the compositor is up;
* every top-level ``hl.exec_cmd()`` is guarded on a live ``WAYLAND_DISPLAY``
  so it only fires on ``hyprctl reload``;
* the wallpaper daemon is in *both* — a theme switch rewrites hyprpaper.conf
  and reloads, and that is what repaints the desktop;
* no exec command starts with ``[`` — Hyprland parses a leading bracket as an
  exec rule list (``exec = [workspace 2 silent] foo``), so the shell never
  sees it (it segfaults ``Hyprland --verify-config`` outright).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hyprconf.lua_syntax import strip_lua_comment

REPO_ROOT = Path(__file__).resolve().parents[2]
HYPR_DIR = REPO_ROOT / "stow" / "hypr" / ".config" / "hypr"
HYPRLAND_LUA = HYPR_DIR / "hyprland.lua"

# Prefix a top-level exec command must carry so it no-ops during the first parse.
COMPOSITOR_UP_GUARD = 'test -n "$WAYLAND_DISPLAY" || exit 0;'

LUA_CONFIGS = sorted(HYPR_DIR.rglob("*.lua"))

_LOCAL_RE = re.compile(r"^local\s+([A-Za-z_]\w*)\s*=\s*(.+)$")
_EXEC_RE = re.compile(r"^hl\.exec_cmd\((.*)\)$")
_START_RE = re.compile(r'^hl\.on\(\s*"hyprland\.start"')
_LITERAL_EXEC_RE = re.compile(r"""exec_cmd\(\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""")


# ---------------------------------------------------------------------------
# Minimal Lua reading — single-line calls plus `..` continuation lines
# ---------------------------------------------------------------------------


def _paren_depth(text: str) -> int:
    """Net ``(`` minus ``)`` outside of string literals."""
    depth = 0
    quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    return depth


def _logical_lines(text: str) -> list[str]:
    """One statement per entry.

    Joins both continuation styles the config uses: a leading ``.. "…"`` and a
    call whose parentheses stay open across lines. A block opener
    (``… function()``) is emitted on its own so callers can still see where a
    ``hl.on(…)`` block starts and ends.
    """
    out: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = strip_lua_comment(raw).strip()
        if not line:
            continue
        if buf:
            buf = f"{buf} {line}"
        elif line.startswith("..") and out:
            out[-1] = f"{out[-1]} {line}"
            continue
        else:
            buf = line
        if buf.endswith("function()") or _paren_depth(buf) <= 0:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def _split_concat(expr: str) -> list[str]:
    """Split a Lua ``a .. b`` concatenation, ignoring ``..`` inside strings."""
    parts: list[str] = []
    buf = ""
    quote: str | None = None
    i = 0
    while i < len(expr):
        ch = expr[i]
        if quote:
            if ch == "\\":
                buf += expr[i : i + 2]
                i += 2
                continue
            if ch == quote:
                quote = None
            buf += ch
        elif ch in "\"'":
            quote = ch
            buf += ch
        elif ch == "." and expr[i + 1 : i + 2] == ".":
            parts.append(buf)
            buf = ""
            i += 2
            continue
        else:
            buf += ch
        i += 1
    parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def _unquote(token: str) -> str | None:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return None


def _resolve(expr: str, names: dict[str, str]) -> str | None:
    """Resolve a concatenation of string literals / known locals to its value."""
    out: list[str] = []
    for token in _split_concat(expr):
        literal = _unquote(token)
        if literal is not None:
            out.append(literal)
        elif token in names:
            out.append(names[token])
        else:
            return None
    return "".join(out)


def _exec_commands(path: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (top-level cmds, hyprland.start cmds, unresolved expressions)."""
    names: dict[str, str] = {}
    top: list[str] = []
    on_start: list[str] = []
    unresolved: list[str] = []
    in_start_block = False

    for line in _logical_lines(path.read_text(encoding="utf-8")):
        if _START_RE.match(line):
            in_start_block = True
            continue
        if in_start_block and line == "end)":
            in_start_block = False
            continue

        local = _LOCAL_RE.match(line)
        if local and not in_start_block:
            value = _resolve(local.group(2), names)
            if value is not None:
                names[local.group(1)] = value
            continue

        exec_call = _EXEC_RE.match(line)
        if exec_call:
            cmd = _resolve(exec_call.group(1), names)
            if cmd is None:
                unresolved.append(line)
            else:
                (on_start if in_start_block else top).append(cmd)

    return top, on_start, unresolved


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_every_exec_cmd_is_readable() -> None:
    """The parser above must understand every call, or the tests go vacuous."""
    _, _, unresolved = _exec_commands(HYPRLAND_LUA)
    assert not unresolved, "hl.exec_cmd() calls this test cannot resolve:\n" + "\n".join(unresolved)


def test_wallpaper_and_bar_start_with_the_session() -> None:
    """Wayland clients launch from hyprland.start — not while the config parses."""
    _, on_start, _ = _exec_commands(HYPRLAND_LUA)
    joined = "\n".join(on_start)
    assert "hyprpaper --config" in joined, (
        'hyprpaper is not launched from hl.on("hyprland.start", …) — spawned during '
        "config parsing it inherits an empty WAYLAND_DISPLAY and dies, leaving no "
        "wallpaper until `hyprctl reload`"
    )
    assert "quickshell/launch.sh" in joined, (
        'the quickshell bar is not launched from hl.on("hyprland.start", …) — see above'
    )


def test_top_level_exec_cmds_only_run_once_a_compositor_exists() -> None:
    """Top-level calls are the reload path; they must no-op during the first parse."""
    top, _, _ = _exec_commands(HYPRLAND_LUA)
    assert top, "expected top-level hl.exec_cmd() calls (the `hyprctl reload` path)"
    unguarded = [cmd for cmd in top if not cmd.startswith(COMPOSITOR_UP_GUARD)]
    assert not unguarded, (
        "top-level hl.exec_cmd() runs during config parsing, before the Wayland "
        f"socket exists — prefix these with {COMPOSITOR_UP_GUARD!r}:\n" + "\n".join(unguarded)
    )


def test_reload_relaunches_the_wallpaper_daemon() -> None:
    """A theme switch rewrites hyprpaper.conf and reloads; that must repaint."""
    top, _, _ = _exec_commands(HYPRLAND_LUA)
    assert any("hyprpaper --config" in cmd for cmd in top), (
        "no top-level hyprpaper launch — `hyprctl reload` would no longer pick up a "
        "new wallpaper after a theme switch"
    )


def test_reload_does_not_restart_the_bar() -> None:
    """Restarting quickshell tears down the tray's StatusNotifierWatcher."""
    top, _, _ = _exec_commands(HYPRLAND_LUA)
    bar = [cmd for cmd in top if "quickshell/launch.sh" in cmd]
    assert bar, "expected a top-level quickshell launch"
    for cmd in bar:
        assert "pgrep -x 'qs|quickshell'" in cmd, f"unguarded quickshell relaunch on reload: {cmd}"


@pytest.mark.parametrize("conf", LUA_CONFIGS, ids=lambda p: p.name)
def test_no_exec_command_starts_with_a_bracket(conf: Path) -> None:
    """A leading `[` is eaten by Hyprland as an exec rule list, never by the shell."""
    offenders = [
        literal
        for match in _LITERAL_EXEC_RE.finditer(conf.read_text(encoding="utf-8"))
        if (literal := _unquote(match.group(1))) and literal.lstrip().startswith("[")
    ]
    assert not offenders, (
        "exec commands starting with `[` are parsed as exec rules "
        "(`exec = [workspace 2 silent] foo`), not shell:\n" + "\n".join(offenders)
    )
