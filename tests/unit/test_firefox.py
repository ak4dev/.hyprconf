"""
Tests for Firefox-related logic in switch_theme.py and infra/firefox/policies.json.

Covers:
- FIREFOX_ENFORCED_PREFS contains all required telemetry/privacy/userChrome keys
- format_firefox_pref formats bool, string, and int values correctly
- write_firefox_userjs merges new prefs, updates existing ones, preserves others
- get_firefox_builtin_theme_id returns correct compact theme for dark/light themes
- write_firefox_userchrome generates valid CSS with palette colors
- set_firefox_theme_activation returns bool (True=found, False=not found)
- update_firefox runs for all themes (no firefox key → falls back to compact theme)
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
    # Released-Firefox vertical-tabs prefs (137+).
    "sidebar.revamp",
    "sidebar.verticalTabs",
    # Legacy/nightly vertical-tabs prefs, kept for back-compat.
    "browser.tabs.verticalTabs",
    "browser.tabs.verticalTabs.showPinnedTabs",
    "toolkit.legacyUserProfileCustomizations.stylesheets",
    "browser.compactmode.show",
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
    # The sidebar.* prefs are what actually enable vertical tabs in current Firefox.
    assert _st.FIREFOX_ENFORCED_PREFS["sidebar.revamp"] is True
    assert _st.FIREFOX_ENFORCED_PREFS["sidebar.verticalTabs"] is True
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


# ---------------------------------------------------------------------------
# get_firefox_builtin_theme_id
# ---------------------------------------------------------------------------

_DARK_THEME  = {"background": "#1e1e2e", "foreground": "#cdd6f4", "accent": "#cba6f7"}
_LIGHT_THEME = {"background": "#eff1f5", "foreground": "#4c4f69", "accent": "#8839ef"}


def test_builtin_theme_id_dark() -> None:
    tid = _st.get_firefox_builtin_theme_id(_DARK_THEME)
    assert tid == _st.FIREFOX_COMPACT_DARK_ID


def test_builtin_theme_id_light() -> None:
    tid = _st.get_firefox_builtin_theme_id(_LIGHT_THEME)
    assert tid == _st.FIREFOX_COMPACT_LIGHT_ID


def test_builtin_theme_id_no_background_defaults_dark() -> None:
    tid = _st.get_firefox_builtin_theme_id({})
    assert tid == _st.FIREFOX_COMPACT_DARK_ID


# ---------------------------------------------------------------------------
# write_firefox_userchrome
# ---------------------------------------------------------------------------

def test_write_userchrome_creates_chrome_dir(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    _st.write_firefox_userchrome(profile, _DARK_THEME)
    assert (profile / "chrome" / "userChrome.css").exists()


def test_write_userchrome_contains_palette_colors(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    _st.write_firefox_userchrome(profile, _DARK_THEME)
    css = (profile / "chrome" / "userChrome.css").read_text()
    assert _DARK_THEME["background"] in css
    assert _DARK_THEME["foreground"] in css
    assert _DARK_THEME["accent"] in css


def test_write_userchrome_light_theme(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    _st.write_firefox_userchrome(profile, _LIGHT_THEME)
    css = (profile / "chrome" / "userChrome.css").read_text()
    assert _LIGHT_THEME["background"] in css
    assert _LIGHT_THEME["foreground"] in css


def test_write_userchrome_uses_comment_for_fields(tmp_path: Path) -> None:
    theme = {**_DARK_THEME, "comment": "#313244"}
    profile = tmp_path / "profile"
    profile.mkdir()
    _st.write_firefox_userchrome(profile, theme)
    css = (profile / "chrome" / "userChrome.css").read_text()
    assert "#313244" in css


def test_write_userchrome_overwritten_on_second_call(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    _st.write_firefox_userchrome(profile, _DARK_THEME)
    _st.write_firefox_userchrome(profile, _LIGHT_THEME)
    css = (profile / "chrome" / "userChrome.css").read_text()
    assert _LIGHT_THEME["background"] in css
    assert _DARK_THEME["background"] not in css


def test_write_userchrome_contains_lwt_variables(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    _st.write_firefox_userchrome(profile, _DARK_THEME)
    css = (profile / "chrome" / "userChrome.css").read_text()
    assert "--lwt-accent-color" in css
    assert "--toolbar-bgcolor" in css
    assert "--tab-selected-bgcolor" in css


# ---------------------------------------------------------------------------
# set_firefox_theme_activation return value
# ---------------------------------------------------------------------------

def _make_extensions_json(tmp_path: Path, themes: list) -> Path:
    data = {"addons": themes}
    p = tmp_path / "extensions.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_set_activation_returns_true_when_found(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    _make_extensions_json(profile, [
        {"id": "firefox-compact-dark@mozilla.org", "type": "theme",
         "location": "app-builtin", "active": False, "userDisabled": True},
    ])
    result = _st.set_firefox_theme_activation(profile, "firefox-compact-dark@mozilla.org")
    assert result is True


def test_set_activation_returns_false_when_not_found(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    _make_extensions_json(profile, [
        {"id": "some-other-theme@example.com", "type": "theme",
         "location": "app-builtin", "active": True, "userDisabled": False},
    ])
    result = _st.set_firefox_theme_activation(profile, "firefox-compact-dark@mozilla.org")
    assert result is False


def test_set_activation_returns_false_no_extensions_json(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    result = _st.set_firefox_theme_activation(profile, "firefox-compact-dark@mozilla.org")
    assert result is False


# ---------------------------------------------------------------------------
# update_firefox — runs for all themes (no firefox key → fallback)
# ---------------------------------------------------------------------------

def _make_profile(tmp_path: Path, theme_id: str = "firefox-compact-dark@mozilla.org") -> Path:
    profile = tmp_path / "profile"
    profile.mkdir()
    _make_extensions_json(profile, [
        {"id": theme_id, "type": "theme",
         "location": "app-builtin", "active": False, "userDisabled": True},
    ])
    return profile


def test_update_firefox_runs_without_firefox_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """update_firefox must run for themes that have no 'firefox' key."""
    profile = _make_profile(tmp_path)
    monkeypatch.setattr(_st, "get_default_firefox_profile", lambda: profile)
    monkeypatch.setattr(_st, "FIREFOX_BASE_PREFS_FILE", str(tmp_path / "user.js"))

    _st.update_firefox(_DARK_THEME)

    assert (profile / "chrome" / "userChrome.css").exists()
    assert (profile / "user.js").exists()


def test_update_firefox_writes_userchrome_with_palette(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _make_profile(tmp_path)
    monkeypatch.setattr(_st, "get_default_firefox_profile", lambda: profile)
    monkeypatch.setattr(_st, "FIREFOX_BASE_PREFS_FILE", str(tmp_path / "user.js"))

    _st.update_firefox(_DARK_THEME)

    css = (profile / "chrome" / "userChrome.css").read_text()
    assert _DARK_THEME["background"] in css


def test_update_firefox_sets_dark_pref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _make_profile(tmp_path)
    monkeypatch.setattr(_st, "get_default_firefox_profile", lambda: profile)
    monkeypatch.setattr(_st, "FIREFOX_BASE_PREFS_FILE", str(tmp_path / "user.js"))

    _st.update_firefox(_DARK_THEME)

    content = (profile / "user.js").read_text()
    assert 'user_pref("ui.systemUsesDarkTheme", 1)' in content


def test_update_firefox_sets_light_pref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _make_profile(tmp_path, theme_id="firefox-compact-light@mozilla.org")
    monkeypatch.setattr(_st, "get_default_firefox_profile", lambda: profile)
    monkeypatch.setattr(_st, "FIREFOX_BASE_PREFS_FILE", str(tmp_path / "user.js"))

    _st.update_firefox(_LIGHT_THEME)

    content = (profile / "user.js").read_text()
    assert 'user_pref("ui.systemUsesDarkTheme", 0)' in content


def test_update_firefox_skips_when_no_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_st, "get_default_firefox_profile", lambda: None)
    # Must not raise
    _st.update_firefox(_DARK_THEME)


def test_update_firefox_enables_userchrome_pref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _make_profile(tmp_path)
    monkeypatch.setattr(_st, "get_default_firefox_profile", lambda: profile)
    monkeypatch.setattr(_st, "FIREFOX_BASE_PREFS_FILE", str(tmp_path / "user.js"))

    _st.update_firefox(_DARK_THEME)

    content = (profile / "user.js").read_text()
    assert "toolkit.legacyUserProfileCustomizations.stylesheets" in content


# ---------------------------------------------------------------------------
# get_default_firefox_profile — profile path validation
# ---------------------------------------------------------------------------

def _write_profiles_ini(ini_path: Path, content: str) -> None:
    ini_path.parent.mkdir(parents=True, exist_ok=True)
    ini_path.write_text(content, encoding="utf-8")


def _patch_firefox_paths(monkeypatch: pytest.MonkeyPatch, firefox_dir: Path) -> Path:
    ini_path = firefox_dir / "profiles.ini"
    monkeypatch.setattr(_st, "FIREFOX_PROFILES_INI", str(ini_path))
    monkeypatch.setattr(_st, "FIREFOX_PROFILES_INI_XDG", str(firefox_dir / "xdg_profiles.ini"))
    monkeypatch.setattr(_st, "FIREFOX_DIR", str(firefox_dir))
    return ini_path


def test_get_default_firefox_profile_install_section_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[Install...] section pointing to an existing dir is returned."""
    firefox_dir = tmp_path / "firefox"
    profile_dir = firefox_dir / "profiles" / "abc123.default"
    profile_dir.mkdir(parents=True)
    ini = _patch_firefox_paths(monkeypatch, firefox_dir)
    _write_profiles_ini(ini, (
        "[Install1234ABCD]\n"
        "Default=profiles/abc123.default\n"
        "Locked=1\n"
    ))
    result = _st.get_default_firefox_profile()
    assert result == profile_dir


