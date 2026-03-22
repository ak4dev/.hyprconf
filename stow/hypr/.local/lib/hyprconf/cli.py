"""
hyprconf.cli — Python CLI for all hyprconf subcommands.

This module is the Python-side implementation of the hyprconf CLI commands
that operate on the shared config layer.  The bash entry-point
(~/.local/bin/hyprconf) delegates these subcommands here.

Usage (called from bash):
    python3 ~/.local/lib/hyprconf/cli.py <subcommand> [args…]

Subcommands
    get      [section] [key]
    set      <section> <key> <value…>
    configure
    schema   dump | validate | list-sections | keys <section>
    autodetect
    keybind  list | add <kind> <mods|-> <key> <dispatcher> [args…]
           | delete <index> | update <index> <kind> <mods|-> <key> <disp> [args…]
    rule     window  list | add <rule> <filter> | delete <index> | update <index> <rule> <filter>
             workspace list | add <id> <options> | delete <index>
    monitor  list | set <name> <res> <pos> <scale> [extras…] | delete <name>
    lock     list | add <type> | delete <index> | set <index> <key> <value>
    idle     list | add <type> | delete <index> | set <index> <key> <value>
    paper    list | set-wallpaper <monitor> <path> | add-preload <path>
           | delete-wallpaper <index> | delete-preload <index>
           | setting <key> <value>

All subcommands import from the shared schema / config / hyprctl / keybinds /
rules / monitors / hyprlock / hypridle / hyprpaper modules; no business logic
is duplicated here.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ── Shared library path ────────────────────────────────────────────────────────
# Allow running as a script without installing the package.
sys.path.insert(0, str(Path.home() / ".local" / "lib"))

from hyprconf.schema import (  # noqa: E402
    OPTION_SCHEMA,
    SECTION_ORDER,
    SECTION_LABELS,
    get_all_sections,
    get_option_meta,
    get_section_keys,
    validate_value,
    format_type_short,
    schema_to_dict,
)
from hyprconf.config import read_persisted, upsert_option  # noqa: E402
import hyprconf.hyprctl as _hyprctl  # noqa: E402

# ── Terminal colours ───────────────────────────────────────────────────────────

if sys.stdout.isatty():
    _B = "\033[1m"
    _C = "\033[36m"
    _Y = "\033[33m"
    _R = "\033[0m"
else:
    _B = _C = _Y = _R = ""


# ── Section list for the configure REPL ───────────────────────────────────────

_REPL_SECTIONS: list[str] = [s for s in SECTION_ORDER if s and s in OPTION_SCHEMA]


# ════════════════════════════════════════════════════════════════════════════
#  get
# ════════════════════════════════════════════════════════════════════════════

def cmd_get(args: list[str]) -> int:
    """hyprconf get [section] [key]"""
    section = args[0] if args else ""
    key     = args[1] if len(args) > 1 else ""

    if not section:
        print(f"{_B}Available sections:{_R}")
        for s in _REPL_SECTIONS:
            label = SECTION_LABELS.get(s, s)
            print(f"  {s:<22}  {label}")
        return 0

    if section not in OPTION_SCHEMA:
        print(f"{_Y}Unknown section: {section}  (run: hyprconf get){_R}", file=sys.stderr)
        return 1

    if key:
        meta = get_option_meta(section, key)
        if meta is None:
            print(
                f"{_Y}Unknown option '{key}' in section '{section}'  "
                f"(try: hyprconf get {section}){_R}",
                file=sys.stderr,
            )
            return 1
        type_, default, desc = meta
        current = _get_live_or_persisted(section, key, default)
        print(f"{_B}{section}:{key}{_R}  {_C}{current}{_R}")
        print(f"  type: {type_}   default: {default}")
        print(f"  {desc}")
        return 0

    # Section table
    print(f"{_B}{section}{_R}")
    print(f"  {'KEY':<38}  {'CURRENT':<22}  DEFAULT")
    print(f"  {'─'*38}  {'─'*22}  {'─'*12}")
    for k in get_section_keys(section):
        meta = get_option_meta(section, k)
        if meta is None:
            continue
        type_, default, _desc = meta
        current = _get_live_or_persisted(section, k, default)
        if current == default:
            current_str = f"{_Y}({current}){_R}"
        else:
            current_str = f"{_C}{current}{_R}"
        print(f"  {k:<38}  {current_str:<22}  {default}")
    return 0


def _get_live_or_persisted(section: str, key: str, default: str) -> str:
    live = _hyprctl.get_option(section, key)
    if live is not None:
        return live
    persisted = read_persisted(section, key)
    if persisted is not None:
        return persisted
    return f"({default})"


# ════════════════════════════════════════════════════════════════════════════
#  set
# ════════════════════════════════════════════════════════════════════════════

def cmd_set(args: list[str]) -> int:
    """hyprconf set <section> <key> <value…>"""
    if len(args) < 3:
        print(
            f"{_Y}Usage: hyprconf set <section> <key> <value>\n"
            f"Example: hyprconf set general gaps_in 8{_R}",
            file=sys.stderr,
        )
        return 1

    section = args[0]
    key     = args[1]
    value   = " ".join(args[2:])

    if section not in OPTION_SCHEMA:
        print(f"{_Y}Unknown section: {section}  (run: hyprconf get){_R}", file=sys.stderr)
        return 1

    meta = get_option_meta(section, key)
    if meta is None:
        print(
            f"{_Y}Unknown option '{key}' in section '{section}'  "
            f"(try: hyprconf get {section}){_R}",
            file=sys.stderr,
        )
        return 1

    type_, default, _desc = meta
    ok, err = validate_value(type_, value)
    if not ok:
        print(f"{_Y}Invalid value for {type_}: {err}{_R}", file=sys.stderr)
        return 1

    if _hyprctl.set_option(section, key, value):
        print(f"{_B}Applied:{_R}  {_C}{section}:{key}{_R} = {value}")
    else:
        print(
            f"{_Y}Warning: Hyprland not running — change written to config only.{_R}"
        )

    upsert_option(section, key, value)
    from hyprconf.config import OVERRIDES_FILE
    print(f"{_B}Persisted:{_R} {OVERRIDES_FILE}")
    return 0


# ════════════════════════════════════════════════════════════════════════════
#  configure  — interactive IOS-style REPL
# ════════════════════════════════════════════════════════════════════════════

def cmd_configure(_args: list[str]) -> int:
    """Interactive Cisco IOS-style configuration REPL."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(f"{_Y}configure requires an interactive TTY{_R}", file=sys.stderr)
        return 1

    print(
        f"\n{_B}  hyprconf configure{_R}  — interactive configuration mode\n"
        f"{_C}  Type '?' for help, 'exit' to leave.{_R}\n"
    )

    context = ""  # empty = root, otherwise = section name

    while True:
        if context:
            prompt = f"hyprconf(config-{context})# "
        else:
            prompt = "hyprconf(config)# "

        try:
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        if not context:
            # ── Root context ──
            if line in ("exit", "quit", "q"):
                print("Leaving configure mode.")
                break
            if line in ("?", "help"):
                _repl_help_root()
            else:
                if line in _REPL_SECTIONS:
                    context = line
                else:
                    print(f"{_Y}  Unknown section: {line}{_R}")
                    print("  Type '?' to list sections.")
        else:
            # ── Section context ──
            if line in ("exit", "quit", "q", "up"):
                context = ""
            elif line in ("?", "help"):
                _repl_help_section(context)
            elif line == "show":
                cmd_get([context])
            elif line.startswith("show "):
                cmd_get([context, line[5:].strip()])
            elif line.startswith("no "):
                _repl_reset(context, line[3:].strip())
            elif line.endswith(" ?"):
                _repl_query(context, line[:-2].strip())
            else:
                parts = line.split(None, 1)
                if len(parts) == 2:
                    cmd_set([context, parts[0], parts[1]])
                elif len(parts) == 1:
                    cmd_get([context, parts[0]])

    return 0


