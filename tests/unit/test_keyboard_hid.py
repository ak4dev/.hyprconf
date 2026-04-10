"""Tests for Keychron / Lemokey keyboard HID permissions udev rule."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SETUP_SH = REPO_ROOT / "setup.sh"


def _setup_text() -> str:
    return SETUP_SH.read_text()


class TestSetupKeyboardHidPermissionsFunction:
    def test_function_exists(self) -> None:
        assert "setup_keyboard_hid_permissions()" in _setup_text()

    def test_udev_rule_path(self) -> None:
        assert "70-keychron.rules" in _setup_text()

    def test_vendor_id(self) -> None:
        text = _setup_text()
        idx = text.index("setup_keyboard_hid_permissions()")
        body = text[idx : idx + 2000]
        assert '3434' in body

    def test_uaccess_tag(self) -> None:
        text = _setup_text()
        idx = text.index("setup_keyboard_hid_permissions()")
        body = text[idx : idx + 2000]
        assert 'uaccess' in body

    def test_hidraw_subsystem(self) -> None:
        text = _setup_text()
        idx = text.index("setup_keyboard_hid_permissions()")
        body = text[idx : idx + 2000]
        assert 'hidraw' in body

    def test_udevadm_reload(self) -> None:
        text = _setup_text()
        idx = text.index("setup_keyboard_hid_permissions()")
        body = text[idx : idx + 2000]
        assert "udevadm control --reload-rules" in body

    def test_idempotent_check(self) -> None:
        text = _setup_text()
        idx = text.index("setup_keyboard_hid_permissions()")
        body = text[idx : idx + 2000]
        assert "already installed" in body

    def test_graceful_failure(self) -> None:
        """Should warn and return 0 on failure, not abort."""
        text = _setup_text()
        idx = text.index("setup_keyboard_hid_permissions()")
        body = text[idx : idx + 2000]
        assert "log_warn" in body
        assert "return 0" in body

    def test_chroot_guard(self) -> None:
        """udevadm reload must be guarded by _in_chroot check."""
        text = _setup_text()
        idx = text.index("setup_keyboard_hid_permissions()")
        body = text[idx : idx + 2000]
        assert "_in_chroot" in body


class TestSyncServicesCallsFunction:
    def test_called_from_sync_services(self) -> None:
        text = _setup_text()
        idx = text.index("sync_services()")
        # Find the function definition (not the call site)
        fn_idx = text.index("sync_services() {")
        body = text[fn_idx : fn_idx + 2000]
        assert "setup_keyboard_hid_permissions" in body


class TestReadmeDocumentation:
    def test_readme_mentions_keychron(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text()
        assert "Keychron" in readme or "keychron" in readme.lower()

    def test_readme_mentions_lemokey(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text()
        assert "Lemokey" in readme or "lemokey" in readme.lower()
