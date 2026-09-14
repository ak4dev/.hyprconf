"""modules/firefox-theme — Omarchy's rendered userChrome.css into Firefox.
HERMETIC: the `box` fixture, its omarchy-hook-install and omarchy-theme-refresh
made to act the way bin/omarchy-hook-install:27-29 and omarchy-theme-refresh:8 do.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import HOOK_INSTALL, Box

MODULE = Path(__file__).parent
INSTALL, HOOK, TPL = MODULE / "install", MODULE / "hook", MODULE / "userChrome.css.tpl"
THEMED = ".config/omarchy/themed/userChrome.css.tpl"
INSTALLED_HOOK = ".config/omarchy/hooks/theme-set.d/10-hyprconf"
RENDER = ".local/state/omarchy/current/theme/userChrome.css"
THEME_NAME = ".local/state/omarchy/current/theme.name"
XDG, LEGACY = ".config/mozilla/firefox", ".mozilla/firefox"
PROFILE, OTHER = "aaa.default-release", "bbb.default"

# omarchy-theme-refresh:8 is omarchy-theme-set of theme.name, which ends in
# `omarchy-hook theme-set` (omarchy-theme-set:341): a refresh re-runs the hook.
THEME_REFRESH = (
    'h="$HOME/.config/omarchy/hooks/theme-set.d/10-hyprconf"\n'
    '[[ -f $h ]] && bash "$h" "$(cat "$HOME/.local/state/omarchy/current/theme.name")"\nexit 0\n'
)

# profiles.ini in the shapes Firefox 155.0.1-1 writes.
P0 = f"[Profile0]\nName=one\nIsRelative=1\nPath={PROFILE}\n"
P1 = f"[Profile1]\nName=two\nIsRelative=1\nPath={OTHER}\n"
INI_INSTALL = f"{P0}\n[Install0123456789ABCDEF]\nDefault={PROFILE}\nLocked=1\n\n{P1}Default=1\n"
INI_FLAGGED = f"{P0}\n{P1}Default=1\n"
INI_FIRST = f"{P0}\n{P1}"
INI_ABSOLUTE = f"[Profile0]\nName=one\nIsRelative=0\nPath={{root}}/{OTHER}\n"

PREFS = (
    'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);\n'
    'user_pref("extensions.activeThemeID", "firefox-compact-dark@mozilla.org");\n'
    'user_pref("ui.systemUsesDarkTheme", 1);\n'
)
FOREIGN = 'user_pref("browser.startup.homepage", "about:blank");'


def firefox(box: Box, ini: str = INI_INSTALL, where: str = XDG) -> Path:
    """A profile root: both profile directories and `ini`, `{root}` resolved."""
    root = box.home / where
    root.mkdir(parents=True, exist_ok=True)
    for name in (PROFILE, OTHER):
        (root / name).mkdir(exist_ok=True)
    (root / "profiles.ini").write_text(ini.format(root=root))
    return root


def rendered(box: Box, mode: str = "dark") -> Path:
    """What omarchy-theme-set-templates leaves in current/theme."""
    path = box.home / RENDER
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f":root {{\n  --hyprconf-theme-mode: {mode};\n}}\n")
    (box.home / THEME_NAME).write_text("dracula\n")
    return path


def snapshot(box: Box) -> dict[str, bytes]:
    return {str(p.relative_to(box.home)): p.read_bytes() for p in box.files()}


@pytest.fixture
def live(box: Box) -> Box:
    box.stub("omarchy-hook-install", HOOK_INSTALL)
    box.stub("omarchy-theme-refresh", THEME_REFRESH)
    return box


def test_install_lands_the_template_the_hook_and_the_themed_profile(live: Box) -> None:
    profile = firefox(live) / PROFILE
    rendered(live)
    result = live.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert (live.home / THEMED).read_bytes() == TPL.read_bytes()
    assert (live.home / INSTALLED_HOOK).read_bytes() == HOOK.read_bytes()
    assert (profile / "chrome/userChrome.css").read_bytes() == (live.home / RENDER).read_bytes()
    assert (profile / "user.js").read_text() == PREFS
    assert "omarchy-notification-send" in live.commands
    # The refresh IS a theme set, ending in the hook: install must not re-run it.
    assert "chrome/userChrome.css (" not in result.stdout


def test_a_second_run_writes_nothing_and_calls_no_mutating_command(live: Box) -> None:
    firefox(live)
    rendered(live)
    live.run(INSTALL)
    before = snapshot(live)
    live.reset()
    result = live.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert snapshot(live) == before
    assert live.commands == []


def test_install_without_a_theme_or_a_profile_still_lands_the_template_and_hook(live: Box) -> None:
    result = live.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert (live.home / THEMED).read_bytes() == TPL.read_bytes()
    assert (live.home / INSTALLED_HOOK).read_bytes() == HOOK.read_bytes()
    assert live.commands == ["omarchy-hook-install"]


@pytest.mark.parametrize(
    ("seed", "left"),
    [(FOREIGN + "\n", FOREIGN + "\n"), ("", None)],  # merged back, or ours alone: removed
)
def test_undo_restores_stock(live: Box, seed: str, left: str | None) -> None:
    profile = firefox(live) / PROFILE
    rendered(live)
    if seed:
        (profile / "user.js").write_text(seed)
    live.run(INSTALL)
    live.reset()
    result = live.undo("firefox-theme")
    assert result.returncode == 0, result.stderr
    for gone in (INSTALLED_HOOK, THEMED, RENDER):
        assert not (live.home / gone).exists()
    assert not (profile / "chrome").exists()
    js = profile / "user.js"
    assert (js.read_text() if js.exists() else None) == left
    assert live.commands == []


def test_undo_reports_a_profile_file_that_stays_and_clears_the_module_anyway(live: Box) -> None:
    """Root-proof: plain `rm -f` refuses a directory for everyone."""
    profile = firefox(live) / PROFILE
    rendered(live)
    live.run(INSTALL)
    stuck = profile / "chrome" / "userChrome.css"
    stuck.unlink()
    stuck.mkdir()
    result = live.undo("firefox-theme")
    assert result.returncode != 0
    assert "some profile files remain" in result.stderr
    assert stuck.is_dir()
    for gone in (INSTALLED_HOOK, THEMED, RENDER):
        assert not (live.home / gone).exists()


@pytest.mark.parametrize(
    ("ini", "where", "profile"),
    [
        (INI_INSTALL, XDG, PROFILE),
        (INI_FLAGGED, XDG, OTHER),
        (INI_FIRST, LEGACY, PROFILE),
        (INI_ABSOLUTE, XDG, OTHER),
    ],
)
def test_the_hook_themes_the_profile_firefox_will_start(
    box: Box, ini: str, where: str, profile: str
) -> None:
    root = firefox(box, ini, where)
    render = rendered(box)
    assert box.run(HOOK, "dracula").returncode == 0
    assert (root / profile / "chrome/userChrome.css").read_bytes() == render.read_bytes()
    assert not (root / (OTHER if profile == PROFILE else PROFILE) / "chrome").exists()


def test_the_hook_writes_the_light_prefs_for_a_light_render(box: Box) -> None:
    profile = firefox(box) / PROFILE
    rendered(box, mode="light")
    box.run(HOOK)
    user_js = (profile / "user.js").read_text()
    assert 'user_pref("extensions.activeThemeID", "firefox-compact-light@mozilla.org");' in user_js
    assert 'user_pref("ui.systemUsesDarkTheme", 0);' in user_js


def test_the_hook_keeps_foreign_user_js_lines_and_rewrites_its_own_in_place(box: Box) -> None:
    """`managed` anchors on a leading `user_pref(`: a commented-out or `pref(` line is the user's."""
    profile = firefox(box) / PROFILE
    rendered(box)
    commented = '// user_pref("ui.systemUsesDarkTheme", 0);'
    bare = 'pref("extensions.activeThemeID", "firefox-compact-light@mozilla.org");'
    (profile / "user.js").write_text(
        f'{FOREIGN}\nuser_pref("ui.systemUsesDarkTheme", 0);\n{commented}\n{bare}\n'
    )
    box.run(HOOK)
    first = (profile / "user.js").read_text()
    box.reset()
    box.run(HOOK)
    assert (profile / "user.js").read_text() == first
    assert first.splitlines() == [FOREIGN, commented, bare, *PREFS.splitlines()]
    assert box.commands == []  # nothing changed the second time