# ── REPL helpers ───────────────────────────────────────────────────────────────


def _repl_help_root() -> None:
    print(f"\n{_B}  Available sections:{_R}")
    for s in _REPL_SECTIONS:
        keys = get_section_keys(s)
        first = keys[0] if keys else ""
        hint  = f"<{first}> ..." if first else ""
        print(f"  {s:<22}  {hint}")
    print()
    print(f"  {'?':<22}  Show this help")
    print(f"  {'exit / quit':<22}  Leave configure mode")
    print()


def _repl_help_section(section: str) -> None:
    print(f"\n{_B}  {section} options:{_R}")
    print(f"  {'KEY':<40}  {'TYPE':<12}  {'DEFAULT':<18}  DESCRIPTION")
    print(f"  {'─'*40}  {'─'*12}  {'─'*18}")
    for k in get_section_keys(section):
        meta = get_option_meta(section, k)
        if meta is None:
            continue
        type_, default, desc = meta
        tshort = format_type_short(type_)
        print(f"  {k:<40}  {tshort:<12}  {default:<18}  {desc}")
    print()
    print(f"  {'<key> <value>':<40}  Set option")
    print(f"  {'<key> ?':<40}  Show option details and current value")
    print(f"  {'no <key>':<40}  Reset option to its default value")
    print(f"  {'show [key]':<40}  Show current value(s)")
    print(f"  {'exit':<40}  Return to root context")
    print()


def _repl_reset(section: str, key: str) -> None:
    meta = get_option_meta(section, key)
    if meta is None:
        print(f"{_Y}  Unknown key: {key}{_R}")
        return
    _, default, _ = meta
    cmd_set([section, key, default])


def _repl_query(section: str, key: str) -> None:
    meta = get_option_meta(section, key)
    if meta is None:
        print(f"{_Y}  Unknown key: {key}{_R}")
        return
    cmd_get([section, key])


