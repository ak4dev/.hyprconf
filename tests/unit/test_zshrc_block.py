"""zsh/zshrc.block — the managed ~/.zshrc block install.sh writes.

The `hyprsync` alias has to name the checkout wherever it is (HYPRCONF_DIR
relocates it), so it carries the `@HYPRCONF_DIR@` placeholder every other
payload that names the checkout carries; stage_shell renders it through the
same `sed` pass as stage_bin and stage_hooks, and a relocated checkout is
re-applied from its new location, which rewrites the block.

It used to derive the path from `readlink -f ~/.p10k.zsh`, which GNU readlink
answers for a file that is not there too: with the link gone — the documented
revert removes it several steps before the .zshrc block — the two dirnames left
`/home` and the alias ran `bash /home/install.sh --sync`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

BLOCK = Path(__file__).parent.parent.parent / "zsh" / "zshrc.block"


def _alias() -> str:
    return next(ln for ln in BLOCK.read_text().splitlines() if ln.startswith("alias hyprsync="))


def test_hyprsync_alias_carries_the_placeholder_not_a_derived_path() -> None:
    alias = _alias()
    assert "@HYPRCONF_DIR@/install.sh" in alias
    assert "readlink" not in BLOCK.read_text(), "the checkout path is rendered in, not derived"


def test_rendered_hyprsync_alias_runs_the_checkouts_installer(tmp_path: Path) -> None:
    checkout = tmp_path / "elsewhere" / "checkout"
    checkout.mkdir(parents=True)
    alias = _alias().replace("@HYPRCONF_DIR@", str(checkout))
    # The alias body is POSIX sh, so bash expands it exactly as zsh does; bash
    # is replaced by a function so nothing runs.
    script = (
        f"shopt -s expand_aliases\n{alias}\nbash() {{ printf '%s\\n' \"$@\"; }}\neval hyprsync\n"
    )
    res = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        env={"HOME": str(tmp_path / "home"), "PATH": os.environ["PATH"]},
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.splitlines() == [str(checkout / "install.sh"), "--sync"]
