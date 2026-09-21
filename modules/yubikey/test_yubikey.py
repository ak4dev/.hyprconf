"""modules/yubikey — the install link, and bin/hyprconf-yubikey itself.
The tool enrols a key into the LUKS header and rebuilds the boot images, so every
external is a recording stub (the root conftest.py `box`) and every system path a seam.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import SUDO_RUNS, Box

# The tool reads the LUKS header as JSON with jq (Omarchy's base ships it).
pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
TOOL = MODULE / "bin" / "hyprconf-yubikey"

# Omarchy 4.0.0's /etc/mkinitcpio.conf.d/omarchy_hooks.conf, verbatim; its
# omarchy_resume.conf then appends resume. Unchanged in 4.0.3-1.
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
RD_OPTS = f"rd.luks.options={UUID}=fido2-device=auto,token-timeout=0"
# what 8.1.2 and earlier wrote: the passphrase after 30 s
RD_OPTS_OLD = f"rd.luks.options={UUID}=fido2-device=auto"
DROPIN_NAME = "zz-hyprconf-fido2.conf"
# The proof the passphrase wipe stands on: the FIDO2 token alone (--token-only on its own
# would accept any PIN-less token in the header).
TOKEN_PROOF = f"cryptsetup open --test-passphrase --token-only --token-type systemd-fido2 {DEV}"
TOKEN_LINE = "/dev/hidraw3: vendor=0x1050, product=0x0407 (Yubico YubiKey OTP+FIDO+CCID)"
KERNEL_VERSION = "7.1.8-arch1-3"
# /etc/vconsole.conf as systemd-localed writes it on a stock Omarchy
VCONSOLE = "KEYMAP=us\nXKBLAYOUT=us\nXKBMODEL=pc105+inet\nXKBOPTIONS=terminate:ctrl_alt_bksp\n"
# The first-layout list Omarchy's guard withholds vconsole.conf for, copied verbatim
# (/etc/mkinitcpio.conf.d/omarchy_hooks.conf; its second copy is default/hypr/input.lua:24-27).
NON_LATIN = "af am ara bd bg by et ge gr il in iq ir kg kh kz la lk mk mm mn mv np rs ru sy th tj ua".split()
# What limine-mkinitcpio-install prints (error_msg) when a build fails, verbatim, and the
# silent skip at :104 — no build message, and the image on the ESP stays the old one.
BUILD_FAILED = f"ERROR: mkinitcpio failed for kernel {KERNEL_VERSION}, skipping."
KERNEL_SKIPPED = f"ERROR: kernel name of '/usr/lib/modules/{KERNEL_VERSION}' is empty, skipping."
# Hardcoded in the shipped drop-in (root sources it at every rebuild, so it carries no
# test seam); _source_dropin swaps it out.
INITCPIO_INSTALL = "/usr/lib/initcpio/install"

# `lsblk -rno PATH,FSTYPE,FSVER,UUID`: raw, one space per separator, empty fields empty.
LSBLK_STOCK = (
    "/dev/nvme0n1   \n"
    "/dev/nvme0n1p1 vfat FAT32 1234-ABCD\n"
    f"{DEV} crypto_LUKS 2 {UUID}\n"
    f"/dev/mapper/root btrfs  {UUID2}\n"
)

# The bodies this tool's externals need over the box's recording stubs. limine-update is
# deliberately absent: the rebuild is limine-mkinitcpio, so a call to it finds no fake
# and test_every_external_the_tool_calls_has_a_fake turns red.
STUBS = {
    "sudo": SUDO_RUNS,
    # two shapes: the LUKS listing, and the picked device's own tree (NAME,TYPE),
    # where the `crypt` child it is open under shows up
    "lsblk": (
        'case " $* " in\n'
        '  *" NAME,TYPE "*) printf \'%s\\n\' "$FAKE_LSBLK_CRYPT" ;;\n'
        "  *) printf '%s\\n' \"$FAKE_LSBLK\" ;;\n"
        "esac\nexit 0\n"
    ),
    "findmnt": "printf '%s\\n' \"$FAKE_ROOT_SOURCE\"\nexit 0\n",
    # the header as --dump-json-metadata prints it, built from the box's slot files:
    # keyslot 0 the passphrase, 1 the FIDO2 key, 2 the recovery key; `open
    # --test-passphrase` answers per FAKE_TOKEN_OPEN_RC (--token-only) and
    # FAKE_RECOVERY_OPEN_RC (--key-slot=, the recovery key typed back)
    "cryptsetup": (
        "if [[ $1 == luksDump ]]; then\n"
        "  [[ $2 == --dump-json-metadata ]] || exit 2\n"
        "  [[ -n ${FAKE_LUKSDUMP_FAILS:-} ]] && exit 1\n"
        "  ks=() tok=()\n"
        "  [[ -e $FAKE_STATE/password-slot ]] && ks+=('\"0\":{}')\n"
        '  [[ -e $FAKE_STATE/fido2-slot ]] && ks+=(\'"1":{}\') tok+=(\'"0":{"type":"systemd-fido2","keyslots":["1"]}\')\n'
        '  [[ -e $FAKE_STATE/recovery-slot ]] && ks+=(\'"2":{}\') tok+=(\'"1":{"type":"systemd-recovery","keyslots":["2"]}\')\n'
        '  (IFS=,; printf \'{"keyslots":{%s},"tokens":{%s}}\\n\' "${ks[*]}" "${tok[*]}")\n'
        "  exit 0\n"
        "fi\n"
        'case " $* " in\n'
        '  *" --token-only "*) exit "${FAKE_TOKEN_OPEN_RC:-0}" ;;\n'
        '  *" --key-slot=2 "*) [[ -e $FAKE_STATE/recovery-slot ]] || exit 1; exit "${FAKE_RECOVERY_OPEN_RC:-0}" ;;\n'
        '  *" --key-slot="*) exit 1 ;;\n'
        "esac\nexit 0\n"
    ),
    "systemd-cryptenroll": (
        'case " $* " in\n  *" --wipe-slot=fido2 "*) rm -f "$FAKE_STATE/fido2-slot" ;;\n'
        '  *" --wipe-slot=password "*) rm -f "$FAKE_STATE/password-slot" ;;\n'
        '  *" --recovery-key "*) touch "$FAKE_STATE/recovery-slot" ;;\n'
        '  *" --password "*) touch "$FAKE_STATE/password-slot" ;;\n'
        '  *" --fido2-device=auto "*) touch "$FAKE_STATE/fido2-slot" ;;\nesac\nexit 0\n'
    ),
    "mkinitcpio": "exit 0\n",
    # limine-mkinitcpio exits 0 whatever mkinitcpio did (`|| true` in
    # limine-mkinitcpio-install): "fail" is that case, "exit1" the one that exits 1
    "limine-mkinitcpio": (
        "case ${FAKE_LIMINE_MKINITCPIO:-ok} in\n"
        f'  ok) echo "Building UKI for linux ({KERNEL_VERSION})" ;;\n'
        f'  fail) echo "Building UKI for linux ({KERNEL_VERSION})"; echo "{BUILD_FAILED}" >&2 ;;\n'
        f'  skipped) echo "{KERNEL_SKIPPED}" >&2 ;;\n'
        '  exit1) echo "ERROR: FAT32 boot partition not found." >&2; exit 1 ;;\n'
        "esac\nexit 0\n"
    ),
    # the cmdline limine assembles out of its four config layers: /etc/default/limine
    # first, the drop-ins after it, a plain `=` there replacing them all
    # (/etc/limine-entry-tool.conf:38-43). FAKE_BASE_CMDLINE replaces that first layer,
    # FAKE_CMDLINE_FROZEN and FAKE_CMDLINE_SILENT the whole answer.
    "limine-entry-tool": (
        "[[ ${1:-} == --get-cmdline ]] || exit 2\n"
        "[[ -n ${FAKE_CMDLINE_SILENT:-} ]] && exit 0\n"
        "if [[ -n ${FAKE_CMDLINE_FROZEN-} ]]; then printf '%s\\n' \"$FAKE_CMDLINE_FROZEN\"; exit 0; fi\n"
        'out="" plain=""\n'
        'files=("$_HYPRCONF_LIMINE_DEFAULT" "$_HYPRCONF_LIMINE_CONF_D"/*.conf)\n'
        "if [[ -n ${FAKE_BASE_CMDLINE-} ]]; then\n"
        '  out=" $FAKE_BASE_CMDLINE"; files=("$_HYPRCONF_LIMINE_CONF_D"/*.conf)\n'
        "fi\n"
        'for f in "${files[@]}"; do\n'
        "  [[ -f $f ]] || continue\n"
        "  while IFS= read -r v; do\n"
        "    case $v in\n"
        '      +=*) out+=" ${v#+=}" ;;\n'
        "      =*) plain=${v#=} ;;\n"
        "    esac\n"
        "  done \\\n"
        '    < <(sed -n \'s/^[[:space:]]*KERNEL_CMDLINE\\[default\\]\\([+]\\?=\\)/\\1/p\' "$f" | tr -d "\\"\'")\n'
        "done\n"
        "printf '%s\\n' \"${plain:-${out# }}\"\nexit 0\n"
    ),
    "omarchy-pkg-add": "exit 0\n",
    "omarchy-snapshot": 'exit "${FAKE_SNAPSHOT_RC:-0}"\n',
    "fido2-token": "[[ $1 == -L && -n ${FAKE_TOKENS:-} ]] && printf '%s\\n' \"$FAKE_TOKENS\"\nexit 0\n",
    "omarchy-setup-security-fido2": 'echo "OMARCHY FIDO2 SETUP"\nexit 0\n',
}


def dropin_for(mapper: str) -> str:
    """The limine drop-in enroll writes, exactly (omarchy-hibernation-setup:138)."""
    return f'KERNEL_CMDLINE[default]+=" rd.luks.name={UUID}={mapper} {RD_OPTS}"\n'


LIMINE_DROPIN = dropin_for("root")


@pytest.fixture
def box(box: Box) -> Box:
    """A throwaway Omarchy in its stock 4.0.0 shape (unchanged in 4.0.3-1), every path behind the tool's own _HYPRCONF_* seam."""
    box.state = box.tmp / "state"
    box.state.mkdir()
    (box.state / "password-slot").touch()  # a stock Omarchy install: the passphrase alone
    box.limine = box.etc / "default" / "limine"
    box.limine.parent.mkdir(parents=True)
    set_limine_line(box, LIMINE_LINE)
    box.conf_d = box.etc / "limine-entry-tool.d"
    box.conf_d.mkdir()
    (box.conf_d / "omarchy-defaults.conf").write_text(
        'TARGET_OS_NAME="Omarchy"\n\nKERNEL_CMDLINE[default]+=" quiet splash loglevel=0"\n'
    )
    (box.conf_d / "resume.conf").write_text(
        'KERNEL_CMDLINE[default]+=" resume=/dev/mapper/root resume_offset=1234567"\n'
    )
    box.omarchy_conf_d = sorted(p.name for p in box.conf_d.iterdir())
    box.mkinitcpio_d = box.etc / "mkinitcpio.conf.d"
    box.mkinitcpio_d.mkdir()
    (box.mkinitcpio_d / "omarchy_hooks.conf").write_text(f"HOOKS=({OMARCHY_HOOKS})\n")
    (box.mkinitcpio_d / "omarchy_resume.conf").write_text("HOOKS+=(resume)\n")
    box.dropin = box.mkinitcpio_d / DROPIN_NAME
    box.limine_dropin = box.conf_d / DROPIN_NAME
    box.vconsole = box.etc / "vconsole.conf"
    box.vconsole.write_text(VCONSOLE)
    box.initcpio_install = box.tmp / "initcpio-install"
    box.initcpio_install.mkdir()
    (box.initcpio_install / "sd-btrfs-overlayfs").write_text("#!/bin/bash\n")
    box.lsblk, box.tokens, box.snapshot_rc, box.limine_mkinitcpio = LSBLK_STOCK, TOKEN_LINE, 0, "ok"
    box.crypt_child = "root"  # `lsblk -rno NAME,TYPE <dev>`: what DEV is open as
    box.root_source = "/dev/mapper/root"  # `findmnt -no SOURCE --nofsroot /`
    # base: the /etc/default/limine layer (empty = assembled from the box's own files);
    # frozen/silent: limine's whole answer, which nothing written can then move
    box.base_cmdline = box.frozen_cmdline = box.cmdline_silent = ""
    box.token_open_rc = box.recovery_open_rc = 0
    box.env.update(
        {
            "_HYPRCONF_LIMINE_DEFAULT": str(box.limine),
            "_HYPRCONF_LIMINE_CONF_D": str(box.conf_d),
            "_HYPRCONF_MKINITCPIO_D": str(box.mkinitcpio_d),
            "_HYPRCONF_INITCPIO_INSTALL": str(box.initcpio_install),
            "_HYPRCONF_VCONSOLE": str(box.vconsole),
            "FAKE_STATE": str(box.state),
        }
    )
    for name, body in STUBS.items():
        box.stub(name, body)
    return box


