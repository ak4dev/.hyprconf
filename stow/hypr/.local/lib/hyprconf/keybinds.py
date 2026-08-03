"""hyprconf.keybinds — read and write Hyprland keybinds.

Keybinds live in ``keybinds.lua`` (``require``d by ``hyprland.lua``). Hyprland
0.55+ moved from hyprlang bind flags (``bind``/``bindl``/``bindel``/``bindm``/…)
to a single ``hl.bind(keys, dispatcher, opts)`` call with a boolean options
table (``{locked=, repeating=, release=, non_consuming=, mouse=, transparent=}``).

hyprconf keeps writing (and, for the familiar TUI vocabulary, reading) the same
five logical fields it always has — ``kind`` (bind flags), ``mods``, ``key``,
``dispatcher``, ``args`` — translating them to/from the Lua call form. One
``hl.bind(...)`` call per physical line (matching the official example config's
own style), so entries stay addressable by ``(file_path, line_idx)`` exactly
as they were for hyprlang ``.conf``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from . import lua_syntax
from .file_edit import (
    SOURCE_RE,
    append_block,
    read_lines,
    resolve_source_paths,
    strip_comment,
    update_line,
)
from .paths import HYPR_DIR, KEYBINDS_FILE

# ─────────────────────────────────────────────────────────────────────────────
#  Data types
# ─────────────────────────────────────────────────────────────────────────────


class KeybindEntry(NamedTuple):
    kind: str  # bind / bindl / bindel / etc. (reconstructed from the opts table)
    mods: str  # e.g. "SUPER SHIFT" or ""
    key: str  # e.g. "T" or "XF86AudioPlay"
    dispatcher: str  # e.g. "exec_cmd" or "window.close"
    args: str  # e.g. "kitty"
    file_path: Path  # source file
    line_idx: int  # 0-based line index in file_path
    raw_line: str  # verbatim line (for display / round-trip)


# ─────────────────────────────────────────────────────────────────────────────
#  Parsing
# ─────────────────────────────────────────────────────────────────────────────

_BIND_CALL_RE = re.compile(r"^(?:local\s+\w+\s*=\s*)?hl\.bind\((.*)\)\s*$")
_LOCAL_STR_VAR_RE = re.compile(r'^local\s+([A-Za-z_]\w*)\s*=\s*"([^"]*)"\s*$')

# Reverse of the write-side bind-flag -> opts-table-key mapping.
_OPT_TO_FLAG = {
    "locked": "l",
    "repeating": "e",
    "release": "r",
    "non_consuming": "n",
    "mouse": "m",
    "transparent": "t",
}
_FLAG_ORDER = "lernmt"


def _kind_from_opts(opts: dict[str, object]) -> str:
    flags = [_OPT_TO_FLAG[k] for k in opts if k in _OPT_TO_FLAG and opts[k] is True]
    flags.sort(key=_FLAG_ORDER.index)
    return "bind" + "".join(flags)


def _parse_key_expr(expr: str, local_vars: dict[str, str]) -> tuple[str, str]:
    """Evaluate a key-string expression (e.g. ``mainMod .. " + SHIFT + Q"``).

    Returns ``(mods, key)`` for display — string-concat parts are resolved
    against *local_vars* (tracked ``local NAME = "VALUE"`` assignments).
    """
    parts = [p.strip() for p in expr.split("..")]
    resolved: list[str] = []
    for p in parts:
        if len(p) >= 2 and p[0] == p[-1] and p[0] in ('"', "'"):
            resolved.append(lua_syntax.lua_literal_to_py(p))  # type: ignore[arg-type]
        else:
            resolved.append(local_vars.get(p, p))
    full = "".join(resolved)
    if " + " in full:
        mods, _, key = full.rpartition(" + ")
        return mods, key
    return "", full


def _parse_dispatcher_expr(expr: str, local_vars: dict[str, str]) -> tuple[str, str]:
    """Turn a dispatcher-call expression (e.g. ``hl.dsp.exec_cmd("kitty")``)
    into ``(display_name, args)`` for the TUI's dispatcher/args columns."""
    call = lua_syntax.parse_call(expr)
    if call is None:
        return expr.strip(), ""
    fn_name, inner = call
    display_name = fn_name[len("hl.dsp.") :] if fn_name.startswith("hl.dsp.") else fn_name
    inner = inner.strip()
    if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in ('"', "'"):
        return display_name, str(lua_syntax.lua_literal_to_py(inner))
    if inner in local_vars:
        return display_name, local_vars[inner]
    return display_name, inner


