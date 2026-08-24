"""hyprconf.rules — read and write Hyprland window and workspace rules.

Window/workspace rules live in ``hyprland.lua`` (or any file it ``require``s).
New rules appended by hyprconf are written to dedicated ``windowrules.lua`` /
``workspacerules.lua`` files under ``conf.d/``, individually ``require``d from
``hyprland.lua`` (see ``try_require`` there) — this keeps the user's original
files untouched while still allowing addition and deletion.

Deletion of rules that exist in the original config files is performed
in-place on the file that owns the rule line.

Hyprland's own compositor config moved from hyprlang ``.conf`` to Lua in
0.55+ (``.conf`` deprecated in 0.56, slated for removal ~0.57). Following the
precedent set by this exact module during the 0.55 ``windowrulev2`` ->
``windowrule`` migration: the reader stays *permissive* (accepts rule lines
in both the legacy hyprlang form and the new Lua form, for configs mid
transition), the writer is *strict* (only ever emits Lua).
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
)
from .paths import HYPR_DIR, HYPRLAND_CONF, WINRULES_FILE, WKSPRULES_FILE

# ─────────────────────────────────────────────────────────────────────────────
#  Data types
# ─────────────────────────────────────────────────────────────────────────────


class RuleEntry(NamedTuple):
    rule: str  # full rule text, e.g. 'hl.window_rule({ float = true, match = { class = "X" } })'
    file_path: Path  # source file
    line_idx: int  # 0-based index in file_path


# ─────────────────────────────────────────────────────────────────────────────
#  Patterns — permissive reader: legacy hyprlang OR new Lua form
# ─────────────────────────────────────────────────────────────────────────────

_WIN_RULE_RE = re.compile(
    r"^(?:(?:windowrulev2|windowrule)\s*=|(?:local\s+\w+\s*=\s*)?hl\.window_rule\()",
    re.IGNORECASE,
)
_WKSP_RULE_RE = re.compile(
    r"^(?:workspace\s*=|(?:local\s+\w+\s*=\s*)?hl\.workspace_rule\()",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Parsing — follows `source = …` (legacy) and `require(...)`/`try_require(...)`
#  (Lua) recursively
# ─────────────────────────────────────────────────────────────────────────────


def _collect_rules(root: Path, pattern: re.Pattern) -> list[RuleEntry]:
    entries: list[RuleEntry] = []
    seen: set[Path] = set()

    def _parse(p: Path) -> None:
        if p in seen or not p.exists():
            return
        seen.add(p)
        strip_fn = lua_syntax.strip_lua_comment if p.suffix == ".lua" else strip_comment
        lines = read_lines(p)
        for idx, raw in enumerate(lines):
            stripped = strip_fn(raw)
            if not stripped:
                continue
            ms = SOURCE_RE.match(stripped)
            if ms:
                for sp in resolve_source_paths(ms.group(1), p.parent):
                    _parse(sp)
                continue
            mr = lua_syntax.REQUIRE_RE.match(stripped)
            if mr:
                for candidate in lua_syntax.resolve_require_paths(mr.group(1), HYPR_DIR):
                    if candidate.exists():
                        _parse(candidate)
                        break
                continue
            if pattern.search(stripped):
                entries.append(RuleEntry(rule=stripped, file_path=p, line_idx=idx))

    _parse(root)
    return entries


def read_window_rules_with_location(
    root: Path | None = None,
) -> list[RuleEntry]:
    """Return all window rules (windowrule / windowrulev2 / hl.window_rule) with file+line."""
    return _collect_rules(root or HYPRLAND_CONF, _WIN_RULE_RE)


def read_workspace_rules_with_location(
    root: Path | None = None,
) -> list[RuleEntry]:
    """Return all workspace rules with file+line."""
    return _collect_rules(root or HYPRLAND_CONF, _WKSP_RULE_RE)


# ─────────────────────────────────────────────────────────────────────────────
#  Writers — Lua table composition
# ─────────────────────────────────────────────────────────────────────────────
#
# The TUI's rule-edit screen collects the same free-text fields it always
# has: an "effect" string (e.g. "float", "opacity 0.9", "size 800 600") and a
# list of "field:value" filters (e.g. "class:Alacritty"). These are composed
# into a single-line `hl.window_rule({ … })` / `hl.workspace_rule({ … })`
# call — one call per line, so the existing (file, line_idx) addressing used
# throughout this package keeps working unchanged.

# Legacy windowrulev2 filter field  ->  current Lua `match` table key.
_PROP_RENAMES = {
    "floating": "float",
    "pinned": "pin",
    "onworkspace": "workspace",
    "initialclass": "initial_class",
    "initialtitle": "initial_title",
    "fullscreenstate": "fullscreen_state_internal",
}

# Effect keywords that get a value-type-driven rename (mirrors HL.WindowRuleSpec).
_EFFECT_RENAMES = {"bordersize": "border_size"}

# match-table fields that are boolean in Lua (HL.WindowRuleSpec.match values
# are `string|number|boolean`) — legacy filters spell these "0"/"1".
_BOOL_MATCH_FIELDS = {"xwayland", "float", "pin", "fullscreen"}

# workspace_rule option fields that are boolean in Lua (HL.WorkspaceRuleSpec).
_WKSP_BOOL_FIELDS = {"default", "persistent", "decorate", "no_border", "no_rounding", "no_shadow"}
_WKSP_OPT_RENAMES = {"on-created-empty": "on_created_empty"}


def _coerce_effect_value(rest: str) -> object:
    """Coerce a trailing effect value to int/float/str, e.g. 800 600 -> str, 0.9 -> float."""
    if " " in rest:
        return rest
    try:
        return int(rest)
    except ValueError:
        pass
    try:
        return float(rest)
    except ValueError:
        pass
    return rest


def _effect_to_kv(rule: str) -> tuple[str, object]:
    """Split an effect string (e.g. "opacity 0.9") into (lua_key, value).

    A bare keyword with no value (e.g. "float") becomes a boolean flag
    (``float = true``), matching the Lua API's boolean effect fields.
    """
    r = rule.strip()
    key, sep, rest = r.partition(" ")
    key = _EFFECT_RENAMES.get(key.lower(), key.lower())
    if not sep:
        return key, True
    return key, _coerce_effect_value(rest.strip())


def _match_clause(filt: str) -> tuple[str, object] | None:
    """Convert a legacy ``field:value`` filter to a ``(match_key, value)`` pair."""
    f = filt.strip()
    if not f:
        return None
    field, sep, value = f.partition(":")
    if not sep:
        return None
    field = _PROP_RENAMES.get(field.strip().lower(), field.strip().lower())
    value = value.strip()
    if field in _BOOL_MATCH_FIELDS and value in ("0", "1"):
        return field, value == "1"
    return field, value


def compose_window_rule(rule: str, filters: list[str]) -> str:
    """Build a single-line ``hl.window_rule({ … })`` call from *rule* + *filters*.

    *rule* is the effect, e.g. ``"float"`` or ``"size 800 600"``. *filters*
    are legacy ``field:value`` match clauses, e.g. ``["class:Alacritty"]``.
    """
    key, value = _effect_to_kv(rule)
    table: dict[str, object] = {key: value}
    match: dict[str, object] = {}
    for f in filters:
        kv = _match_clause(f)
        if kv:
            match[kv[0]] = kv[1]
    if match:
        table["match"] = match
    return "hl.window_rule(" + lua_syntax.format_lua_literal(table) + ")"


def add_window_rule(rule: str, filters: list[str], file: Path | None = None) -> bool:
    """Append an ``hl.window_rule({ … })`` line to *file*.

    *file* defaults to the managed windowrules file.
    """
    if file is None:
        file = WINRULES_FILE
    return append_block(file, compose_window_rule(rule, filters))


def _wksp_opt_clause(opt: str) -> tuple[str, object] | None:
    o = opt.strip()
    if not o:
        return None
    field, sep, value = o.partition(":")
    if not sep:
        return None
    field = _WKSP_OPT_RENAMES.get(field.strip().lower(), field.strip().lower())
    value = value.strip()
    if field in _WKSP_BOOL_FIELDS and value.lower() in ("true", "false"):
        return field, value.lower() == "true"
    return field, value


def compose_workspace_rule(workspace_id: str, options: str) -> str:
    """Build a single-line ``hl.workspace_rule({ … })`` call.

    *workspace_id*: e.g. ``"1"`` or ``"special:magic"``.
    *options*: e.g. ``"monitor:HDMI-A-1, default:true"``.
    """
    table: dict[str, object] = {"workspace": workspace_id.strip()}
    for opt in options.split(","):
        kv = _wksp_opt_clause(opt)
        if kv:
            table[kv[0]] = kv[1]
    return "hl.workspace_rule(" + lua_syntax.format_lua_literal(table) + ")"


def add_workspace_rule(workspace_id: str, options: str, file: Path | None = None) -> bool:
    """Append ``hl.workspace_rule({ … })`` to *file*.

    *file* defaults to the managed workspacerules file.
    """
    if file is None:
        file = WKSPRULES_FILE
    return append_block(file, compose_workspace_rule(workspace_id, options))