def run(
    box: Box, *args: str, stdin_text: str | None = None, assume_tty: bool = False
) -> subprocess.CompletedProcess:
    """The tool against the box; the knobs are read here, so a test may set them late."""
    box.env.update(
        FAKE_LSBLK=box.lsblk,
        FAKE_LSBLK_CRYPT=f"nvme0n1p2 part\n{box.crypt_child} crypt" if box.crypt_child else "",
        FAKE_ROOT_SOURCE=box.root_source,
        FAKE_TOKENS=box.tokens,
        FAKE_SNAPSHOT_RC=str(box.snapshot_rc),
        FAKE_LIMINE_MKINITCPIO=box.limine_mkinitcpio,
        FAKE_BASE_CMDLINE=box.base_cmdline,
        FAKE_CMDLINE_FROZEN=box.frozen_cmdline,
        FAKE_CMDLINE_SILENT=box.cmdline_silent,
        FAKE_TOKEN_OPEN_RC=str(box.token_open_rc),
        FAKE_RECOVERY_OPEN_RC=str(box.recovery_open_rc),
    )
    return box.run(TOOL, *args, tty=assume_tty, stdin=stdin_text)


def set_limine_line(box: Box, line: str) -> None:
    box.limine_file = f'ESP_PATH="/boot"\n\n{line}\n'
    box.limine.write_text(box.limine_file)


