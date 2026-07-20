"""Tests for hyprconf.monitors — monitor line parser and writer."""

from __future__ import annotations

import re
from pathlib import Path

from hyprconf.monitors import (
    MonitorConfig,
    delete_monitor,
    read_monitor_configs,
    upsert_monitor,
)

# ---------------------------------------------------------------------------
# Repo-root paths used for config regression tests
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent
_LAPTOP_CONF = _REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "laptopMonitors.conf"

MONITORS_CONF = """\
monitor = HDMI-A-1, 3840x2160@120, 0x0, 1.5
monitor = DP-1, 1920x1080@60, 3840x0, 1.0
"""

EXTRAS_CONF = """\
monitor = HDMI-A-1, 3840x2160@120, 0x0, 1.5, vrr, 1, bitdepth, 10, cm, hdr
"""

DISABLED_CONF = """\
monitor = eDP-1, disable
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mon_file(hypr_dir: Path, content: str) -> Path:
    p = hypr_dir / "monitors.conf"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# read_monitor_configs
# ---------------------------------------------------------------------------


def test_reads_two_monitors(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    configs = read_monitor_configs(p)
    assert len(configs) == 2


def test_parses_fields_correctly(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    m = read_monitor_configs(p)[0]
    assert m.name == "HDMI-A-1"
    assert m.resolution == "3840x2160@120"
    assert m.position == "0x0"
    assert m.scale == "1.5"


def test_parses_extras(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, EXTRAS_CONF)
    m = read_monitor_configs(p)[0]
    assert "vrr" in m.extras
    assert "bitdepth" in m.extras
    assert "cm" in m.extras


def test_empty_file(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, "")
    assert read_monitor_configs(p) == []


def test_missing_file(hypr_dir: Path) -> None:
    assert read_monitor_configs(hypr_dir / "nonexistent.conf") == []


def test_ignores_comments(hypr_dir: Path) -> None:
    p = _mon_file(
        hypr_dir, "# monitor = DP-1, preferred, auto, 1\nmonitor = HDMI-A-1, preferred, auto, 1\n"
    )
    configs = read_monitor_configs(p)
    assert len(configs) == 1
    assert configs[0].name == "HDMI-A-1"


def test_is_disabled_false(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    m = read_monitor_configs(p)[0]
    assert m.is_disabled is False


def test_is_disabled_true(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, DISABLED_CONF)
    m = read_monitor_configs(p)[0]
    assert m.is_disabled is True


def test_to_line_no_extras(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    m = read_monitor_configs(p)[0]
    line = m.to_line()
    assert line == "monitor = HDMI-A-1, 3840x2160@120, 0x0, 1.5"


def test_to_line_with_extras(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, EXTRAS_CONF)
    m = read_monitor_configs(p)[0]
    line = m.to_line()
    assert "vrr" in line
    assert "cm" in line


def test_line_idx_correct(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    configs = read_monitor_configs(p)
    assert configs[0].line_idx == 0
    assert configs[1].line_idx == 1


# ---------------------------------------------------------------------------
# upsert_monitor
# ---------------------------------------------------------------------------


def test_upsert_appends_new(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, "")
    assert upsert_monitor("HDMI-A-1", "preferred", "auto", "1", file=p) is True
    configs = read_monitor_configs(p)
    assert len(configs) == 1
    assert configs[0].name == "HDMI-A-1"


def test_upsert_updates_existing(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    upsert_monitor("HDMI-A-1", "1920x1080@60", "0x0", "1.0", file=p)
    configs = read_monitor_configs(p)
    hdmi = next(c for c in configs if c.name == "HDMI-A-1")
    assert hdmi.resolution == "1920x1080@60"
    assert hdmi.scale == "1.0"


def test_upsert_with_extras(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, "")
    upsert_monitor("HDMI-A-1", "3840x2160@120", "0x0", "1.5", "vrr, 1, bitdepth, 10", file=p)
    text = p.read_text()
    assert "vrr, 1, bitdepth, 10" in text


def test_upsert_preserves_other_monitors(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    upsert_monitor("HDMI-A-1", "preferred", "auto", "1", file=p)
    configs = read_monitor_configs(p)
    names = [c.name for c in configs]
    assert "DP-1" in names  # second monitor preserved


# ---------------------------------------------------------------------------
# delete_monitor
# ---------------------------------------------------------------------------


def test_delete_monitor(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    configs = read_monitor_configs(p)
    first = configs[0]
    assert delete_monitor(first.file_path, first.line_idx) is True
    remaining = read_monitor_configs(p)
    assert len(remaining) == 1
    assert remaining[0].name == "DP-1"


def test_delete_monitor_invalid_idx(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    assert delete_monitor(p, 999) is False


# ---------------------------------------------------------------------------
# Default path coverage (covers L79, L114, L136, L147)
# ---------------------------------------------------------------------------


def test_read_monitor_configs_uses_default_path(hypr_dir: Path) -> None:
    from hyprconf.monitors import MONITORS_FILE, read_monitor_configs

    MONITORS_FILE.write_text("monitor = eDP-1, 1920x1080@60, 0x0, 1\n")
    configs = read_monitor_configs()  # no file arg → MONITORS_FILE
    assert len(configs) == 1
    assert configs[0].name == "eDP-1"


def test_upsert_monitor_uses_default_path(hypr_dir: Path) -> None:
    from hyprconf.monitors import MONITORS_FILE, read_monitor_configs, upsert_monitor

    MONITORS_FILE.write_text("")
    upsert_monitor("HDMI-A-1", "1920x1080@60", "0x0", "1")  # no file arg
    configs = read_monitor_configs(MONITORS_FILE)
    assert any(m.name == "HDMI-A-1" for m in configs)


def test_delete_monitor_uses_default_file_path(hypr_dir: Path) -> None:
    from hyprconf.monitors import (
        MONITORS_FILE,
        delete_monitor,
        read_monitor_configs,
        upsert_monitor,
    )

    MONITORS_FILE.write_text("")
    upsert_monitor("eDP-1", "preferred", "auto", "1", file=MONITORS_FILE)
    configs = read_monitor_configs(MONITORS_FILE)
    assert len(configs) == 1
    mc = configs[0]
    # delete_monitor uses mc.file_path which is MONITORS_FILE
    delete_monitor(mc.file_path, mc.line_idx)
    assert read_monitor_configs(MONITORS_FILE) == []


# ---------------------------------------------------------------------------
# Regression tests — laptopMonitors.conf config correctness
# ---------------------------------------------------------------------------


def _laptop_configs() -> list[MonitorConfig]:
    """Parse the real laptopMonitors.conf from the stow tree."""
    return read_monitor_configs(_LAPTOP_CONF)


def test_laptop_conf_has_catchall_wildcard() -> None:
    """A catch-all rule must exist so any unrecognised connector gets a mode."""
    configs = _laptop_configs()
    assert any(c.name == "" for c in configs), (
        "laptopMonitors.conf is missing a catch-all wildcard rule "
        "(monitor=,preferred,auto,auto).  Without it, connectors not "
        "explicitly listed (e.g. a USB-C HDMI adapter) are ignored by "
        "Hyprland and produce no output."
    )


def test_laptop_dp_connectors_use_preferred_not_hardcoded_hz() -> None:
    """DP-* entries must use 'preferred' resolution, not a hardcoded @Hz mode.

    Hardcoding a refresh rate (e.g. 3840x2160@120.00Hz) silently breaks any
    monitor that doesn't support that exact rate — Hyprland applies the mode
    but the display rejects it and shows a blank screen.
    """
    hz_pattern = re.compile(r"@\d+(\.\d+)?Hz", re.IGNORECASE)
    configs = _laptop_configs()
    bad = [c for c in configs if c.name.startswith("DP-") and hz_pattern.search(c.resolution or "")]
    assert bad == [], (
        f"DP connector(s) in laptopMonitors.conf use hardcoded @Hz modes: "
        f"{[c.name + '=' + (c.resolution or '') for c in bad]}.  "
        f"Use 'preferred' so the display negotiates its own best mode."
    )


def test_laptop_external_connectors_use_preferred() -> None:
    """All external connector entries (DP-*, HDMI-*) should use 'preferred'."""
    configs = _laptop_configs()
    bad = [
        c
        for c in configs
        if (c.name.startswith(("DP-", "HDMI-")))
        and c.resolution not in ("preferred", "highres", "highrr", "disable")
    ]
    assert bad == [], (
        f"External connector(s) in laptopMonitors.conf use fixed resolutions: "
        f"{[c.name + '=' + (c.resolution or '') for c in bad]}.  "
        f"Use 'preferred' for portability across different monitors."
    )


def test_laptop_internal_display_uses_preferred() -> None:
    """eDP-1 (internal display) must use 'preferred' so the native panel mode is applied."""
    configs = _laptop_configs()
    edp = next((c for c in configs if c.name == "eDP-1"), None)
    assert edp is not None, "eDP-1 entry missing from laptopMonitors.conf"
    assert edp.resolution == "preferred", (
        f"eDP-1 resolution is '{edp.resolution}', expected 'preferred'"
    )
