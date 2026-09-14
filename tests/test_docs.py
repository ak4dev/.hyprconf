"""The docs contract, structure only (AGENTS.md rule 7 keeps the prose a
review norm): the README branding block never changes; the root README's
module index names exactly the modules that exist — one row each, so a module
added or removed without its row turns red here rather than in a reader's
hands; and every module README carries the six sections of the module
contract with its solo-install and undo lines.

HERMETIC: reads of the checkout only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"

# Rule 7: never alter the README branding block (banner + badges). Pinned as
# the bytes themselves, so a rewrite of the file around it cannot drift them.
BRANDING = """<p align="center">
  <img src="assets/banner.svg" width="920" alt=".hyprconf" />
</p>

<p align="center">
  <a href="https://hyprconf.sh"><img alt="installer" src="https://img.shields.io/badge/installer-hyprconf.sh-0ea5e9?style=for-the-badge" /></a>
  <img alt="arch linux" src="https://img.shields.io/badge/arch-linux-1793d1?style=for-the-badge&logo=archlinux&logoColor=white" />
  <img alt="hyprland" src="https://img.shields.io/badge/hyprland-wayland-111827?style=for-the-badge&logo=wayland&logoColor=white" />
  <a href="https://omarchy.org"><img alt="omarchy overlay" src="https://img.shields.io/badge/omarchy-overlay-3a7f2e?style=for-the-badge" /></a>
</p>

# .hyprconf
"""


def modules() -> list[str]:
    """Every module directory: the ones install.sh's loop runs."""
    return sorted(p.parent.name for p in (REPO_ROOT / "modules").glob("*/install"))


def test_readme_branding_block_is_byte_identical() -> None:
    assert README.read_text(encoding="utf-8").startswith(BRANDING)


def test_root_readme_indexes_every_module_once() -> None:
    """One row per module in the Modules table, linking its README, with the
    solo install and the undo command; no row for a module that is gone."""
    text = README.read_text(encoding="utf-8")
    rows = re.findall(r"^\| \[`([a-z-]+)`\]\(modules/([a-z-]+)/README\.md\) \|(.*)$", text, re.M)
    assert [name for name, _, _ in rows] == modules(), "the Modules table and modules/ differ"
    for name, target, rest in rows:
        assert name == target, f"{name}: row links {target}"
        assert f"`bash modules/{name}/install` |" in rest, f"{name}: no solo install cell"
        assert f"`bash modules/{name}/install undo`" in rest, f"{name}: no undo cell"
    for name in modules():
        assert f"(modules/{name}/README.md#undo)" in text, f"{name}: no Reverting-to-stock line"


# The module README contract (the module layout's parity target, AGENTS rule 7):
# the six sections, the solo-install line and the undo line. Length and prose
# are a review norm, not a gate.
SECTIONS = (
    "## What",
    "## Requires",
    "## Install alone",
    "## Settings",
    "## Undo",
    "## Verified against",
)
SOLO = "git -C ~/.hyprconf sparse-checkout set modules/{name} && bash ~/.hyprconf/modules/{name}/install"


@pytest.mark.parametrize("name", modules())
def test_module_readme_carries_the_contract(name: str) -> None:
    text = (REPO_ROOT / "modules" / name / "README.md").read_text(encoding="utf-8")
    headings = [ln for ln in text.splitlines() if ln.startswith("## ")]
    for section in SECTIONS:
        assert any(h.startswith(section) for h in headings), f"{name}: no {section!r} section"
    assert SOLO.format(name=name) in text, f"{name}: no solo install line"
    assert f"modules/{name}/install undo" in text, f"{name}: the undo line does not name the module"
