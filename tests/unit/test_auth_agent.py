"""
Structural tests for the Polkit authentication agent configuration.

Ensures hyprpolkitagent (the official Hyprland-ecosystem polkit agent) is
consistently referenced across packages, hyprland.conf, and README.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
PACKAGES_FILE  = REPO_ROOT / "packages"
HYPRLAND_CONF  = REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "hyprland.conf"
README         = REPO_ROOT / "README.md"


def test_packages_contains_hyprpolkitagent() -> None:
    lines = [l for l in PACKAGES_FILE.read_text().splitlines() if not l.strip().startswith("#")]
    assert any("hyprpolkitagent" in l for l in lines), \
        "hyprpolkitagent must be listed in packages"


def test_packages_does_not_contain_polkit_kde_agent() -> None:
    lines = [l for l in PACKAGES_FILE.read_text().splitlines() if not l.strip().startswith("#")]
    assert not any("polkit-kde-agent" in l for l in lines), \
        "polkit-kde-agent should be replaced by hyprpolkitagent"


def test_hyprland_conf_starts_hyprpolkitagent() -> None:
    text = HYPRLAND_CONF.read_text()
    assert "systemctl --user start hyprpolkitagent" in text, \
        "hyprland.conf must start hyprpolkitagent via systemctl --user"


def test_hyprland_conf_does_not_use_polkit_kde_binary() -> None:
    text = HYPRLAND_CONF.read_text()
    assert "polkit-kde-authentication-agent-1" not in text, \
        "polkit-kde-authentication-agent-1 should be replaced by hyprpolkitagent"


def test_readme_references_hyprpolkitagent() -> None:
    text = README.read_text()
    assert "hyprpolkitagent" in text, \
        "README must reference hyprpolkitagent in the dependencies table"