def slots(box: Box) -> set[str]:
    """The fake header's keyslots by kind: password, fido2, recovery."""
    return {p.name.removesuffix("-slot") for p in box.state.glob("*-slot")}


def unpadded(text: str) -> str:
    """Status pads its labels into columns: match on what it says, not on the gap."""
    return re.sub(r"[ \t]{2,}", " ", text)


MUTATORS = {"omarchy-pkg-add", "systemd-cryptenroll", "limine-mkinitcpio",
            "mkinitcpio", "omarchy-snapshot"}  # fmt: skip


def assert_order(calls: list[str], *steps: str) -> None:
    """Each step ran, in this order (substring match on the recorded call lines)."""
    seen = []
    for step in steps:
        hit = [i for i, c in enumerate(calls) if step in c]
        assert hit, f"{step} never ran: {calls}"
        seen.append(hit[0])
    assert seen == sorted(seen), f"out of order: {steps}"


def _assert_untouched(box: Box, *, allow: tuple[str, ...] = ()) -> None:
    """No system change of any kind — the package install included."""
    assert not (MUTATORS - set(allow)) & set(box.commands), box.calls
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert box.limine.read_text() == box.limine_file
    assert slots(box) == {"password"}


def _assert_configured(box: Box, mapper: str = "root") -> None:
    """Both drop-ins as enroll writes them, /etc/default/limine untouched."""
    assert box.dropin.is_file() and box.limine_dropin.read_text() == dropin_for(mapper)
    assert box.limine.read_text() == box.limine_file


def test_install_links_the_tool_and_a_second_run_writes_nothing(box: Box) -> None:
    """~/.local/bin is on the session PATH (default/bash/env-bootstrap:38-39); a re-created link would have a new inode."""
    bin_dir = box.home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "hyprconf-yubikey").write_text("# the copy releases before the module split left")
    (bin_dir / "something-else").write_text("#!/bin/sh\n")
    assert box.run(INSTALL).returncode == 0
    link = bin_dir / "hyprconf-yubikey"
    assert link.is_symlink() and os.readlink(link) == str(TOOL)
    assert (bin_dir / "something-else").read_text() == "#!/bin/sh\n"
    assert box.calls == [], "installing runs no command at all"
    before = box.snapshot()
    assert box.run(INSTALL).returncode == 0
    assert box.snapshot() == before and box.calls == []


