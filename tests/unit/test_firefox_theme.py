"""Tests for hyprconf.firefox_theme — Firefox/LibreWolf chrome from Omarchy's theme.

Omarchy ships no Firefox theming (omarchy-theme-set-browser is Chromium-only),
so this module is the overlay's own bridge, run from the theme-set hook. It
must: find the right profiles the way Firefox does (every [Install…] Default
— each build honours only its own section — falling back to a Profile
Default=1, then the first profile), colour a userChrome.css from the
colors.toml Omarchy renders, merge — never clobber — the profile's user.js,
and be idempotent, since the hook re-runs on every theme switch and every
install.sh run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hyprconf import firefox_theme as ft

COLORS = """\
mode = "dark"
accent = "#8bc9eb"
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


@pytest.fixture(autouse=True)
def notices(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What main() announced. notify() runs omarchy-notification-send when it
    is on PATH, so it is replaced for every test, not per test."""
    sent: list[str] = []
    monkeypatch.setattr(ft, "notify", sent.append)
    return sent


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
    assert ft.default_profiles(ini) == [tmp_path / "new.default-release"]


def test_every_install_section_names_its_own_profile(tmp_path: Path) -> None:
    """Two builds sharing one profiles.ini (the package and, say, Developer
    Edition) each keep an [Install<hash of their install dir>] section and
    honour only their own, so both profiles must be themed — there is no
    telling which build starts next."""
    (tmp_path / "release.default-release").mkdir()
    (tmp_path / "dev.dev-edition-default").mkdir()
    ini = _ini(
        tmp_path,
        "[Profile0]\nPath=release.default-release\nIsRelative=1\n\n"
        "[Profile1]\nPath=dev.dev-edition-default\nIsRelative=1\n\n"
        "[Install4F96D1932A9F858E]\nDefault=release.default-release\nLocked=1\n\n"
        "[Install11457493C5A56847]\nDefault=dev.dev-edition-default\nLocked=1\n",
    )
    assert ft.default_profiles(ini) == [
        tmp_path / "release.default-release",
        tmp_path / "dev.dev-edition-default",
    ]


def test_install_sections_naming_the_same_profile_are_deduplicated(tmp_path: Path) -> None:
    (tmp_path / "one.default-release").mkdir()
    ini = _ini(
        tmp_path,
        "[Profile0]\nPath=one.default-release\nIsRelative=1\nDefault=1\n\n"
        "[InstallAAAA]\nDefault=one.default-release\n\n"
        "[InstallBBBB]\nDefault=one.default-release\n",
    )
    assert ft.default_profiles(ini) == [tmp_path / "one.default-release"]


def test_profile_default_flag_then_first_profile_when_no_install_section(tmp_path: Path) -> None:
    ini = _ini(
        tmp_path,
        "[Profile0]\nPath=a.default\nIsRelative=1\n\n[Profile1]\nPath=b.default\nIsRelative=1\nDefault=1\n",
    )
    assert ft.default_profiles(ini) == [tmp_path / "b.default"]
    ini2 = _ini(tmp_path / "second", "[Profile0]\nPath=only.default\nIsRelative=1\n")
    assert ft.default_profiles(ini2) == [tmp_path / "second" / "only.default"]
    # An [Install] pointing at a profile that no longer exists is not a default.
    (tmp_path / "third" / "live.default").mkdir(parents=True)
    ini3 = _ini(
        tmp_path / "third",
        "[Profile0]\nPath=live.default\nIsRelative=1\n\n[InstallDEAD]\nDefault=gone.default\n",
    )
    assert ft.default_profiles(ini3) == [tmp_path / "third" / "live.default"]


def test_absolute_profile_path(tmp_path: Path) -> None:
    ini = _ini(tmp_path, f"[Profile0]\nPath={tmp_path}/elsewhere\nIsRelative=0\nDefault=1\n")
    assert ft.default_profiles(ini) == [tmp_path / "elsewhere"]
    (tmp_path / "abs").mkdir()
    ini2 = _ini(tmp_path / "other", f"[InstallABCD]\nDefault={tmp_path}/abs\n")
    assert ft.default_profiles(ini2) == [tmp_path / "abs"]


def test_unparseable_or_empty_ini_yields_nothing(tmp_path: Path) -> None:
    assert ft.default_profiles(_ini(tmp_path, "[General]\nVersion=2\n")) == []
    assert ft.default_profiles(_ini(tmp_path / "bad", "not an ini\n[[[")) == []


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
    # Only roles the stylesheet renders are carried.
    assert set(p) == {
        "mode",
        "background",
        "foreground",
        "accent",
        "dark_background",
        "lighter_background",
    }


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
    # browser.theme.{content,toolbar}-theme are what Firefox writes from the
    # active theme, not inputs — exactly three prefs are managed.
    assert (
        set(dark)
        == set(light)
        == {
            "toolkit.legacyUserProfileCustomizations.stylesheets",
            "extensions.activeThemeID",
            "ui.systemUsesDarkTheme",
        }
    )


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


def test_merge_user_js_recognises_single_quoted_keys() -> None:
    """Firefox's pref parser takes either quote style; a single-quoted managed
    pref must be replaced, not left behind as a duplicate."""
    assert ft._pref_key("user_pref('ui.systemUsesDarkTheme', 0);") == "ui.systemUsesDarkTheme"
    assert ft._pref_key('user_pref("ui.systemUsesDarkTheme", 0);') == "ui.systemUsesDarkTheme"
    assert ft._pref_key("user_pref(\"a\", 'x');") == "a"
    assert ft._pref_key('// user_pref("a", 1);') is None
    assert ft._pref_key('pref("a", 1);') is None


def test_merge_user_js_replaces_a_single_quoted_managed_line(tmp_path: Path) -> None:
    user_js = tmp_path / "user.js"
    user_js.write_text("user_pref('ui.systemUsesDarkTheme', 0);\n")
    ft.merge_user_js(user_js, {"ui.systemUsesDarkTheme": 1})
    assert user_js.read_text() == 'user_pref("ui.systemUsesDarkTheme", 1);\n'


def test_merge_user_js_keeps_the_users_inline_comment(tmp_path: Path) -> None:
    user_js = tmp_path / "user.js"
    user_js.write_text(
        'user_pref("ui.systemUsesDarkTheme", 0); // set by hand\n'
        'user_pref("extensions.activeThemeID", "default-theme@mozilla.org"); /* was */\n'
        'user_pref("keep.me", "a); b"); // tricky value\n'
    )
    ft.merge_user_js(user_js, {"ui.systemUsesDarkTheme": 1, "extensions.activeThemeID": "x@y"})
    assert user_js.read_text() == (
        'user_pref("ui.systemUsesDarkTheme", 1); // set by hand\n'
        'user_pref("extensions.activeThemeID", "x@y"); /* was */\n'
        'user_pref("keep.me", "a); b"); // tricky value\n'
    )


def test_merge_user_js_drops_later_duplicates_of_a_managed_key(tmp_path: Path) -> None:
    user_js = tmp_path / "user.js"
    user_js.write_text(
        'user_pref("ui.systemUsesDarkTheme", 0); // first\n'
        "// between\n"
        "user_pref('ui.systemUsesDarkTheme', 0);\n"
    )
    ft.merge_user_js(user_js, {"ui.systemUsesDarkTheme": 1})
    assert user_js.read_text() == 'user_pref("ui.systemUsesDarkTheme", 1); // first\n// between\n'


def test_merge_user_js_drops_prefs_an_earlier_release_managed(tmp_path: Path) -> None:
    """browser.theme.{content,toolbar}-theme used to be written here; Firefox
    derives them from the active theme, so a stale 0 left behind would force
    dark toolbars under a light theme. They go, everything else stays."""
    user_js = tmp_path / "user.js"
    user_js.write_text(
        'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);\n'
        'user_pref("browser.theme.content-theme", 0);\n'
        'user_pref("keep.me", 1);\n'
        "user_pref('browser.theme.toolbar-theme', 0); // by hand\n"
    )
    assert ft.merge_user_js(user_js, ft.theme_prefs("light"))
    text = user_js.read_text()
    assert "browser.theme" not in text
    assert 'user_pref("keep.me", 1);\n' in text
    assert f'user_pref("extensions.activeThemeID", "{ft.THEME_ID_LIGHT}");' in text
    # Second pass: nothing left to retire, nothing to change.
    assert not ft.merge_user_js(user_js, ft.theme_prefs("light"))


def test_merge_user_js_preserves_crlf_line_endings(tmp_path: Path) -> None:
    user_js = tmp_path / "user.js"
    user_js.write_bytes(b'// mine\r\nuser_pref("ui.systemUsesDarkTheme", 0);\r\n')
    assert ft.merge_user_js(user_js, {"ui.systemUsesDarkTheme": 1, "x.y": True}) is True
    assert user_js.read_bytes() == (
        b'// mine\r\nuser_pref("ui.systemUsesDarkTheme", 1);\r\nuser_pref("x.y", true);\r\n'
    )
    # And a second run is a byte-for-byte no-op, CRLF included.
    assert ft.merge_user_js(user_js, {"ui.systemUsesDarkTheme": 1, "x.y": True}) is False
    assert b"\r\n" in user_js.read_bytes() and b"\n\n" not in user_js.read_bytes()


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


def _two_install_home(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A home whose profiles.ini carries two [Install…] sections — the package
    and a Developer Edition, each naming its own profile."""
    home, release = _home_with_theme_and_profile(tmp_path)
    ff = release.parent
    dev = ff / "dev.dev-edition-default"
    dev.mkdir()
    _ini(
        ff,
        "[Profile0]\nPath=abc.default-release\nIsRelative=1\n\n"
        "[Profile1]\nPath=dev.dev-edition-default\nIsRelative=1\n\n"
        "[InstallAAAA]\nDefault=abc.default-release\n\n"
        "[InstallBBBB]\nDefault=dev.dev-edition-default\n",
    )
    return home, release, dev


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


def test_main_themes_each_installs_profile_and_announces_the_browser_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    notices: list[str],
) -> None:
    home, release, dev = _two_install_home(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    assert ft.main([]) == 0
    for profile in (release, dev):
        assert (profile / "chrome" / "userChrome.css").is_file()
        assert "firefox-compact-dark@mozilla.org" in (profile / "user.js").read_text()
    out = capsys.readouterr().out
    assert out.count("firefox: ") == 2 and "restart firefox" in out.lower()
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


# ---------------------------------------------------------------------------
# --status: the "has Firefox restarted?" question, answered from prefs.js
# ---------------------------------------------------------------------------


def test_status_reports_restart_state_from_prefs_js(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home, profile = _home_with_theme_and_profile(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    assert ft.main([]) == 0
    capsys.readouterr()

    # Firefox has not been restarted: prefs.js still names the default theme.
    (profile / "prefs.js").write_text(
        'user_pref("extensions.activeThemeID", "default-theme@mozilla.org");\n'
    )
    assert ft.main(["--status"]) == 0
    out = capsys.readouterr().out
    assert "userChrome.css: written" in out
    assert "3/3 managed prefs present" in out
    assert "restarted since the files were written: NO" in out

    # After a restart Firefox writes the theme it activated from user.js.
    (profile / "prefs.js").write_text(
        'user_pref("extensions.activeThemeID", "firefox-compact-dark@mozilla.org");\n'
    )
    assert ft.main(["--status"]) == 0
    assert "restarted since the files were written: yes" in capsys.readouterr().out


def test_status_reports_every_installs_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home, release, dev = _two_install_home(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    assert ft.main(["--status"]) == 0
    out = capsys.readouterr().out
    assert f"firefox: profile {release}" in out and f"firefox: profile {dev}" in out
    assert out.count("userChrome.css: MISSING") == 2
    assert out.count("0/3 managed prefs present") == 2


def test_status_without_a_profile_or_theme_still_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    assert ft.main(["--status"]) == 0
    out = capsys.readouterr().out
    assert "colors.toml: MISSING" in out and "no Firefox/LibreWolf profile" in out
