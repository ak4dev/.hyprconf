"""
Tests for the no-automatic-AUR policy.

hyprconf installs ONLY official-repo packages automatically. It must never:
- build/install the yay AUR helper automatically,
- install the on-screen keyboard (wvkbd, AUR-only) automatically, even on touch
  devices,
- install any AUR package in an addon without an explicit warning + confirmation.

It must also offer to remove foreign (AUR) packages already on the system, while
keeping the yay helper so `hyprconf addon` can still build AUR packages on demand.

Covers:
- setup.sh has no automatic AUR install (no `yay -S`, no `makepkg`, no
  install_yay / _install_wvkbd helpers).
- setup.sh's remove_aur_packages(): keeps yay, removes other foreign packages,
  prompts, defaults to "no" when non-interactive, and is wired into both the
  install and sync paths.
- hyprconf's addon AUR install requires confirmation and drops --noconfirm.
"""

from __future__ import annotations

import os
import pty
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SETUP_SH = REPO_ROOT / "setup.sh"
HYPRCONF = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf"


# ---------------------------------------------------------------------------
# Static analysis helpers
# ---------------------------------------------------------------------------


def _setup_text() -> str:
    return SETUP_SH.read_text()


def _noncomment_lines(text: str) -> str:
    """Join all lines whose first non-space char is not '#'.

    Manual-install hints (`# ... yay -S wvkbd`) live in comments and must be
    ignored so we only assert on code that actually executes.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _invokes_command(text: str, cmd: str) -> bool:
    """True if any line *runs* `cmd` (as the command word), ignoring comments and
    strings that merely mention it (e.g. a log_warn manual-install hint like
    'install it manually: yay -S wvkbd')."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Command word appears at the start of a statement: line start, or after
        # a shell separator (`&& yay`, `| yay`, `$(yay`, `; yay`).
        if stripped.startswith(f"{cmd} "):
            return True
        for sep in ("&& ", "|| ", "; ", "| ", "$(", "`"):
            if f"{sep}{cmd} " in line:
                return True
    return False


