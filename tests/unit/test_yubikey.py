"""Tests for bin/hyprconf-yubikey — FIDO2 (YubiKey) unlock of the LUKS2 root.

Verifies:
- enroll: read-only preflight (Omarchy's tools, the keyboard-layout guard, the
  LUKS2-only device pick, the cmdline parse) BEFORE the --yes/TTY confirmation,
  and nothing — not even omarchy-pkg-add — before it; then snapshot,
  systemd-cryptenroll with the FIDO2 flags, the mkinitcpio drop-in, the
  rd.luks.* parameters added once next to a kept cryptdevice=, a .bak.<epoch>
  backup before the first edit, one limine-update rebuild, and the rebuilt
  image found on the ESP before success is announced
- every KERNEL_CMDLINE[default] shape /etc/limine-entry-tool.conf documents
  (quoted, bare with inner quotes, comment after the quotes, single quotes,
  = and +=, pre-existing rd.luks.* for this and other devices) — the exact
  resulting line after enroll and after disable — and the shapes refused
- the mapper name comes from the edited line alone (cryptdevice= cross-checked
  with root=/dev/mapper/), never from a commented or another entry's line
- limine-update's exit-0-on-failure is caught by its message and by the
  image's mtime on the ESP (UKI on UEFI per Omarchy's omarchy-uki.conf, else
  the initramfs), with an identical unrewritten image accepted only when the
  hook set did not change
- the drop-in REALLY rewrites Omarchy's exact HOOKS array when sourced by bash
- disable puts the drop-in and cmdline back; remove wipes only the fido2 slot
- status/help/sudo, and the restraint scans (no password slot, no AUR, no set -e)

HERMETIC: the tool talks to sudo, lsblk, cryptsetup, systemd-cryptenroll,
limine-update, omarchy-pkg-add, omarchy-snapshot, fido2-token and
omarchy-setup-security-fido2. Every one of them is a recording stub on a
fake-bins dir put FIRST on PATH, and every system path the tool reads or edits
— /etc/default/limine and limine's other config files, mkinitcpio.conf.d,
vconsole.conf, machine-id, /usr/lib/modules, /sys/firmware/efi and the ESP
itself — is pointed at a tmp copy through its env overrides. The real ones
would enrol a key into the developer's LUKS header, rewrite their initramfs
and bootloader entries, and take a snapper snapshot. stdin is never a terminal
here, so the --yes / TTY guard is exercised on every run.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import time
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
RD_NAME = f"rd.luks.name={UUID}=root"
RD_OPTS = f"rd.luks.options={UUID}=fido2-device=auto"
ADDED = f"{RD_NAME} {RD_OPTS}"
TOKEN_LINE = "/dev/hidraw3: vendor=0x1050, product=0x0407 (Yubico YubiKey OTP+FIDO+CCID)"
MACHINE_ID = "0123456789abcdef0123456789abcdef"
KERNEL_VERSION = "7.1.8-arch1-3"
# /etc/vconsole.conf as systemd-localed writes it on a stock Omarchy
VCONSOLE = "KEYMAP=us\nXKBLAYOUT=us\nXKBMODEL=pc105+inet\nXKBOPTIONS=terminate:ctrl_alt_bksp\n"
# The first-layout list Omarchy's guard withholds vconsole.conf for (omarchy_hooks.conf).
NON_LATIN = "af am ara bd bg by et ge gr il in iq ir kg kh kz la lk mk mm mn mv np rs ru sy th tj ua".split()
# What limine-mkinitcpio-install prints (error_msg) when a build fails, verbatim.
BUILD_FAILED = f"ERROR: mkinitcpio failed for kernel {KERNEL_VERSION}, skipping."

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
    # The real one exits 0 whatever mkinitcpio did (limine-mkinitcpio-install
    # `|| true`); "ok" writes the images the test expects, "fail" prints the
    # failure message instead, "stale" builds nothing and says nothing.
    "limine-update": (
        'echo "limine-install: fake"\n'
        "case ${FAKE_LIMINE_UPDATE:-ok} in\n"
        f'  ok) echo "Building UKI for linux ({KERNEL_VERSION})"\n'
        '      while IFS= read -r f; do [[ -n $f ]] || continue; mkdir -p "${f%/*}" && : >"$f"; done'
        ' <<<"${FAKE_BOOT_IMAGES:-}" ;;\n'
        f'  fail) echo "Building UKI for linux ({KERNEL_VERSION})"; echo "{BUILD_FAILED}" >&2 ;;\n'
        "  stale) ;;\n"
        '  exit1) echo "ERROR: FAT32 boot partition not found." >&2; exit 1 ;;\n'
        "esac\nexit 0\n"
    ),
    "omarchy-pkg-add": "exit 0\n",
    "omarchy-snapshot": 'exit "${FAKE_SNAPSHOT_RC:-0}"\n',
    "fido2-token": "[[ $1 == -L && -n ${FAKE_TOKENS:-} ]] && printf '%s\\n' \"$FAKE_TOKENS\"\nexit 0\n",
    "omarchy-setup-security-fido2": 'echo "OMARCHY FIDO2 SETUP"\nexit 0\n',
}


class Box:
    """A throwaway Omarchy: fake bins, limine's config files, a mkinitcpio.conf.d,
    vconsole.conf, one installed kernel, a machine-id, a UEFI marker and an ESP.

    Stock Omarchy 4.0.0 shape: ESP_PATH in /etc/default/limine, ENABLE_UKI=yes
    from /etc/limine-entry-tool.d/omarchy-uki.conf over the packaged
    /etc/limine-entry-tool.conf's ENABLE_UKI=no, CUSTOM_UKI_NAME="omarchy" in
    omarchy-defaults.conf — so the boot image is <ESP>/EFI/Linux/omarchy_linux.efi.
    """

    def __init__(
        self, tmp: Path, *, sd_overlay: bool = True, uki: bool = True, uefi: bool = True
    ) -> None:
        self.tmp = tmp
        self.bins = tmp / "bins"
        self.bins.mkdir()
        self.calls_file = tmp / "calls.txt"
        self.state = tmp / "state"
        self.state.mkdir()
        etc = tmp / "etc"
        self.esp = tmp / "boot"
        self.esp.mkdir()
        self.limine = etc / "default" / "limine"
        self.limine.parent.mkdir(parents=True)
        self.limine_file = f'ESP_PATH="{self.esp}"\n\n{LIMINE_LINE}\n'
        self.limine.write_text(self.limine_file)
        self.entry_conf = etc / "limine-entry-tool.conf"
        self.entry_conf.write_text("ENABLE_VERIFICATION=yes\nENABLE_UKI=no\n")
        self.conf_d = etc / "limine-entry-tool.d"
        self.conf_d.mkdir()
        (self.conf_d / "omarchy-defaults.conf").write_text(
            'TARGET_OS_NAME="Omarchy"\n\nKERNEL_CMDLINE[default]+=" quiet splash loglevel=0"\n\n'
            'CUSTOM_UKI_NAME="omarchy"\nENABLE_LIMINE_FALLBACK=yes\n'
        )
        if uki:
            (self.conf_d / "omarchy-uki.conf").write_text("ENABLE_UKI=yes\n")
        self.usr_d = tmp / "usr" / "share" / "limine-entry-tool.d"  # absent, as on 1.37.1
        self.mkinitcpio_d = etc / "mkinitcpio.conf.d"
        self.mkinitcpio_d.mkdir()
        (self.mkinitcpio_d / "omarchy_hooks.conf").write_text(f"HOOKS=({OMARCHY_HOOKS})\n")
        (self.mkinitcpio_d / "omarchy_resume.conf").write_text("HOOKS+=(resume)\n")
        self.vconsole = etc / "vconsole.conf"
        self.vconsole.write_text(VCONSOLE)
        self.machine_id = etc / "machine-id"
        self.machine_id.write_text(f"{MACHINE_ID}\n")
        self.modules = tmp / "usr" / "lib" / "modules"
        self.add_kernel(KERNEL_VERSION, "linux")
        self.efi_dir = tmp / "sys-firmware-efi"
        if uefi:
            self.efi_dir.mkdir()
        self.initcpio_install = tmp / "initcpio-install"
        self.initcpio_install.mkdir()
        if sd_overlay:
            (self.initcpio_install / "sd-btrfs-overlayfs").write_text("#!/bin/bash\n")
        self.lsblk = LSBLK_STOCK
        self.tokens = TOKEN_LINE
        self.snapshot_rc = 0
        self.limine_update = "ok"
        self.boot_images = [self.image_path("linux", uki=uki and uefi)]
        for name, body in STUBS.items():
            fake = self.bins / name
            fake.write_text(RECORD.format(name=name) + body)
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def add_kernel(self, version: str, pkgbase: str) -> None:
        d = self.modules / version
        d.mkdir(parents=True)
        (d / "pkgbase").write_text(f"{pkgbase}\n")
        (d / "vmlinuz").write_bytes(b"")

    def image_path(self, name: str, *, uki: bool = True) -> Path:
        """Where limine-mkinitcpio-install puts the image (limine-entry-tool README)."""
        if uki:
            return self.esp / "EFI" / "Linux" / f"omarchy_{name}.efi"
        return self.esp / MACHINE_ID / name / "initramfs"

    def write_stale_image(self, path: Path | None = None, *, age: int = 3600) -> Path:
        """An image from an earlier build: present, but older than any run."""
        path = path or self.boot_images[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")
        then = time.time() - age
        os.utime(path, (then, then))
        return path

    def set_limine_line(self, line: str) -> None:
        self.limine_file = f'ESP_PATH="{self.esp}"\n\n{line}\n'
        self.limine.write_text(self.limine_file)

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
            "_HYPRCONF_LIMINE_ENTRY_CONF": str(self.entry_conf),
            "_HYPRCONF_LIMINE_CONF_D": str(self.conf_d),
            "_HYPRCONF_LIMINE_USR_D": str(self.usr_d),
            "_HYPRCONF_MKINITCPIO_D": str(self.mkinitcpio_d),
            "_HYPRCONF_FIDO2_DROPIN": "zz-hyprconf-fido2.conf",
            "_HYPRCONF_INITCPIO_INSTALL": str(self.initcpio_install),
            "_HYPRCONF_VCONSOLE": str(self.vconsole),
            "_HYPRCONF_MACHINE_ID": str(self.machine_id),
            "_HYPRCONF_MODULES_DIR": str(self.modules),
            "_HYPRCONF_EFI_DIR": str(self.efi_dir),
            "FAKE_CALLS": str(self.calls_file),
            "FAKE_STATE": str(self.state),
            "FAKE_LSBLK": self.lsblk,
            "FAKE_TOKENS": self.tokens,
            "FAKE_SNAPSHOT_RC": str(self.snapshot_rc),
            "FAKE_LIMINE_UPDATE": self.limine_update,
            "FAKE_BOOT_IMAGES": "\n".join(str(p) for p in self.boot_images),
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


def _assert_untouched(box: Box, *, allow: tuple[str, ...] = ()) -> None:
    """No system change of any kind — the package install included."""
    calls = box.calls()
    for name in (
        "omarchy-pkg-add",
        "systemd-cryptenroll",
        "limine-update",
        "mkinitcpio",
        "omarchy-snapshot",
    ):
        if name in allow:
            continue
        assert not any(c.startswith(name) for c in calls), f"{name} ran: {calls}"
    assert not box.dropin.exists()
    assert box.limine.read_text() == box.limine_file
    assert box.backups() == []
    assert not box.enrolled


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


# ---------------------------------------------------------------------------
# enroll
# ---------------------------------------------------------------------------


def test_enroll_happy_path(tmp_path: Path) -> None:
    box = Box(tmp_path)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr + res.stdout
    calls = box.calls()

    # read-only preflight (lsblk) first; libfido2 only after the confirmation;
    # the snapshot BEFORE any other change
    pkg = "omarchy-pkg-add libfido2"
    assert pkg in calls and "fido2-token -L" in calls and "omarchy-snapshot create" in calls
    assert calls.index("lsblk -rno PATH,FSTYPE,FSVER,UUID") < calls.index(pkg)
    enroll = f"systemd-cryptenroll --fido2-device=auto --fido2-with-client-pin=yes {DEV}"
    assert enroll in calls
    assert calls.index(pkg) < calls.index("omarchy-snapshot create") < calls.index(enroll)
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
    assert line.count("cryptdevice=PARTUUID=") == 1
    assert line.count(RD_NAME) == 1 and line.count(RD_OPTS) == 1
    assert line == f'KERNEL_CMDLINE[default]+="{CMDLINE} {ADDED}"'
    assert box.limine.read_text().startswith(f'ESP_PATH="{box.esp}"\n\n')

    # backup before the first edit, Omarchy's .bak.<epoch> convention
    backups = box.backups()
    assert len(backups) == 1 and re.fullmatch(r"limine\.bak\.\d+", backups[0].name)
    assert backups[0].read_text() == box.limine_file

    # the UKI limine-update wrote (Omarchy: ENABLE_UKI=yes, CUSTOM_UKI_NAME=omarchy)
    # was looked up on the ESP, as root, and found fresh — only then "Done"
    image = box.image_path("linux")
    assert image.is_file()
    assert f"sudo -- stat -c %Y -- {image}" in calls
    assert f"{image}: rebuilt" in res.stdout
    assert "Boot images verified" in res.stdout
    assert "Done." in res.stdout and "passphrase" in res.stdout.lower()
    assert res.stdout.index("verified") < res.stdout.index("Done.")


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
    """libfido2 (which fido2-token comes from) is the one install before the
    token check; everything else stays untouched."""
    box = Box(tmp_path)
    box.tokens = ""
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "fido2-token" in res.stderr
    assert set(box.calls()) <= {
        "lsblk -rno PATH,FSTYPE,FSVER,UUID",
        "omarchy-pkg-add libfido2",
        "fido2-token -L",
    }
    _assert_untouched(box, allow=("omarchy-pkg-add",))


def test_enroll_refuses_without_tty_or_yes(tmp_path: Path) -> None:
    """Without a terminal and without --yes the run dies at the confirmation —
    and NOTHING ran before it, omarchy-pkg-add included."""
    box = Box(tmp_path)
    res = box.run("enroll", "--device", DEV)
    assert res.returncode != 0
    assert "--yes" in res.stderr
    assert box.calls() == ["lsblk -rno PATH,FSTYPE,FSVER,UUID"]
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
    _assert_untouched(box, allow=("omarchy-snapshot", "omarchy-pkg-add"))

    box.snapshot_rc = 127  # omarchy-snapshot: snapper not installed
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "snapper" in res.stderr and box.enrolled


# ---------------------------------------------------------------------------
# The cmdline edit: every line shape, the exact line after enroll and disable
# ---------------------------------------------------------------------------

CRYPT = "cryptdevice=UUID=x:root root=/dev/mapper/root rw"
CMDLINE_SHAPES = [
    pytest.param(
        LIMINE_LINE,
        f'KERNEL_CMDLINE[default]+="{CMDLINE} {ADDED}"',
        id="quoted-stock",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="cryptdevice=PARTUUID=a:root root=/dev/mapper/root rd.luks.options={UUID}=discard rw"',
        f'KERNEL_CMDLINE[default]+="cryptdevice=PARTUUID=a:root root=/dev/mapper/root rd.luks.options={UUID}=discard,fido2-device=auto rw {RD_NAME}"',
        id="options-for-same-uuid-gain-fido2-once",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID2}=data rd.luks.options={UUID2}=discard"',
        f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID2}=data rd.luks.options={UUID2}=discard {ADDED}"',
        id="rd.luks-of-another-uuid-survives",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+={CRYPT} acpi_osi="Windows 2015" video=efifb:off',
        f'KERNEL_CMDLINE[default]+={CRYPT} acpi_osi="Windows 2015" video=efifb:off {ADDED}',
        id="bare-with-inner-quoted-parameter",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT}"   # keep me',
        f'KERNEL_CMDLINE[default]+="{CRYPT} {ADDED}"   # keep me',
        id="quoted-then-trailing-comment",
    ),
    pytest.param(
        f"KERNEL_CMDLINE[default]+='{CRYPT}'",
        f"KERNEL_CMDLINE[default]+='{CRYPT} {ADDED}'",
        id="single-quoted",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]="{CRYPT}"',
        f'KERNEL_CMDLINE[default]="{CRYPT} {ADDED}"',
        id="plain-assignment",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT}"',
        f'KERNEL_CMDLINE[default]+="{CRYPT} {ADDED}"',
        id="append-assignment",
    ),
    pytest.param(
        'KERNEL_CMDLINE[default]+=" cryptdevice=UUID=x:root rw "',
        f'KERNEL_CMDLINE[default]+=" cryptdevice=UUID=x:root rw {ADDED} "',
        id="blanks-inside-quotes-kept",
    ),
    pytest.param(
        "KERNEL_CMDLINE[default]+=cryptdevice=UUID=x:cryptroot root=/dev/mapper/cryptroot rw",
        f"KERNEL_CMDLINE[default]+=cryptdevice=UUID=x:cryptroot root=/dev/mapper/cryptroot rw rd.luks.name={UUID}=cryptroot {RD_OPTS}",
        id="bare-mapper-name-from-cryptdevice",
    ),
    pytest.param(
        'KERNEL_CMDLINE[default]+="root=/dev/mapper/vault rw"',
        f'KERNEL_CMDLINE[default]+="root=/dev/mapper/vault rw rd.luks.name={UUID}=vault {RD_OPTS}"',
        id="mapper-name-from-root-alone",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT} {ADDED}"',
        f'KERNEL_CMDLINE[default]+="{CRYPT} {ADDED}"',
        id="already-configured-unchanged",
    ),
]


@pytest.mark.parametrize(("line", "after_enroll"), CMDLINE_SHAPES)
def test_cmdline_edit_shapes(tmp_path: Path, line: str, after_enroll: str) -> None:
    box = Box(tmp_path)
    box.set_limine_line(line)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert box.limine_line() == after_enroll
    assert box.limine.read_text() == f'ESP_PATH="{box.esp}"\n\n{after_enroll}\n'

    # disable takes back exactly what enroll put there (or would have): the
    # fido2-device option and the rd.luks.name of the device that carried it
    res = box.run("disable", "--yes", "--no-snapshot")
    assert res.returncode == 0, res.stderr
    stripped = line
    for added in (f" {ADDED}", ",fido2-device=auto", f" {RD_NAME}"):
        stripped = stripped.replace(added, "")
    assert box.limine_line() == stripped
    assert box.limine.read_text() == f'ESP_PATH="{box.esp}"\n\n{stripped}\n'


REFUSED_LINES = [
    pytest.param(
        'KERNEL_CMDLINE[default]+="cryptdevice=UUID=x:root root=/dev/mapper/cryptroot rw"',
        "root=/dev/mapper/cryptroot",
        id="cryptdevice-and-root-disagree",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID}=other"',
        f"rd.luks.name={UUID}=other",
        id="rd.luks.name-for-uuid-names-another-mapper",
    ),
    pytest.param(
        'KERNEL_CMDLINE[default]+="root=UUID=y rw"',
        "cannot tell",
        id="no-cryptdevice-no-mapper-root",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT} acpi_osi="Linux" quiet"',
        "with certainty",
        id="quoted-with-more-quotes-inside",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT}" quiet',
        "with certainty",
        id="parameters-after-the-closing-quote",
    ),
    pytest.param(
        f"KERNEL_CMDLINE[default]+={CRYPT} # comment",
        "with certainty",
        id="bare-with-hash",
    ),
    pytest.param(
        f'#KERNEL_CMDLINE[default]+="{CRYPT}"',
        "no KERNEL_CMDLINE[default] line",
        id="only-a-commented-line",
    ),
]


@pytest.mark.parametrize(("line", "reason"), REFUSED_LINES)
def test_cmdline_edit_refuses_before_anything_changes(
    tmp_path: Path, line: str, reason: str
) -> None:
    """A line the tool cannot rewrite with certainty stops enroll (and disable,
    remove) before the confirmation: no package, slot, drop-in, backup."""
    box = Box(tmp_path)
    box.set_limine_line(line)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert reason in res.stderr, res.stderr
    assert box.calls() == ["lsblk -rno PATH,FSTYPE,FSVER,UUID"]
    _assert_untouched(box)


def test_mapper_name_comes_from_the_edited_line_only(tmp_path: Path) -> None:
    """Not from a commented line, another entry's line, or an earlier default
    line without cryptdevice= — those stay byte-identical too."""
    box = Box(tmp_path)
    others = (
        '#KERNEL_CMDLINE[default]+="cryptdevice=PARTUUID=old:old root=/dev/mapper/old rw"\n'
        'KERNEL_CMDLINE[linux-lts]+="cryptdevice=PARTUUID=lts:lts root=/dev/mapper/lts rw"\n'
        'KERNEL_CMDLINE[default]="quiet splash"\n'
    )
    mine = (
        'KERNEL_CMDLINE[default]+="cryptdevice=PARTUUID=a:cryptroot root=/dev/mapper/cryptroot rw"'
    )
    box.limine_file = f'ESP_PATH="{box.esp}"\n{others}{mine}\n'
    box.limine.write_text(box.limine_file)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert box.limine.read_text() == (
        f'ESP_PATH="{box.esp}"\n{others}'
        f'KERNEL_CMDLINE[default]+="cryptdevice=PARTUUID=a:cryptroot root=/dev/mapper/cryptroot rw'
        f' rd.luks.name={UUID}=cryptroot {RD_OPTS}"\n'
    )


def test_disable_and_remove_parse_the_cmdline_before_changing_anything(tmp_path: Path) -> None:
    box = Box(tmp_path)
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    box.limine.write_text(box.limine.read_text().replace(" rw ", ' acpi_osi="Linux" rw ', 1))
    corrupted = box.limine.read_text()
    box.reset_calls()

    res = box.run("disable", "--yes")
    assert res.returncode != 0 and "with certainty" in res.stderr
    assert box.dropin.exists() and box.calls() == []

    res = box.run("remove", "--yes", "--device", DEV)
    assert res.returncode != 0 and "with certainty" in res.stderr
    assert box.enrolled and box.dropin.exists()
    assert not any(c.startswith("systemd-cryptenroll") for c in box.calls())
    assert box.limine.read_text() == corrupted


# ---------------------------------------------------------------------------
# The rebuild: limine-update exits 0 whatever mkinitcpio did
# ---------------------------------------------------------------------------


def test_rebuild_dies_on_limine_updates_failure_message(tmp_path: Path) -> None:
    """The exact error_msg limine-mkinitcpio-install prints, on stderr, with
    limine-update still exiting 0 — the previous image stays and still boots."""
    box = Box(tmp_path)
    box.write_stale_image()
    box.limine_update = "fail"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert BUILD_FAILED in res.stderr, "limine-update's output is shown"
    assert "previous one and still boots" in res.stderr
    assert "sudo limine-update" in res.stderr
    assert "Done." not in res.stdout and "verified" not in res.stdout
    # the config changes are in place — that is what the retry rebuilds
    assert box.dropin.exists() and RD_OPTS in box.limine_line()


def test_rebuild_dies_on_limine_update_exit_code(tmp_path: Path) -> None:
    box = Box(tmp_path)
    box.limine_update = "exit1"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "limine-update exited 1" in res.stderr and "sudo limine-update" in res.stderr
    assert "Done." not in res.stdout


def test_rebuild_dies_when_the_image_was_not_rewritten_after_a_hook_change(tmp_path: Path) -> None:
    """Exit 0, no message, but the UKI on the ESP predates the run although the
    drop-in changed the hook set: not a rebuild."""
    box = Box(tmp_path)
    image = box.write_stale_image()
    box.limine_update = "stale"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert f"{image} predates this run" in res.stderr
    assert "still boots" in res.stderr and "sudo limine-update" in res.stderr
    assert "Done." not in res.stdout

    # disable removes the drop-in, so the image must change again
    box.limine_update = "ok"
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    box.write_stale_image()
    box.limine_update = "stale"
    res = box.run("disable", "--yes", "--no-snapshot")
    assert res.returncode != 0 and "predates this run" in res.stderr


def test_rebuild_accepts_an_identical_unrewritten_image_when_hooks_did_not_change(
    tmp_path: Path,
) -> None:
    """mkinitcpio builds reproducibly and limine-entry-tool skips an identical
    image, so a re-run that changed nothing may find the old mtime."""
    box = Box(tmp_path)
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    image = box.write_stale_image()
    box.limine_update = "stale"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert f"{image}: unchanged" in res.stdout and "Done." in res.stdout


def test_rebuild_dies_when_no_image_is_where_limine_puts_it(tmp_path: Path) -> None:
    box = Box(tmp_path)
    box.boot_images = [box.esp / "somewhere" / "else.efi"]
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert f"no boot image at {box.image_path('linux')}" in res.stderr
    assert f"ESP_PATH={box.esp}" in res.stderr and "ENABLE_UKI=yes" in res.stderr


def test_rebuild_checks_every_installed_kernel(tmp_path: Path) -> None:
    box = Box(tmp_path)
    box.add_kernel("6.18.9-1-lts", "linux-lts")
    leftover = box.modules / "6.0.0-old"  # modules dir without pkgbase/vmlinuz: skipped
    leftover.mkdir()
    (leftover / "extramodules").mkdir()
    lts = box.image_path("linux-lts")
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and f"no boot image at {lts}" in res.stderr

    box.boot_images.append(lts)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert f"{lts}: rebuilt" in res.stdout and f"{box.image_path('linux')}: rebuilt" in res.stdout


@pytest.mark.parametrize(
    ("uki", "uefi"),
    [pytest.param(False, True, id="ENABLE_UKI=no"), pytest.param(True, False, id="no-UEFI")],
)
def test_rebuild_looks_for_the_initramfs_without_uki(tmp_path: Path, uki: bool, uefi: bool) -> None:
    """ENABLE_UKI=no (the packaged /etc/limine-entry-tool.conf, no omarchy-uki.conf),
    or ENABLE_UKI=yes on a non-UEFI box: <ESP>/<machine-id>/<kernel>/initramfs."""
    box = Box(tmp_path, uki=uki, uefi=uefi)
    initramfs = box.image_path("linux", uki=False)
    assert box.boot_images == [initramfs]
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert f"{initramfs}: rebuilt" in res.stdout
    assert f"sudo -- stat -c %Y -- {initramfs}" in box.calls()


def test_rebuild_uki_prefix_falls_back_to_machine_id(tmp_path: Path) -> None:
    """CUSTOM_UKI_NAME must match ^[a-z0-9]+$ (limine-mkinitcpio-install
    resolve_uki_prefix), else the machine-id names the UKI."""
    box = Box(tmp_path)
    defaults = box.conf_d / "omarchy-defaults.conf"
    defaults.write_text(
        defaults.read_text().replace('CUSTOM_UKI_NAME="omarchy"', 'CUSTOM_UKI_NAME="Om archy"')
    )
    image = box.esp / "EFI" / "Linux" / f"{MACHINE_ID}_linux.efi"
    box.boot_images = [image]
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert f"{image}: rebuilt" in res.stdout


def test_rebuild_without_esp_path_warns_and_relies_on_the_message(tmp_path: Path) -> None:
    box = Box(tmp_path)
    box.limine_file = f"{LIMINE_LINE}\n"
    box.limine.write_text(box.limine_file)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "ESP_PATH" in res.stderr and "not double-checked" in res.stderr
    assert "Done." in res.stdout

    box.limine_update = "fail"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "still boots" in res.stderr


# ---------------------------------------------------------------------------
# The keyboard-layout guard Omarchy's omarchy_hooks.conf has and sd-vconsole lacks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("layout", NON_LATIN)
def test_enroll_refuses_non_latin_first_layout(tmp_path: Path, layout: str) -> None:
    box = Box(tmp_path)
    box.vconsole.write_text(f'KEYMAP=us\nXKBLAYOUT="{layout},us"\n')
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert layout in res.stderr and "--allow-non-latin-layout" in res.stderr
    assert box.calls() == [], "refused before the device pick, the install, anything"
    _assert_untouched(box)


def test_enroll_allow_non_latin_layout_flag_warns_and_proceeds(tmp_path: Path) -> None:
    box = Box(tmp_path)
    box.vconsole.write_text("KEYMAP=ru\nXKBLAYOUT=ru\n")
    res = box.run("enroll", "--yes", "--device", DEV, "--allow-non-latin-layout")
    assert res.returncode == 0, res.stderr
    assert "warning" in res.stderr and "ru" in res.stderr and "passphrase" in res.stderr
    assert box.enrolled and box.dropin.exists()


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("KEYMAP=us\nXKBLAYOUT=us,ru\n", id="latin-first"),
        pytest.param("KEYMAP=de\nXKBLAYOUT='de'\n", id="single-quoted-latin"),
        pytest.param("XKBLAYOUT=ru\nXKBLAYOUT=us\n", id="last-assignment-wins"),
        pytest.param("KEYMAP=us\n", id="no-XKBLAYOUT"),
        pytest.param(None, id="no-vconsole.conf"),
    ],
)
def test_enroll_accepts_latin_or_absent_layout(tmp_path: Path, content: str | None) -> None:
    box = Box(tmp_path)
    if content is None:
        box.vconsole.unlink()
    else:
        box.vconsole.write_text(content)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "warning" not in res.stderr


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
    """The drop-in is generated, so this is the only shellcheck it gets (the
    tool itself is covered by `make shellcheck`)."""
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
    assert box.limine.read_text() == box.limine_file
    assert len(box.backups()) == 2, "backup before the disable edit too"
    assert "omarchy-snapshot create" in calls
    assert "limine-update" in calls
    assert "Boot images verified" in res.stdout
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
    assert box.limine.read_text() == box.limine_file and box.backups() == []


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


def test_help_documents_flags_limitations_and_revert(tmp_path: Path) -> None:
    box = Box(tmp_path)
    res = box.run("help")
    assert res.returncode == 0
    out = res.stdout
    for sub in ("status", "enroll", "disable", "remove", "sudo", "help"):
        assert re.search(rf"^(usage:)?\s+hyprconf-yubikey {sub}\b", out, re.M), sub
    for flag in ("--device", "--yes", "--no-snapshot", "--allow-non-latin-layout"):
        assert flag in out
    assert "snapshot" in out and "sd-btrfs-overlayfs" in out
    assert "XKBLAYOUT" in out and "omarchy_hooks.conf" in out, "the layout limitation"
    assert "mkinitcpio failed for kernel" in out and "exits 0" in out, "the rebuild check"
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
