"""Tests for bin/hyprconf-yubikey — FIDO2 (YubiKey) unlock of the LUKS2 root.

Verifies:
- enroll: preflight through Omarchy's tools, LUKS2-only device pick, snapshot
  first, systemd-cryptenroll with the FIDO2 flags, the mkinitcpio drop-in,
  the rd.luks.* cmdline parameters added once next to a kept cryptdevice=, a
  .bak.<epoch> backup before the first edit, one limine-update rebuild
- the drop-in REALLY rewrites Omarchy's exact HOOKS array when sourced by bash
- disable puts the drop-in and cmdline back; remove wipes only the fido2 slot
- status/help/sudo, and the restraint scans (no password slot, no pacman/AUR,
  no sbctl, no set -e)

HERMETIC: the tool talks to sudo, lsblk, cryptsetup, systemd-cryptenroll,
limine-update, omarchy-pkg-add, omarchy-snapshot, fido2-token and
omarchy-setup-security-fido2. Every one of them is a recording stub on a
fake-bins dir put FIRST on PATH, and every system path the tool edits is
pointed at a tmp copy through its env overrides — the real ones would enrol a
key into the developer's LUKS header, rewrite their initramfs and bootloader
entries, and take a snapper snapshot. stdin is never a terminal here, so the
--yes / TTY guard is exercised on every run.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
TOOL = REPO_ROOT / "bin" / "hyprconf-yubikey"

# Every external command the tool may call; the self-check below derives the
# same set from the tool's text so a new call cannot slip past the fakes.
EXTERNALS = (
    "sudo",
    "lsblk",
    "cryptsetup",
    "systemd-cryptenroll",
    "mkinitcpio",
    "limine-update",
    "omarchy-pkg-add",
    "omarchy-snapshot",
    "fido2-token",
    "omarchy-setup-security-fido2",
)

# Omarchy 4.0.0's /etc/mkinitcpio.conf.d/omarchy_hooks.conf, verbatim; its
# omarchy_resume.conf then appends resume.
OMARCHY_HOOKS = (
    "base udev plymouth keyboard autodetect microcode modconf kms keymap "
    "consolefont block encrypt filesystems fsck btrfs-overlayfs"
)
UUID = "11111111-2222-3333-4444-555555555555"
UUID2 = "66666666-7777-8888-9999-000000000000"
DEV = "/dev/nvme0n1p2"
CMDLINE = (
    "cryptdevice=PARTUUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee:root "
    "root=/dev/mapper/root zswap.enabled=0 rootflags=subvol=@ rw rootfstype=btrfs"
)
LIMINE_LINE = f'KERNEL_CMDLINE[default]+="{CMDLINE}"'
LIMINE_FILE = f'ESP_PATH="/boot"\n\n{LIMINE_LINE}\n'
RD_NAME = f"rd.luks.name={UUID}=root"
RD_OPTS = f"rd.luks.options={UUID}=fido2-device=auto"
TOKEN_LINE = "/dev/hidraw3: vendor=0x1050, product=0x0407 (Yubico YubiKey OTP+FIDO+CCID)"

# `lsblk -rno PATH,FSTYPE,FSVER,UUID` output: raw, one space per separator,
# empty fields empty (hence the runs of spaces).
LSBLK_STOCK = (
    "/dev/nvme0n1   \n"
    "/dev/nvme0n1p1 vfat FAT32 1234-ABCD\n"
    f"{DEV} crypto_LUKS 2 {UUID}\n"
    f"/dev/mapper/root btrfs  {UUID2}\n"
)

RECORD = '#!/usr/bin/env bash\nprintf \'%s\\n\' "{name}${{*:+ $*}}" >> "$FAKE_CALLS"\n'
STUBS = {
    # execs its arguments, the way the real one would run them as root
    "sudo": 'while (($#)); do case $1 in -- | -n) shift ;; *) break ;; esac; done\nexec "$@"\n',
    "lsblk": "printf '%s\\n' \"$FAKE_LSBLK\"\nexit 0\n",
    "cryptsetup": (
        'if [[ $1 == luksDump ]]; then\n  echo "Version:        2"\n'
        "  [[ -e $FAKE_STATE/fido2-slot ]] && printf 'Tokens:\\n  0: systemd-fido2\\n'\n"
        "fi\nexit 0\n"
    ),
    "systemd-cryptenroll": (
        'case " $* " in\n  *" --wipe-slot=fido2 "*) rm -f "$FAKE_STATE/fido2-slot" ;;\n'
        '  *" --fido2-device=auto "*) touch "$FAKE_STATE/fido2-slot" ;;\nesac\nexit 0\n'
    ),
    "mkinitcpio": "exit 0\n",
    "limine-update": "exit 0\n",
    "omarchy-pkg-add": "exit 0\n",
    "omarchy-snapshot": 'exit "${FAKE_SNAPSHOT_RC:-0}"\n',
    "fido2-token": "[[ $1 == -L && -n ${FAKE_TOKENS:-} ]] && printf '%s\\n' \"$FAKE_TOKENS\"\nexit 0\n",
    "omarchy-setup-security-fido2": 'echo "OMARCHY FIDO2 SETUP"\nexit 0\n',
}


class Box:
    """A throwaway Omarchy: fake bins, a limine file, a mkinitcpio.conf.d."""

    def __init__(self, tmp: Path, *, sd_overlay: bool = True) -> None:
        self.tmp = tmp
        self.bins = tmp / "bins"
        self.bins.mkdir()
        self.calls_file = tmp / "calls.txt"
        self.state = tmp / "state"
        self.state.mkdir()
        self.limine = tmp / "etc" / "default" / "limine"
        self.limine.parent.mkdir(parents=True)
        self.limine.write_text(LIMINE_FILE)
        self.mkinitcpio_d = tmp / "etc" / "mkinitcpio.conf.d"
        self.mkinitcpio_d.mkdir()
        (self.mkinitcpio_d / "omarchy_hooks.conf").write_text(f"HOOKS=({OMARCHY_HOOKS})\n")
        (self.mkinitcpio_d / "omarchy_resume.conf").write_text("HOOKS+=(resume)\n")
        self.initcpio_install = tmp / "initcpio-install"
        self.initcpio_install.mkdir()
        if sd_overlay:
            (self.initcpio_install / "sd-btrfs-overlayfs").write_text("#!/bin/bash\n")
        self.lsblk = LSBLK_STOCK
        self.tokens = TOKEN_LINE
        self.snapshot_rc = 0
        for name, body in STUBS.items():
            fake = self.bins / name
            fake.write_text(RECORD.format(name=name) + body)
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    @property
    def dropin(self) -> Path:
        return self.mkinitcpio_d / "zz-hyprconf-fido2.conf"

    @property
    def enrolled(self) -> bool:
        return (self.state / "fido2-slot").exists()

    def backups(self) -> list[Path]:
        return sorted(self.limine.parent.glob("limine.bak.*"))

    def limine_line(self) -> str:
        return next(ln for ln in self.limine.read_text().splitlines() if ln.startswith("KERNEL_"))

    def calls(self) -> list[str]:
        return self.calls_file.read_text().splitlines() if self.calls_file.exists() else []

    def reset_calls(self) -> None:
        self.calls_file.unlink(missing_ok=True)

    def run(self, *args: str) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "PATH": f"{self.bins}:{os.environ['PATH']}",
            "HOME": str(self.tmp),
            "_HYPRCONF_LIMINE_DEFAULT": str(self.limine),
            "_HYPRCONF_MKINITCPIO_D": str(self.mkinitcpio_d),
            "_HYPRCONF_FIDO2_DROPIN": "zz-hyprconf-fido2.conf",
            "_HYPRCONF_INITCPIO_INSTALL": str(self.initcpio_install),
            "FAKE_CALLS": str(self.calls_file),
            "FAKE_STATE": str(self.state),
            "FAKE_LSBLK": self.lsblk,
            "FAKE_TOKENS": self.tokens,
            "FAKE_SNAPSHOT_RC": str(self.snapshot_rc),
        }
        return subprocess.run(
            ["bash", str(TOOL), *args],
            capture_output=True,
            text=True,
            env=env,
            stdin=subprocess.DEVNULL,
            timeout=60,
        )


def _shellcheck(path: Path) -> subprocess.CompletedProcess:
    """Local shellcheck, else the project's docker invocation, else skip."""
    if shutil.which("shellcheck"):
        return subprocess.run(
            ["shellcheck", "--severity=warning", str(path)], capture_output=True, text=True
        )
    if (
        shutil.which("docker")
        and subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    ):
        return subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{path.parent}:/mnt:ro",
                "koalaman/shellcheck:stable",
                "--severity=warning",
                f"/mnt/{path.name}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    pytest.skip("neither shellcheck nor a docker daemon is available")


