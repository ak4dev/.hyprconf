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

import os
import re
from pathlib import Path
from typing import NamedTuple, Optional

from .file_edit import read_lines, update_line, delete_line, append_block, strip_comment

# ─────────────────────────────────────────────────────────────────────────────
#  Paths
# ─────────────────────────────────────────────────────────────────────────────

_CFG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
HYPR_DIR       = _CFG / "hypr"
HYPRLAND_CONF  = HYPR_DIR / "hyprland.conf"
# Managed rule files — created on first write; sourced via conf.d glob
WINRULES_FILE  = HYPR_DIR / "conf.d" / "50-windowrules.conf"
WKSPRULES_FILE = HYPR_DIR / "conf.d" / "50-workspacerules.conf"

# ─────────────────────────────────────────────────────────────────────────────
#  Data types
# ─────────────────────────────────────────────────────────────────────────────

class RuleEntry(NamedTuple):
    rule:      str     # full rule text, e.g. "windowrulev2 = float, class:Alacritty"
    file_path: Path    # source file
    line_idx:  int     # 0-based index in file_path


# ─────────────────────────────────────────────────────────────────────────────
#  Patterns
# ─────────────────────────────────────────────────────────────────────────────

_WIN_RULE_RE  = re.compile(r"^(windowrulev2|windowrule)\s*=", re.IGNORECASE)
_WKSP_RULE_RE = re.compile(r"^workspace\s*=", re.IGNORECASE)
_SOURCE_RE    = re.compile(r"^source\s*=\s*(.+)$")

# ─────────────────────────────────────────────────────────────────────────────
#  Parsing — follows source directives recursively
# ─────────────────────────────────────────────────────────────────────────────

def _collect_rules(root: Path, pattern: re.Pattern) -> list[RuleEntry]:
    entries: list[RuleEntry] = []
    seen:    set[Path]        = set()

    def _parse(p: Path) -> None:
        if p in seen or not p.exists():
            return
        seen.add(p)
        lines = read_lines(p)
        for idx, raw in enumerate(lines):
            stripped = strip_comment(raw)
            if not stripped:
                continue
            ms = _SOURCE_RE.match(stripped)
            if ms:
                src_raw = os.path.expanduser(os.path.expandvars(ms.group(1).strip()))
                src_path = Path(src_raw)
                if not src_path.is_absolute():
                    src_path = p.parent / src_path
                if "*" in src_path.name:
                    for sp in sorted(src_path.parent.glob(src_path.name)):
                        _parse(sp)
                else:
                    _parse(src_path)
                continue
            if pattern.search(stripped):
                entries.append(RuleEntry(rule=stripped, file_path=p, line_idx=idx))

    _parse(root)
    return entries


def read_window_rules_with_location(
    root: Optional[Path] = None,
) -> list[RuleEntry]:
    """Return all window rules (windowrule / windowrulev2) with file+line."""
    return _collect_rules(root or HYPRLAND_CONF, _WIN_RULE_RE)


def read_workspace_rules_with_location(
    root: Optional[Path] = None,
) -> list[RuleEntry]:
    """Return all workspace rules with file+line."""
    return _collect_rules(root or HYPRLAND_CONF, _WKSP_RULE_RE)


# ─────────────────────────────────────────────────────────────────────────────
#  Writers
# ─────────────────────────────────────────────────────────────────────────────

def add_window_rule(rule: str, filters: list[str],
                    file: Optional[Path] = None) -> bool:
    """Append ``windowrulev2 = RULE, FILTER...`` to *file*.

    *rule* is the action, e.g. ``"float"``.
    *filters* are match clauses, e.g. ``["class:Alacritty", "title:.*"]``.
    *file* defaults to the managed windowrules file.
    """
    if file is None:
        file = WINRULES_FILE
    filter_str = ", ".join(f.strip() for f in filters if f.strip())
    line = f"windowrulev2 = {rule.strip()}, {filter_str}" if filter_str \
        else f"windowrulev2 = {rule.strip()}"
    return append_block(file, line)


def add_workspace_rule(workspace_id: str, options: str,
                       file: Optional[Path] = None) -> bool:
    """Append ``workspace = ID, OPTIONS`` to *file*.

    *workspace_id*: e.g. ``"1"`` or ``"special:magic"``.
    *options*: e.g. ``"monitor:HDMI-A-1, default:true"``.
    *file* defaults to the managed workspacerules file.
    """
    if file is None:
        file = WKSPRULES_FILE
    options = options.strip()
    line = f"workspace = {workspace_id.strip()}, {options}" if options \
        else f"workspace = {workspace_id.strip()}"
    return append_block(file, line)


def delete_rule(file_path: Path, line_idx: int) -> bool:
    """Delete the rule line at *line_idx* in *file_path*."""
    return delete_line(file_path, line_idx)


def update_window_rule(file_path: Path, line_idx: int,
                       rule: str, filters: list[str]) -> bool:
    """Replace the window rule at *line_idx* in *file_path*."""
    filter_str = ", ".join(f.strip() for f in filters if f.strip())
    line = f"windowrulev2 = {rule.strip()}, {filter_str}" if filter_str \
        else f"windowrulev2 = {rule.strip()}"
    return update_line(file_path, line_idx, line)


def update_workspace_rule(file_path: Path, line_idx: int,
                          workspace_id: str, options: str) -> bool:
    """Replace the workspace rule at *line_idx* in *file_path*."""
    options = options.strip()
    line = f"workspace = {workspace_id.strip()}, {options}" if options \
        else f"workspace = {workspace_id.strip()}"
    return update_line(file_path, line_idx, line)


# ─────────────────────────────────────────────────────────────────────────────
#  Convenience: simple list (no location, for read-only display)
# ─────────────────────────────────────────────────────────────────────────────

def read_window_rules(root: Optional[Path] = None) -> list[str]:
    return [e.rule for e in read_window_rules_with_location(root)]


def read_workspace_rules(root: Optional[Path] = None) -> list[str]:
    return [e.rule for e in read_workspace_rules_with_location(root)]
