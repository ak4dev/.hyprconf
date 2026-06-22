"""
Unit tests for hyprconf-secureboot — the Secure Boot (signed UKI) setup &
verification helper (stowed to ~/.local/bin), its hyprconf CLI / doctor wiring,
the installer hook, and the UKI-awareness added to yubikey-fido2-setup.

All tests are static-analysis only: they assert the script is valid bash, is
reachable on a new system (lives under stow/, not the export-ignored scripts/),
and that the Secure Boot / UKI / sbctl / firmware-password / key-only-LUKS wiring
matches the documented, layered behaviour. No root, UEFI, TPM, or sbctl required.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf-secureboot"
YUBIKEY = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "yubikey-fido2-setup"
HYPRCONF_BIN = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf"
INSTALL = REPO_ROOT / "install" / "install.sh"
PACKAGES = REPO_ROOT / "packages"
README = REPO_ROOT / "README.md"
HARDENING = REPO_ROOT / "docs" / "security-hardening.md"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _bin_text() -> str:
    return HYPRCONF_BIN.read_text(encoding="utf-8")


def _func_body(name: str, path: Path = SCRIPT) -> str:
    """Extract a single shell function body via awk (matches existing test style)."""
    result = subprocess.run(
        ["awk", f"/^{name}\\(\\) \\{{/,/^}}$/", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Reachability: must be stowed (so new systems get it), valid, and executable
# ---------------------------------------------------------------------------


def test_script_exists_in_stowed_bin() -> None:
    assert SCRIPT.exists(), (
        "hyprconf-secureboot must live under stow/hypr/.local/bin so it is stowed "
        "onto new systems and on PATH — scripts/ is export-ignored and absent from "
        "the installer's sparse-checkout paths."
    )


def test_script_not_in_dev_only_scripts_dir() -> None:
    assert not (REPO_ROOT / "scripts" / "hyprconf-secureboot").exists()


def test_script_is_executable() -> None:
    assert SCRIPT.stat().st_mode & stat.S_IXUSR, "hyprconf-secureboot must be executable"


def test_script_shebang() -> None:
    assert _text().startswith("#!/usr/bin/env bash\n")


def test_script_bash_syntax() -> None:
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"


def test_script_has_pipefail_guard() -> None:
    # `-uo pipefail` (not -e): relies on `|| die` + an ERR trap for rollback.
    assert "set -uo pipefail" in _text()


# ---------------------------------------------------------------------------
# Backup / rollback safety net
# ---------------------------------------------------------------------------


def test_backs_up_and_rolls_back() -> None:
    txt = _text()
    assert "backup()" in txt and "rollback()" in txt
    assert "BACKUP_DIR=" in txt
    # ERR trap offers rollback on unexpected failure
    assert "trap " in txt and "ERR" in txt and "rollback" in txt


def test_log_uses_unique_file_and_tolerates_unwritable() -> None:
    txt = _text()
    assert "mktemp" in txt
    assert 'tee -a "$LOG" 2>/dev/null || true' in txt


# ---------------------------------------------------------------------------
# State detection — bootctl → mokutil → raw efivar (mokutil is often absent)
# ---------------------------------------------------------------------------


def test_detects_secure_boot_state_with_efivar_fallback() -> None:
    txt = _text()
    assert "sb_enabled()" in txt and "setup_mode()" in txt
    assert "bootctl status" in txt
    assert "mokutil --sb-state" in txt
    # Global EFI variable GUID for SecureBoot / SetupMode (the dependable fallback)
    assert "8be4df61-93ca-11d2-aa0d-00e098032b8c" in txt
    body = _func_body("_efivar_byte")
    assert "SecureBoot" in txt and "SetupMode" in txt
    assert "od -An" in body


def test_status_is_uefi_gated() -> None:
    body = _func_body("do_status")
    assert "/sys/firmware/efi/efivars" in body, "status must no-op cleanly on non-UEFI"


# ---------------------------------------------------------------------------
# Unified Kernel Image conversion
# ---------------------------------------------------------------------------


def test_converts_to_signed_uki() -> None:
    txt = _text()
    body = _func_body("convert_to_uki")
    assert "/etc/kernel/cmdline" in txt, "cmdline must be baked into the signed UKI"
    assert "_uki=" in body, "mkinitcpio preset must emit a UKI"
    assert "EFI/Linux" in body
    assert "mkinitcpio -P" in body
    # cmdline editing must be disabled at the menu (init=/bin/sh bypass under SB)
    assert "editor" in body and "no" in body


def test_uki_conversion_is_idempotent() -> None:
    # is_uki() short-circuits re-conversion
    assert "is_uki()" in _text()
    assert "is_uki" in _func_body("convert_to_uki")


# ---------------------------------------------------------------------------
# Keys · signing · verification · enrollment ordering
# ---------------------------------------------------------------------------


def test_creates_and_signs_with_sbctl() -> None:
    txt = _text()
    assert "sbctl create-keys" in txt
    # -s tracks files so sbctl's own pacman hook re-signs on upgrades
    assert "sbctl sign -s" in txt
    assert "sbctl sign-all" in txt
    assert "sbctl verify" in txt


def test_enroll_requires_setup_mode_and_clean_verify() -> None:
    body = _func_body("enroll_keys")
    assert body, "enroll_keys must exist"
    # never enroll unless firmware is in Setup Mode …
    assert "setup_mode" in body
    # … and never enroll over an unsigned chain (would brick the next SB-on boot)
    assert "verify_quiet" in body
    # key policy: keep Microsoft keys, or own-keys-only
    assert "--microsoft" in body or "-m" in body


def test_enroll_own_keys_passes_brick_override() -> None:
    # Own-keys-only enrollment: modern sbctl ABORTS with an "Option ROM" error
    # unless --yes-this-might-brick-my-machine (alias --yolo) is passed. Without it,
    # `sbctl enroll-keys` (no flag) fails and the default no-dGPU "own keys only
    # (recommended)" path never enrolls.
    body = _func_body("enroll_keys")
    assert "--yes-this-might-brick-my-machine" in body or "--yolo" in body, (
        "own-keys-only enroll must pass sbctl's Option-ROM brick override, else "
        "`sbctl enroll-keys` aborts and enrollment fails"
    )


def test_setup_does_not_enroll_over_unsigned_chain() -> None:
    body = _func_body("do_setup")
    # setup must verify before it is willing to enroll
    assert "verify_report" in body
    assert "enroll" in body
    # signing happens before enrollment in the setup flow
    assert body.index("sign_all") < body.index("verify_report")


# ---------------------------------------------------------------------------
# Key policy — detect & offer both (own-keys-only vs Microsoft)
# ---------------------------------------------------------------------------


def test_key_policy_detect_and_offer() -> None:
    txt = _text()
    assert "decide_key_policy()" in txt
    assert "detect_dgpu()" in txt, "discrete-GPU heuristic biases toward keeping MS keys"
    assert "USE_MS_KEYS" in txt
    # both flags are accepted
    assert "--own-keys-only" in txt
    assert "--microsoft" in txt


# ---------------------------------------------------------------------------
# Persistence — verify-only pacman hook (sbctl's own hook does the re-signing)
# ---------------------------------------------------------------------------


def test_installs_verify_pacman_hook() -> None:
    txt = _text()
    body = _func_body("install_verify_hook")
    assert "/etc/pacman.d/hooks/" in txt
    assert "zz-hyprconf-sb-verify.hook" in txt
    assert "PostTransaction" in body
    assert "sbctl verify" in body
    # triggers on the kernel / bootloader / sbctl
    assert "vmlinuz" in body and "sbctl" in body


# ---------------------------------------------------------------------------
# Optional TPM2 PCR binding — FIDO2 stays the default factor
# ---------------------------------------------------------------------------


def test_tpm_bind_is_optional_and_pcr_aware() -> None:
    txt = _text()
    body = _func_body("tpm_bind")
    assert "tpm_bind()" in txt
    assert "have_tpm" in body, "must skip cleanly when no TPM2 device is present"
    assert "systemd-cryptenroll" in body
    assert "--tpm2-device=auto" in body
    assert "--tpm2-pcrs=" in body
    assert "--tpm2-with-pin=yes" in body, "a PIN blocks auto-unlock on powered-off theft"


# ---------------------------------------------------------------------------
# Firmware admin password gating (best-effort read + explicit acknowledgement)
# ---------------------------------------------------------------------------


def test_firmware_password_gating() -> None:
    txt = _text()
    assert "firmware_password_state()" in txt
    assert "/sys/class/firmware-attributes" in txt, "best-effort read where firmware exposes it"
    assert "ack_firmware_password()" in txt
    assert "FWPW_ACK" in txt


# ---------------------------------------------------------------------------
# Key-only LUKS — delegate to yubikey-fido2-setup (don't reimplement its guards)
# ---------------------------------------------------------------------------


def test_harden_delegates_to_yubikey_harden_luks() -> None:
    body = _func_body("do_harden")
    assert body, "do_harden must exist"
    assert "yubikey-fido2-setup" in body
    assert "harden-luks" in body
    # must NOT reimplement slot wiping here — that lives in yubikey-fido2-setup
    assert "--wipe-slot" not in body


# ---------------------------------------------------------------------------
# Read-only status report + the YubiKey-bypass-via-passphrase finding
# ---------------------------------------------------------------------------


def test_status_is_readonly_and_flags_passphrase_bypass() -> None:
    body = _func_body("do_status")
    assert body, "do_status must exist"
    # read-only: disables the rollback ERR trap, makes no mutating edits
    assert "trap - ERR" in body
    for mutating in ("sed -i", "sbctl sign", "enroll-keys", "--wipe-slot", "create-keys"):
        assert mutating not in body, f"status must not call {mutating} (read-only)"
    # surfaces the core finding: a coexisting passphrase slot makes the YubiKey bypassable
    assert "fido2" in body.lower()
    assert "passphrase" in body.lower()
    assert "harden" in body, "status should point at key-only LUKS when bypassable"


# ---------------------------------------------------------------------------
# Subcommand dispatch
# ---------------------------------------------------------------------------


def test_main_dispatches_subcommands() -> None:
    txt = _text()
    for fn in (
        "do_setup()",
        "do_enroll()",
        "do_status()",
        "do_sign()",
        "do_verify()",
        "usage_sb()",
    ):
        assert fn in txt, f"missing {fn}"
    # default action is the read-only status report
    assert 'action="${1:-status}"' in txt
    for token in ("setup)", "enroll|enroll-keys)", "sign|sign-all)", "verify)", "tpm-bind|tpm)"):
        assert token in txt, f"main() must route {token}"
    assert "harden" in txt and "ack-firmware-password" in txt


# ---------------------------------------------------------------------------
# No hardcoded device paths (mirror the no-PII discipline of the other scripts)
# ---------------------------------------------------------------------------


def test_no_hardcoded_block_devices() -> None:
    txt = _text()
    for dev in ("/dev/nvme0n1", "/dev/sda", "/dev/vda"):
        assert dev not in txt, f"{dev} hardcoded — devices must be detected dynamically"
    assert "_first_luks2_device" in txt, "LUKS device must be detected, not assumed"


# ---------------------------------------------------------------------------
# hyprconf CLI integration: `hyprconf secureboot <sub>`
# ---------------------------------------------------------------------------


def test_cli_cmd_secureboot_exists() -> None:
    assert "cmd_secureboot()" in _bin_text()


def test_cli_dispatcher_entry() -> None:
    lines = [
        l.strip()
        for l in _bin_text().splitlines()
        if "cmd_secureboot " in l and l.lstrip().startswith("secureboot")
    ]
    assert lines, "secureboot must have a dispatcher entry in main()"


def test_cli_help_lists_secureboot() -> None:
    assert "hyprconf secureboot" in _bin_text()


def test_cli_references_script_and_escalates() -> None:
    txt = _bin_text()
    assert 'SECUREBOOT_SCRIPT="$HOME/.local/bin/hyprconf-secureboot"' in txt
    assert "sudo" in _func_body("_sb_run", HYPRCONF_BIN)
    for sub in ("status", "setup", "enroll", "sign", "verify", "harden"):
        assert sub in _func_body("cmd_secureboot", HYPRCONF_BIN)


# ---------------------------------------------------------------------------
# hyprconf doctor integration: a read-only drift check, silent on non-SB systems
# ---------------------------------------------------------------------------


def test_doctor_check_exists_and_is_wired() -> None:
    txt = _bin_text()
    assert "_doctor_check_secureboot()" in txt
    # called from cmd_doctor
    body = _func_body("cmd_doctor", HYPRCONF_BIN)
    assert "_doctor_check_secureboot" in body


def test_doctor_check_is_readonly_and_gated() -> None:
    body = _func_body("_doctor_check_secureboot", HYPRCONF_BIN)
    # UEFI-gated and reads SB state without root (efivar / bootctl)
    assert "/sys/firmware/efi/efivars" in body
    assert "8be4df61-93ca-11d2-aa0d-00e098032b8c" in body
    # no mutating commands in a health check
    for mutating in ("sbctl sign", "enroll-keys", "sed -i", "mkinitcpio"):
        assert mutating not in body, f"doctor check must not call {mutating}"
    # stays silent on systems that never engaged Secure Boot (no nagging)
    assert "return 0" in body


# ---------------------------------------------------------------------------
# Installer integration: offer_secureboot_setup, CI-skipped, after YubiKey
# ---------------------------------------------------------------------------


def test_installer_offers_secureboot_after_yubikey() -> None:
    txt = INSTALL.read_text(encoding="utf-8")
    assert "offer_secureboot_setup()" in txt
    # CI-skipped like the YubiKey offer
    body = _func_body("offer_secureboot_setup", INSTALL)
    assert 'HYPRCONF_CI:-0}" == "1" ]] && return 0' in body
    assert "hyprconf-secureboot" in body and "setup" in body
    # invoked after offer_yubikey_setup so the FIDO2 cmdline is captured in the UKI
    assert txt.index("offer_yubikey_setup\n") < txt.index("offer_secureboot_setup\n")


# ---------------------------------------------------------------------------
# yubikey-fido2-setup is UKI-aware (re-sign after rebuild; cmdline branch)
# ---------------------------------------------------------------------------


def test_yubikey_resigns_uki_after_rebuild() -> None:
    txt = YUBIKEY.read_text(encoding="utf-8")
    # after `mkinitcpio -P`, re-sign when sbctl keys exist so the chain stays valid
    assert "sbctl sign-all" in txt
    # update_bootloader learns the UKI cmdline location
    assert "/etc/kernel/cmdline" in txt


# ---------------------------------------------------------------------------
# Repo wiring: packages + README + docs parity
# ---------------------------------------------------------------------------


def test_packages_lists_sbctl_commented() -> None:
    lines = PACKAGES.read_text(encoding="utf-8").splitlines()
    matches = [ln for ln in lines if "sbctl" in ln]
    assert matches, "sbctl missing from packages"
    # optional Secure Boot tooling → must stay commented so non-SB users skip it
    assert all(ln.lstrip().startswith("#") for ln in matches), (
        "sbctl must be commented (optional, installed on demand)"
    )


def test_readme_documents_secureboot() -> None:
    txt = README.read_text(encoding="utf-8")
    assert "hyprconf secureboot" in txt
    assert "Unified Kernel Image" in txt or "signed UKI" in txt


def test_hardening_doc_describes_layered_flow() -> None:
    txt = HARDENING.read_text(encoding="utf-8")
    assert "hyprconf secureboot" in txt
    # the doc must name the layered controls and the bypass it closes
    assert "signed UKI" in txt or "Unified Kernel Image" in txt
    assert "firmware" in txt.lower() and "password" in txt.lower()
    assert "key-only" in txt.lower()