def read_keybinds_with_location(
    path: Path | None = None,
    *,
    follow_sources: bool = False,
) -> list[KeybindEntry]:
    """Parse keybinds from *path*, returning entries with file+line location.

    When *follow_sources* is True, ``source =`` (legacy) and
    ``require(...)``/``try_require(...)`` (Lua) directives are recursively
    followed. By default only *path* itself is parsed (keybinds.lua is a flat
    file). Local string variables (``local mainMod = "SUPER"``) are resolved
    for display in ``mods``/``key``; ``raw_line`` always preserves the
    original text.
    """
    if path is None:
        path = KEYBINDS_FILE

    entries: list[KeybindEntry] = []
    seen: set[Path] = set()

    def _parse(p: Path, inherited_vars: dict[str, str]) -> None:
        if p in seen or not p.exists():
            return
        seen.add(p)
        local_vars: dict[str, str] = dict(inherited_vars)
        strip_fn = lua_syntax.strip_lua_comment if p.suffix == ".lua" else strip_comment
        lines = read_lines(p)
        for idx, raw in enumerate(lines):
            stripped = strip_fn(raw)
            if not stripped:
                continue
            mv = _LOCAL_STR_VAR_RE.match(stripped)
            if mv:
                local_vars[mv.group(1)] = mv.group(2)
                continue
            if follow_sources:
                ms = SOURCE_RE.match(stripped)
                if ms:
                    for sp in resolve_source_paths(ms.group(1), p.parent):
                        _parse(sp, local_vars)
                    continue
                mr = lua_syntax.REQUIRE_RE.match(stripped)
                if mr:
                    for candidate in lua_syntax.resolve_require_paths(mr.group(1), HYPR_DIR):
                        if candidate.exists():
                            _parse(candidate, local_vars)
                            break
                    continue
            mb = _BIND_CALL_RE.match(stripped)
            if mb:
                call_args = lua_syntax.split_top_level(mb.group(1))
                if len(call_args) < 2:
                    continue
                mods, key = _parse_key_expr(call_args[0], local_vars)
                dispatcher, args = _parse_dispatcher_expr(call_args[1], local_vars)
                opts = (
                    {
                        k: lua_syntax.lua_literal_to_py(v)
                        for k, v in lua_syntax.parse_flat_table(call_args[2]).items()
                    }
                    if len(call_args) > 2
                    else {}
                )
                entries.append(
                    KeybindEntry(
                        kind=_kind_from_opts(opts),
                        mods=mods,
                        key=key,
                        dispatcher=dispatcher,
                        args=args,
                        file_path=p,
                        line_idx=idx,
                        raw_line=raw,
                    )
                )

    _parse(path, {})
    return entries


# ─────────────────────────────────────────────────────────────────────────────
#  Writers
# ─────────────────────────────────────────────────────────────────────────────

_DIRECTION_MAP = {"l": "left", "r": "right", "u": "up", "d": "down"}

# Bind-flag letter (from a `kind` like "bindel") -> Lua opts-table key.
_FLAG_TO_OPT = {
    "l": "locked",
    "e": "repeating",
    "r": "release",
    "n": "non_consuming",
    "m": "mouse",
    "t": "transparent",
}


_OPT_ORDER = ("locked", "repeating", "release", "mouse", "non_consuming", "transparent")


def _opts_from_kind(kind: str) -> dict[str, bool]:
    flags = kind.strip().lower()
    flags = flags[4:] if flags.startswith("bind") else ""
    present = {_FLAG_TO_OPT[ch] for ch in flags if ch in _FLAG_TO_OPT}
    return {name: True for name in _OPT_ORDER if name in present}


