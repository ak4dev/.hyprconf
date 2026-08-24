"""hyprconf.keybinds — read and write Hyprland keybinds (Omarchy's bindings.lua).

Keybinds live in ``~/.config/hypr/bindings.lua``, the override point Omarchy's
``hyprland.lua`` ``require``s after its own defaults (install.sh symlinks the
overlay's ``hypr/bindings.lua`` there). Three call forms appear in that file,
one call per physical line, and all three are parsed here:

``hl.bind(keys, dispatcher[, opts])``
    Hyprland's own API (0.55+): a key-string expression, an ``hl.dsp.*``
    dispatcher call and a boolean options table (``{locked=, repeating=,
    release=, non_consuming=, mouse=, transparent=}``).

``o.bind(keys, "description", dispatcher_or_"shell command"[, opts])``
    Omarchy's helper (``/usr/share/omarchy/default/hypr/helpers.lua``). The
    description is what Omarchy's keybindings menu (SUPER+K) lists; a string
    dispatcher becomes ``hl.dsp.exec_cmd(string)``; a table such as
    ``{ omarchy = "terminal" }`` / ``{ launch = … }`` / ``{ webapp = … }`` /
    ``{ tui = … }`` is resolved by ``command_from`` at load time — shown here
    as its table text, never executed.

``rebind(keys, "description", dispatcher[, opts])``
    The overlay's own local helper in ``hypr/bindings.lua`` (``hl.unbind``
    then ``o.bind``); parsed exactly like ``o.bind``.

``hl.unbind(…)`` / ``unbind_keycode(…)`` calls, ``local`` assignments and
comments are skipped; ``local NAME = "…"`` string variables (``mainMod``) are
tracked so key expressions display resolved.

hyprconf keeps writing (and, for the familiar TUI vocabulary, reading) the same
logical fields it always has — ``kind`` (bind flags), ``mods``, ``key``,
``dispatcher``, ``args`` — plus ``description`` and ``call``. A NEW bind is
written as ``o.bind(...)`` so it carries a description into Omarchy's menu; an
UPDATE keeps the line's original call name. One call per line keeps entries
addressable by ``(file_path, line_idx)``.
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
    dispatcher: str  # e.g. "exec_cmd", "window.close", or an Omarchy launch table's text
    args: str  # e.g. "kitty"
    file_path: Path  # source file
    line_idx: int  # 0-based line index in file_path
    raw_line: str  # verbatim line (for display / round-trip)
    description: str = ""  # o.bind/rebind description (what SUPER+K lists)
    call: str = "hl.bind"  # the call form the line uses: hl.bind / o.bind / rebind


NEW_BIND_CALL = "o.bind"

# ─────────────────────────────────────────────────────────────────────────────
#  Parsing
# ─────────────────────────────────────────────────────────────────────────────

_BIND_CALL_RE = re.compile(r"^(?:local\s+\w+\s*=\s*)?(hl\.bind|o\.bind|rebind)\((.*)\)\s*$")
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


def _is_string_literal(text: str) -> bool:
    t = text.strip()
    return len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'")


def _kind_from_opts(opts: dict[str, object]) -> str:
    flags = [_OPT_TO_FLAG[k] for k in opts if k in _OPT_TO_FLAG and opts[k] is True]
    flags.sort(key=_FLAG_ORDER.index)
    return "bind" + "".join(flags)


def _parse_opts(text: str) -> dict[str, object]:
    return {
        k: lua_syntax.lua_literal_to_py(v) for k, v in lua_syntax.parse_flat_table(text).items()
    }


def _parse_key_expr(expr: str, local_vars: dict[str, str]) -> tuple[str, str] | None:
    """Evaluate a key-string expression (e.g. ``mainMod .. " + SHIFT + Q"``).

    Returns ``(mods, key)`` for display — string-concat parts are resolved
    against *local_vars* (tracked ``local NAME = "VALUE"`` assignments) — or
    None when nothing in it is a literal or a known variable (a helper's own
    ``o.bind(keys, description, …)`` body, not a bind).
    """
    parts = [p.strip() for p in expr.split("..")]
    resolved: list[str] = []
    known = False
    for p in parts:
        if _is_string_literal(p):
            resolved.append(str(lua_syntax.lua_literal_to_py(p)))
            known = True
        elif p in local_vars:
            resolved.append(local_vars[p])
            known = True
        else:
            resolved.append(p)
    if not known:
        return None
    full = "".join(resolved)
    if " + " in full:
        mods, _, key = full.rpartition(" + ")
        # Display mods space-separated ("SUPER SHIFT"), the vocabulary the
        # editor's hints use and the writer reads back.
        return " ".join(mods.split(" + ")), key
    return "", full


def _parse_dispatcher_expr(expr: str, local_vars: dict[str, str]) -> tuple[str, str]:
    """Turn a dispatcher expression into ``(display_name, args)``.

    ``hl.dsp.exec_cmd("kitty")`` → ``("exec_cmd", "kitty")``; a bare string
    (``o.bind``'s shell-command form, which helpers.lua wraps in
    ``hl.dsp.exec_cmd``) → ``("exec_cmd", command)``; an Omarchy launch table
    (``{ omarchy = "terminal" }``) is kept as its own text with no args.
    """
    e = expr.strip()
    if _is_string_literal(e):
        return "exec_cmd", str(lua_syntax.lua_literal_to_py(e))
    if e.startswith("{"):
        return e, ""
    call = lua_syntax.parse_call(e)
    if call is None:
        return e, ""
    fn_name, inner = call
    display_name = fn_name[len("hl.dsp.") :] if fn_name.startswith("hl.dsp.") else fn_name
    inner = inner.strip()
    if _is_string_literal(inner):
        return display_name, str(lua_syntax.lua_literal_to_py(inner))
    if inner in local_vars:
        return display_name, local_vars[inner]
    return display_name, inner


class _ParsedBind(NamedTuple):
    call: str
    kind: str
    mods: str
    key: str
    dispatcher: str
    args: str
    description: str


def _parse_bind_line(stripped: str, local_vars: dict[str, str]) -> _ParsedBind | None:
    """Parse one comment-stripped line as a bind call, or None if it isn't one."""
    mb = _BIND_CALL_RE.match(stripped)
    if not mb:
        return None
    call, call_args = mb.group(1), lua_syntax.split_top_level(mb.group(2))
    if call == "hl.bind":
        if len(call_args) < 2:
            return None
        key_expr, disp_expr = call_args[0], call_args[1]
        opts = _parse_opts(call_args[2]) if len(call_args) > 2 else {}
        desc = opts.get("description")
        description = desc if isinstance(desc, str) else ""
    else:
        if len(call_args) < 3 or not _is_string_literal(call_args[1]):
            return None
        key_expr, disp_expr = call_args[0], call_args[2]
        description = str(lua_syntax.lua_literal_to_py(call_args[1]))
        opts = _parse_opts(call_args[3]) if len(call_args) > 3 else {}
    parsed_key = _parse_key_expr(key_expr, local_vars)
    if parsed_key is None:
        return None
    mods, key = parsed_key
    dispatcher, args = _parse_dispatcher_expr(disp_expr, local_vars)
    return _ParsedBind(call, _kind_from_opts(opts), mods, key, dispatcher, args, description)