def test_get_default_firefox_profile_install_section_missing_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[Install...] section pointing to a non-existent dir falls through to Default=1."""
    real_dir = tmp_path / "firefox" / "profiles" / "real.default"
    real_dir.mkdir(parents=True)
    ini = _patch_firefox_paths(monkeypatch, tmp_path / "firefox")
    _write_profiles_ini(ini, (
        "[Install1234ABCD]\n"
        "Default=profiles/ghost.empty\n"
        "\n"
        "[Profile0]\n"
        "Name=default\n"
        "IsRelative=1\n"
        "Path=profiles/real.default\n"
        "Default=1\n"
    ))
    result = _st.get_default_firefox_profile()
    assert result == real_dir


def test_get_default_firefox_profile_default_section_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Profile with Default=1 pointing to an existing dir is returned."""
    profile_dir = tmp_path / "firefox" / "profiles" / "main.default"
    profile_dir.mkdir(parents=True)
    ini = _patch_firefox_paths(monkeypatch, tmp_path / "firefox")
    _write_profiles_ini(ini, (
        "[Profile0]\n"
        "Name=default\n"
        "IsRelative=1\n"
        "Path=profiles/main.default\n"
        "Default=1\n"
    ))
    result = _st.get_default_firefox_profile()
    assert result == profile_dir