def _compose_key_expr(mods: str, key: str) -> str:
    """Build the Lua key-string expression for ``hl.bind``'s first argument."""
    key = key.strip()
    tokens = mods.replace("$mainMod", "mainMod").split()
    if tokens and tokens[0] == "mainMod":
        rest = " + ".join(tokens[1:] + [key])
        return f'mainMod .. " + {rest}"'
    if tokens:
        return lua_syntax.quote(" + ".join(tokens + [key]))
    return lua_syntax.quote(key)


def _wksp_arg(raw: str) -> str:
    v = raw.strip()
    try:
        int(v)
        return v
    except ValueError:
        return lua_syntax.quote(v)


def _compose_dispatcher_expr(dispatcher: str, args: str) -> str:
    """Translate a legacy hyprlang dispatcher + args into an ``hl.dsp.*`` call."""
    d = dispatcher.strip().lower()
    a = args.strip()
    if d == "exec":
        return f"hl.dsp.exec_cmd({lua_syntax.quote(a)})"
    if d == "killactive":
        return "hl.dsp.window.close()"
    if d == "exit":
        return "hl.dsp.exit()"
    if d == "togglefloating":
        return 'hl.dsp.window.float({ action = "toggle" })'
    if d == "pseudo":
        return "hl.dsp.window.pseudo()"
    if d == "fullscreen":
        return "hl.dsp.window.fullscreen()"
    if d == "movefocus":
        direction = _DIRECTION_MAP.get(a.lower(), a)
        return f"hl.dsp.focus({{ direction = {lua_syntax.quote(direction)} }})"
    if d == "swapwindow":
        direction = _DIRECTION_MAP.get(a.lower(), a)
        return f"hl.dsp.window.swap({{ direction = {lua_syntax.quote(direction)} }})"
    if d == "resizeactive":
        x, _, y = a.partition(" ")
        return f"hl.dsp.window.resize({{ x = {x or 0}, y = {y or 0} }})"
    if d == "workspace":
        return f"hl.dsp.focus({{ workspace = {_wksp_arg(a)} }})"
    if d == "movetoworkspace":
        return f"hl.dsp.window.move({{ workspace = {_wksp_arg(a)} }})"
    if d == "togglespecialworkspace":
        return f"hl.dsp.workspace.toggle_special({lua_syntax.quote(a)})"
    if d == "movewindow":
        return "hl.dsp.window.drag()"
    if d == "resizewindow":
        return "hl.dsp.window.resize()"
    # Unknown dispatcher — pass through as a raw exec_cmd-style call so
    # nothing is silently dropped; the TUI still shows what was entered.
    return f"hl.dsp.{d}({lua_syntax.quote(a)})" if a else f"hl.dsp.{d}()"


def _format_bind_line(kind: str, mods: str, key: str, dispatcher: str, args: str) -> str:
    """Produce a canonical ``hl.bind(...)`` line."""
    key_expr = _compose_key_expr(mods, key)
    dispatcher_expr = _compose_dispatcher_expr(dispatcher, args)
    opts = _opts_from_kind(kind)
    line = f"hl.bind({key_expr}, {dispatcher_expr}"
    if opts:
        line += ", " + lua_syntax.format_lua_literal(opts)
    return line + ")"


def add_keybind(
    kind: str, mods: str, key: str, dispatcher: str, args: str, file: Path | None = None
) -> bool:
    """Append a new keybind to *file* (default: keybinds.lua).

    Returns True on success.
    """
    if file is None:
        file = KEYBINDS_FILE
    line = _format_bind_line(kind, mods, key, dispatcher, args)
    return append_block(file, line)


def update_keybind(
    file_path: Path, line_idx: int, kind: str, mods: str, key: str, dispatcher: str, args: str
) -> bool:
    """Replace the keybind at *line_idx* in *file_path*.

    Returns True on success.
    """
    line = _format_bind_line(kind, mods, key, dispatcher, args)
    return update_line(file_path, line_idx, line)