@pytest.mark.parametrize("blocked", ["user.js", "user.js.$$.tmp"])
def test_a_write_the_hook_cannot_make_is_reported_and_takes_nothing_away(
    box: Box, blocked: str
) -> None:
    """Bash 5.3.15's failed-redirection status 1, which `!` does not invert, must never read as
    "user.js held nothing but ours"; the temp is $$-named, so the wrapper `exec`s the hook."""
    profile = firefox(box) / PROFILE
    rendered(box)
    kept = None if blocked == "user.js" else FOREIGN + "\n"
    if kept:
        (profile / "user.js").write_text(kept)
    wrapper = box.tmp / "same-pid"
    wrapper.write_text(f'mkdir "{profile}/{blocked}"\nexec bash "{HOOK}"\n')
    result = box.run(wrapper)
    assert result.returncode != 0
    js = profile / "user.js"
    assert js.exists()
    assert (js.read_text() if js.is_file() else None) == kept


def test_the_hook_is_a_no_op_without_a_render(box: Box) -> None:
    firefox(box)
    before = snapshot(box)
    result = box.run(HOOK, "dracula")
    assert result.returncode == 0
    assert snapshot(box) == before
    assert box.commands == []


# omarchy-theme-set-templates:195-207 substitutes one `s|{{ <key> }}|<value>|g`
# per palette key; dark_background (:236) and lighter_background (:226) are
# derived when the theme's colors.toml omits them.
PALETTE = ("mode", "background", "foreground", "accent", "dark_background", "lighter_background")


def test_the_template_declares_the_mode_and_renders_with_no_token_left_over() -> None:
    css = TPL.read_text()
    assert "--hyprconf-theme-mode: {{ mode }};" in css  # what the hook greps back
    for key in PALETTE:
        css = css.replace(f"{{{{ {key} }}}}", "x")
    assert "{{" not in css
