"""
hyprconf.autodetect — first-run config detection and non-destructive migration.

When hyprconf is launched on a system that has never used it before, this
module locates the user's existing Hyprland config, parses as much of it as
possible into the shared config layer, and writes only a minimal managed
block — preserving all original files untouched.

──────────────────────────────────────────────────────────────────────────────
Design goals
──────────────────────────────────────────────────────────────────────────────
  - Never modify existing config files.
  - Write only to the managed overrides file (conf.d/99-hyprconf-local.conf).
  - Degrade gracefully: unknown syntax is logged as warnings, not errors.
  - Fast: no subprocess calls except optional hyprctl at the end.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import OVERRIDES_FILE
from .file_edit import strip_comment
from .schema import get_option_meta

# ── Candidate config paths ─────────────────────────────────────────────────────

_CFG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
_HYPR_DIR = _CFG_HOME / "hypr"

CANDIDATE_CONFIGS: list[Path] = [
    _HYPR_DIR / "hyprland.conf",
    Path.home() / ".hyprland.conf",
]

# Marker written by hyprconf after first-run to suppress repeated prompts
_FIRST_RUN_MARKER: Path = _CFG_HOME / "hyprconf" / ".initialized"

# ── Pre-compiled parsing regexes (used per-line in _parse_file) ────────────────
_RE_SOURCE     = re.compile(r"^source\s*=\s*(.+)$")
_RE_BLOCK_OPEN = re.compile(r"^(\w[\w.]*)\s*\{$")
_RE_KEY_VAL    = re.compile(r"^([\w.]+[\w])\s*=\s*(.+)$")


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class ParsedOption:
    section: str
    key: str
    value: str
    source_file: Path
    source_line: int


@dataclass
class DetectionResult:
    found_config: Optional[Path]
    parsed_options: list[ParsedOption] = field(default_factory=list)
    unknown_lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def option_count(self) -> int:
        return len(self.parsed_options)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


# ── Detection ──────────────────────────────────────────────────────────────────

def is_initialized() -> bool:
    """Return True if hyprconf has already been set up on this system."""
    return _FIRST_RUN_MARKER.exists() or OVERRIDES_FILE.exists()


def find_config() -> Optional[Path]:
    """Locate the user's hyprland.conf."""
    for p in CANDIDATE_CONFIGS:
        if p.is_file():
            return p
    return None


def detect_and_parse() -> DetectionResult:
    """Find and parse the user's existing Hyprland config.

    Does not write anything; the caller decides whether to migrate.
    """
    config_path = find_config()
    result = DetectionResult(found_config=config_path)
    if config_path is None:
        result.warnings.append("No hyprland.conf found.")
        return result

    _parse_file(config_path, result, section_stack=[], visited=set())
    return result


def _parse_file(
    path: Path,
    result: DetectionResult,
    section_stack: list[str],
    visited: set[Path],
) -> None:
    if path in visited or not path.is_file():
        return
    visited.add(path)

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        result.warnings.append(f"Cannot read {path}: {e}")
        return

    current_section: list[str] = list(section_stack)

    for lineno, raw in enumerate(text.splitlines(), 1):
        ln = strip_comment(raw)
        if not ln:
            continue

        # source = ...
        m = _RE_SOURCE.match(ln)
        if m:
            raw_path = os.path.expanduser(os.path.expandvars(m.group(1).strip()))
            for p in sorted(
                Path(raw_path).parent.glob(Path(raw_path).name)
                if "*" in raw_path else [Path(raw_path)]
            ):
                _parse_file(p, result, current_section, visited)
            continue

        # section open: "general {" or "decoration {"
        m = _RE_BLOCK_OPEN.match(ln)
        if m:
            sec = m.group(1).strip()
            parent = current_section[-1] if current_section else ""
            if parent:
                current_section.append(f"{parent}.{sec}")
            else:
                current_section.append(sec)
            continue

        # section close: "}"
        if ln == "}":
            if current_section:
                current_section.pop()
            continue

        # key = value
        m = _RE_KEY_VAL.match(ln)
        if m and current_section:
            key = m.group(1).strip()
            value = m.group(2).strip()
            section = current_section[-1]

            meta = get_option_meta(section, key)
            if meta is not None:
                result.parsed_options.append(
                    ParsedOption(
                        section=section,
                        key=key,
                        value=value,
                        source_file=path,
                        source_line=lineno,
                    )
                )
            else:
                result.unknown_lines.append(
                    f"{path}:{lineno}: {section}.{key} = {value}"
                )


# ── Migration ──────────────────────────────────────────────────────────────────

def migrate(result: DetectionResult) -> int:
    """Write detected options to the managed overrides file.

    Only writes options that are not already present.  Returns the count
    of options written.
    """
    if not result.parsed_options:
        return 0

    pending: dict[str, dict[str, str]] = {}
    for opt in result.parsed_options:
        pending.setdefault(opt.section, {})[opt.key] = opt.value

    from .config import save_pending
    ok, n = save_pending(pending)
    if ok:
        _mark_initialized()
    return n if ok else 0


def _mark_initialized() -> None:
    """Write the first-run marker to suppress future prompts."""
    try:
        _FIRST_RUN_MARKER.parent.mkdir(parents=True, exist_ok=True)
        _FIRST_RUN_MARKER.touch()
    except OSError:
        pass


# ── Entry point (called by CLI on first run) ───────────────────────────────────

def first_run_check(interactive: bool = True) -> None:
    """Check whether this is a first run and offer to import the existing config.

    If interactive is False (e.g. running in a pipe), skips the prompt and
    only prints a warning if a config was found but not yet imported.
    """
    if is_initialized():
        return

    config = find_config()
    if config is None:
        _mark_initialized()
        return

    if not interactive or not sys.stdin.isatty():
        print(
            f"[hyprconf] Found existing config at {config}.\n"
            "  Run 'hyprconf autodetect' to import it.",
            file=sys.stderr,
        )
        return

    print(f"\n  hyprconf — first run detected")
    print(f"  Found existing Hyprland config: {config}")
    print("  Scan and non-destructively import your current settings? [Y/n] ", end="", flush=True)
    answer = input().strip().lower()
    if answer in ("", "y", "yes"):
        result = detect_and_parse()
        n = migrate(result)
        print(f"  Imported {n} option(s) to {OVERRIDES_FILE}")
        if result.warning_count:
            print(f"  {result.warning_count} line(s) could not be parsed — see the source files.")
    else:
        _mark_initialized()
        print("  Skipped.  Run 'hyprconf autodetect' at any time.")
    print()
