"""
Static-analysis tests for `hyprconf dev checkout`.

Verifies that the _dev_checkout function and its dispatch in cmd_dev are
correctly defined in the hyprconf bash binary without executing live git
commands.  Follows the pattern established in test_hyprlauncher_migration.py.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
HYPRCONF_BIN = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf"


def _text() -> str:
    return HYPRCONF_BIN.read_text(encoding="utf-8")


def _extract_function(name: str) -> str:
    """Return the body of a bash function by name."""
    match = re.search(
        rf"^{re.escape(name)}\(\)\s*\{{(.*?)\n\}}",
        _text(),
        re.DOTALL | re.MULTILINE,
    )
    assert match, f"Function {name}() not found in hyprconf binary"
    return match.group(1)


# ---------------------------------------------------------------------------
# _dev_checkout function definition
# ---------------------------------------------------------------------------

def test_dev_checkout_function_exists() -> None:
    """_dev_checkout() must be defined in the hyprconf binary."""
    assert "_dev_checkout()" in _text(), "_dev_checkout() not found in hyprconf binary"


def test_dev_checkout_disables_sparse() -> None:
    """_dev_checkout must disable sparse checkout."""
    body = _extract_function("_dev_checkout")
    assert "sparse-checkout disable" in body, (
        "_dev_checkout must run 'git sparse-checkout disable'"
    )


def test_dev_checkout_fetches_dev_branch() -> None:
    """_dev_checkout must fetch the dev branch from origin."""
    body = _extract_function("_dev_checkout")
    assert "fetch origin dev" in body, (
        "_dev_checkout must run 'git fetch origin dev'"
    )


def test_dev_checkout_switches_to_dev_branch() -> None:
    """_dev_checkout must switch to the dev branch."""
    body = _extract_function("_dev_checkout")
    assert "checkout dev" in body, (
        "_dev_checkout must run 'git checkout dev'"
    )


# ---------------------------------------------------------------------------
# cmd_dev dispatch
# ---------------------------------------------------------------------------

def test_dev_checkout_dispatched_from_cmd_dev() -> None:
    """cmd_dev must dispatch the 'checkout' subcommand to _dev_checkout."""
    body = _extract_function("cmd_dev")
    assert "checkout)" in body, "'checkout)' case not found in cmd_dev"
    assert "_dev_checkout" in body, "cmd_dev checkout) case must call _dev_checkout"


# ---------------------------------------------------------------------------
# Usage / documentation
# ---------------------------------------------------------------------------

def test_dev_checkout_documented_in_usage() -> None:
    """_dev_usage must document 'hyprconf dev checkout'."""
    body = _extract_function("_dev_usage")
    assert "dev checkout" in body, (
        "_dev_usage must document 'hyprconf dev checkout'"
    )