# ════════════════════════════════════════════════════════════════════════════
#  schema
# ════════════════════════════════════════════════════════════════════════════

def cmd_schema(args: list[str]) -> int:
    """hyprconf schema dump | validate | list-sections | keys <section>"""
    sub = args[0] if args else ""

    if sub == "dump":
        print(json.dumps(schema_to_dict(), indent=2))
        return 0

    if sub == "list-sections":
        for s in get_all_sections():
            label = SECTION_LABELS.get(s, s)
            keys  = len(OPTION_SCHEMA[s])
            print(f"  {s:<24}  {label:<18}  ({keys} keys)")
        # Special sections managed outside OPTION_SCHEMA
        for s, label, note in (
            ("monitors", "Monitors",  "use: hyprconf get monitors"),
            ("theme",    "Theme",     "use: hyprconf theme"),
            ("hardware", "Hardware",  "use: hyprconf hardware"),
        ):
            print(f"  {s:<24}  {label:<18}  ({note})")
        return 0

    if sub == "keys":
        section = args[1] if len(args) > 1 else ""
        if not section or section not in OPTION_SCHEMA:
            print(f"{_Y}Usage: hyprconf schema keys <section>{_R}", file=sys.stderr)
            return 1
        for k, (t, d, desc) in OPTION_SCHEMA[section].items():
            tshort = format_type_short(t)
            print(f"  {k:<40}  {tshort:<8}  {d:<18}  {desc}")
        return 0

    if sub == "validate":
        from hyprconf.config import read_all_persisted
        managed = read_all_persisted()
        errors = 0
        for hkey, value in managed.items():
            parts = hkey.rsplit(":", 1)
            if len(parts) != 2:
                continue
            section, key = parts[0].replace(":", "."), parts[1]
            meta = get_option_meta(section, key)
            if meta is None:
                print(f"  {_Y}UNKNOWN{_R}  {hkey}")
                errors += 1
                continue
            type_, _, _ = meta
            ok, err = validate_value(type_, value)
            if not ok:
                print(f"  {_Y}INVALID{_R}  {hkey} = {value!r}  — {err}")
                errors += 1
            else:
                print(f"  {'OK':<8}  {hkey} = {value}")
        if errors:
            print(f"\n{errors} issue(s) found.")
            return 1
        print("All managed options are valid.")
        return 0

    print(f"{_Y}Usage: hyprconf schema dump|validate|list-sections|keys <section>{_R}", file=sys.stderr)
    return 1


# ════════════════════════════════════════════════════════════════════════════
#  autodetect
# ════════════════════════════════════════════════════════════════════════════

def cmd_autodetect(args: list[str]) -> int:
    """Scan existing Hyprland config and non-destructively import it."""
    from hyprconf.autodetect import detect_and_parse, migrate

    print("  Scanning for existing Hyprland configuration…")
    result = detect_and_parse()

    if result.found_config is None:
        print("  No hyprland.conf found.  Nothing to import.")
        return 0

    print(f"  Found: {result.found_config}")
    print(f"  Parsed {result.option_count} option(s)")
    if result.warning_count:
        print(f"  {result.warning_count} line(s) could not be parsed:")
        for w in result.unknown_lines[:10]:
            print(f"    {w}")
        if result.warning_count > 10:
            print(f"    … and {result.warning_count - 10} more")

    n = migrate(result)
    from hyprconf.config import OVERRIDES_FILE
    print(f"  Wrote {n} option(s) to {OVERRIDES_FILE}")
    return 0


# ════════════════════════════════════════════════════════════════════════════
#  Entry point
# ════════════════════════════════════════════════════════════════════════════

def main() -> int:
    args = sys.argv[1:]
    cmd  = args[0] if args else ""
    rest = args[1:]

    if cmd == "get":
        return cmd_get(rest)
    if cmd == "set":
        return cmd_set(rest)
    if cmd in ("configure", "conf"):
        return cmd_configure(rest)
    if cmd == "schema":
        return cmd_schema(rest)
    if cmd == "autodetect":
        return cmd_autodetect(rest)

    if cmd == "keybind":
        return cmd_keybind(rest)
    if cmd == "rule":
        return cmd_rule(rest)
    if cmd == "monitor":
        return cmd_monitor(rest)
    if cmd == "lock":
        return cmd_lock(rest)
    if cmd == "idle":
        return cmd_idle(rest)
    if cmd == "paper":
        return cmd_paper(rest)

    print(
        f"{_Y}Usage: hyprconf-cli get|set|configure|schema|autodetect"
        f"|keybind|rule|monitor|lock|idle|paper [args…]{_R}",
        file=sys.stderr,
    )
    return 1


# ════════════════════════════════════════════════════════════════════════════
#  keybind
# ════════════════════════════════════════════════════════════════════════════

