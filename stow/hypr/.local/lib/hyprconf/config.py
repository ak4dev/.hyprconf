"""
hyprconf.config — unified config reader and writer.

Both the CLI and TUI use these functions exclusively for all persistent
storage.  The single canonical overrides file is:

    ~/.config/hypr/conf.d/99-hyprconf-local.conf

This file is sourced by Hyprland via the conf.d/*.conf glob and survives
restarts.  It is managed in a two-zone format:

    [user-written content, preserved verbatim]

    # hyprconf-managed
    decoration:blur:enabled = true
    general:gaps_in = 8
    ...

The managed block is entirely regenerated on each write; the user zone
above it is never touched.
"""

from __future__ import annotations

import re
from pathlib import Path

from .file_edit import atomic_write_text
from .paths import HYPR_DIR as _HYPR_DIR
from .paths import OVERRIDES_FILE

# ── Paths ──────────────────────────────────────────────────────────────────────

LEGACY_OVERRIDES_FILE: Path = _HYPR_DIR / "hyprconf.local.conf"

MANAGED_MARKER: str = "# hyprconf-managed"
# Legacy marker written by older TUI versions — recognised on read, replaced on write.
_LEGACY_MARKER: str = "# hyprconf-tui managed"

# Pre-compiled regex for parsing managed-block key=value lines
_MANAGED_LINE_RE = re.compile(r"^([^#\s][^=]*?)\s*=\s*(.+)$")

# ── Key formatting ─────────────────────────────────────────────────────────────


def section_key_to_hyprctl(section: str, key: str) -> str:
    """Convert section + key to the hyprctl keyword / getoption path.

    Examples:
        general, gaps_in          →  general:gaps_in
        decoration.blur, enabled  →  decoration:blur:enabled
    """
    return section.replace(".", ":") + ":" + key


# ── Read ───────────────────────────────────────────────────────────────────────


def read_persisted(section: str, key: str) -> str | None:
    """Read a persisted value from the managed overrides file.

    Returns None if the key is not present.
    """
    path = _effective_overrides_path()
    if not path.exists():
        return None

    hkey = section_key_to_hyprctl(section, key)
    in_block = False
    for ln in path.read_text(encoding="utf-8").splitlines():
        if MANAGED_MARKER in ln or _LEGACY_MARKER in ln:
            in_block = True
            continue
        if not in_block:
            continue
        m = _MANAGED_LINE_RE.match(ln.strip())
        if m and m.group(1) == hkey:
            return m.group(2).strip()
    return None


def read_all_persisted() -> dict[str, str]:
    """Return all persisted key=value pairs from the managed block.

    Keys are in hyprctl format:  section:subsection:key
    """
    path = _effective_overrides_path()
    if not path.exists():
        return {}

    result: dict[str, str] = {}
    in_block = False
    for ln in path.read_text(encoding="utf-8").splitlines():
        if MANAGED_MARKER in ln or _LEGACY_MARKER in ln:
            in_block = True
            continue
        if in_block:
            m = _MANAGED_LINE_RE.match(ln.strip())
            if m:
                result[m.group(1).strip()] = m.group(2).strip()
    return result


# ── Write ──────────────────────────────────────────────────────────────────────


def save_pending(pending: dict[str, dict[str, str]]) -> tuple[bool, int]:
    """Write a dict of pending changes to the overrides file.

    pending is shaped as:  { section: { key: value } }

    Merges with existing managed entries.  Returns (success, num_written).
    """
    path = _effective_overrides_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""

        # Split user zone from managed block (accept both legacy and new marker)
        pre = existing  # fallback: no marker found
        for m in (MANAGED_MARKER, _LEGACY_MARKER):
            if m in existing:
                pre, _, existing = existing.partition(m)
                break

        # Parse the managed block directly from the remaining text (avoids a second file read)
        managed: dict[str, str] = {}
        for ln in existing.splitlines():
            m2 = _MANAGED_LINE_RE.match(ln.strip())
            if m2:
                managed[m2.group(1).strip()] = m2.group(2).strip()

        # Merge pending on top
        for sec, opts in pending.items():
            for k, v in opts.items():
                managed[section_key_to_hyprctl(sec, k)] = v

        body = pre.rstrip()
        if body:
            body += "\n"
        body += f"\n{MANAGED_MARKER}\n"
        for k in sorted(managed):
            body += f"{k} = {managed[k]}\n"

        atomic_write_text(path, body)
        return True, len(managed)
    except OSError:
        return False, 0


def upsert_option(section: str, key: str, value: str) -> bool:
    """Immediately write a single option to the overrides file.

    Equivalent to save_pending with a single-key pending dict, but
    more convenient for the CLI's immediate-write use case.
    """
    ok, _ = save_pending({section: {key: value}})
    return ok


# ── Legacy migration ───────────────────────────────────────────────────────────


def migrate_legacy() -> bool:
    """Copy the legacy overrides file to the new location if needed.

    Returns True if a migration was performed.
    """
    if LEGACY_OVERRIDES_FILE.exists() and not OVERRIDES_FILE.exists():
        OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            OVERRIDES_FILE,
            LEGACY_OVERRIDES_FILE.read_text(encoding="utf-8"),
        )
        return True
    return False


# ── Internal helpers ───────────────────────────────────────────────────────────


def _effective_overrides_path() -> Path:
    """Return the active overrides file path, migrating legacy if needed."""
    migrate_legacy()
    return OVERRIDES_FILE
