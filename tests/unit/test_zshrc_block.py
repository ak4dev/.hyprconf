"""zsh/zshrc.block — the managed ~/.zshrc block install.sh writes verbatim.

The `hyprsync` alias has to find the checkout wherever it is (HYPRCONF_DIR
relocates it), so it follows the ~/.p10k.zsh symlink the same install stage
makes instead of carrying a path.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

BLOCK = Path(__file__).parent.parent.parent / "zsh" / "zshrc.block"


def test_hyprsync_alias_follows_the_p10k_link_to_the_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "elsewhere" / "checkout"
    (checkout / "zsh").mkdir(parents=True)
    (checkout / "zsh" / ".p10k.zsh").touch()
    home = tmp_path / "home"
    home.mkdir()
    (home / ".p10k.zsh").symlink_to(checkout / "zsh" / ".p10k.zsh")
    alias = next(ln for ln in BLOCK.read_text().splitlines() if ln.startswith("alias hyprsync="))
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
        env={"HOME": str(home), "PATH": os.environ["PATH"]},
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.splitlines() == [str(checkout / "install.sh"), "--sync"]
