"""hyprconf.lua_syntax — primitives for single-line Hyprland Lua config statements.

hyprconf always emits one ``hl.*(...)`` call per physical line — the same style
the official ``/usr/share/hypr/hyprland.lua`` example already uses for binds
(e.g. ``hl.bind(mainMod .. " + Q", hl.dsp.exec_cmd(terminal))`` is one line).
That convention means every other module in this package can keep addressing
rules/keybinds/monitors by ``(file_path, line_idx)`` exactly as it did for
hyprlang ``.conf`` — only the regex patterns and text templates change. This
module is the shared layer: comment stripping, Lua-literal formatting, and a
small bracket/quote-aware tokenizer for reading back a *single-line* call —
not a general Lua parser.
"""

from __future__ import annotations

import re
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
#  Comment stripping
# ─────────────────────────────────────────────────────────────────────────────


def strip_lua_comment(line: str) -> str:
    """Remove a trailing ``-- …`` comment, ignoring ``--`` inside quoted strings.

    e.g. ``hl.dsp.exec_cmd("mpv --loop")`` must not be truncated at the ``--``
    inside the command string.
    """
    in_string: str | None = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            i += 1
            continue
        if ch == "-" and i + 1 < n and line[i + 1] == "-":
            return line[:i].rstrip()
        i += 1
    return line.rstrip()


# ─────────────────────────────────────────────────────────────────────────────
#  Writing — Python value -> Lua literal
# ─────────────────────────────────────────────────────────────────────────────


def quote(s: str) -> str:
    """Quote *s* as a Lua double-quoted string literal."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def format_lua_value(value: str, type_hint: str = "str") -> str:
    """Format a raw hyprctl-style value string as a Lua literal.

    *type_hint* uses ``hyprconf.schema``'s vocabulary: ``int``, ``float``,
    ``bool``, ``str``, ``color``, ``gradient``, ``vec2``, or ``enum:a,b,c``.
    Only ``bool``/``int``/``float`` are emitted unquoted; everything else
    (including color/gradient/vec2, which Hyprland's Lua API accepts as plain
    strings — see ``HL.ConfigValueTypes``) is a quoted Lua string.
    """
    v = value.strip()
    base = type_hint.split(":", 1)[0]
    if base == "bool":
        return "true" if v.lower() in ("1", "true", "yes", "on") else "false"
    if base in ("int", "float"):
        return v
    return quote(v)


def format_lua_literal(value: object, *, indent: int | None = None) -> str:
    """Format a native Python value (bool/int/float/str/dict/list) as Lua.

    Dicts become ``{ key = value, … }`` table constructors (nested dicts
    recurse); lists become ``{ v1, v2, … }`` array constructors. Pass
    *indent* (starting at 0) to pretty-print nested tables one field per
    line instead of the default single-line form — used for files that are
    fully regenerated on each write (no per-line addressing to preserve).
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return quote(value)
    if isinstance(value, dict):
        if indent is None:
            parts = [f"{k} = {format_lua_literal(v)}" for k, v in value.items()]
            return "{ " + ", ".join(parts) + " }"
        if not value:
            return "{}"
        pad = "    " * (indent + 1)
        parts = [f"{pad}{k} = {format_lua_literal(v, indent=indent + 1)}," for k, v in value.items()]
        return "{\n" + "\n".join(parts) + "\n" + "    " * indent + "}"
    if isinstance(value, (list, tuple)):
        return "{ " + ", ".join(format_lua_literal(v) for v in value) + " }"
    raise TypeError(f"Cannot format {value!r} as a Lua literal")


# ─────────────────────────────────────────────────────────────────────────────
#  Reading — single-line tokenizing helpers
# ─────────────────────────────────────────────────────────────────────────────


def split_top_level(text: str, sep: str = ",") -> list[str]:
    """Split *text* on *sep*, ignoring separators nested inside (), {}, or quotes."""
    parts: list[str] = []
    depth = 0
    in_string: str | None = None
    start = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
        elif ch in ("'", '"'):
            in_string = ch
        elif ch in "({":
            depth += 1
        elif ch in ")}":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    tail = text[start:]
    if tail.strip() or parts:
        parts.append(tail)
    return [p.strip() for p in parts if p.strip()]


def strip_outer_braces(text: str) -> str:
    """Strip one layer of matching ``{ … }`` (or return *text* unchanged)."""
    t = text.strip()
    if t.startswith("{") and t.endswith("}"):
        return t[1:-1].strip()
    return t


def lua_literal_to_py(raw: str) -> str | bool | float | int:
    """Convert a single raw Lua literal token to a Python value.

    Strings are unquoted; ``true``/``false`` become bool; bare numbers become
    int/float. Anything else (identifiers, expressions) is returned as-is
    (callers that need the raw text for display can use it verbatim).
    """
    t = raw.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
        return t[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if t == "true":
        return True
    if t == "false":
        return False
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t


def parse_flat_table(text: str) -> dict[str, str]:
    """Parse a *flat* (non-nested-value) ``{ key = value, … }`` table.

    Returns ``{key: raw_value_text}`` — values are the raw Lua literal text
    (still quoted if a string), not interpreted; use :func:`lua_literal_to_py`
    on individual values when a Python type is needed. Sufficient for the
    single-level tables hyprconf itself generates (monitor specs, bind opts);
    not a general Lua table parser.
    """
    inner = strip_outer_braces(text)
    result: dict[str, str] = {}
    for part in split_top_level(inner):
        key, sep, val = part.partition("=")
        if not sep:
            continue
        result[key.strip()] = val.strip()
    return result


def parse_call(line: str) -> tuple[str, str] | None:
    """Match a single-line ``[local NAME = ]fn.call(ARGS)`` statement.

    Returns ``(fn_name, args_text)`` — *args_text* is the raw text between the
    outermost parens (not yet split into individual arguments; use
    :func:`split_top_level` for that) — or ``None`` if *line* isn't a
    recognizable single-line call.
    """
    s = strip_lua_comment(line).strip()
    if s.startswith("local "):
        _, _, s = s.partition("=")
        s = s.strip()
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*\((.*)\)\s*$", s, re.DOTALL)
    if not m:
        return None
    return m.group(1), m.group(2)


# ─────────────────────────────────────────────────────────────────────────────
#  `require` — the Lua analogue of hyprlang's `source = path` directive
# ─────────────────────────────────────────────────────────────────────────────

# Matches `require("a.b.c")` / `try_require("a.b.c")`, optionally assigned to
# a local. Unlike `source = …`, `require` takes a fixed module name — no glob
# equivalent, so hyprland.lua individually `pcall`-wraps each optional module
# (see `try_require` there) instead of relying on a "glob matches >=1 file"
# placeholder file.
REQUIRE_RE = re.compile(r'^(?:local\s+\w+\s*=\s*)?(?:try_require|require)\(\s*"([^"]+)"\s*\)\s*$')


def resolve_require_paths(module: str, hypr_dir: Path) -> list[Path]:
    """Resolve a Lua ``require("name")`` module name to its candidate file(s).

    Mirrors the two ``package.path`` templates hyprland.lua sets up: modules
    resolve directly under *hypr_dir* first, then (for the bare, dot-free
    names used by the optional ``conf.d`` overrides) under ``hypr_dir/conf.d``
    — added there specifically because ``require`` converts every "." in a
    module name to a path separator, so a dotted name can't address a
    directory that is itself named with a literal dot (``conf.d``). Returns
    candidates in the same search order Lua would use; callers should use the
    first one that exists.
    """
    rel = module.replace(".", "/") + ".lua"
    return [hypr_dir / rel, hypr_dir / "conf.d" / rel]