def test_undo_removes_the_link_only_and_is_idempotent(box: Box) -> None:
    """Undo reverts no boot config — that is `hyprconf-yubikey remove`, which needs the tool, so undo says so."""
    assert box.run(INSTALL).returncode == 0
    bin_dir = box.home / ".local" / "bin"
    (bin_dir / "something-else").write_text("#!/bin/sh\n")
    res = box.undo("yubikey")
    assert res.returncode == 0, res.stderr
    assert not (bin_dir / "hyprconf-yubikey").exists() and (bin_dir / "something-else").exists()
    assert "remove" in res.stdout and box.calls == []
    res = box.undo("yubikey")  # nothing to do
    assert res.returncode == 0 and box.calls == []


def test_every_external_the_tool_calls_has_a_fake(box: Box) -> None:
    """A new external call fails here before it can reach the real system."""
    code = "\n".join(ln for ln in TOOL.read_text().splitlines() if not ln.lstrip().startswith("#"))
    pattern = (
        r"\b(sudo|lsblk|findmnt|cryptsetup|systemd-cryptenroll|mkinitcpio|limine-mkinitcpio"
        r"|limine-update|limine-entry-tool|fido2-token|omarchy-[a-z0-9-]+)\b"
    )
    called = set(re.findall(pattern, code))
    assert called, "no external calls found — the scan regex is broken"
    assert called <= box.fakes, f"unstubbed externals: {sorted(called - box.fakes)}"


def test_restraint_scan() -> None:
    """Never sbctl, never errexit, never a backup copy; the passphrase wipe has one call site, behind its proofs."""
    text = TOOL.read_text()
    assert text.count("run_root systemd-cryptenroll --wipe-slot=password") == 1
    for forbidden in ("wipe-slot=all", "sbctl", "set -e", ".bak"):
        assert forbidden not in text, f"{forbidden!r} must not appear in hyprconf-yubikey"
    # a value starting with '-' must never become an option to a root coreutils command
    loose = re.findall(r"run_root(?:_quiet)? (?:tee|rm -f|mkdir -p)(?! --)", text)
    assert not loose, f"root write without -- separator: {loose}"


def test_enroll_happy_path(box: Box) -> None:
    res = run(box, "enroll", "--yes")  # one LUKS2 device: no --device needed
    assert res.returncode == 0, res.stderr + res.stdout
    calls = box.calls
    # the read-only preflight and the mapper question first, libfido2 and the snapshot
    # only after the confirmation, then the inert cmdline drop-in before the hooks one
    # (rd.luks.* without the systemd hooks is ignored by the busybox initramfs; the
    # hooks without rd.luks.* make an initramfs that cannot unlock the root), and the
    # rebuild last — limine-mkinitcpio alone, which runs mkinitcpio for every kernel
    # itself (the mkinitcpio on Omarchy's PATH is limine's interactive wrapper)
    assert_order(
        calls,
        "lsblk -rno PATH,FSTYPE,FSVER,UUID",
        "sudo -- limine-entry-tool --get-cmdline default",
        "omarchy-pkg-add libfido2",
        "fido2-token -L",
        "omarchy-snapshot create",
        f"systemd-cryptenroll --fido2-device=auto --fido2-with-client-pin=yes {DEV}",
        # the proofs the wipe stands on: the key opens the volume, a recovery key made
        # with the key, and typed back against its own slot
        TOKEN_PROOF,
        f"systemd-cryptenroll --unlock-fido2-device=auto --recovery-key {DEV}",
        f"cryptsetup open --test-passphrase --key-slot=2 {DEV}",
        f"tee -- {box.limine_dropin}",
        f"tee -- {box.dropin}",
        "limine-mkinitcpio",
        # the passphrase goes last, once the boot images are built
        f"systemd-cryptenroll --wipe-slot=password {DEV}",
    )
    assert slots(box) == {"fido2", "recovery"}, "the key and the recovery key, no passphrase"
    assert not any(c.startswith("mkinitcpio") or "wipe-slot=fido2" in c for c in calls)
    # the hooks drop-in, sorted after Omarchy's own, with the revert path in its header
    assert "hyprconf-yubikey disable" in box.dropin.read_text()
    assert sorted(p.name for p in box.mkinitcpio_d.iterdir())[-1] == box.dropin.name
    # the cmdline through limine-entry-tool's drop-in dir, beside Omarchy's own
    # resume.conf — the exact one line, nothing else, /etc/default/limine never named
    _assert_configured(box)
    assert sorted(p.name for p in box.conf_d.iterdir()) == [*box.omarchy_conf_d, DROPIN_NAME]
    assert f"{box.limine_dropin}: written" in res.stdout
    assert not any(str(box.limine) in c for c in calls), "no root command ever names the file"
    # and the drop-in is read back before the hooks drop-in is written
    assert "the drop-in reaches it" in res.stdout and "Boot images rebuilt" in res.stdout
    assert "Done." in res.stdout and "no passphrase any more" in res.stdout
    assert "WRITE IT DOWN" in res.stdout and "passphrase slots wiped" in res.stdout
    assert res.stdout.index("reaches it") < res.stdout.index(f"{box.dropin}: written")


def test_enroll_rerun_is_idempotent(box: Box) -> None:
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    dropin_first = box.dropin.read_text()
    box.reset()
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert not any(c.startswith("systemd-cryptenroll") for c in box.calls), (
        "every slot already right"
    )
    # the proofs run again: a re-run never trusts the last one
    assert TOKEN_PROOF in box.calls
    assert f"cryptsetup open --test-passphrase --key-slot=2 {DEV}" in box.calls
    assert f"{box.limine_dropin}: already in place" in res.stdout
    assert "no passphrase slot left" in res.stdout
    assert box.dropin.read_text() == dropin_first
    assert slots(box) == {"fido2", "recovery"}
    _assert_configured(box)