# ---------------------------------------------------------------------------
# Hermeticity and restraint self-checks
# ---------------------------------------------------------------------------


def test_every_external_the_tool_calls_has_a_fake() -> None:
    """A new external call fails here before it can reach the real system."""
    code = "\n".join(ln for ln in TOOL.read_text().splitlines() if not ln.lstrip().startswith("#"))
    pattern = r"\b(sudo|lsblk|cryptsetup|systemd-cryptenroll|mkinitcpio|limine-update|fido2-token|omarchy-[a-z0-9-]+)\b"
    called = set(re.findall(pattern, code))
    assert called, "no external calls found — the scan regex is broken"
    assert called <= set(EXTERNALS), f"unstubbed externals: {called - set(EXTERNALS)}"


def test_restraint_scan() -> None:
    """Never the password slot, pacman, the AUR, sbctl or set -e."""
    text = TOOL.read_text()
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -uo pipefail" in text
    for forbidden in (
        "wipe-slot=password",
        "pacman",
        "yay",
        "makepkg",
        "omarchy-pkg-aur-add",
        "sbctl",
        "set -e",
    ):
        assert forbidden not in text, f"{forbidden!r} must not appear in hyprconf-yubikey"
    assert "readonly" not in text, "system paths must stay env-overridable"


def test_bash_syntax() -> None:
    res = subprocess.run(["bash", "-n", str(TOOL)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_shellcheck_tool() -> None:
    res = _shellcheck(TOOL)
    assert res.returncode == 0, res.stdout + res.stderr


# ---------------------------------------------------------------------------
# enroll
# ---------------------------------------------------------------------------


def test_enroll_happy_path(tmp_path: Path) -> None:
    box = Box(tmp_path)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr + res.stdout
    calls = box.calls()

    # preflight through Omarchy's tools, then the snapshot BEFORE any change
    assert "omarchy-pkg-add libfido2" in calls
    assert "fido2-token -L" in calls
    assert "omarchy-snapshot create" in calls
    enroll = f"systemd-cryptenroll --fido2-device=auto --fido2-with-client-pin=yes {DEV}"
    assert enroll in calls
    assert calls.index("omarchy-snapshot create") < calls.index(enroll)
    assert box.enrolled

    # the rebuild is limine-update alone: it runs mkinitcpio for every kernel
    # itself (limine-mkinitcpio-install), and the mkinitcpio on Omarchy's PATH
    # is limine's interactive wrapper
    assert "limine-update" in calls
    assert calls.index(enroll) < calls.index("limine-update")
    assert not any(c.startswith("mkinitcpio") for c in calls)
    assert not any("wipe-slot" in c for c in calls)

    # the drop-in, sorted after Omarchy's own, with the revert path in its header
    assert box.dropin.is_file()
    dropin = box.dropin.read_text()
    assert "hyprconf-yubikey disable" in dropin
    assert sorted(p.name for p in box.mkinitcpio_d.iterdir())[-1] == box.dropin.name

    # cmdline: both parameters once, cryptdevice= kept, other lines untouched
    line = box.limine_line()
    assert line.startswith('KERNEL_CMDLINE[default]+="') and line.endswith('"')
    assert line.count("cryptdevice=PARTUUID=") == 1
    assert line.count(RD_NAME) == 1 and line.count(RD_OPTS) == 1
    assert line == f'KERNEL_CMDLINE[default]+="{CMDLINE} {RD_NAME} {RD_OPTS}"'
    assert box.limine.read_text().startswith('ESP_PATH="/boot"\n\n')

    # backup before the first edit, Omarchy's .bak.<epoch> convention
    backups = box.backups()
    assert len(backups) == 1 and re.fullmatch(r"limine\.bak\.\d+", backups[0].name)
    assert backups[0].read_text() == LIMINE_FILE

    assert "reboot" in res.stdout.lower() and "passphrase" in res.stdout.lower()


def test_enroll_no_snapshot_flag(tmp_path: Path) -> None:
    box = Box(tmp_path)
    res = box.run("enroll", "--yes", "--no-snapshot", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert not any(c.startswith("omarchy-snapshot") for c in box.calls())
    assert box.enrolled and box.dropin.is_file()


def test_enroll_rerun_is_idempotent(tmp_path: Path) -> None:
    box = Box(tmp_path)
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    after_first = box.limine.read_text()
    dropin_first = box.dropin.read_text()
    box.reset_calls()

    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    calls = box.calls()
    assert not any(c.startswith("systemd-cryptenroll") for c in calls), "slot already present"
    assert "limine-update" in calls
    assert box.limine.read_text() == after_first
    assert box.dropin.read_text() == dropin_first
    assert box.limine_line().count("rd.luks.") == 2
    assert len(box.backups()) == 1, "no second backup when nothing changed"


def test_enroll_refuses_luks1(tmp_path: Path) -> None:
    box = Box(tmp_path)
    box.lsblk = LSBLK_STOCK.replace(f"{DEV} crypto_LUKS 2 {UUID}", f"{DEV} crypto_LUKS 1 {UUID}")
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "LUKS2" in res.stderr
    _assert_untouched(box)


def test_enroll_without_token_touches_nothing(tmp_path: Path) -> None:
    box = Box(tmp_path)
    box.tokens = ""
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "fido2-token" in res.stderr
    assert set(box.calls()) <= {"omarchy-pkg-add libfido2", "fido2-token -L"}
    _assert_untouched(box)


def test_enroll_refuses_without_tty_or_yes(tmp_path: Path) -> None:
    box = Box(tmp_path)
    res = box.run("enroll", "--device", DEV)
    assert res.returncode != 0
    assert "--yes" in res.stderr
    _assert_untouched(box)


def test_enroll_needs_device_flag_when_several(tmp_path: Path) -> None:
    box = Box(tmp_path)
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS 2 {UUID2}\n"
    res = box.run("enroll", "--yes")
    assert res.returncode != 0 and "--device" in res.stderr
    _assert_untouched(box)

    res = box.run("enroll", "--yes", "--device", "/dev/sdz")
    assert res.returncode != 0 and "/dev/sdz" in res.stderr
    _assert_untouched(box)


def test_enroll_single_device_needs_no_flag(tmp_path: Path) -> None:
    box = Box(tmp_path)
    res = box.run("enroll", "--yes")
    assert res.returncode == 0, res.stderr
    assert RD_NAME in box.limine_line()


def test_enroll_aborts_when_snapshot_fails(tmp_path: Path) -> None:
    box = Box(tmp_path)
    box.snapshot_rc = 1
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "--no-snapshot" in res.stderr
    _assert_untouched(box, allow=("omarchy-snapshot",))

    box.snapshot_rc = 127  # omarchy-snapshot: snapper not installed
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "snapper" in res.stderr and box.enrolled


def test_enroll_takes_mapper_name_from_cryptdevice_and_keeps_bare_form(tmp_path: Path) -> None:
    box = Box(tmp_path)
    box.limine.write_text(
        "KERNEL_CMDLINE[default]+=cryptdevice=UUID=x:cryptroot root=/dev/mapper/cryptroot rw\n"
    )
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert box.limine_line() == (
        "KERNEL_CMDLINE[default]+=cryptdevice=UUID=x:cryptroot root=/dev/mapper/cryptroot rw "
        f"rd.luks.name={UUID}=cryptroot {RD_OPTS}"
    )


def _assert_untouched(box: Box, *, allow: tuple[str, ...] = ()) -> None:
    calls = box.calls()
    for name in ("systemd-cryptenroll", "limine-update", "mkinitcpio", "omarchy-snapshot"):
        if name in allow:
            continue
        assert not any(c.startswith(name) for c in calls), f"{name} ran: {calls}"
    assert not box.dropin.exists()
    assert box.limine.read_text() == LIMINE_FILE
    assert box.backups() == []
    assert not box.enrolled


# ---------------------------------------------------------------------------
# The drop-in, sourced the way mkinitcpio sources it
# ---------------------------------------------------------------------------


def _source_dropin(box: Box, hooks: str, *, sd_overlay_dir: Path | None = None) -> list[str]:
    script = (
        "set -u\n"
        f"HOOKS=({hooks})\n"
        f'source "{box.dropin}"\n'
        "declare -p _hyprconf_hooks _hyprconf_hook >/dev/null 2>&1 && echo LEAKED\n"
        "printf '%s\\n' \"${HOOKS[@]}\"\n"
    )
    env = {
        "PATH": os.environ["PATH"],
        "_HYPRCONF_INITCPIO_INSTALL": str(sd_overlay_dir or box.initcpio_install),
    }
    res = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=30
    )
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert "LEAKED" not in lines, "the drop-in must unset its temporaries"
    return lines


def test_dropin_rewrites_omarchy_hooks(tmp_path: Path) -> None:
    box = Box(tmp_path)
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0

    # Omarchy's final HOOKS: omarchy_hooks.conf + omarchy_resume.conf
    hooks = _source_dropin(box, f"{OMARCHY_HOOKS} resume")
    assert hooks == [
        "base", "systemd", "plymouth", "keyboard", "autodetect", "microcode", "modconf", "kms",
        "sd-vconsole", "block", "sd-encrypt", "filesystems", "fsck", "sd-btrfs-overlayfs",
    ]  # fmt: skip
    for gone in ("udev", "encrypt", "keymap", "consolefont", "resume", ""):
        assert gone not in hooks

    # empty elements are dropped too
    assert _source_dropin(box, 'base "" udev encrypt') == ["base", "systemd", "sd-encrypt"]

    # an already-systemd HOOKS passes through untouched (re-sourcing is a no-op)
    converted = " ".join(hooks)
    assert _source_dropin(box, converted) == hooks


def test_dropin_keeps_busybox_overlay_hook_without_sd_variant(tmp_path: Path) -> None:
    """Older limine-mkinitcpio-hook without sd-btrfs-overlayfs: keep the busybox
    hook (harmless under systemd) rather than name a hook that does not exist."""
    box = Box(tmp_path, sd_overlay=False)
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    hooks = _source_dropin(box, OMARCHY_HOOKS)
    assert hooks[-1] == "btrfs-overlayfs" and "sd-btrfs-overlayfs" not in hooks
    assert "systemd" in hooks and "sd-encrypt" in hooks


def test_shellcheck_dropin(tmp_path: Path) -> None:
    box = Box(tmp_path)
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    res = _shellcheck(box.dropin)
    assert res.returncode == 0, res.stdout + res.stderr


# ---------------------------------------------------------------------------
# disable / remove
# ---------------------------------------------------------------------------


def test_disable_reverts_dropin_and_cmdline(tmp_path: Path) -> None:
    box = Box(tmp_path)
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    box.reset_calls()

    res = box.run("disable", "--yes")
    assert res.returncode == 0, res.stderr
    calls = box.calls()
    assert not box.dropin.exists()
    assert box.limine_line() == LIMINE_LINE
    assert box.limine.read_text() == LIMINE_FILE
    assert len(box.backups()) == 2, "backup before the disable edit too"
    assert "omarchy-snapshot create" in calls
    assert "limine-update" in calls
    assert not any(c.startswith("systemd-cryptenroll") for c in calls)
    assert box.enrolled, "disable keeps the LUKS slot"
    assert (box.mkinitcpio_d / "omarchy_hooks.conf").exists(), "Omarchy's own drop-ins stay"


def test_disable_refuses_without_tty_or_yes(tmp_path: Path) -> None:
    box = Box(tmp_path)
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    box.reset_calls()
    res = box.run("disable")
    assert res.returncode != 0 and "--yes" in res.stderr
    assert box.dropin.exists() and RD_OPTS in box.limine_line()
    assert box.calls() == []


def test_disable_when_not_configured_changes_nothing(tmp_path: Path) -> None:
    box = Box(tmp_path)
    res = box.run("disable", "--yes", "--no-snapshot")
    assert res.returncode == 0, res.stderr
    assert box.calls() == []
    assert box.limine.read_text() == LIMINE_FILE and box.backups() == []


def test_remove_wipes_fido2_slot_then_disables(tmp_path: Path) -> None:
    box = Box(tmp_path)
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    box.reset_calls()

    res = box.run("remove", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    calls = box.calls()
    wipe = f"systemd-cryptenroll --wipe-slot=fido2 {DEV}"
    assert wipe in calls
    assert calls.index(wipe) < calls.index("limine-update")
    assert not any("password" in c for c in calls), "passphrase slots are never touched"
    assert not box.enrolled
    assert not box.dropin.exists()
    assert box.limine_line() == LIMINE_LINE


def test_remove_refuses_without_tty_or_yes(tmp_path: Path) -> None:
    box = Box(tmp_path)
    res = box.run("remove", "--device", DEV)
    assert res.returncode != 0 and "--yes" in res.stderr
    assert not any(c.startswith("systemd-cryptenroll") for c in box.calls())


# ---------------------------------------------------------------------------
# status / help / sudo
# ---------------------------------------------------------------------------


def test_status_prints_facts(tmp_path: Path) -> None:
    box = Box(tmp_path)
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS 1 {UUID2}\n"

    res = box.run("status")
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert f"{DEV}  LUKS2  UUID {UUID}  systemd-fido2 slot: no" in out
    assert "/dev/sdd  LUKS1" in out and "not eligible" in out
    assert "initramfs drop-in:    absent" in out
    assert "no rd.luks.options fido2-device" in out
    assert f"plugged in — {TOKEN_LINE}" in out
    assert "sd-btrfs-overlayfs installed" in out
    for name in ("systemd-cryptenroll", "limine-update", "omarchy-snapshot", "mkinitcpio"):
        assert not any(c.startswith(name) for c in box.calls())

    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    box.tokens = ""
    res = box.run()  # status is the default subcommand
    assert res.returncode == 0
    assert "systemd-fido2 slot: yes" in res.stdout
    assert "initramfs drop-in:    present" in res.stdout
    assert "rd.luks.options fido2-device present" in res.stdout
    assert "FIDO2 token:          none detected" in res.stdout


def test_status_never_fails(tmp_path: Path) -> None:
    box = Box(tmp_path, sd_overlay=False)
    box.limine.unlink()
    box.lsblk = ""
    res = box.run("status")
    assert res.returncode == 0, res.stderr
    assert "none found" in res.stdout and "not found" in res.stdout
    assert "sd-btrfs-overlayfs NOT installed" in res.stdout


def test_help_documents_flags_limitation_and_revert(tmp_path: Path) -> None:
    box = Box(tmp_path)
    res = box.run("help")
    assert res.returncode == 0
    out = res.stdout
    for sub in ("status", "enroll", "disable", "remove", "sudo", "help"):
        assert re.search(rf"^(usage:)?\s+hyprconf-yubikey {sub}\b", out, re.M), sub
    for flag in ("--device", "--yes", "--no-snapshot"):
        assert flag in out
    assert "snapshot" in out and "sd-btrfs-overlayfs" in out
    assert "hyprconf-yubikey disable" in out and "hyprconf-yubikey remove" in out
    assert "Passphrase slots are never touched" in out
    assert box.run("--help").returncode == 0
    assert box.run("bogus").returncode != 0
    assert box.calls() == []


def test_sudo_subcommand_execs_omarchy_script(tmp_path: Path) -> None:
    box = Box(tmp_path)
    res = box.run("sudo")
    assert res.returncode == 0, res.stderr
    assert "OMARCHY FIDO2 SETUP" in res.stdout
    assert box.calls() == ["omarchy-setup-security-fido2"]
