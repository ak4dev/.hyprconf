"""Tests for bin/hyprconf-help — every add-on at a glance, derived at run time.

Verifies:
- every bin/hyprconf-* tool is listed with the one-liner from its own header,
  and the convention itself ("# <name> — <desc>" in the first comment lines)
  holds for every tool, so a new tool cannot ship without a line here
- bar widgets (manifest descriptions, jq real when present), themes and hook
  directories are listed by name
- the @HYPRCONF_DIR@ fallback makes the un-rendered tool work straight from
  the checkout; a rendered copy pointing nowhere dies naming the path
- unknown arguments die; nothing is written

HERMETIC: the tool reads only the checkout it is pointed at — a rendered
copy gets @HYPRCONF_DIR@ substituted the way stage_bin does; no HOME, no
system paths.
"""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
TOOL = REPO_ROOT / "bin" / "hyprconf-help"
BIN_TOOLS = sorted(p.name for p in (REPO_ROOT / "bin").glob("hyprconf-*"))
ONE_LINER = re.compile(r"^# (hyprconf-[a-z0-9-]+) — (\S.*)$")


def rendered(tmp_path: Path, root: Path | None = None) -> Path:
    """The tool as stage_bin installs it: @HYPRCONF_DIR@ resolved."""
    out = tmp_path / "hyprconf-help"
    out.write_text(TOOL.read_text().replace("@HYPRCONF_DIR@", str(root or REPO_ROOT)))
    out.chmod(0o755)
    return out


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def header_one_liner(tool: Path) -> str | None:
    for line in tool.read_text().splitlines()[:12]:
        m = ONE_LINER.match(line)
        if m and m.group(1) == tool.name:
            return m.group(2)
    return None


def test_every_tool_carries_the_header_convention() -> None:
    """The pin: a bin tool without a '# <name> — <desc>' header fails here."""
    for name in BIN_TOOLS:
        assert header_one_liner(REPO_ROOT / "bin" / name), f"{name} has no header one-liner"


def test_every_tool_is_listed_with_its_own_one_liner(tmp_path: Path) -> None:
    r = run(rendered(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    for name in BIN_TOOLS:
        matches = [ln for ln in r.stdout.splitlines() if ln.strip().startswith(name)]
        assert matches, f"{name} missing from the listing"
        desc = header_one_liner(REPO_ROOT / "bin" / name)
        assert desc in matches[0], f"{name} listed without its header one-liner"
    assert "(no header one-liner)" not in r.stdout


def test_widgets_themes_and_hooks_are_listed(tmp_path: Path) -> None:
    r = run(rendered(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    for d in (REPO_ROOT / "plugins").iterdir():
        assert d.name in r.stdout
    for d in (REPO_ROOT / "themes").iterdir():
        assert d.name in r.stdout
    for d in (REPO_ROOT / "hooks").iterdir():
        assert d.name in r.stdout
    if shutil.which("jq"):
        assert "CPU/temp/memory/GPU/network readout" in r.stdout
    else:
        pytest.skip("jq not installed — widget descriptions unchecked")


def test_unrendered_tool_falls_back_to_the_checkout() -> None:
    r = run(TOOL)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"checkout: {REPO_ROOT}" in r.stdout


def test_missing_checkout_dies_naming_the_path(tmp_path: Path) -> None:
    r = run(rendered(tmp_path, root=tmp_path / "nope"))
    assert r.returncode == 1
    assert f"no checkout at {tmp_path / 'nope'}" in r.stderr


def test_unknown_argument_dies(tmp_path: Path) -> None:
    r = run(rendered(tmp_path), "bogus")
    assert r.returncode == 1 and "unknown argument: bogus" in r.stderr


def test_writes_nothing(tmp_path: Path) -> None:
    script = rendered(tmp_path)
    before = set(tmp_path.rglob("*"))
    run(script)
    assert set(tmp_path.rglob("*")) == before


def test_script_hygiene() -> None:
    text = TOOL.read_text()
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text
    assert "readonly" not in text
    assert TOOL.stat().st_mode & stat.S_IXUSR