def test_enroll_on_a_box_enrolled_before_token_timeout(box: Box) -> None:
    """8.1.2's drop-in (passphrase after 30 s) is on the cmdline: it is forgiven, rewritten, and the passphrase goes."""
    (box.state / "fido2-slot").touch()
    box.limine_dropin.write_text(
        f'KERNEL_CMDLINE[default]+=" rd.luks.name={UUID}=root {RD_OPTS_OLD}"\n'
    )
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert f"{box.limine_dropin}: written" in res.stdout
    _assert_configured(box)
    assert slots(box) == {"fido2", "recovery"}


# A proof that fails stops enroll with the passphrase and the boot config as they were.
PROOFS = {
    "key-does-not-unlock": ("token_open_rc", "did not unlock", set()),
    "recovery-key-not-typed-back": ("recovery_open_rc", "wipe-slot=recovery", {"recovery"}),
}  # fmt: skip


@pytest.mark.parametrize(("knob", "said", "made"), PROOFS.values(), ids=PROOFS)
def test_a_failed_proof_keeps_the_passphrase(box: Box, knob: str, said: str, made: set) -> None:
    setattr(box, knob, 1)
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and said in res.stderr, res.stderr
    assert "no passphrase was wiped" in res.stderr
    assert slots(box) == {"password", "fido2", *made}
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert not any("wipe-slot" in c or c.startswith("limine-mkinitcpio") for c in box.calls)


def test_an_unreadable_header_is_never_read_as_an_empty_one(box: Box) -> None:
    """A luksDump that fails (a cancelled sudo prompt) must stop the run: read as "no such slot" it would enrol a second key, or call the passphrase wiped while it still unlocks."""
    box.env["FAKE_LUKSDUMP_FAILS"] = "1"
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "could not read" in res.stderr, res.stderr
    assert "Done." not in res.stdout
    _assert_untouched(box, allow=("omarchy-pkg-add", "omarchy-snapshot"))


def test_the_recovery_proof_is_its_own_slot_not_any_passphrase(box: Box) -> None:
    """A recovery key already there is kept and typed back against its keyslot, never a bare --test-passphrase the old passphrase would pass."""
    (box.state / "recovery-slot").touch()
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "recovery key is already enrolled (keyslot 2)" in res.stdout
    assert not any("--recovery-key" in c for c in box.calls)
    opens = [c for c in box.calls if c.startswith("cryptsetup open")]
    assert opens == [
        TOKEN_PROOF,
        f"cryptsetup open --test-passphrase --key-slot=2 {DEV}",
    ]


# lsblk leaves FSVER empty when blkid cannot tell: the empty field must survive the
# awk-to-read round trip, or the UUID becomes the version in every diagnostic.
NOT_LUKS2 = {
    "luks1": (f"{DEV} crypto_LUKS 1 {UUID}", DEV, "LUKS2"),
    "empty-fsver": (f"/dev/sdd crypto_LUKS  {UUID2}", "/dev/sdd", "is LUKS? — systemd-cryptenroll needs LUKS2"),
}  # fmt: skip


@pytest.mark.parametrize(("row", "device", "said"), NOT_LUKS2.values(), ids=NOT_LUKS2)
def test_enroll_refuses_anything_but_luks2(box: Box, row: str, device: str, said: str) -> None:
    box.lsblk = (
        LSBLK_STOCK.replace(f"{DEV} crypto_LUKS 2 {UUID}", row)
        if device == DEV
        else LSBLK_STOCK + f"{row}\n"
    )
    res = run(box, "enroll", "--yes", "--device", device)
    assert res.returncode != 0 and said in res.stderr, res.stderr
    _assert_untouched(box)


def test_enroll_without_token_touches_nothing(box: Box) -> None:
    """libfido2 (which fido2-token comes from) is the one install before the check."""
    box.tokens = ""
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "fido2-token" in res.stderr
    _assert_untouched(box, allow=("omarchy-pkg-add",))


@pytest.mark.parametrize(("sub", "enrolled"), [("enroll", False), ("disable", True)])
def test_refuses_without_tty_or_yes(box: Box, sub: str, enrolled: bool) -> None:
    """No terminal and no --yes: the run dies at the confirmation, nothing having changed."""
    if enrolled:
        assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
        box.reset()
    res = run(box, sub, "--device", DEV)
    assert res.returncode != 0 and "--yes" in res.stderr
    assert not MUTATORS & set(box.commands), box.calls
    assert ("fido2" in slots(box)) is enrolled
    assert box.dropin.exists() is enrolled and box.limine_dropin.exists() is enrolled
    assert box.limine.read_text() == box.limine_file


def test_interactive_confirm_n_aborts_untouched(box: Box) -> None:
    res = run(box, "enroll", "--device", DEV, assume_tty=True, stdin_text="n\n")
    assert res.returncode == 1 and "aborted — nothing changed" in res.stderr
    _assert_untouched(box)


def test_enroll_needs_device_flag_when_several(box: Box) -> None:
    """Several LUKS2 devices: --device, never a menu, and it must name one of them."""
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS 2 {UUID2}\n"
    res = run(box, "enroll", "--yes")
    assert res.returncode != 0 and "--device" in res.stderr
    assert DEV in res.stderr and "/dev/sdd" in res.stderr
    _assert_untouched(box)
    res = run(box, "enroll", "--yes", "--device", "/dev/sdz")
    assert res.returncode != 0 and "/dev/sdz" in res.stderr
    _assert_untouched(box)


def test_enroll_aborts_when_snapshot_fails(box: Box) -> None:
    box.snapshot_rc = 1
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "--no-snapshot" in res.stderr
    _assert_untouched(box, allow=("omarchy-snapshot", "omarchy-pkg-add"))
    box.snapshot_rc = 127  # omarchy-snapshot: snapper not installed
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "snapper" in res.stderr and "fido2" in slots(box)