def cmd_keybind(args: list[str]) -> int:
    """hyprconf keybind list|add|delete|update"""
    from hyprconf.keybinds import (
        read_keybinds_with_location,
        add_keybind,
        delete_keybind,
        update_keybind,
    )

    sub = args[0] if args else ""

    if sub == "list" or not sub:
        entries = read_keybinds_with_location()
        if not entries:
            print("  No keybinds found.")
            return 0
        print(f"  {'#':<4} {'KIND':<8} {'MODS':<22} {'KEY':<10} {'DISPATCHER':<18} ARGS")
        print(f"  {'─'*4} {'─'*8} {'─'*22} {'─'*10} {'─'*18} {'─'*20}")
        for i, e in enumerate(entries, 1):
            mods = e.mods if e.mods else "(none)"
            args_str = e.args or ""
            print(f"  {i:<4} {e.kind:<8} {mods:<22} {e.key:<10} {e.dispatcher:<18} {args_str}")
        return 0

    if sub == "add":
        # add <kind> <mods|-> <key> <dispatcher> [args…]
        if len(args) < 5:
            print(
                f"{_Y}Usage: hyprconf keybind add <kind> <mods|-> <key> <dispatcher> [args…]\n"
                f"  mods: SUPER  'SUPER SHIFT'  '-' (empty)  etc.{_R}",
                file=sys.stderr,
            )
            return 1
        kind       = args[1]
        mods       = "" if args[2] == "-" else args[2]
        key        = args[3]
        dispatcher = args[4]
        kbargs     = " ".join(args[5:]) if len(args) > 5 else ""
        add_keybind(kind, mods, key, dispatcher, kbargs)
        print(f"  {_B}Added:{_R}  {kind} = {mods}, {key}, {dispatcher}{', ' + kbargs if kbargs else ''}")
        return 0

    if sub == "delete":
        if len(args) < 2 or not args[1].isdigit():
            print(f"{_Y}Usage: hyprconf keybind delete <index>  (1-based from 'keybind list'){_R}", file=sys.stderr)
            return 1
        entries = read_keybinds_with_location()
        idx = int(args[1]) - 1
        if idx < 0 or idx >= len(entries):
            print(f"{_Y}Index {args[1]} out of range (1–{len(entries)}){_R}", file=sys.stderr)
            return 1
        e = entries[idx]
        delete_keybind(e.file_path, e.line_idx)
        print(f"  {_B}Deleted:{_R}  {e.kind} = {e.mods!r}, {e.key!r}, {e.dispatcher!r}")
        return 0

    if sub == "update":
        # update <index> <kind> <mods|-> <key> <dispatcher> [args…]
        if len(args) < 6 or not args[1].isdigit():
            print(
                f"{_Y}Usage: hyprconf keybind update <index> <kind> <mods|-> <key> <dispatcher> [args…]{_R}",
                file=sys.stderr,
            )
            return 1
        entries = read_keybinds_with_location()
        idx = int(args[1]) - 1
        if idx < 0 or idx >= len(entries):
            print(f"{_Y}Index {args[1]} out of range (1–{len(entries)}){_R}", file=sys.stderr)
            return 1
        e    = entries[idx]
        kind = args[2]
        mods = "" if args[3] == "-" else args[3]
        key  = args[4]
        disp = args[5]
        kbargs = " ".join(args[6:]) if len(args) > 6 else ""
        update_keybind(e.file_path, e.line_idx, kind, mods, key, disp, kbargs)
        print(f"  {_B}Updated:{_R}  [{args[1]}] → {kind} = {mods}, {key}, {disp}{', ' + kbargs if kbargs else ''}")
        return 0

    print(f"{_Y}Usage: hyprconf keybind list|add|delete|update{_R}", file=sys.stderr)
    return 1


# ════════════════════════════════════════════════════════════════════════════
#  rule
# ════════════════════════════════════════════════════════════════════════════