def test_get_default_firefox_profile_default_section_missing_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default=1 pointing to non-existent dir falls through to first-profile fallback."""
    fallback_dir = tmp_path / "firefox" / "profiles" / "fallback.esr"
    fallback_dir.mkdir(parents=True)
    ini = _patch_firefox_paths(monkeypatch, tmp_path / "firefox")
    _write_profiles_ini(ini, (
        "[Profile0]\n"
        "Name=default\n"
        "IsRelative=1\n"
        "Path=profiles/ghost.default\n"
        "Default=1\n"
        "\n"
        "[Profile1]\n"
        "Name=esr\n"
        "IsRelative=1\n"
        "Path=profiles/fallback.esr\n"
    ))
    result = _st.get_default_firefox_profile()
    assert result == fallback_dir


def test_get_default_firefox_profile_fallback_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no Install/Default=1 section, first profile with an existing dir is returned."""
    profile_dir = tmp_path / "firefox" / "profiles" / "only.profile"
    profile_dir.mkdir(parents=True)
    ini = _patch_firefox_paths(monkeypatch, tmp_path / "firefox")
    _write_profiles_ini(ini, (
        "[Profile0]\n"
        "Name=only\n"
        "IsRelative=1\n"
        "Path=profiles/only.profile\n"
    ))
    result = _st.get_default_firefox_profile()
    assert result == profile_dir