CRYPT = "cryptdevice=UUID=x:root root=/dev/mapper/root rw"


# The mapper name and the tolerated neighbours, by shape of the assembled cmdline; the
# UUID-less rd.luks.options= is systemd-cryptsetup-generator(8)'s global form, not a
# per-device competitor.
SHAPES = {
    "rd.luks-of-another-uuid": (f"{CRYPT} rd.luks.name={UUID2}=data rd.luks.options={UUID2}=discard", "root"),
    "mapper-name-from-both": ("cryptdevice=UUID=x:cryptroot root=/dev/mapper/cryptroot rw", "cryptroot"),
    "mapper-name-from-root-alone": ("root=/dev/mapper/vault rw", "vault"),
    "mapper-name-from-cryptdevice": ("cryptdevice=UUID=x:vault rw", "vault"),
    "matching-rd.luks.name-tolerated": (f"{CRYPT} rd.luks.name={UUID}=root", "root"),
    "uuid-less-global-tolerated": (f"{CRYPT} rd.luks.options=fido2-device=auto", "root"),
}  # fmt: skip


@pytest.mark.parametrize(("cmdline", "mapper"), SHAPES.values(), ids=SHAPES)
def test_cmdline_shapes(box: Box, cmdline: str, mapper: str) -> None:
    box.base_cmdline = cmdline
    # the running system agrees with the cmdline: the device is open under <mapper>
    box.crypt_child, box.root_source = mapper, f"/dev/mapper/{mapper}"
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    _assert_configured(box, mapper)


# Shape of the assembled cmdline -> what the refusal must say. "" is limine printing
# nothing at all (the FAKE_CMDLINE_SILENT knob).
REFUSED = {
    "cryptdevice-and-root-disagree": ("cryptdevice=UUID=x:root root=/dev/mapper/cryptroot rw", "root=/dev/mapper/cryptroot"),
    "rd.luks.name-names-another-mapper": (f"{CRYPT} rd.luks.name={UUID}=other", f"rd.luks.name={UUID}=other"),
    "no-cryptdevice-no-mapper-root": ("root=UUID=y rw", "cannot tell"),
    "limine-says-nothing": ("", "printed nothing"),
}  # fmt: skip


@pytest.mark.parametrize(("cmdline", "reason"), REFUSED.values(), ids=REFUSED)
def test_cmdline_refused_before_anything_changes(box: Box, cmdline: str, reason: str) -> None:
    """A cmdline that would fight the drop-in, or does not say what the root is opened as, stops enroll before the confirmation."""
    if cmdline:
        box.base_cmdline = cmdline
    else:
        box.cmdline_silent = "1"  # limine-entry-tool answers with nothing at all
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and reason in res.stderr, res.stderr
    _assert_untouched(box)


def test_enroll_refuses_a_mapper_the_picked_device_is_not_open_as(box: Box) -> None:
    """A data volume must never be handed the root's rd.luks.name=; both cross-checks refuse independently."""
    box.crypt_child = "data"
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "--device" in res.stderr
    assert "open as /dev/mapper/data" in res.stderr
    _assert_untouched(box)
    box.crypt_child = ""  # the device is not open: nothing to compare it against
    box.root_source = "/dev/mapper/somethingelse"
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "running from /dev/mapper/somethingelse" in res.stderr
    _assert_untouched(box)
    box.root_source = "/dev/sda2"  # a root that is not on /dev/mapper says nothing
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0


def test_enroll_refuses_a_competing_rd_luks_options_in_another_dropin(box: Box) -> None:
    """systemd keeps one rd.luks.options= per device; which layer wins is the assembled cmdline's answer, so the file is only a hint."""
    other = box.conf_d / "zz-other.conf"
    other.write_text(f'KERNEL_CMDLINE[default]+=" rd.luks.options={UUID}=discard"\n')
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and f"rd.luks.options={UUID}=discard" in res.stderr
    assert "would override the drop-in" in res.stderr and str(other) in res.stderr
    _assert_untouched(box)


def test_enroll_names_the_inline_rd_luks_on_etc_default_limine(box: Box) -> None:
    """rd.luks.* inline on /etc/default/limine is refused, naming the file and what to do."""
    set_limine_line(box, f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID}=root {RD_OPTS}"')
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and str(box.limine) in res.stderr
    assert "inline rd.luks.*" in res.stderr and "keep cryptdevice=" in res.stderr
    _assert_untouched(box)


def test_enroll_refuses_a_plain_assignment_in_etc_default_limine(box: Box) -> None:
    """A plain `=` there replaces every drop-in's parameters (/etc/limine-entry-tool.conf:38-43)."""
    set_limine_line(box, f'KERNEL_CMDLINE[default]="{CMDLINE}"')
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "make it += first" in res.stderr
    assert str(box.limine) in res.stderr
    _assert_untouched(box)


def test_enroll_stops_at_the_cmdline_proof_when_the_dropin_does_not_reach_the_kernel(
    box: Box,
) -> None:
    """If limine does not hand the parameters to the kernel, the hooks drop-in is never written."""
    box.frozen_cmdline = CMDLINE  # limine never reports the drop-in, whatever the reason
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "is not on the cmdline limine assembles" in res.stderr
    assert "hyprconf-yubikey disable" in res.stderr
    assert box.limine_dropin.read_text() == LIMINE_DROPIN
    assert not box.dropin.exists(), "the hooks drop-in is the dangerous half"
    assert not any(c.startswith("limine-mkinitcpio") for c in box.calls)