def cmd_rule(args: list[str]) -> int:
    """hyprconf rule window|workspace …"""
    from hyprconf.rules import (
        read_window_rules_with_location,
        read_workspace_rules_with_location,
        add_window_rule,
        add_workspace_rule,
        delete_rule,
        update_window_rule,
        update_workspace_rule,
    )

    kind = args[0] if args else ""
    sub  = args[1] if len(args) > 1 else ""

    if kind == "window":
        if sub == "list" or not sub:
            entries = read_window_rules_with_location()
            if not entries:
                print("  No window rules found.")
                return 0
            print(f"  {'#':<4} {'FILE':<20} {'LINE':<6} RULE")
            print(f"  {'─'*4} {'─'*20} {'─'*6} {'─'*50}")
            for i, e in enumerate(entries, 1):
                print(f"  {i:<4} {e.file_path.name:<20} {e.line_idx + 1:<6} {e.rule}")
            return 0

        if sub == "add":
            # add <rule_part> <filter_part>
            # e.g.: hyprconf rule window add "float" "class:kitty"
            if len(args) < 4:
                print(
                    f"{_Y}Usage: hyprconf rule window add <rule> <filter>\n"
                    f"  Example: hyprconf rule window add 'float' 'class:kitty'{_R}",
                    file=sys.stderr,
                )
                return 1
            rule_str   = args[2]
            filter_str = args[3]
            add_window_rule(rule_str, [filter_str])
            print(f"  {_B}Added:{_R}  windowrule = {rule_str}, {filter_str}")
            return 0

        if sub == "delete":
            if len(args) < 3 or not args[2].isdigit():
                print(f"{_Y}Usage: hyprconf rule window delete <index>{_R}", file=sys.stderr)
                return 1
            entries = read_window_rules_with_location()
            idx = int(args[2]) - 1
            if idx < 0 or idx >= len(entries):
                print(f"{_Y}Index out of range{_R}", file=sys.stderr)
                return 1
            e = entries[idx]
            delete_rule(e.file_path, e.line_idx)
            print(f"  {_B}Deleted:{_R}  {e.rule}")
            return 0

        if sub == "update":
            if len(args) < 5 or not args[2].isdigit():
                print(f"{_Y}Usage: hyprconf rule window update <index> <rule> <filter>{_R}", file=sys.stderr)
                return 1
            entries = read_window_rules_with_location()
            idx = int(args[2]) - 1
            if idx < 0 or idx >= len(entries):
                print(f"{_Y}Index out of range{_R}", file=sys.stderr)
                return 1
            e = entries[idx]
            update_window_rule(e.file_path, e.line_idx, args[3], args[4])
            print(f"  {_B}Updated:{_R}  [{args[2]}] → windowrule = {args[3]}, {args[4]}")
            return 0

        print(f"{_Y}Usage: hyprconf rule window list|add|delete|update{_R}", file=sys.stderr)
        return 1

    if kind == "workspace":
        if sub == "list" or not sub:
            entries = read_workspace_rules_with_location()
            if not entries:
                print("  No workspace rules found.")
                return 0
            print(f"  {'#':<4} {'FILE':<20} {'LINE':<6} RULE")
            print(f"  {'─'*4} {'─'*20} {'─'*6} {'─'*50}")
            for i, e in enumerate(entries, 1):
                print(f"  {i:<4} {e.file_path.name:<20} {e.line_idx + 1:<6} {e.rule}")
            return 0

        if sub == "add":
            if len(args) < 4:
                print(
                    f"{_Y}Usage: hyprconf rule workspace add <ws_id> <options>\n"
                    f"  Example: hyprconf rule workspace add 1 'monitor:HDMI-A-1'{_R}",
                    file=sys.stderr,
                )
                return 1
            ws_id   = args[2]
            options = args[3]
            add_workspace_rule(ws_id, options)
            print(f"  {_B}Added:{_R}  workspace = {ws_id}, {options}")
            return 0

        if sub == "delete":
            if len(args) < 3 or not args[2].isdigit():
                print(f"{_Y}Usage: hyprconf rule workspace delete <index>{_R}", file=sys.stderr)
                return 1
            entries = read_workspace_rules_with_location()
            idx = int(args[2]) - 1
            if idx < 0 or idx >= len(entries):
                print(f"{_Y}Index out of range{_R}", file=sys.stderr)
                return 1
            e = entries[idx]
            delete_rule(e.file_path, e.line_idx)
            print(f"  {_B}Deleted:{_R}  {e.rule}")
            return 0

        if sub == "update":
            if len(args) < 5 or not args[2].isdigit():
                print(f"{_Y}Usage: hyprconf rule workspace update <index> <ws_id> <options>{_R}", file=sys.stderr)
                return 1
            entries = read_workspace_rules_with_location()
            idx = int(args[2]) - 1
            if idx < 0 or idx >= len(entries):
                print(f"{_Y}Index out of range{_R}", file=sys.stderr)
                return 1
            e = entries[idx]
            update_workspace_rule(e.file_path, e.line_idx, args[3], args[4])
            print(f"  {_B}Updated:{_R}  [{args[2]}] → workspace = {args[3]}, {args[4]}")
            return 0

        print(f"{_Y}Usage: hyprconf rule workspace list|add|delete|update{_R}", file=sys.stderr)
        return 1

    print(f"{_Y}Usage: hyprconf rule window|workspace …{_R}", file=sys.stderr)
    return 1


# ════════════════════════════════════════════════════════════════════════════
#  monitor
# ════════════════════════════════════════════════════════════════════════════

