"""hyprconf.rules — read and write Hyprland window and workspace rules.

Window rules live in hyprland.conf (or any sourced file).
Workspace rules also live in hyprland.conf (or monitors.conf).

New rules appended by hyprconf are written to a dedicated
``windowrules.conf`` and ``workspacerules.conf`` file that is sourced from
hyprland.conf via the ``conf.d/*.conf`` glob — this keeps the user's original
file untouched while still allowing addition and deletion.

Deletion of rules that exist in the original config files is performed
in-place on the file that owns the rule line.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from .file_edit import (
    SOURCE_RE,
    append_block,
    delete_line,
    read_lines,
    resolve_source_paths,
    strip_comment,
    update_line,
)
from .paths import HYPRLAND_CONF, WINRULES_FILE, WKSPRULES_FILE

# ─────────────────────────────────────────────────────────────────────────────
#  Data types
# ─────────────────────────────────────────────────────────────────────────────


class RuleEntry(NamedTuple):
    rule: str  # full rule text, e.g. "windowrule = float on, match:class Alacritty"
    file_path: Path  # source file
    line_idx: int  # 0-based index in file_path


# ─────────────────────────────────────────────────────────────────────────────
#  Patterns
# ─────────────────────────────────────────────────────────────────────────────

_WIN_RULE_RE = re.compile(r"^(windowrulev2|windowrule)\s*=", re.IGNORECASE)
_WKSP_RULE_RE = re.compile(r"^workspace\s*=", re.IGNORECASE)

# ─────────────────────────────────────────────────────────────────────────────
#  Parsing — follows source directives recursively
# ─────────────────────────────────────────────────────────────────────────────


def _collect_rules(root: Path, pattern: re.Pattern) -> list[RuleEntry]:
    entries: list[RuleEntry] = []
    seen: set[Path] = set()

    def _parse(p: Path) -> None:
        if p in seen or not p.exists():
            return
        seen.add(p)
        lines = read_lines(p)
        for idx, raw in enumerate(lines):
            stripped = strip_comment(raw)
            if not stripped:
                continue
            ms = SOURCE_RE.match(stripped)
            if ms:
                for sp in resolve_source_paths(ms.group(1), p.parent):
                    _parse(sp)
                continue
            if pattern.search(stripped):
                entries.append(RuleEntry(rule=stripped, file_path=p, line_idx=idx))

    _parse(root)
    return entries


def read_window_rules_with_location(
    root: Path | None = None,
) -> list[RuleEntry]:
    """Return all window rules (windowrule / windowrulev2) with file+line."""
    return _collect_rules(root or HYPRLAND_CONF, _WIN_RULE_RE)


def read_workspace_rules_with_location(
    root: Path | None = None,
) -> list[RuleEntry]:
    """Return all workspace rules with file+line."""
    return _collect_rules(root or HYPRLAND_CONF, _WKSP_RULE_RE)


# ─────────────────────────────────────────────────────────────────────────────
#  Writers
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
#  Window-rule line composition (Hyprland 0.55 ``match:`` grammar)
# ─────────────────────────────────────────────────────────────────────────────
#
# Hyprland 0.55 retired the old ``windowrulev2 = <effect>, <field>:<regex>``
# form: its parser now rejects ``windowrulev2`` outright ("windowrulev2 is
# deprecated") and the surviving ``windowrule`` keyword expects
#
#     windowrule = <effect value>[, <effect value>…], match:<prop> <regex>[, …]
#
# i.e. every comma-clause must carry a value (the parser splits on the first
# space), match props are prefixed with ``match:``, and a few prop names were
# renamed. We keep accepting ``windowrulev2`` on *read* (legacy user configs)
# but only ever *write* the new grammar.

# Legacy windowrulev2 filter field  ->  current ``match:`` prop name.
_PROP_RENAMES = {
    "floating": "float",
    "pinned": "pin",
    "onworkspace": "workspace",
    "initialclass": "initial_class",
    "initialtitle": "initial_title",
    "fullscreenstate": "fullscreen_state_internal",
}


def _effect_clause(rule: str) -> str:
    """Normalise an effect so it always carries a value.

    0.55 requires every clause to have a value, so a bare boolean effect
    (``float``) becomes ``float on``; effects that already carry one
    (``size 800 600``, ``opacity 0.9``) are left untouched.
    """
    r = rule.strip()
    return r if " " in r else f"{r} on"


def _match_clause(filt: str) -> str:
    """Convert a legacy ``field:value`` filter to a ``match:field value`` clause.

    Clauses already in ``match:`` form, or without a ``field:value`` colon, are
    passed through unchanged.
    """
    f = filt.strip()
    if not f or f.startswith("match:"):
        return f
    field, sep, value = f.partition(":")
    if not sep:
        return f
    field = field.strip().lower()
    field = _PROP_RENAMES.get(field, field)
    return f"match:{field} {value.strip()}"


def compose_window_rule(rule: str, filters: list[str]) -> str:
    """Build a valid Hyprland 0.55 ``windowrule = …`` line from *rule* + *filters*."""
    clauses = [_effect_clause(rule)]
    clauses.extend(_match_clause(f) for f in filters if f.strip())
    return "windowrule = " + ", ".join(clauses)


def add_window_rule(rule: str, filters: list[str], file: Path | None = None) -> bool:
    """Append a ``windowrule = …`` line (0.55 ``match:`` grammar) to *file*.

    *rule* is the effect, e.g. ``"float"`` or ``"size 800 600"``.
    *filters* are legacy ``field:value`` match clauses, e.g.
    ``["class:Alacritty", "title:.*"]`` — translated to ``match:`` props.
    *file* defaults to the managed windowrules file.
    """
    if file is None:
        file = WINRULES_FILE
    return append_block(file, compose_window_rule(rule, filters))


def add_workspace_rule(workspace_id: str, options: str, file: Path | None = None) -> bool:
    """Append ``workspace = ID, OPTIONS`` to *file*.

    *workspace_id*: e.g. ``"1"`` or ``"special:magic"``.
    *options*: e.g. ``"monitor:HDMI-A-1, default:true"``.
    *file* defaults to the managed workspacerules file.
    """
    if file is None:
        file = WKSPRULES_FILE
    options = options.strip()
    line = (
        f"workspace = {workspace_id.strip()}, {options}"
        if options
        else f"workspace = {workspace_id.strip()}"
    )
    return append_block(file, line)


def delete_rule(file_path: Path, line_idx: int) -> bool:
    """Delete the rule line at *line_idx* in *file_path*."""
    return delete_line(file_path, line_idx)


def update_window_rule(file_path: Path, line_idx: int, rule: str, filters: list[str]) -> bool:
    """Replace the window rule at *line_idx* in *file_path* (0.55 ``match:`` grammar)."""
    return update_line(file_path, line_idx, compose_window_rule(rule, filters))


def update_workspace_rule(file_path: Path, line_idx: int, workspace_id: str, options: str) -> bool:
    """Replace the workspace rule at *line_idx* in *file_path*."""
    options = options.strip()
    line = (
        f"workspace = {workspace_id.strip()}, {options}"
        if options
        else f"workspace = {workspace_id.strip()}"
    )
    return update_line(file_path, line_idx, line)


# ─────────────────────────────────────────────────────────────────────────────
#  Convenience: simple list (no location, for read-only display)
# ─────────────────────────────────────────────────────────────────────────────


def read_window_rules(root: Path | None = None) -> list[str]:
    return [e.rule for e in read_window_rules_with_location(root)]


def read_workspace_rules(root: Path | None = None) -> list[str]:
    return [e.rule for e in read_workspace_rules_with_location(root)]