def _extract_function(name: str) -> str:
    """Return the body of a bash function from setup.sh via awk."""
    result = subprocess.run(
        ["awk", f"/^{name}\\(\\)/,/^\\}}$/", str(SETUP_SH)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Functional harness — run remove_aur_packages() in isolation with fake
# pacman/sudo binaries so we can observe what it would remove.
# ---------------------------------------------------------------------------


def _make_fakes(tmp_path: Path) -> tuple[Path, Path]:
    """Create fake `pacman` and `sudo` on a private bindir. Returns (bindir, rns_log)."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    rns_log = tmp_path / "rns.log"

    pacman = bindir / "pacman"
    pacman.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "${1:-}" == "-Qmq" ]]; then\n'
        "  printf '%s\\n' ${FAKE_FOREIGN:-}\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "${1:-}" == "-Rns" ]]; then\n'
        "  shift\n"
        '  printf \'RNS %s\\n\' "$*" >> "$RNS_LOG"\n'
        "  exit 0\n"
        "fi\n"
        "exit 0\n"
    )
    pacman.chmod(0o755)

    sudo = bindir / "sudo"
    sudo.write_text('#!/usr/bin/env bash\nexec "$@"\n')
    sudo.chmod(0o755)

    return bindir, rns_log


def _fragment() -> str:
    """A runnable bash program that stubs the logging helpers and invokes the
    real remove_aur_packages() body extracted from setup.sh."""
    return "\n".join(
        [
            "set -euo pipefail",
            "WH=''; RS=''",
            "log_step(){ printf '%s\\n' \"$*\"; }",
            "log_ok(){ printf '%s\\n' \"$*\"; }",
            "log_warn(){ printf '%s\\n' \"$*\"; }",
            _extract_function("remove_aur_packages"),
            "remove_aur_packages",
        ]
    )


def _run(bindir: Path, rns_log: Path, foreign: str) -> subprocess.CompletedProcess:
    """Run the fragment non-interactively (stdin = /dev/null → not a tty)."""
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "RNS_LOG": str(rns_log),
        "FAKE_FOREIGN": foreign,
    }
    return subprocess.run(
        ["bash", "-c", _fragment()],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
    )


def _run_tty(bindir: Path, rns_log: Path, foreign: str, answer: str) -> str:
    """Run the fragment with a pty on stdin (so `[[ -t 0 ]]` is true) and feed
    `answer`. Returns combined stdout/stderr."""
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "RNS_LOG": str(rns_log),
        "FAKE_FOREIGN": foreign,
    }
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        ["bash", "-c", _fragment()],
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    os.close(slave)
    os.write(master, answer.encode())
    out, _ = proc.communicate(timeout=30)
    os.close(master)
    return out


# ---------------------------------------------------------------------------
# 1. setup.sh must not install AUR packages automatically
# ---------------------------------------------------------------------------


class TestNoAutomaticAurInstall:
    def test_no_yay_install_command(self) -> None:
        assert not _invokes_command(_setup_text(), "yay"), (
            "setup.sh must not run yay (no automatic AUR installs); manual-install "
            "hints in messages/comments are fine"
        )

    def test_no_makepkg_build(self) -> None:
        code = _noncomment_lines(_setup_text())
        assert "makepkg" not in code, "setup.sh must not build AUR packages via makepkg"

    def test_install_yay_helper_removed(self) -> None:
        code = _noncomment_lines(_setup_text())
        assert "install_yay" not in code, "the install_yay auto-installer must be gone"

    def test_wvkbd_autoinstaller_removed(self) -> None:
        """Even the on-screen keyboard (wvkbd, AUR-only) must not auto-install."""
        code = _noncomment_lines(_setup_text())
        assert "_install_wvkbd" not in code, "the _install_wvkbd auto-installer must be gone"

    def test_touchscreen_branch_warns_instead_of_installing(self) -> None:
        func = _extract_function("setup_hardware_features")
        assert not _invokes_command(func, "yay"), "touchscreen branch must not run yay"
        assert "wvkbd" in func, "touchscreen branch should still mention the OSK (as a manual step)"


# ---------------------------------------------------------------------------
# 2. remove_aur_packages — structure and wiring
# ---------------------------------------------------------------------------


class TestRemoveAurStructure:
    def test_function_defined(self) -> None:
        assert "remove_aur_packages()" in _setup_text()

    def test_uses_qmq_and_rns(self) -> None:
        func = _extract_function("remove_aur_packages")
        assert "pacman -Qmq" in func, "must enumerate foreign packages via pacman -Qmq"
        assert "pacman -Rns" in func, "must remove via pacman -Rns"

    def test_keeps_yay(self) -> None:
        func = _extract_function("remove_aur_packages")
        assert "yay" in func, "yay helper must be on the keep-list"

    def test_defaults_to_no_when_non_interactive(self) -> None:
        func = _extract_function("remove_aur_packages")
        assert "-t 0" in func, "must gate the removal prompt on an interactive stdin"

    def test_wired_into_install_and_sync(self) -> None:
        call_lines = [
            line for line in _setup_text().splitlines() if line.strip() == "remove_aur_packages"
        ]
        assert len(call_lines) >= 2, "remove_aur_packages must run in both install and sync paths"


# ---------------------------------------------------------------------------
# 3. remove_aur_packages — behaviour
# ---------------------------------------------------------------------------


class TestRemoveAurBehaviour:
    def test_noop_when_no_foreign_packages(self, tmp_path: Path) -> None:
        bindir, rns_log = _make_fakes(tmp_path)
        res = _run(bindir, rns_log, foreign="")
        assert res.returncode == 0
        assert "nothing to remove" in res.stdout.lower()
        assert not rns_log.exists(), "must not remove anything when there is nothing to remove"

    def test_noninteractive_defaults_to_no_removal(self, tmp_path: Path) -> None:
        bindir, rns_log = _make_fakes(tmp_path)
        res = _run(bindir, rns_log, foreign="foopkg yay barpkg")
        assert res.returncode == 0
        # It lists the foreign packages (yay excluded) but removes nothing.
        assert "foopkg" in res.stdout and "barpkg" in res.stdout
        assert "yay" not in res.stdout, "yay must never be listed for removal"
        assert not rns_log.exists(), "non-interactive run must default to NOT removing"

    def test_interactive_yes_removes_non_yay_only(self, tmp_path: Path) -> None:
        bindir, rns_log = _make_fakes(tmp_path)
        _run_tty(bindir, rns_log, foreign="foopkg yay barpkg", answer="y\n")
        assert rns_log.exists(), "confirming should invoke pacman -Rns"
        removed = rns_log.read_text()
        assert "foopkg" in removed and "barpkg" in removed
        assert "yay" not in removed, "yay must never be removed"

    def test_interactive_no_removes_nothing(self, tmp_path: Path) -> None:
        bindir, rns_log = _make_fakes(tmp_path)
        _run_tty(bindir, rns_log, foreign="foopkg barpkg", answer="n\n")
        assert not rns_log.exists(), "declining must not remove anything"


# ---------------------------------------------------------------------------
# 4. hyprconf addon — AUR installs require an explicit warning + confirmation
# ---------------------------------------------------------------------------


class TestAddonAurConfirmation:
    def _hyprconf_text(self) -> str:
        return HYPRCONF.read_text()

    def test_aur_install_has_no_noconfirm(self) -> None:
        for line in self._hyprconf_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("yay -S"):
                assert "--noconfirm" not in stripped, (
                    "addon AUR install must not use --noconfirm (require review/confirmation)"
                )

    def test_aur_block_warns(self) -> None:
        txt = self._hyprconf_text()
        assert "WARNING" in txt, "addon AUR install must display a warning"

    def test_aur_block_prompts_for_confirmation(self) -> None:
        txt = self._hyprconf_text()
        assert "_aur_ans" in txt and "read -r _aur_ans" in txt, (
            "addon AUR install must read an explicit confirmation before installing"
        )