def cmd_monitor(args: list[str]) -> int:
    """hyprconf monitor list|set|delete|field"""
    from hyprconf.monitors import (
        read_monitor_configs, upsert_monitor, delete_monitor,
        get_monitor_fields, update_monitor_field, _MONITOR_FIELDS,
    )

    sub = args[0] if args else ""

    if sub == "field":
        action = args[1] if len(args) > 1 else ""
        if action == "show" or not action:
            name = args[2] if len(args) > 2 else None
            print(get_monitor_fields(name))
            return 0
        if action == "set":
            if len(args) < 5:
                print(
                    f"{_Y}Usage: hyprconf monitor field set <name> <field> <value>\n"
                    f"  Fields: {', '.join(sorted(_MONITOR_FIELDS))}{_R}",
                    file=sys.stderr,
                )
                return 1
            name  = args[2]
            field = args[3]
            value = args[4]
            try:
                update_monitor_field(name, field, value)
            except ValueError as exc:
                print(f"{_Y}{exc}{_R}", file=sys.stderr)
                return 1
            print(f"  {_B}Set:{_R}  {name}  {field} = {value}")
            return 0
        print(f"{_Y}Usage: hyprconf monitor field show [<name>] | set <name> <field> <value>{_R}", file=sys.stderr)
        return 1

    if sub == "list" or not sub:
        configs = read_monitor_configs()
        if not configs:
            print("  No monitor configs found.")
            return 0
        print(f"  {'NAME':<18} {'RESOLUTION':<16} {'POSITION':<12} {'SCALE':<8} EXTRAS")
        print(f"  {'─'*18} {'─'*16} {'─'*12} {'─'*8} {'─'*20}")
        for m in configs:
            print(
                f"  {m.name:<18} {m.resolution:<16} {m.position:<12} "
                f"{m.scale:<8} {m.extras or ''}"
            )
        return 0

    if sub == "set":
        # set <name> <resolution> <position> <scale> [extras…]
        if len(args) < 5:
            print(
                f"{_Y}Usage: hyprconf monitor set <name> <resolution> <position> <scale> [extras…]\n"
                f"  Example: hyprconf monitor set HDMI-A-1 3840x2160@120 0x0 1.5{_R}",
                file=sys.stderr,
            )
            return 1
        name       = args[1]
        resolution = args[2]
        position   = args[3]
        scale      = args[4]
        extras     = " ".join(args[5:]) if len(args) > 5 else ""
        upsert_monitor(name, resolution, position, scale, extras)
        print(f"  {_B}Set:{_R}  {name}  {resolution}  {position}  scale={scale}{', ' + extras if extras else ''}")
        return 0

    if sub == "delete":
        if len(args) < 2:
            print(f"{_Y}Usage: hyprconf monitor delete <name>{_R}", file=sys.stderr)
            return 1
        name = args[1]
        configs = read_monitor_configs()
        mc = next((m for m in configs if m.name == name), None)
        if mc is None:
            print(f"{_Y}Monitor '{name}' not found in monitors.conf{_R}", file=sys.stderr)
            return 1
        delete_monitor(mc.file_path, mc.line_idx)
        print(f"  {_B}Deleted:{_R}  {name}")
        return 0

    print(f"{_Y}Usage: hyprconf monitor list|set|delete|field{_R}", file=sys.stderr)
    return 1


# ════════════════════════════════════════════════════════════════════════════
#  lock  — hyprlock.conf management
# ════════════════════════════════════════════════════════════════════════════

def cmd_lock(args: list[str]) -> int:
    """hyprconf lock list|add|delete|set"""
    from hyprconf.hyprlock import (
        read_hyprlock_blocks,
        add_hyprlock_block,
        delete_hyprlock_block,
        update_hyprlock_field,
        BLOCK_TYPES,
    )

    sub = args[0] if args else ""

    if sub == "list" or not sub:
        blocks = read_hyprlock_blocks()
        if not blocks:
            print("  No hyprlock blocks found.")
            return 0
        print(f"  {'#':<4} {'TYPE':<14} {'FIELDS'}")
        print(f"  {'─'*4} {'─'*14} {'─'*50}")
        for i, b in enumerate(blocks, 1):
            fields_preview = "  ".join(f"{k}={v}" for k, v in list(b.fields.items())[:4])
            print(f"  {i:<4} {b.block_type:<14} {fields_preview}")
        return 0

    if sub == "add":
        block_type = args[1] if len(args) > 1 else ""
        if not block_type or block_type not in BLOCK_TYPES:
            print(
                f"{_Y}Usage: hyprconf lock add <type>\n"
                f"  Types: {', '.join(BLOCK_TYPES)}{_R}",
                file=sys.stderr,
            )
            return 1
        ok = add_hyprlock_block(block_type)
        print(f"  {_B}Added:{_R}  {block_type} block")
        return 0 if ok else 1

    if sub == "delete":
        if len(args) < 2 or not args[1].isdigit():
            print(f"{_Y}Usage: hyprconf lock delete <index>  (1-based from 'lock list'){_R}", file=sys.stderr)
            return 1
        blocks = read_hyprlock_blocks()
        idx = int(args[1]) - 1
        if not (0 <= idx < len(blocks)):
            print(f"{_Y}Index out of range (1–{len(blocks)}){_R}", file=sys.stderr)
            return 1
        b = blocks[idx]
        ok = delete_hyprlock_block(b.file_path, b.start_line, b.end_line)
        print(f"  {_B}Deleted:{_R}  [{args[1]}] {b.block_type}")
        return 0 if ok else 1

    if sub == "set":
        # set <index> <key> <value>
        if len(args) < 4 or not args[1].isdigit():
            print(
                f"{_Y}Usage: hyprconf lock set <index> <key> <value>\n"
                f"  Example: hyprconf lock set 2 blur_passes 5{_R}",
                file=sys.stderr,
            )
            return 1
        blocks = read_hyprlock_blocks()
        idx = int(args[1]) - 1
        if not (0 <= idx < len(blocks)):
            print(f"{_Y}Index out of range (1–{len(blocks)}){_R}", file=sys.stderr)
            return 1
        b     = blocks[idx]
        key   = args[2]
        value = " ".join(args[3:])
        ok = update_hyprlock_field(b.file_path, b.start_line, b.end_line, key, value)
        print(f"  {_B}Set:{_R}  [{args[1]}] {b.block_type}.{key} = {value}")
        return 0 if ok else 1

    print(f"{_Y}Usage: hyprconf lock list|add|delete|set{_R}", file=sys.stderr)
    return 1


