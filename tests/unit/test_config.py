"""Tests for hyprconf.config — the overrides file reader and writer."""
from __future__ import annotations

from pathlib import Path

import pytest

from hyprconf.config import (
    MANAGED_MARKER,
    migrate_legacy,
    read_all_persisted,
    read_persisted,
    save_pending,
    section_key_to_hyprctl,
    upsert_option,
)


# ---------------------------------------------------------------------------
# section_key_to_hyprctl
# ---------------------------------------------------------------------------

def test_simple_section_key(hypr_dir: Path) -> None:
    assert section_key_to_hyprctl("general", "gaps_in") == "general:gaps_in"


def test_dotted_section_key(hypr_dir: Path) -> None:
    assert section_key_to_hyprctl("decoration.blur", "enabled") == "decoration:blur:enabled"


def test_deeply_nested_key(hypr_dir: Path) -> None:
    assert section_key_to_hyprctl("input.touchpad", "natural_scroll") == "input:touchpad:natural_scroll"


# ---------------------------------------------------------------------------
# read_persisted — file absent
# ---------------------------------------------------------------------------

def test_read_persisted_missing_file(hypr_dir: Path) -> None:
    assert read_persisted("general", "gaps_in") is None


# ---------------------------------------------------------------------------
# upsert_option + read_persisted round-trip
# ---------------------------------------------------------------------------

def test_upsert_and_read_int(hypr_dir: Path) -> None:
    assert upsert_option("general", "gaps_in", "12") is True
    assert read_persisted("general", "gaps_in") == "12"


def test_upsert_and_read_bool(hypr_dir: Path) -> None:
    upsert_option("decoration.blur", "enabled", "true")
    assert read_persisted("decoration.blur", "enabled") == "true"


def test_upsert_updates_existing(hypr_dir: Path) -> None:
    upsert_option("general", "gaps_in", "5")
    upsert_option("general", "gaps_in", "20")
    assert read_persisted("general", "gaps_in") == "20"


def test_upsert_preserves_other_keys(hypr_dir: Path) -> None:
    upsert_option("general", "gaps_in", "8")
    upsert_option("general", "border_size", "2")
    assert read_persisted("general", "gaps_in") == "8"
    assert read_persisted("general", "border_size") == "2"


def test_read_absent_key_returns_none(hypr_dir: Path) -> None:
    upsert_option("general", "gaps_in", "8")
    assert read_persisted("general", "nonexistent_key") is None


# ---------------------------------------------------------------------------
# save_pending
# ---------------------------------------------------------------------------

def test_save_pending_writes_marker(hypr_dir: Path) -> None:
    ok, count = save_pending({"general": {"gaps_in": "8"}})
    assert ok is True
    assert count >= 1
    import hyprconf.config as cfg
    text = cfg.OVERRIDES_FILE.read_text()
    assert MANAGED_MARKER in text


def test_save_pending_multiple_sections(hypr_dir: Path) -> None:
    ok, _ = save_pending({
        "general": {"gaps_in": "8", "border_size": "2"},
        "decoration.blur": {"enabled": "true"},
    })
    assert ok is True
    assert read_persisted("general", "gaps_in") == "8"
    assert read_persisted("decoration.blur", "enabled") == "true"


def test_save_pending_preserves_user_zone(hypr_dir: Path) -> None:
    import hyprconf.config as cfg
    cfg.OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.OVERRIDES_FILE.write_text("# My custom config\nbind = SUPER, T, exec, kitty\n")
    save_pending({"general": {"gaps_in": "5"}})
    text = cfg.OVERRIDES_FILE.read_text()
    assert "# My custom config" in text
    assert "bind = SUPER, T, exec, kitty" in text
    assert "general:gaps_in = 5" in text


def test_save_pending_idempotent(hypr_dir: Path) -> None:
    save_pending({"general": {"gaps_in": "8"}})
    save_pending({"general": {"gaps_in": "8"}})
    all_keys = read_all_persisted()
    # Key should appear exactly once
    assert list(all_keys.values()).count("8") == 1


def test_save_pending_sorted_keys(hypr_dir: Path) -> None:
    save_pending({"z_section": {"z_key": "1"}, "a_section": {"a_key": "2"}})
    import hyprconf.config as cfg
    lines = cfg.OVERRIDES_FILE.read_text().splitlines()
    managed_lines = [l for l in lines if "=" in l and not l.startswith("#")]
    keys = [l.split("=")[0].strip() for l in managed_lines]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# read_all_persisted
# ---------------------------------------------------------------------------

def test_read_all_persisted_empty(hypr_dir: Path) -> None:
    assert read_all_persisted() == {}


def test_read_all_persisted_multiple(hypr_dir: Path) -> None:
    save_pending({
        "general": {"gaps_in": "8"},
        "decoration.blur": {"enabled": "false"},
    })
    result = read_all_persisted()
    assert result.get("general:gaps_in") == "8"
    assert result.get("decoration:blur:enabled") == "false"


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------

def test_migrate_legacy_copies_file(hypr_dir: Path) -> None:
    import hyprconf.config as cfg
    legacy = cfg.LEGACY_OVERRIDES_FILE
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(f"{MANAGED_MARKER}\ngeneral:gaps_in = 5\n")
    assert migrate_legacy() is True
    assert cfg.OVERRIDES_FILE.exists()
    assert "general:gaps_in = 5" in cfg.OVERRIDES_FILE.read_text()


def test_migrate_legacy_no_op_if_new_exists(hypr_dir: Path) -> None:
    import hyprconf.config as cfg
    cfg.LEGACY_OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.LEGACY_OVERRIDES_FILE.write_text("old content\n")
    cfg.OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.OVERRIDES_FILE.write_text("new content\n")
    assert migrate_legacy() is False
    assert cfg.OVERRIDES_FILE.read_text() == "new content\n"


# ---------------------------------------------------------------------------
# save_pending — legacy marker stripping (covers L116)
# ---------------------------------------------------------------------------

def test_save_pending_strips_legacy_marker(hypr_dir: Path) -> None:
    from hyprconf.config import save_pending, read_all_persisted, OVERRIDES_FILE, MANAGED_MARKER
    OVERRIDES_FILE.write_text("# hyprconf-tui managed\ngeneral:gaps_in = 3\n")
    ok, n = save_pending({"general": {"border_size": "2"}})
    assert ok is True
    text = OVERRIDES_FILE.read_text()
    assert MANAGED_MARKER in text
    assert "# hyprconf-tui managed" not in text


# ---------------------------------------------------------------------------
# save_pending — OSError path (covers L137-138)
# ---------------------------------------------------------------------------

def test_save_pending_returns_false_on_oserror(hypr_dir: Path) -> None:
    import unittest.mock as _mock
    from hyprconf.config import save_pending
    with _mock.patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
        ok, n = save_pending({"general": {"gaps_in": "5"}})
    assert ok is False
    assert n == 0