# limine-mkinitcpio exits 0 whatever mkinitcpio did, so a failure is its own error_msg on
# stderr — any "ERROR:" line, the build's (:202) and the skip that builds nothing at all
# (:104) alike — and the other a non-zero exit.
@pytest.mark.parametrize(
    ("mode", "said"),
    [("fail", BUILD_FAILED), ("skipped", KERNEL_SKIPPED), ("exit1", "limine-mkinitcpio exited 1")],
)
def test_rebuild_failure_dies_with_the_config_left_in_place(box: Box, mode: str, said: str) -> None:
    box.limine_mkinitcpio = mode
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and said in res.stderr
    assert "sudo limine-mkinitcpio" in res.stderr, "the retry is named"
    assert "Done." not in res.stdout and "Boot images rebuilt" not in res.stdout
    assert box.dropin.exists() and box.limine_dropin.read_text() == LIMINE_DROPIN
    assert "password" in slots(box) and not any("wipe-slot" in c for c in box.calls)


def test_the_non_latin_layout_list_is_the_tools_own() -> None:
    """The list cannot be derived at run time: its home is not under $OMARCHY_PATH."""
    assert " | ".join(NON_LATIN) + ") ;;" in TOOL.read_text()


def test_enroll_refuses_non_latin_first_layout(box: Box) -> None:
    box.vconsole.write_text('KEYMAP=us\nXKBLAYOUT="ru,us"\n')
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "--allow-non-latin-layout" in res.stderr
    assert "ru" in res.stderr and box.calls == [], "refused before the device pick, anything"
    _assert_untouched(box)


def test_enroll_allow_non_latin_layout_flag_warns_and_proceeds(box: Box) -> None:
    box.vconsole.write_text("KEYMAP=ru\nXKBLAYOUT=ru\n")
    res = run(box, "enroll", "--yes", "--device", DEV, "--allow-non-latin-layout")
    assert res.returncode == 0, res.stderr
    assert "warning" in res.stderr and "ru" in res.stderr and "recovery key" in res.stderr
    assert "fido2" in slots(box) and box.dropin.exists()


# the last assignment wins and one pair of quotes goes; no XKBLAYOUT and no file at all
# read as Latin too (Omarchy bundles vconsole.conf then)
@pytest.mark.parametrize("content", ["XKBLAYOUT=ru\nXKBLAYOUT='us,ru'\n", "KEYMAP=us\n", None])
def test_enroll_accepts_latin_or_absent_layout(box: Box, content: str | None) -> None:
    box.vconsole.unlink() if content is None else box.vconsole.write_text(content)
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "warning" not in res.stderr


def _source_dropin(box: Box, hooks: str, *, sd_overlay: bool = True) -> list[str]:
    """The drop-in ships the real /usr/lib/initcpio/install path (root sources it): swap it for the box's."""
    fake = box.initcpio_install if sd_overlay else box.tmp / "no-initcpio-install"
    fake.mkdir(exist_ok=True)
    swapped = box.tmp / "dropin-under-test.conf"
    swapped.write_text(box.dropin.read_text().replace(INITCPIO_INSTALL, str(fake)))
    res = subprocess.run(
        [
            "bash",
            "-c",
            f'set -u\nHOOKS=({hooks})\nsource "{swapped}"\n'
            "declare -p _hyprconf_hooks _hyprconf_hook >/dev/null 2>&1 && echo LEAKED\n"
            "printf '%s\\n' \"${HOOKS[@]}\"\n",
        ],
        capture_output=True,
        text=True,
        env={"PATH": box.env["PATH"]},
    )
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert "LEAKED" not in lines, "the drop-in must unset its temporaries"
    return lines


def test_dropin_rewrites_omarchy_hooks(box: Box) -> None:
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    assert INITCPIO_INSTALL in box.dropin.read_text(), "no test seam ships into /etc"
    # Omarchy's final HOOKS: omarchy_hooks.conf + omarchy_resume.conf
    hooks = _source_dropin(box, f"{OMARCHY_HOOKS} resume")
    assert hooks == [
        "base", "systemd", "plymouth", "keyboard", "autodetect", "microcode", "modconf", "kms",
        "sd-vconsole", "block", "sd-encrypt", "filesystems", "fsck", "sd-btrfs-overlayfs",
    ]  # fmt: skip
    # empty elements go too, and an already-systemd HOOKS passes through untouched
    assert _source_dropin(box, 'base "" udev encrypt') == ["base", "systemd", "sd-encrypt"]
    assert _source_dropin(box, " ".join(hooks)) == hooks


def test_dropin_keeps_busybox_overlay_hook_without_sd_variant(box: Box) -> None:
    """Older limine-mkinitcpio-hook: keep the busybox hook rather than name one that does not exist."""
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    hooks = _source_dropin(box, OMARCHY_HOOKS, sd_overlay=False)
    assert hooks[-1] == "btrfs-overlayfs" and "sd-btrfs-overlayfs" not in hooks
    assert "systemd" in hooks and "sd-encrypt" in hooks


