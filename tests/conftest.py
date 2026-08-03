"""
Shared pytest fixtures for hyprconf tests.

All tests that touch config files receive an isolated tmpdir-based config
tree via the ``hypr_dir`` fixture — no test ever touches ~/.config/hypr.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path constants — repo root is two levels above this file
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
LIB_DIR = REPO_ROOT / "stow" / "hypr" / ".local" / "lib"

# Ensure the library is importable regardless of how pytest was invoked.
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))


# ---------------------------------------------------------------------------
# Isolated config directory
# ---------------------------------------------------------------------------


@pytest.fixture()
def hypr_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a temporary ~/.config/hypr directory.

    All hyprconf modules that look up XDG_CONFIG_HOME are monkeypatched to
    point at this temp tree so no test ever touches the real config.
    """
    cfg = tmp_path / ".config"
    hypr = cfg / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "conf.d").mkdir()

    # Seed minimal stub files so parsers don't see a missing file as an error.
    # hyprland's own compositor config (hyprland/keybinds/monitors) is Lua as
    # of 0.55+; hypridle/hyprlock/hyprpaper are separate programs still on
    # hyprlang `.conf`.
    (hypr / "keybinds.lua").write_text('local mainMod = "SUPER"\n')
    (hypr / "monitors.lua").write_text("")
    (hypr / "hyprlock.conf").write_text("")
    (hypr / "hypridle.conf").write_text("")
    (hypr / "hyprpaper.conf").write_text("")
    (hypr / "hyprland.lua").write_text("")

    # Monkeypatch every module-level path constant that was resolved at
    # import time from XDG_CONFIG_HOME.
    import hyprconf.config as _config_mod
    import hyprconf.hypridle as _hypridle_mod
    import hyprconf.hyprlock as _hyprlock_mod
    import hyprconf.hyprpaper as _hyprpaper_mod
    import hyprconf.keybinds as _keybinds_mod
    import hyprconf.monitors as _monitors_mod
    import hyprconf.paths as _paths_mod
    import hyprconf.rules as _rules_mod

    # rules.py/keybinds.py resolve Lua `require(...)`/`try_require(...)`
    # directives relative to HYPR_DIR (imported by value at module load), so
    # it must be repointed at the fixture tree too, not just the individual
    # file constants below.
    monkeypatch.setattr(_paths_mod, "HYPR_DIR", hypr)
    monkeypatch.setattr(_rules_mod, "HYPR_DIR", hypr)
    monkeypatch.setattr(_keybinds_mod, "HYPR_DIR", hypr)

    monkeypatch.setattr(_config_mod, "OVERRIDES_FILE", hypr / "conf.d" / "local.lua")
    monkeypatch.setattr(_config_mod, "LEGACY_OVERRIDES_FILE", hypr / "hyprconf.local.conf")
    monkeypatch.setattr(_config_mod, "_CONF_ERA_OVERRIDES_FILE", hypr / "conf.d" / "99-hyprconf-local.conf")
    monkeypatch.setattr(_keybinds_mod, "KEYBINDS_FILE", hypr / "keybinds.lua")
    monkeypatch.setattr(_monitors_mod, "MONITORS_FILE", hypr / "monitors.lua")
    monkeypatch.setattr(_rules_mod, "HYPRLAND_CONF", hypr / "hyprland.lua")
    monkeypatch.setattr(_rules_mod, "WINRULES_FILE", hypr / "conf.d" / "windowrules.lua")
    monkeypatch.setattr(_rules_mod, "WKSPRULES_FILE", hypr / "conf.d" / "workspacerules.lua")
    monkeypatch.setattr(_hyprlock_mod, "HYPRLOCK_FILE", hypr / "hyprlock.conf")
    monkeypatch.setattr(_hypridle_mod, "HYPRIDLE_FILE", hypr / "hypridle.conf")
    monkeypatch.setattr(_hyprpaper_mod, "HYPRPAPER_FILE", hypr / "hyprpaper.conf")

    return hypr


# ---------------------------------------------------------------------------
# VM / install markers — skip unless explicitly requested
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "vm: live Hyprland session in QEMU/KVM (pass --run-vm to enable)"
    )
    config.addinivalue_line(
        "markers", "install: full Arch install smoke test (pass --run-install to enable)"
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-vm", action="store_true", default=False)
    parser.addoption("--run-install", action="store_true", default=False)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_vm = pytest.mark.skip(reason="pass --run-vm to enable")
    skip_install = pytest.mark.skip(reason="pass --run-install to enable")
    for item in items:
        if "vm" in item.keywords and not config.getoption("--run-vm"):
            item.add_marker(skip_vm)
        if "install" in item.keywords and not config.getoption("--run-install"):
            item.add_marker(skip_install)
