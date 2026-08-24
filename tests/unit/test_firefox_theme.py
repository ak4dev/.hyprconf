"""Tests for hyprconf.firefox_theme — Firefox/LibreWolf chrome from Omarchy's theme.

Omarchy ships no Firefox theming (omarchy-theme-set-browser is Chromium-only),
so this module is the overlay's own bridge, run from the theme-set hook. It
must: find the right profile the way Firefox does (an [Install…] Default
wins over a Profile Default=1, which wins over the first profile), colour a
userChrome.css from the colors.toml Omarchy renders, merge — never clobber —
the profile's user.js, and be idempotent, since the hook re-runs on every
theme switch and every install.sh run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hyprconf import firefox_theme as ft

COLORS = """\
mode = "dark"
accent = "#8bc9eb"
selection = "#243d56"
muted = "#304860"
background = "#16242d"
dark_background = "#101b21"
lighter_background = "#1b2d40"
foreground = "#d6e2ee"
"""


def _ini(root: Path, body: str) -> Path:
    ini = root / "profiles.ini"
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_text(body)
    return ini


# ---------------------------------------------------------------------------
# Profile discovery
# ---------------------------------------------------------------------------


def test_install_default_wins_over_profile_default(tmp_path: Path) -> None:
    """Modern Firefox records the profile it last used per install; that is
    the one the user sees, even when an older [Profile] still says Default=1."""
    (tmp_path / "new.default-release").mkdir()
    (tmp_path / "old.default").mkdir()
    ini = _ini(
        tmp_path,
        "[Profile0]\nName=default-release\nIsRelative=1\nPath=new.default-release\n\n"
        "[Install4F96]\nDefault=new.default-release\nLocked=1\n\n"
        "[Profile1]\nName=default\nIsRelative=1\nPath=old.default\nDefault=1\n",
    )
    assert ft.default_profile(ini) == tmp_path / "new.default-release"


def test_profile_default_flag_then_first_profile(tmp_path: Path) -> None:
    ini = _ini(
        tmp_path,
        "[Profile0]\nPath=a.default\nIsRelative=1\n\n[Profile1]\nPath=b.default\nIsRelative=1\nDefault=1\n",
    )
    assert ft.default_profile(ini) == tmp_path / "b.default"
    ini2 = _ini(tmp_path / "second", "[Profile0]\nPath=only.default\nIsRelative=1\n")
    assert ft.default_profile(ini2) == tmp_path / "second" / "only.default"


def test_absolute_profile_path(tmp_path: Path) -> None:
    ini = _ini(tmp_path, f"[Profile0]\nPath={tmp_path}/elsewhere\nIsRelative=0\nDefault=1\n")
    assert ft.default_profile(ini) == tmp_path / "elsewhere"


def test_unparseable_or_empty_ini_yields_none(tmp_path: Path) -> None:
    assert ft.default_profile(_ini(tmp_path, "[General]\nVersion=2\n")) is None
    assert ft.default_profile(_ini(tmp_path / "bad", "not an ini\n[[[")) is None


def test_profile_inis_finds_firefox_and_librewolf_under_home(tmp_path: Path) -> None:
    _ini(tmp_path / ".config" / "mozilla" / "firefox", "[Profile0]\nPath=x\n")
    _ini(tmp_path / ".librewolf", "[Profile0]\nPath=y\n")
    found = ft.profile_inis(tmp_path)
    assert [b for b, _ in found] == ["firefox", "librewolf"]


# ---------------------------------------------------------------------------
# Palette -> stylesheet and prefs
# ---------------------------------------------------------------------------


def test_palette_reads_omarchy_colors_toml_with_defaults(tmp_path: Path) -> None:
    toml = tmp_path / "colors.toml"
    toml.write_text('mode = "light"\nbackground = "#ffffff"\naccent = ""\n')
    p = ft.read_palette(toml)
    assert p["mode"] == "light" and p["background"] == "#ffffff"
    # Missing or blank keys fall back rather than emitting an empty colour.
    assert p["accent"] == ft.DEFAULT_PALETTE["accent"]
    assert p["foreground"] == ft.DEFAULT_PALETTE["foreground"]


def test_userchrome_uses_the_lightweight_theme_variables() -> None:
    css = ft.render_userchrome({**ft.DEFAULT_PALETTE, "background": "#16242d", "accent": "#8bc9eb"})
    assert css.startswith(ft.HEADER)
    assert "--toolbar-bgcolor: #16242d !important;" in css
    assert "--lwt-accent-color: #16242d !important;" in css
    assert "--focus-outline-color: #8bc9eb !important;" in css
    assert "--lwt-sidebar-background-color: #16242d !important;" in css
    for var in ("--lwt-text-color", "--toolbar-field-background-color", "--tab-selected-bgcolor"):
        assert var in css
    # Direct chrome selectors too, so the colours hold under any active theme.
    assert "#navigator-toolbox, #TabsToolbar, #nav-bar, #PersonalToolbar {" in css
    assert ".tab-background[selected] {" in css and "#urlbar-background, #searchbar {" in css
    assert css.count("#16242d !important") >= 4


def test_theme_prefs_follow_the_mode() -> None:
    dark = ft.theme_prefs("dark")
    light = ft.theme_prefs("light")
    assert dark["toolkit.legacyUserProfileCustomizations.stylesheets"] is True
    # The variables only apply under a lightweight theme: the built-in one is
    # activated, dark or light to match the palette.
    assert dark["extensions.activeThemeID"] == "firefox-compact-dark@mozilla.org"
    assert light["extensions.activeThemeID"] == "firefox-compact-light@mozilla.org"
    assert dark["ui.systemUsesDarkTheme"] == 1 and light["ui.systemUsesDarkTheme"] == 0
    assert dark["browser.theme.content-theme"] == 0 and light["browser.theme.content-theme"] == 1


def test_format_pref_literals() -> None:
    assert ft.format_pref("a.b", True) == 'user_pref("a.b", true);'
    assert ft.format_pref("a.b", 0) == 'user_pref("a.b", 0);'
    assert ft.format_pref("a.b", 'say "hi"') == 'user_pref("a.b", "say \\"hi\\"");'


# ---------------------------------------------------------------------------
# user.js merge
# ---------------------------------------------------------------------------


def test_merge_user_js_replaces_managed_keys_and_keeps_the_rest(tmp_path: Path) -> None:
    user_js = tmp_path / "user.js"
    user_js.write_text(
        "// mine\n"
        'user_pref("browser.startup.homepage", "about:blank");\n'
        'user_pref("ui.systemUsesDarkTheme", 0);\n'
    )
    ft.merge_user_js(user_js, {"ui.systemUsesDarkTheme": 1, "x.y": True})
    body = user_js.read_text()
    assert "// mine" in body
    assert 'user_pref("browser.startup.homepage", "about:blank");' in body
    assert body.count("ui.systemUsesDarkTheme") == 1
    assert 'user_pref("ui.systemUsesDarkTheme", 1);' in body
    assert 'user_pref("x.y", true);' in body


def test_merge_user_js_creates_the_file(tmp_path: Path) -> None:
    ft.merge_user_js(tmp_path / "user.js", {"a": 1})
    assert (tmp_path / "user.js").read_text() == 'user_pref("a", 1);\n'


# ---------------------------------------------------------------------------
# apply + main
# ---------------------------------------------------------------------------


def _home_with_theme_and_profile(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    theme = home / ".local" / "state" / "omarchy" / "current" / "theme"
    theme.mkdir(parents=True)
    (theme / "colors.toml").write_text(COLORS)
    ff = home / ".config" / "mozilla" / "firefox"
    profile = ff / "abc.default-release"
    profile.mkdir(parents=True)
    _ini(ff, "[Profile0]\nPath=abc.default-release\nIsRelative=1\nDefault=1\n")
    return home, profile


def test_apply_writes_stylesheet_and_prefs_idempotently(tmp_path: Path) -> None:
    _, profile = _home_with_theme_and_profile(tmp_path)
    palette = ft.read_palette(
        tmp_path / "home" / ".local" / "state" / "omarchy" / "current" / "theme" / "colors.toml"
    )
    assert ft.apply(profile, palette) is True
    css = (profile / "chrome" / "userChrome.css").read_text()
    js = (profile / "user.js").read_text()
    assert "#16242d" in css and "#8bc9eb" in css
    assert 'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);' in js
    assert 'user_pref("ui.systemUsesDarkTheme", 1);' in js

    assert ft.apply(profile, palette) is False  # nothing to rewrite, nothing to announce
    assert (profile / "chrome" / "userChrome.css").read_text() == css
    assert (profile / "user.js").read_text() == js


def test_main_themes_every_default_profile_under_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home, profile = _home_with_theme_and_profile(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    notices: list[str] = []
    monkeypatch.setattr(ft, "notify", notices.append)
    assert ft.main([]) == 0
    assert (profile / "chrome" / "userChrome.css").is_file()
    out = capsys.readouterr().out
    assert "firefox:" in out and "restart firefox" in out.lower()
    # Firefox reads userChrome.css at startup only: the change is announced
    # once, through Omarchy's notification command, and not on a no-op re-run.
    assert notices == ["Restart firefox to apply the new theme"]
    assert ft.main([]) == 0
    assert len(notices) == 1


def test_main_without_a_theme_fails_and_without_a_profile_is_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    assert ft.main([]) == 1
    assert "no" in capsys.readouterr().err

    theme = home / ".local" / "state" / "omarchy" / "current" / "theme"
    theme.mkdir(parents=True)
    (theme / "colors.toml").write_text(COLORS)
    assert ft.main([]) == 0
    assert "nothing to do" in capsys.readouterr().out