def test_get_default_firefox_profile_no_valid_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All profile paths non-existent → returns None."""
    ini = _patch_firefox_paths(monkeypatch, tmp_path / "firefox")
    _write_profiles_ini(ini, (
        "[Install1234ABCD]\n"
        "Default=profiles/ghost1\n"
        "\n"
        "[Profile0]\n"
        "Name=default\n"
        "IsRelative=1\n"
        "Path=profiles/ghost2\n"
        "Default=1\n"
    ))
    result = _st.get_default_firefox_profile()
    assert result is None


def test_get_default_firefox_profile_no_profiles_ini(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing profiles.ini → returns None."""
    _patch_firefox_paths(monkeypatch, tmp_path / "firefox")
    # profiles.ini is deliberately not written
    result = _st.get_default_firefox_profile()
    assert result is None


def test_get_default_firefox_profile_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """IsRelative=0 with an absolute path is resolved and returned when it exists."""
    abs_profile = tmp_path / "external" / "profile.abs"
    abs_profile.mkdir(parents=True)
    ini = _patch_firefox_paths(monkeypatch, tmp_path / "firefox")
    _write_profiles_ini(ini, (
        f"[Profile0]\n"
        f"Name=abs\n"
        f"IsRelative=0\n"
        f"Path={abs_profile}\n"
        f"Default=1\n"
    ))
    result = _st.get_default_firefox_profile()
    assert result == abs_profile


# ---------------------------------------------------------------------------
# get_default_firefox_profile — XDG path discovery
# ---------------------------------------------------------------------------

def test_get_default_firefox_profile_xdg_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When only the XDG profiles.ini exists, the profile is still found."""
    xdg_dir = tmp_path / "xdg_firefox"
    profile_dir = xdg_dir / "abc.default-release"
    profile_dir.mkdir(parents=True)
    xdg_ini = xdg_dir / "profiles.ini"
    _write_profiles_ini(xdg_ini, (
        "[Install1234ABCD]\n"
        "Default=abc.default-release\n"
        "Locked=1\n"
    ))
    # Legacy path does NOT exist; only the XDG path does
    monkeypatch.setattr(_st, "FIREFOX_PROFILES_INI", str(tmp_path / "does_not_exist" / "profiles.ini"))
    monkeypatch.setattr(_st, "FIREFOX_PROFILES_INI_XDG", str(xdg_ini))
    result = _st.get_default_firefox_profile()
    assert result == profile_dir


def test_get_default_firefox_profile_legacy_preferred_when_both_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When both legacy and XDG profiles.ini exist, the legacy path wins."""
    legacy_dir = tmp_path / "legacy_firefox"
    legacy_profile = legacy_dir / "legacy.default"
    legacy_profile.mkdir(parents=True)
    legacy_ini = legacy_dir / "profiles.ini"
    _write_profiles_ini(legacy_ini, (
        "[Install0000AAAA]\n"
        "Default=legacy.default\n"
        "Locked=1\n"
    ))

    xdg_dir = tmp_path / "xdg_firefox"
    xdg_profile = xdg_dir / "xdg.default-release"
    xdg_profile.mkdir(parents=True)
    xdg_ini = xdg_dir / "profiles.ini"
    _write_profiles_ini(xdg_ini, (
        "[Install1111BBBB]\n"
        "Default=xdg.default-release\n"
        "Locked=1\n"
    ))

    monkeypatch.setattr(_st, "FIREFOX_PROFILES_INI", str(legacy_ini))
    monkeypatch.setattr(_st, "FIREFOX_PROFILES_INI_XDG", str(xdg_ini))
    result = _st.get_default_firefox_profile()
    assert result == legacy_profile