# ════════════════════════════════════════════════════════════════════════════
#  idle  — hypridle.conf management
# ════════════════════════════════════════════════════════════════════════════

def cmd_idle(args: list[str]) -> int:
    """hyprconf idle list|add|delete|set"""
    from hyprconf.hypridle import (
        read_hypridle_blocks,
        add_hypridle_block,
        delete_hypridle_block,
        update_hypridle_field,
        BLOCK_TYPES,
    )

    sub = args[0] if args else ""

    if sub == "list" or not sub:
        blocks = read_hypridle_blocks()
        if not blocks:
            print("  No hypridle blocks found.")
            return 0
        print(f"  {'#':<4} {'TYPE':<12} {'FIELDS'}")
        print(f"  {'─'*4} {'─'*12} {'─'*60}")
        for i, b in enumerate(blocks, 1):
            fields_preview = "  ".join(f"{k}={v}" for k, v in b.fields.items())
            print(f"  {i:<4} {b.block_type:<12} {fields_preview}")
        return 0

    if sub == "add":
        block_type = args[1] if len(args) > 1 else ""
        if not block_type or block_type not in BLOCK_TYPES:
            print(
                f"{_Y}Usage: hyprconf idle add <type>\n"
                f"  Types: {', '.join(BLOCK_TYPES)}\n"
                f"  Shorthand for listener: hyprconf idle add listener{_R}",
                file=sys.stderr,
            )
            return 1
        ok = add_hypridle_block(block_type)
        print(f"  {_B}Added:{_R}  {block_type} block")
        return 0 if ok else 1

    if sub == "delete":
        if len(args) < 2 or not args[1].isdigit():
            print(f"{_Y}Usage: hyprconf idle delete <index>  (1-based from 'idle list'){_R}", file=sys.stderr)
            return 1
        blocks = read_hypridle_blocks()
        idx = int(args[1]) - 1
        if not (0 <= idx < len(blocks)):
            print(f"{_Y}Index out of range (1–{len(blocks)}){_R}", file=sys.stderr)
            return 1
        b = blocks[idx]
        ok = delete_hypridle_block(b.file_path, b.start_line, b.end_line)
        print(f"  {_B}Deleted:{_R}  [{args[1]}] {b.block_type}")
        return 0 if ok else 1

    if sub == "set":
        if len(args) < 4 or not args[1].isdigit():
            print(
                f"{_Y}Usage: hyprconf idle set <index> <key> <value>\n"
                f"  Example: hyprconf idle set 2 timeout 600{_R}",
                file=sys.stderr,
            )
            return 1
        blocks = read_hypridle_blocks()
        idx = int(args[1]) - 1
        if not (0 <= idx < len(blocks)):
            print(f"{_Y}Index out of range (1–{len(blocks)}){_R}", file=sys.stderr)
            return 1
        b     = blocks[idx]
        key   = args[2]
        value = " ".join(args[3:])
        ok = update_hypridle_field(b.file_path, b.start_line, b.end_line, key, value)
        print(f"  {_B}Set:{_R}  [{args[1]}] {b.block_type}.{key} = {value}")
        return 0 if ok else 1

    print(f"{_Y}Usage: hyprconf idle list|add|delete|set{_R}", file=sys.stderr)
    return 1


# ════════════════════════════════════════════════════════════════════════════
#  paper  — hyprpaper.conf management
# ════════════════════════════════════════════════════════════════════════════

