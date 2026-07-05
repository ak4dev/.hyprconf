"""Policy tests for setup.sh hardening invariants.

- No remote code execution: third-party tools (Oh My Zsh) are installed by
  cloning their repo, never by piping a fetched script into a shell.
- Stow must never ship Python bytecode caches (__pycache__) into $HOME.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SETUP_SH = REPO_ROOT / "setup.sh"


def _text() -> str:
    return SETUP_SH.read_text(encoding="utf-8")


def _extract_function(name: str) -> str:
    result = subprocess.run(
        ["awk", f"/^{name}\\(\\)/,/^\\}}$/", str(SETUP_SH)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


class TestNoRemoteCodeExecution:
    def test_no_curl_piped_into_shell(self) -> None:
        """setup.sh must never execute a script fetched over the network
        (`sh -c "$(curl ...)"` / `curl ... | bash`) — clone the repo instead."""
        for line in _text().splitlines():
            code = line.split("#", 1)[0]
            assert not re.search(r"""(sh|bash)\s+-c\s+["']?\$\(\s*curl""", code), line
            assert not re.search(r"curl\s[^|]*\|\s*(sudo\s+)?(ba)?sh", code), line

    def test_oh_my_zsh_installed_via_git_clone(self) -> None:
        fn = _extract_function("install_oh_my_zsh")
        assert "git clone" in fn and "ohmyzsh" in fn, (
            "Oh My Zsh must be installed by cloning its repo, not via the remote install script"
        )
        assert "curl" not in fn


class TestStowIgnoresPycache:
    def test_stow_invocations_ignore_pycache(self) -> None:
        fn = _extract_function("force_stow_package")
        stow_calls = [ln for ln in fn.splitlines() if re.search(r"\bstow -d\b", ln)]
        assert stow_calls, "force_stow_package must call stow"
        for ln in stow_calls:
            assert "--ignore='__pycache__'" in ln, f"missing --ignore: {ln}"

    def test_additive_linker_prunes_pycache(self) -> None:
        fn = _extract_function("_additive_link_package")
        finds = [ln for ln in fn.splitlines() if "find " in ln and "$pkg_root" in ln]
        assert finds, "_additive_link_package must walk the package with find"
        for ln in finds:
            assert "__pycache__ -prune" in ln, f"missing __pycache__ prune: {ln}"
