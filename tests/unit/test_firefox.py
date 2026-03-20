"""
Tests for Firefox-related logic in switch_theme.py and infra/firefox/policies.json.

Covers:
- FIREFOX_ENFORCED_PREFS contains all required telemetry/privacy keys
- format_firefox_pref formats bool, string, and int values correctly
- write_firefox_userjs merges new prefs, updates existing ones, preserves others
- infra/firefox/policies.json is valid JSON with required enterprise policy fields
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import switch_theme as a module (safe: guarded by if __name__ == "__main__")
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
SWITCH_THEME_PATH = (
    REPO_ROOT
    / "stow"
    / "hypr"
    / ".config"
    / "hypr"
    / "scripts"
    / "theme-switcher"
    / "switch_theme.py"
)
POLICIES_JSON = REPO_ROOT / "infra" / "firefox" / "policies.json"


def _import_switch_theme():
    spec = importlib.util.spec_from_file_location("switch_theme", SWITCH_THEME_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_st = _import_switch_theme()


# ---------------------------------------------------------------------------
# FIREFOX_ENFORCED_PREFS — completeness
# ---------------------------------------------------------------------------

REQUIRED_TELEMETRY_KEYS = [
    "toolkit.telemetry.enabled",
    "toolkit.telemetry.unified",
    "toolkit.telemetry.archive.enabled",
    "toolkit.telemetry.server",
    "toolkit.coverage.opt-out",
    "datareporting.healthreport.uploadEnabled",
    "datareporting.policy.dataSubmissionEnabled",
    "app.shield.optoutstudies.enabled",
    "app.normandy.enabled",
]

REQUIRED_PRIVACY_KEYS = [
    "browser.tabs.crashReporting.sendReport",
    "browser.crashReports.unsubmittedCheck.enabled",
    "browser.crashReports.unsubmittedCheck.autoSubmit2",
    "extensions.pocket.enabled",
    "geo.enabled",
    "network.captive-portal-detection.enabled",
    "network.connectivity-service.enabled",
    "network.prefetch-next",
    "network.dns.disablePrefetch",
    "browser.urlbar.speculativeConnect.enabled",
    "browser.send_pings",
    "beacon.enabled",
    "browser.safebrowsing.malware.enabled",
    "browser.safebrowsing.phishing.enabled",
    "browser.safebrowsing.downloads.enabled",
    "browser.safebrowsing.downloads.remote.enabled",
    "privacy.trackingprotection.enabled",
    "privacy.trackingprotection.socialtracking.enabled",
]

REQUIRED_UI_KEYS = [
    "browser.tabs.verticalTabs",
    "browser.tabs.verticalTabs.showPinnedTabs",
]


@pytest.mark.parametrize("key", REQUIRED_TELEMETRY_KEYS)
def test_enforced_prefs_telemetry_keys_present(key: str) -> None:
    assert key in _st.FIREFOX_ENFORCED_PREFS, f"Missing telemetry pref: {key}"


@pytest.mark.parametrize("key", REQUIRED_PRIVACY_KEYS)
def test_enforced_prefs_privacy_keys_present(key: str) -> None:
    assert key in _st.FIREFOX_ENFORCED_PREFS, f"Missing privacy pref: {key}"


@pytest.mark.parametrize("key", REQUIRED_UI_KEYS)
def test_enforced_prefs_ui_keys_present(key: str) -> None:
    assert key in _st.FIREFOX_ENFORCED_PREFS, f"Missing UI pref: {key}"


def test_enforced_prefs_vertical_tabs_enabled() -> None:
    assert _st.FIREFOX_ENFORCED_PREFS["browser.tabs.verticalTabs"] is True


def test_enforced_prefs_telemetry_disabled() -> None:
    assert _st.FIREFOX_ENFORCED_PREFS["toolkit.telemetry.enabled"] is False
    assert _st.FIREFOX_ENFORCED_PREFS["datareporting.healthreport.uploadEnabled"] is False
    assert _st.FIREFOX_ENFORCED_PREFS["datareporting.policy.dataSubmissionEnabled"] is False


def test_enforced_prefs_tracking_protection_enabled() -> None:
    assert _st.FIREFOX_ENFORCED_PREFS["privacy.trackingprotection.enabled"] is True
    assert _st.FIREFOX_ENFORCED_PREFS["privacy.trackingprotection.socialtracking.enabled"] is True


def test_enforced_prefs_safebrowsing_remote_disabled() -> None:
    assert _st.FIREFOX_ENFORCED_PREFS["browser.safebrowsing.downloads.remote.enabled"] is False


def test_enforced_prefs_pocket_disabled() -> None:
    assert _st.FIREFOX_ENFORCED_PREFS["extensions.pocket.enabled"] is False


# ---------------------------------------------------------------------------
# format_firefox_pref
# ---------------------------------------------------------------------------

def test_format_pref_bool_true() -> None:
    result = _st.format_firefox_pref("some.pref", True)
    assert result == 'user_pref("some.pref", true);'


def test_format_pref_bool_false() -> None:
    result = _st.format_firefox_pref("some.pref", False)
    assert result == 'user_pref("some.pref", false);'


def test_format_pref_string() -> None:
    result = _st.format_firefox_pref("toolkit.telemetry.server", "data:,")
    assert result == 'user_pref("toolkit.telemetry.server", "data:,");'


def test_format_pref_empty_string() -> None:
    result = _st.format_firefox_pref("browser.startup.homepage", "")
    assert result == 'user_pref("browser.startup.homepage", "");'


def test_format_pref_int() -> None:
    result = _st.format_firefox_pref("network.cookie.cookieBehavior", 1)
    assert result == 'user_pref("network.cookie.cookieBehavior", 1);'


def test_format_pref_float() -> None:
    result = _st.format_firefox_pref("some.float", 1.5)
    assert result == 'user_pref("some.float", 1.5);'


# ---------------------------------------------------------------------------
# write_firefox_userjs
# ---------------------------------------------------------------------------

def test_write_userjs_creates_file(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    _st.write_firefox_userjs(profile, {"toolkit.telemetry.enabled": False})
    user_js = profile / "user.js"
    assert user_js.exists()
    assert 'user_pref("toolkit.telemetry.enabled", false);' in user_js.read_text()


def test_write_userjs_merges_new_prefs(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    existing = profile / "user.js"
    existing.write_text('user_pref("existing.pref", true);\n')
    _st.write_firefox_userjs(profile, {"new.pref": False})
    content = existing.read_text()
    assert 'user_pref("existing.pref", true);' in content
    assert 'user_pref("new.pref", false);' in content


def test_write_userjs_updates_existing_pref(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    existing = profile / "user.js"
    existing.write_text('user_pref("toolkit.telemetry.enabled", true);\n')
    _st.write_firefox_userjs(profile, {"toolkit.telemetry.enabled": False})
    content = existing.read_text()
    assert 'user_pref("toolkit.telemetry.enabled", false);' in content
    assert 'user_pref("toolkit.telemetry.enabled", true);' not in content


def test_write_userjs_preserves_comments(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    existing = profile / "user.js"
    existing.write_text("// my custom comment\n")
    _st.write_firefox_userjs(profile, {"new.pref": True})
    content = existing.read_text()
    assert "// my custom comment" in content


def test_write_userjs_all_enforced_prefs(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    _st.write_firefox_userjs(profile, _st.FIREFOX_ENFORCED_PREFS)
    content = (profile / "user.js").read_text()
    for key in REQUIRED_TELEMETRY_KEYS + REQUIRED_PRIVACY_KEYS + REQUIRED_UI_KEYS:
        assert key in content, f"user.js missing pref: {key}"


# ---------------------------------------------------------------------------
# infra/firefox/policies.json
# ---------------------------------------------------------------------------

def test_policies_json_exists() -> None:
    assert POLICIES_JSON.exists(), "infra/firefox/policies.json must exist"


def test_policies_json_valid() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    assert "policies" in data


def test_policies_json_disables_telemetry() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    policies = data["policies"]
    assert policies.get("DisableTelemetry") is True


def test_policies_json_disables_studies() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    assert data["policies"].get("DisableFirefoxStudies") is True


def test_policies_json_disables_pocket() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    assert data["policies"].get("DisablePocket") is True


def test_policies_json_ublock_origin_installed() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    ext_settings = data["policies"].get("ExtensionSettings", {})
    ublock = ext_settings.get("uBlock0@raymondhill.net")
    assert ublock is not None, "uBlock Origin must be in ExtensionSettings"
    assert "install_url" in ublock
    assert "installation_mode" in ublock
    assert "ublock-origin" in ublock["install_url"]


def test_policies_json_tracking_protection_enabled() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    etp = data["policies"].get("EnableTrackingProtection", {})
    assert etp.get("Value") is True
    assert etp.get("Cryptomining") is True
    assert etp.get("Fingerprinting") is True