def cmd_paper(args: list[str]) -> int:
    """hyprconf paper list|set-wallpaper|add-preload|delete-wallpaper|delete-preload|setting"""
    from hyprconf.hyprpaper import (
        read_all,
        read_wallpaper_blocks,
        read_wallpaper_lines,
        read_preloads,
        add_preload,
        delete_preload,
        set_wallpaper_line,
        delete_wallpaper_block,
        delete_wallpaper_line,
        set_setting,
    )

    sub = args[0] if args else ""

    if sub == "list" or not sub:
        data = read_all()
        print(f"\n{_B}  Settings / Variables:{_R}")
        for s in data["settings"]:
            print(f"    {s.key} = {s.value}")

        if data["preloads"]:
            print(f"\n{_B}  Preloads:{_R}")
            for i, p in enumerate(data["preloads"], 1):
                print(f"  {i:<4} preload = {p.path}")

        if data["wallpaper_lines"]:
            print(f"\n{_B}  Wallpapers (line format):{_R}")
            for i, w in enumerate(data["wallpaper_lines"], 1):
                mon = w.monitor or "(all)"
                print(f"  {i:<4} wallpaper = {mon}, {w.path}")

        if data["wallpaper_blocks"]:
            print(f"\n{_B}  Wallpapers (block format):{_R}")
            for i, b in enumerate(data["wallpaper_blocks"], 1):
                mon  = b.fields.get("monitor", "")  or "(all)"
                path = b.fields.get("path", "")
                fit  = b.fields.get("fit_mode", "")
                print(f"  {i:<4} wallpaper {{ monitor={mon}  path={path}  fit_mode={fit} }}")

        if not any([data["preloads"], data["wallpaper_lines"], data["wallpaper_blocks"]]):
            print("  No wallpapers configured.")
        return 0

    if sub == "set-wallpaper":
        # set-wallpaper <monitor|-> <path>
        if len(args) < 3:
            print(
                f"{_Y}Usage: hyprconf paper set-wallpaper <monitor|-> <path>\n"
                f"  '-' = all monitors  e.g. hyprconf paper set-wallpaper eDP-1 ~/wall.jpg{_R}",
                file=sys.stderr,
            )
            return 1
        monitor = "" if args[1] == "-" else args[1]
        path    = args[2]
        ok = set_wallpaper_line(monitor, path)
        print(f"  {_B}Set:{_R}  wallpaper = {monitor or '(all)'}, {path}")
        return 0 if ok else 1

    if sub == "add-preload":
        if len(args) < 2:
            print(f"{_Y}Usage: hyprconf paper add-preload <path>{_R}", file=sys.stderr)
            return 1
        ok = add_preload(args[1])
        print(f"  {_B}Added:{_R}  preload = {args[1]}")
        return 0 if ok else 1

    if sub == "delete-preload":
        if len(args) < 2 or not args[1].isdigit():
            print(f"{_Y}Usage: hyprconf paper delete-preload <index>{_R}", file=sys.stderr)
            return 1
        preloads = read_preloads()
        idx = int(args[1]) - 1
        if not (0 <= idx < len(preloads)):
            print(f"{_Y}Index out of range{_R}", file=sys.stderr)
            return 1
        p  = preloads[idx]
        ok = delete_preload(p.file_path, p.line_idx)
        print(f"  {_B}Deleted:{_R}  preload = {p.path}")
        return 0 if ok else 1

    if sub == "delete-wallpaper":
        if len(args) < 2 or not args[1].isdigit():
            print(f"{_Y}Usage: hyprconf paper delete-wallpaper <index>  (from 'paper list'){_R}", file=sys.stderr)
            return 1
        idx = int(args[1]) - 1
        # Try line format first, then block format
        wlines  = read_wallpaper_lines()
        wblocks = read_wallpaper_blocks()
        if 0 <= idx < len(wlines):
            w  = wlines[idx]
            ok = delete_wallpaper_line(w.file_path, w.line_idx)
            print(f"  {_B}Deleted:{_R}  wallpaper = {w.monitor}, {w.path}")
            return 0 if ok else 1
        bidx = idx - len(wlines)
        if 0 <= bidx < len(wblocks):
            b  = wblocks[bidx]
            ok = delete_wallpaper_block(b.file_path, b.start_line, b.end_line)
            print(f"  {_B}Deleted:{_R}  wallpaper block (monitor={b.fields.get('monitor', '')})")
            return 0 if ok else 1
        print(f"{_Y}Index out of range{_R}", file=sys.stderr)
        return 1

    if sub == "setting":
        if len(args) < 3:
            print(
                f"{_Y}Usage: hyprconf paper setting <key> <value>\n"
                f"  Examples: hyprconf paper setting splash false\n"
                f"            hyprconf paper setting ipc true{_R}",
                file=sys.stderr,
            )
            return 1
        key   = args[1]
        value = " ".join(args[2:])
        ok = set_setting(key, value)
        print(f"  {_B}Set:{_R}  {key} = {value}")
        return 0 if ok else 1

    print(
        f"{_Y}Usage: hyprconf paper list|set-wallpaper|add-preload"
        f"|delete-wallpaper|delete-preload|setting{_R}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