def test_shellcheck_dropin(box: Box) -> None:
    """The drop-in is generated, so this is the only shellcheck it gets."""
    shellcheck = shutil.which("shellcheck") or pytest.skip("shellcheck is not installed")
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    res = subprocess.run(
        [shellcheck, "--severity=warning", str(box.dropin)], capture_output=True, text=True
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_disable_removes_both_dropins(box: Box) -> None:
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    box.reset()
    res = run(box, "disable", "--yes")
    assert res.returncode == 0, res.stderr
    calls = box.calls
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert f"{box.limine_dropin}: removed" in res.stdout
    assert f"sudo -- rm -f -- {box.limine_dropin}" in calls
    assert box.limine.read_text() == box.limine_file
    assert "limine-entry-tool" not in box.commands, "only enroll needs the cmdline"
    assert "omarchy-snapshot create" in calls and "limine-mkinitcpio" in calls
    assert "Boot images rebuilt" in res.stdout
    assert not any(c.startswith("systemd-cryptenroll") for c in calls)
    assert "fido2" in slots(box), "disable keeps the LUKS slot"
    assert (box.mkinitcpio_d / "omarchy_hooks.conf").exists(), "Omarchy's own drop-ins stay"
    assert sorted(p.name for p in box.conf_d.iterdir()) == box.omarchy_conf_d


def test_disable_when_not_configured_changes_nothing(box: Box) -> None:
    """With snapshots ON: nothing to roll back, so omarchy-snapshot is never called for the no-op."""
    res = run(box, "disable", "--yes")
    assert res.returncode == 0, res.stderr
    assert box.calls == [] and "Nothing to rebuild" in res.stdout
    assert box.limine.read_text() == box.limine_file


def test_remove_sets_a_passphrase_then_wipes_fido2_slot_then_disables(box: Box) -> None:
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    box.reset()
    res = run(box, "remove", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    calls = box.calls
    assert_order(
        calls,
        f"systemd-cryptenroll --password {DEV}",
        f"systemd-cryptenroll --wipe-slot=fido2 {DEV}",
        "limine-mkinitcpio",
    )
    assert not any("wipe-slot=password" in c or "wipe-slot=recovery" in c for c in calls)
    assert "limine-entry-tool" not in box.commands, "only enroll needs the cmdline"
    assert slots(box) == {"password", "recovery"}
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert box.limine.read_text() == box.limine_file


def test_remove_keeps_an_existing_passphrase(box: Box) -> None:
    """A box whose passphrase is still there (enrolled before this release) is not asked for a new one."""
    (box.state / "fido2-slot").touch()
    res = run(box, "remove", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert not any("--password" in c for c in box.calls)
    assert slots(box) == {"password"}


def test_status_prints_facts(box: Box) -> None:
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS 1 {UUID2}\n"
    res = run(box, "status")
    assert res.returncode == 0, res.stderr
    out = unpadded(res.stdout)
    assert (
        f"{DEV}  LUKS2  UUID {UUID}  systemd-fido2 slot: no  recovery key: no  passphrase slots: 0"
        in res.stdout
    )
    assert "/dev/sdd  LUKS1" in res.stdout and "not eligible" in out
    assert f"initramfs drop-in: absent ({box.dropin})" in out
    assert f"cmdline drop-in: absent ({box.limine_dropin})" in out
    assert "kernel cmdline: no rd.luks.* parameters" in out
    assert f"plugged in — {TOKEN_LINE}" in out and "sd-btrfs-overlayfs installed" in out
    assert not MUTATORS & set(box.commands), box.calls
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    box.tokens = ""
    res = run(box)  # status is the default subcommand
    out = unpadded(res.stdout)
    assert (
        res.returncode == 0
        and "systemd-fido2 slot: yes recovery key: yes passphrase slots: none" in out
    )
    assert f"initramfs drop-in: present ({box.dropin})" in out
    assert f"cmdline drop-in: present ({box.limine_dropin})" in out
    assert f"kernel cmdline: rd.luks.name={UUID}=root {RD_OPTS}" in out
    assert "set outside" not in out and "FIDO2 token: none detected" in out


def test_status_reports_rd_luks_set_outside_the_dropin(box: Box) -> None:
    """rd.luks.* inline on /etc/default/limine is named as set outside the drop-in; `disable` never touches that file (README › Undo)."""
    set_limine_line(box, f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID}=root {RD_OPTS}"')
    res = run(box, "status")
    assert res.returncode == 0, res.stderr
    out = unpadded(res.stdout)
    assert f"kernel cmdline: rd.luks.name={UUID}=root {RD_OPTS}" in out
    assert "set outside" in out and str(box.limine) in out
    assert "inline rd.luks.*" in out and "keep cryptdevice=" in out


def test_status_says_unknown_instead_of_asking_sudo_per_device(box: Box) -> None:
    """No sudo credentials: the privileged rows read unknown, status exits 0, and sudo is asked once (each `sudo -n` writes an auth-log record)."""
    for name in ("sudo", "cryptsetup"):
        box.stub(name, "exit 1\n")
    res = run(box, "status")
    assert res.returncode == 0, res.stderr
    assert f"{DEV}  LUKS2  UUID {UUID}  systemd-fido2 slot: unknown (run as root)" in res.stdout
    assert "kernel cmdline: unknown (run as root" in unpadded(res.stdout)
    assert [c for c in box.calls if c.startswith("sudo")] == ["sudo -n -- true"]


def test_status_never_fails(box: Box) -> None:
    (box.initcpio_install / "sd-btrfs-overlayfs").unlink()
    box.limine.unlink()
    box.lsblk = ""
    res = run(box, "status")
    assert res.returncode == 0, res.stderr
    assert "none found" in res.stdout and "sd-btrfs-overlayfs NOT installed" in res.stdout


def test_help_lists_the_subcommands_and_rejects_unknown_args(box: Box) -> None:
    res = run(box, "help")
    assert res.returncode == 0
    for sub in ("status", "enroll", "disable", "remove", "sudo", "help"):
        assert re.search(rf"^(usage:)?\s+hyprconf-yubikey {sub}\b", res.stdout, re.M), sub
    assert run(box, "--help").returncode == 0
    assert run(box, "bogus").returncode != 0
    assert run(box, "enroll", "--enrol").returncode != 0, "one spelling per flag"
    assert box.calls == []


def test_sudo_subcommand_execs_omarchy_script(box: Box) -> None:
    res = run(box, "sudo")
    assert res.returncode == 0, res.stderr
    assert "OMARCHY FIDO2 SETUP" in res.stdout and box.calls == ["omarchy-setup-security-fido2"]