def read_keybinds_with_location(
    path: Path | None = None,
    *,
    follow_sources: bool = False,
) -> list[KeybindEntry]:
    """Parse keybinds from *path*, returning entries with file+line location.

    When *follow_sources* is True, ``source =`` (legacy) and
    ``require(...)``/``try_require(...)`` (Lua) directives are recursively
    followed. By default only *path* itself is parsed (bindings.lua is a flat
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
            pb = _parse_bind_line(stripped, local_vars)
            if pb is None:
                continue
            entries.append(
                KeybindEntry(
                    kind=pb.kind,
                    mods=pb.mods,
                    key=pb.key,
                    dispatcher=pb.dispatcher,
                    args=pb.args,
                    file_path=p,
                    line_idx=idx,
                    raw_line=raw,
                    description=pb.description,
                    call=pb.call,
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


def _opts_from_kind(kind: str) -> dict[str, object]:
    flags = kind.strip().lower()
    flags = flags[4:] if flags.startswith("bind") else ""
    present = {_FLAG_TO_OPT[ch] for ch in flags if ch in _FLAG_TO_OPT}
    return {name: True for name in _OPT_ORDER if name in present}


def _local_string_vars(path: Path) -> dict[str, str]:
    """``local NAME = "…"`` string variables defined in *path* (``mainMod``)."""
    found: dict[str, str] = {}
    for raw in read_lines(path):
        mv = _LOCAL_STR_VAR_RE.match(lua_syntax.strip_lua_comment(raw))
        if mv:
            found[mv.group(1)] = mv.group(2)
    return found


def _compose_key_expr(mods: str, key: str, local_vars: dict[str, str]) -> str:
    """Build the Lua key-string expression for a bind's first argument.

    A leading modifier that is the file's ``mainMod`` value (or the literal
    ``mainMod``/``$mainMod``) is written back as ``mainMod .. " + …"``, the
    way the file spells it; with no such variable in the file, ``mainMod``
    falls back to its documented value, SUPER.
    """
    key = key.strip()
    tokens = mods.replace("$mainMod", "mainMod").replace("+", " ").split()
    main_mod = local_vars.get("mainMod")
    if tokens and tokens[0] == "mainMod" and main_mod is None:
        tokens[0] = "SUPER"
    if tokens and (tokens[0] == "mainMod" or (main_mod and tokens[0].upper() == main_mod.upper())):
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


def _compose_dispatcher_expr(dispatcher: str, args: str, call: str) -> str:
    """Translate a dispatcher + args into the expression *call* expects.

    Accepts both the legacy hyprlang vocabulary (``exec``, ``killactive``,
    ``workspace`` …) and the ``hl.dsp.*`` names the parser reports
    (``exec_cmd``, ``window.close``, ``focus`` …); table arguments are passed
    through verbatim. For ``o.bind``/``rebind`` an exec is written as the
    bare command string, which helpers.lua turns into ``hl.dsp.exec_cmd``.
    """
    d = dispatcher.strip()
    a = args.strip()
    if d.startswith("{"):
        return d  # Omarchy launch table — command_from resolves it at load
    dl = d.lower()
    if dl in ("exec", "exec_cmd"):
        return (
            f"hl.dsp.exec_cmd({lua_syntax.quote(a)})" if call == "hl.bind" else lua_syntax.quote(a)
        )
    if dl == "killactive":
        return "hl.dsp.window.close()"
    if dl == "exit":
        return "hl.dsp.exit()"
    if dl == "togglefloating":
        return 'hl.dsp.window.float({ action = "toggle" })'
    if dl == "pseudo":
        return "hl.dsp.window.pseudo()"
    if dl == "fullscreen":
        return "hl.dsp.window.fullscreen()"
    if dl == "movefocus":
        direction = _DIRECTION_MAP.get(a.lower(), a)
        return f"hl.dsp.focus({{ direction = {lua_syntax.quote(direction)} }})"
    if dl == "swapwindow":
        direction = _DIRECTION_MAP.get(a.lower(), a)
        return f"hl.dsp.window.swap({{ direction = {lua_syntax.quote(direction)} }})"
    if dl == "resizeactive":
        x, _, y = a.partition(" ")
        return f"hl.dsp.window.resize({{ x = {x or 0}, y = {y or 0} }})"
    if dl == "workspace":
        return f"hl.dsp.focus({{ workspace = {_wksp_arg(a)} }})"
    if dl == "movetoworkspace":
        return f"hl.dsp.window.move({{ workspace = {_wksp_arg(a)} }})"
    if dl == "togglespecialworkspace":
        return f"hl.dsp.workspace.toggle_special({lua_syntax.quote(a)})"
    if dl == "movewindow":
        return "hl.dsp.window.drag()"
    if dl == "resizewindow":
        return "hl.dsp.window.resize()"
    # An hl.dsp.* name as the parser reports it (or an unknown dispatcher):
    # pass through so nothing is silently dropped — a table argument verbatim,
    # plain text quoted.
    if not a:
        return f"hl.dsp.{d}()"
    if a.startswith("{"):
        return f"hl.dsp.{d}({a})"
    return f"hl.dsp.{d}({lua_syntax.quote(a)})"


def _format_bind_line(
    call: str,
    kind: str,
    mods: str,
    key: str,
    dispatcher: str,
    args: str,
    description: str,
    local_vars: dict[str, str],
) -> str:
    """Produce a canonical bind line in the *call* form."""
    key_expr = _compose_key_expr(mods, key, local_vars)
    dispatcher_expr = _compose_dispatcher_expr(dispatcher, args, call)
    opts = _opts_from_kind(kind)
    if call == "hl.bind":
        if description:
            opts["description"] = description
        line = f"hl.bind({key_expr}, {dispatcher_expr}"
    else:
        line = f"{call}({key_expr}, {lua_syntax.quote(description)}, {dispatcher_expr}"
    if opts:
        line += ", " + lua_syntax.format_lua_literal(opts)
    return line + ")"


def add_keybind(
    kind: str,
    mods: str,
    key: str,
    dispatcher: str,
    args: str,
    file: Path | None = None,
    description: str = "",
) -> bool:
    """Append a new keybind to *file* (default: bindings.lua).

    Written as ``o.bind(keys, "description", dispatcher[, opts])`` — the
    description is what makes it appear in Omarchy's keybindings menu
    (SUPER+K), which is the whole point of going through ``o.bind`` rather
    than ``hl.bind``. Returns True on success.
    """
    if file is None:
        file = KEYBINDS_FILE
    line = _format_bind_line(
        NEW_BIND_CALL, kind, mods, key, dispatcher, args, description, _local_string_vars(file)
    )
    return append_block(file, line)


def update_keybind(
    file_path: Path,
    line_idx: int,
    kind: str,
    mods: str,
    key: str,
    dispatcher: str,
    args: str,
    description: str | None = None,
) -> bool:
    """Replace the keybind at *line_idx* in *file_path*.

    The line keeps its original call form (``hl.bind`` / ``o.bind`` /
    ``rebind``) and, unless *description* is given, its original description.
    Returns True on success.
    """
    lines = read_lines(file_path)
    if not (0 <= line_idx < len(lines)):
        return False
    local_vars = _local_string_vars(file_path)
    existing = _parse_bind_line(lua_syntax.strip_lua_comment(lines[line_idx]), local_vars)
    call = existing.call if existing else NEW_BIND_CALL
    if description is None:
        description = existing.description if existing else ""
    line = _format_bind_line(call, kind, mods, key, dispatcher, args, description, local_vars)
    return update_line(file_path, line_idx, line)
