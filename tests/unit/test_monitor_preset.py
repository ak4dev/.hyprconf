"""Tests for bin/hyprconf-monitor-preset.

Verifies:
- Applying a valid preset COPIES it to Omarchy's Hyprland toggles directory
  (~/.local/state/omarchy/toggles/hypr/hyprconf-monitor-preset.lua — what
  default/hypr/toggles.lua require_all()s after ~/.config/hypr/monitors.lua,
  so its hl.monitor calls win) and reloads; ~/.config/hypr/monitors.lua is
  never touched
- `stock` removes the toggle file and reloads, idempotently
- A missing preset exits non-zero with a useful error, reported through
  Omarchy's notification command (the tool is reached from a hotkey, where
  stderr goes nowhere a human can see)
- A missing or unsafe preset argument exits non-zero

The `pc` / `laptop` short names and the workspace re-homing are covered
against the installed copy by test_omarchy_install.py.

HERMETIC: the tool talks to hyprctl, omarchy-notification-send and
omarchy-osd. Every one of them is a recording stub on a fake-bins dir put
FIRST on PATH — the real ones would reload the developer's compositor, move
their workspaces, and put a critical "Preset not found" notification on their
desktop every time the suite runs.
"""

from __future__ import annotations

import re
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT = REPO_ROOT / "bin" / "hyprconf-monitor-preset"
TOGGLE = Path(".local") / "state" / "omarchy" / "toggles" / "hypr" / "hyprconf-monitor-preset.lua"

# Every external command the tool may call. The self-check below derives the
# same set from the script's text, so a new call cannot slip past the fakes
# unnoticed.
EXTERNALS = ("hyprctl", "omarchy-notification-send", "omarchy-osd")


def _make_fake_bins(tmp: Path) -> Path:
    """Recording stubs for every external; each appends its argv to calls.txt."""
    bins = tmp / "bins"
    bins.mkdir(exist_ok=True)
    calls = tmp / "calls.txt"
    for name in EXTERNALS:
        fake = bins / name
        fake.write_text(f'#!/usr/bin/env bash\nprintf \'%s\\n\' "{name} $*" >> "{calls}"\nexit 0\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bins


def _calls(tmp: Path) -> list[str]:
    f = tmp / "calls.txt"
    return f.read_text().splitlines() if f.exists() else []


def _run(tmp: Path, config_dir: Path, *args: str) -> subprocess.CompletedProcess:
    bins = _make_fake_bins(tmp)
    home = tmp / "home"
    cfg = home / ".config" / "hypr"
    cfg.mkdir(parents=True, exist_ok=True)
    for f in config_dir.iterdir():
        (cfg / f.name).write_text(f.read_text())
    # The fakes first, then only /usr/bin and /bin — never the host's PATH,
    # where /usr/share/omarchy/bin would answer.
    env = {"PATH": f"{bins}:/usr/bin:/bin", "HOME": str(home)}
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=60
    )


def _cfg(tmp_path: Path, **files: str) -> Path:
    cfg_src = tmp_path / "cfg_src"
    cfg_src.mkdir()
    for name, body in files.items():
        (cfg_src / name).write_text(body)
    return cfg_src


PRESET = 'hl.monitor({ output = "HDMI-A-1", mode = "preferred" })\n'


# ---------------------------------------------------------------------------
# Hermeticity self-check
# ---------------------------------------------------------------------------


def test_every_external_the_tool_calls_has_a_fake() -> None:
    """If hyprconf-monitor-preset grows a new omarchy-*/hyprctl call, this
    fails before that call can reach the developer's real desktop from a test."""
    code = "\n".join(
        ln for ln in SCRIPT.read_text().splitlines() if not ln.lstrip().startswith("#")
    )
    called = set(re.findall(r"\b(hyprctl|omarchy-[a-z-]+)\b", code))
    assert called, "no external calls found — the scan regex is broken"
    assert called <= set(EXTERNALS), f"unstubbed externals: {called - set(EXTERNALS)}"


# ---------------------------------------------------------------------------
# Preset application through the toggles seam
# ---------------------------------------------------------------------------


