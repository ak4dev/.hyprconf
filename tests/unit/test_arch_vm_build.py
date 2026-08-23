"""The `vm arch` image builder — gpu-passthrough.sh's Packer front-end.

`build-arch-vm-image.sh` runs a real Arch install inside QEMU, so it cannot be
executed in the hermetic tier. These tests cover the contract that is checkable
from the text: which values reach Packer, and how the guest password gets
there — argv is world-readable through procfs for as long as a build runs, and
a build runs for several minutes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VM_DIR = REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "scripts" / "vm"
BUILD_SCRIPT = VM_DIR / "build-arch-vm-image.sh"
PACKER_TEMPLATE = VM_DIR / "arch-vm.pkr.hcl"


def _script() -> str:
    return BUILD_SCRIPT.read_text(encoding="utf-8")


class TestBuildScriptShape:
    def test_ships_and_parses(self) -> None:
        assert BUILD_SCRIPT.is_file(), f"missing {BUILD_SCRIPT}"
        result = subprocess.run(["bash", "-n", str(BUILD_SCRIPT)], capture_output=True, text=True)
        assert result.returncode == 0, f"syntax error:\n{result.stderr}"

    def test_requires_username_and_password(self) -> None:
        """Both come from the `vm arch` config; a missing one must abort, not
        silently build an image with an empty login."""
        text = _script()
        assert "${VM_USERNAME:?" in text
        assert "${VM_PASSWORD:?" in text

    def test_template_is_the_one_this_repo_ships(self) -> None:
        assert PACKER_TEMPLATE.is_file(), f"missing {PACKER_TEMPLATE}"
        assert "arch-vm.pkr.hcl" in _script()


class TestGuestPasswordHandling:
    def test_password_is_passed_through_the_environment(self) -> None:
        """PKR_VAR_<name> is Packer's env-var form of `-var name=…`."""
        assert "PKR_VAR_password=" in _script()

    def test_password_never_appears_on_the_command_line(self) -> None:
        text = _script()
        assert '-var "password=' not in text, (
            "the guest password must not be passed as a `-var` argument — argv is "
            "readable by every user on the host for the duration of the build"
        )

    def test_template_marks_the_password_sensitive(self) -> None:
        """So Packer redacts it from build logs as well."""
        template = PACKER_TEMPLATE.read_text(encoding="utf-8")
        block = template[template.index('variable "password"') :]
        assert "sensitive   = true" in block.split("}")[0]


class TestPackerVariables:
    def test_non_secret_variables_are_forwarded(self) -> None:
        text = _script()
        for var in (
            "username",
            "hostname",
            "timezone",
            "disk_size",
            "ssh_pubkey",
            "install_script_path",
            "output_directory",
        ):
            assert f'-var "{var}=' in text, f"{var} is never passed to packer"

    def test_every_forwarded_variable_is_declared_by_the_template(self) -> None:
        template = PACKER_TEMPLATE.read_text(encoding="utf-8")
        for var in (
            "username",
            "password",
            "hostname",
            "timezone",
            "disk_size",
            "ssh_pubkey",
            "install_script_path",
            "output_directory",
        ):
            assert f'variable "{var}"' in template, f"template declares no `{var}` variable"


class TestGuestSshKey:
    def test_generates_a_passphraseless_ed25519_key_for_the_vm_only(self) -> None:
        text = _script()
        assert "ssh-keygen -t ed25519" in text
        assert "hyprconf_arch_vm_key" in text

    def test_key_is_reused_when_it_already_exists(self) -> None:
        """`vm arch build` is re-runnable; regenerating the key would lock the
        user out of every previously built image."""
        text = _script()
        assert 'if [[ ! -f "${SSH_KEY}" ]]; then' in text