# ---------------------------------------------------------------------------
# LibreWolf — Firefox-fork theming via the shared engine
# (hyprconf addon librewolf)
# ---------------------------------------------------------------------------

def test_firefox_theme_prefs_enables_userchrome() -> None:
    # The minimal LibreWolf subset must still enable userChrome.css, or our
    # palette stylesheet would never load.
    assert _st.FIREFOX_THEME_PREFS["toolkit.legacyUserProfileCustomizations.stylesheets"] is True


def test_firefox_theme_prefs_is_minimal_not_full_hardening() -> None:
    # LibreWolf ships hardened — we must NOT re-impose Firefox's full enforced
    # set on it (that would fight its own choices). The subset stays small.
    assert "toolkit.telemetry.enabled" not in _st.FIREFOX_THEME_PREFS
    assert len(_st.FIREFOX_THEME_PREFS) < len(_st.FIREFOX_ENFORCED_PREFS)


def test_get_default_librewolf_profile_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lw_dir = tmp_path / "librewolf"
    profile_dir = lw_dir / "abc.default"
    profile_dir.mkdir(parents=True)
    ini = lw_dir / "profiles.ini"
    _write_profiles_ini(ini, "[Profile0]\nPath=abc.default\nIsRelative=1\nDefault=1\n")
    monkeypatch.setattr(_st, "LIBREWOLF_PROFILES_INI", str(ini))
    monkeypatch.setattr(_st, "LIBREWOLF_PROFILES_INI_XDG", str(lw_dir / "xdg.ini"))
    assert _st.get_default_librewolf_profile() == profile_dir


def test_get_default_librewolf_profile_none_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_st, "LIBREWOLF_PROFILES_INI", str(tmp_path / "nope.ini"))
    monkeypatch.setattr(_st, "LIBREWOLF_PROFILES_INI_XDG", str(tmp_path / "nope2.ini"))
    assert _st.get_default_librewolf_profile() is None


def test_update_librewolf_writes_theme_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _make_profile(tmp_path)
    monkeypatch.setattr(_st, "get_default_librewolf_profile", lambda: profile)
    monkeypatch.setattr(_st, "LIBREWOLF_BASE_PREFS_FILE", str(tmp_path / "user.js"))

    _st.update_librewolf(_DARK_THEME)

    css = (profile / "chrome" / "userChrome.css").read_text()
    assert _DARK_THEME["background"] in css
    userjs = (profile / "user.js").read_text()
    assert 'user_pref("ui.systemUsesDarkTheme", 1)' in userjs
    # userChrome enabler present so the palette stylesheet loads.
    assert "toolkit.legacyUserProfileCustomizations.stylesheets" in userjs


def test_update_librewolf_does_not_impose_full_hardening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _make_profile(tmp_path)
    monkeypatch.setattr(_st, "get_default_librewolf_profile", lambda: profile)
    monkeypatch.setattr(_st, "LIBREWOLF_BASE_PREFS_FILE", str(tmp_path / "user.js"))

    _st.update_librewolf(_DARK_THEME)

    userjs = (profile / "user.js").read_text()
    # A Firefox-only hardening pref must NOT be written for LibreWolf.
    assert "toolkit.telemetry.enabled" not in userjs


def test_update_librewolf_skips_when_no_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_st, "get_default_librewolf_profile", lambda: None)
    _st.update_librewolf(_DARK_THEME)  # must not raise


def test_update_librewolf_is_in_apply_flow() -> None:
    # The orchestrator must call update_librewolf alongside update_firefox.
    src = SWITCH_THEME_PATH.read_text(encoding="utf-8")
    assert "update_librewolf(theme)" in src