def test_valid_preset_is_copied_to_the_toggles_file_and_monitors_lua_is_untouched(
    tmp_path: Path,
) -> None:
    """The preset lands as a COPY in Omarchy's toggles directory — never a
    link, so nothing Omarchy does to that directory reaches the preset —
    and Omarchy's own monitors.lua is left exactly as it was — Omarchy keeps
    writing to it (omarchy-hyprland-monitor-scaling seds the scale lines in
    place), so the tool never replaces it."""
    cfg_src = _cfg(
        tmp_path, **{"pcMonitors.bedroom.lua": PRESET, "monitors.lua": "-- omarchy auto\n"}
    )

    res = _run(tmp_path, cfg_src, "bedroom")
    assert res.returncode == 0, f"Tool failed: {res.stderr}"

    home = tmp_path / "home"
    toggle = home / TOGGLE
    assert toggle.is_file() and not toggle.is_symlink()
    assert toggle.read_text() == PRESET
    monitors = home / ".config" / "hypr" / "monitors.lua"
    assert not monitors.is_symlink() and monitors.read_text() == "-- omarchy auto\n"
    assert not (home / ".config" / "hypr" / "monitors.lua.stock").exists()
    calls = _calls(tmp_path)
    assert "hyprctl reload" in calls
    assert any(c.startswith("omarchy-osd") and "bedroom" in c for c in calls)


def test_a_preset_edit_is_what_the_next_switch_applies(tmp_path: Path) -> None:
    """Edits to a preset survive re-selecting it: the toggle is re-copied
    from the preset file every time."""
    cfg_src = _cfg(tmp_path, **{"pcMonitors.bedroom.lua": PRESET})
    assert _run(tmp_path, cfg_src, "bedroom").returncode == 0
    preset = tmp_path / "home" / ".config" / "hypr" / "pcMonitors.bedroom.lua"
    preset.write_text(PRESET + "-- edited on this desk\n")
    (tmp_path / "cfg_src" / "pcMonitors.bedroom.lua").write_text(preset.read_text())
    assert _run(tmp_path, cfg_src, "bedroom").returncode == 0
    assert (tmp_path / "home" / TOGGLE).read_text() == preset.read_text()


def test_stock_removes_the_toggle_and_reloads(tmp_path: Path) -> None:
    """`stock` is the toggle's off: the file goes, Hyprland reloads, and
    Omarchy's monitors.lua — untouched — is the only layout left. Idempotent
    — a second `stock` with nothing to remove still reloads and reports."""
    cfg_src = _cfg(
        tmp_path, **{"pcMonitors.bedroom.lua": PRESET, "monitors.lua": "-- omarchy auto\n"}
    )
    assert _run(tmp_path, cfg_src, "bedroom").returncode == 0
    toggle = tmp_path / "home" / TOGGLE
    assert toggle.exists()

    res = _run(tmp_path, cfg_src, "stock")
    assert res.returncode == 0, res.stderr
    assert not toggle.exists()
    assert (
        tmp_path / "home" / ".config" / "hypr" / "monitors.lua"
    ).read_text() == "-- omarchy auto\n"
    assert _calls(tmp_path).count("hyprctl reload") == 2
    assert any(c.startswith("omarchy-osd") and "stock" in c for c in _calls(tmp_path))

    res = _run(tmp_path, cfg_src, "omarchy")  # the alias, with nothing to remove
    assert res.returncode == 0, res.stderr
    assert _calls(tmp_path).count("hyprctl reload") == 3


def test_help_flags_print_usage_without_a_notification(tmp_path: Path) -> None:
    """-h/--help fit the preset-name whitelist, so without their own branch
    they fell through to log_die's critical desktop notification
    ("Preset not found: pcMonitors.--help.lua")."""
    cfg_src = _cfg(tmp_path)
    for flag in ("-h", "--help"):
        res = _run(tmp_path, cfg_src, flag)
        assert res.returncode == 0, (flag, res.stderr)
        assert "Usage:" in res.stderr and "Presets:" in res.stderr
        assert not any(c.startswith("omarchy-notification-send") for c in _calls(tmp_path)), flag


def test_preset_not_found_exits_nonzero_and_notifies(tmp_path: Path) -> None:
    """A missing preset fails, and the failure is a desktop notification —
    the hotkey path has no terminal to read stderr from."""
    cfg_src = _cfg(tmp_path)

    res = _run(tmp_path, cfg_src, "nonexistent")
    assert res.returncode != 0, "Expected non-zero exit for missing preset"
    assert "Preset not found: pcMonitors.nonexistent.lua" in res.stderr
    assert any(
        c.startswith("omarchy-notification-send") and "nonexistent" in c for c in _calls(tmp_path)
    )
    assert "hyprctl reload" not in _calls(tmp_path)
    assert not (tmp_path / "home" / TOGGLE).exists()


def test_no_preset_argument_exits_nonzero(tmp_path: Path) -> None:
    res = _run(tmp_path, _cfg(tmp_path))
    assert res.returncode != 0
    assert "Usage" in res.stderr and "stock" in res.stderr


def test_preset_name_is_whitelisted(tmp_path: Path) -> None:
    """`$1` is a path component; anything outside [A-Za-z0-9_-] is refused."""
    res = _run(tmp_path, _cfg(tmp_path), "../evil")
    assert res.returncode != 0
    assert "Invalid preset name" in res.stderr
