"""modules/firefox-theme — Omarchy's rendered userChrome.css into Firefox.

The contract, in one sentence each: the template lands in Omarchy's user
template directory, the hook lands in `theme-set.d` under the basename
`10-hyprconf`, and the hook copies the render into the profile Firefox will
start plus three `user_pref` lines, leaving the rest of `user.js` alone. The
hook is what `omarchy-hook theme-set` runs, so it is tested on its own as
well as through `install`.

HERMETIC: the `box` fixture (conftest.py). `omarchy-hook-install` and
`omarchy-theme-refresh` are the two fakes that have to DO something — the
first copies the way bin/omarchy-hook-install:27-29 does, the second re-runs
the installed hook the way omarchy-theme-refresh:8 -> omarchy-theme-set:341
does — so the suite can see whether the hook is applied once or twice.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import Box

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
HOOK = MODULE / "hook"
TPL = MODULE / "userChrome.css.tpl"

THEMED = ".config/omarchy/themed/userChrome.css.tpl"
INSTALLED_HOOK = ".config/omarchy/hooks/theme-set.d/10-hyprconf"
RENDER = ".local/state/omarchy/current/theme/userChrome.css"
THEME_NAME = ".local/state/omarchy/current/theme.name"

# bin/omarchy-hook-install:27-29 — mkdir -p, cp under the file's BASENAME,
# chmod 755.
HOOK_INSTALL = """d="$HOME/.config/omarchy/hooks/$1.d"
mkdir -p "$d"
cp "$2" "$d/$(basename "$2")"
chmod 755 "$d/$(basename "$2")"
"""
# omarchy-theme-refresh:8 is omarchy-theme-set of theme.name, and
# omarchy-theme-set:341 ends with `omarchy-hook theme-set <name>` — so a
# refresh re-runs this module's hook by itself.
THEME_REFRESH = """h="$HOME/.config/omarchy/hooks/theme-set.d/10-hyprconf"
[[ -f $h ]] && bash "$h" "$(cat "$HOME/.local/state/omarchy/current/theme.name")"
exit 0
"""

# A profiles.ini in the shape Firefox 155.0.1-1 writes: an [Install<hash>]
# naming the profile it starts, and a DIFFERENT profile flagged Default=1.
INI_INSTALL = """[General]
StartWithLastProfile=1
Version=2

[Profile0]
Name=default-release
IsRelative=1
Path=aaa.default-release

[Install0123456789ABCDEF]
Default=aaa.default-release
Locked=1

[Profile1]
Name=default
IsRelative=1
Path=bbb.default
Default=1
"""
INI_FLAGGED = """[Profile0]
Name=one
IsRelative=1
Path=aaa.default-release

[Profile1]
Name=two
IsRelative=1
Path=bbb.default
Default=1
"""
INI_FIRST = """[Profile0]
Name=one
IsRelative=1
Path=aaa.default-release

[Profile1]
Name=two
IsRelative=1
Path=bbb.default
"""

PREFS = [
    'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);',
    'user_pref("extensions.activeThemeID", "firefox-compact-dark@mozilla.org");',
    'user_pref("ui.systemUsesDarkTheme", 1);',
]
FOREIGN = 'user_pref("browser.startup.homepage", "about:blank");'


def firefox(box: Box, ini: str = INI_INSTALL, where: str = ".config/mozilla/firefox") -> Path:
    """A Firefox profile root with `ini` and both profile directories."""
    root = box.home / where
    root.mkdir(parents=True, exist_ok=True)
    (root / "profiles.ini").write_text(ini)
    for name in ("aaa.default-release", "bbb.default"):
        (root / name).mkdir(exist_ok=True)
    return root


def rendered(box: Box, mode: str = "dark", theme: str | None = "dracula") -> Path:
    """What omarchy-theme-set-templates leaves in current/theme."""
    path = box.home / RENDER
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f":root {{\n  --hyprconf-theme-mode: {mode};\n}}\n")
    if theme is not None:
        (box.home / THEME_NAME).write_text(f"{theme}\n")
    return path


def snapshot(box: Box) -> dict[str, bytes]:
    return {str(p.relative_to(box.home)): p.read_bytes() for p in box.files()}


@pytest.fixture
def live(box: Box) -> Box:
    """A box where the two Omarchy commands the module calls really act."""
    box.stub("omarchy-hook-install", HOOK_INSTALL)
    box.stub("omarchy-theme-refresh", THEME_REFRESH)
    return box


# -- install ---------------------------------------------------------------


def test_install_lands_the_template_and_the_hook_and_themes_the_profile(live: Box) -> None:
    firefox(live)
    rendered(live)

    result = live.run(INSTALL)

    assert result.returncode == 0, result.stderr
    assert (live.home / THEMED).read_bytes() == TPL.read_bytes()
    assert (live.home / INSTALLED_HOOK).read_bytes() == HOOK.read_bytes()
    css = live.home / ".config/mozilla/firefox/aaa.default-release/chrome/userChrome.css"
    assert css.read_bytes() == (live.home / RENDER).read_bytes()
    assert (live.home / ".config/mozilla/firefox/aaa.default-release/user.js").read_text() == (
        "\n".join(PREFS) + "\n"
    )
    assert "omarchy-notification-send" in live.commands


def test_a_refreshed_run_does_not_run_the_hook_a_second_time(live: Box) -> None:
    """omarchy-theme-refresh IS omarchy-theme-set, which ends in `omarchy-hook
    theme-set` — so the hook has already run and install must not run it
    again (install-core.5#7). The hook's own per-profile line is the tell:
    it is swallowed on the refresh path and printed on the by-hand path."""
    firefox(live)
    rendered(live)

    result = live.run(INSTALL)

    assert "omarchy-theme-refresh" in live.commands
    assert "rendered through omarchy-theme-refresh" in result.stdout
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
    for command in ("omarchy-hook-install", "omarchy-theme-refresh", "omarchy-notification-send"):
        assert command not in live.commands
    # Steady state: the hook runs, finds everything current and says so.
    assert "chrome/userChrome.css (" in result.stdout


def test_with_no_active_theme_nothing_is_rendered_and_the_run_still_succeeds(live: Box) -> None:
    firefox(live)

    result = live.run(INSTALL)

    assert result.returncode == 0, result.stderr
    assert "no active theme yet" in result.stdout
    assert "renders it" not in result.stderr, "the hook said the same thing again"
    assert "omarchy-theme-refresh" not in live.commands
    assert not (live.home / ".config/mozilla/firefox/aaa.default-release/chrome").exists()
    assert (live.home / THEMED).is_file()


def test_install_needs_no_firefox_profile(live: Box) -> None:
    rendered(live)

    result = live.run(INSTALL)

    assert result.returncode == 0, result.stderr
    assert (live.home / INSTALLED_HOOK).is_file()


def test_undo_restores_stock(live: Box) -> None:
    root = firefox(live)
    rendered(live)
    mine = root / "aaa.default-release"
    (mine / "user.js").write_text(FOREIGN + "\n")
    live.run(INSTALL)
    assert (mine / "chrome" / "userChrome.css").is_file()

    result = live.undo("firefox-theme")

    assert result.returncode == 0, result.stderr
    assert not (live.home / INSTALLED_HOOK).exists()
    assert not (live.home / THEMED).exists()
    assert not (live.home / RENDER).exists()
    assert not (mine / "chrome").exists()
    assert (mine / "user.js").read_text() == FOREIGN + "\n"


def test_undo_still_clears_the_module_when_a_profile_file_survives(live: Box) -> None:
    """A profile file the hook cannot take away (a root-owned chrome/, ENOSPC)
    must show in `install undo`'s exit status and its warning — and must not
    keep the module's own three files standing, which is what the core loop's
    `bash … undo || true` relies on. Root-proof: plain `rm -f` refuses a
    directory for everyone."""
    root = firefox(live)
    rendered(live)
    live.run(INSTALL)
    stuck = root / "aaa.default-release" / "chrome" / "userChrome.css"
    stuck.unlink()
    stuck.mkdir()
    (stuck / "keep").write_text("x")

    result = live.undo("firefox-theme")

    assert result.returncode != 0
    assert "some profile files remain" in result.stderr
    assert stuck.is_dir()
    assert not (live.home / INSTALLED_HOOK).exists()
    assert not (live.home / THEMED).exists()
    assert not (live.home / RENDER).exists()


def test_undo_removes_a_user_js_that_was_ours_alone_and_notifies_nobody(live: Box) -> None:
    root = firefox(live)
    rendered(live)
    live.run(INSTALL)
    live.reset()

    live.undo("firefox-theme")

    assert not (root / "aaa.default-release" / "user.js").exists()
    assert "omarchy-notification-send" not in live.commands


# -- the hook --------------------------------------------------------------


@pytest.mark.parametrize(
    ("ini", "profile"),
    [
        (INI_INSTALL, "aaa.default-release"),  # [Install…] wins over Default=1
        (INI_FLAGGED, "bbb.default"),  # no [Install…]: the Default=1 profile
        (INI_FIRST, "aaa.default-release"),  # neither: the first listed
    ],
)
def test_the_hook_themes_the_profile_firefox_will_start(box: Box, ini: str, profile: str) -> None:
    root = firefox(box, ini)
    rendered(box)

    assert box.run(HOOK, "dracula").returncode == 0

    assert (root / profile / "chrome" / "userChrome.css").is_file()
    other = "bbb.default" if profile != "bbb.default" else "aaa.default-release"
    assert not (root / other / "chrome").exists()


def test_the_hook_reads_both_the_legacy_and_the_xdg_profiles_ini(box: Box) -> None:
    legacy = firefox(box, INI_FIRST, where=".mozilla/firefox")
    xdg = firefox(box, INI_FIRST)
    rendered(box)

    box.run(HOOK)

    for root in (legacy, xdg):
        assert (root / "aaa.default-release" / "chrome" / "userChrome.css").is_file()


def test_an_absolute_path_is_not_resolved_against_the_ini(box: Box) -> None:
    elsewhere = box.home / "profiles" / "somewhere"
    elsewhere.mkdir(parents=True)
    firefox(box, f"[Profile0]\nName=one\nIsRelative=0\nPath={elsewhere}\n")
    rendered(box)

    box.run(HOOK)

    assert (elsewhere / "chrome" / "userChrome.css").is_file()


def test_the_hook_writes_the_light_prefs_for_a_light_render(box: Box) -> None:
    root = firefox(box)
    rendered(box, mode="light")

    box.run(HOOK)

    user_js = (root / "aaa.default-release" / "user.js").read_text()
    assert 'user_pref("extensions.activeThemeID", "firefox-compact-light@mozilla.org");' in user_js
    assert 'user_pref("ui.systemUsesDarkTheme", 0);' in user_js


def test_the_hook_keeps_foreign_user_js_lines_and_rewrites_its_own_in_place(box: Box) -> None:
    """Only a live `user_pref(` line naming one of the three is the hook's.
    The `managed` pattern anchors on a leading `user_pref(`, so a line the
    user commented out and a `pref(` default-branch line are foreign even
    when they name the same pref — taking either away would change what
    Firefox does with a pref the hook does not own."""
    root = firefox(box)
    rendered(box)
    profile = root / "aaa.default-release"
    commented = '// user_pref("ui.systemUsesDarkTheme", 0);'
    bare = 'pref("extensions.activeThemeID", "firefox-compact-light@mozilla.org");'
    profile.joinpath("user.js").write_text(
        f'{FOREIGN}\nuser_pref("ui.systemUsesDarkTheme", 0);\n{commented}\n{bare}\n// mine\n'
    )

    box.run(HOOK)
    first = profile.joinpath("user.js").read_bytes()
    box.reset()
    box.run(HOOK)

    assert profile.joinpath("user.js").read_bytes() == first
    lines = first.decode().splitlines()
    assert lines[:4] == [FOREIGN, commented, bare, "// mine"]
    assert lines[4:] == PREFS
    assert "omarchy-notification-send" not in box.commands  # nothing changed the second time


def test_a_failed_user_js_write_is_reported_and_takes_nothing_away(box: Box) -> None:
    """The merge writes a temp file and only then replaces `user.js`. When the
    replacement fails the hook must say so in its exit status and leave what
    was there — a `user.js` that cannot be opened for writing stands in for
    the ENOSPC / root-owned cases. Root-proof: `> <a directory>` is EISDIR for
    everyone."""
    root = firefox(box)
    rendered(box)
    blocked = root / "aaa.default-release" / "user.js"
    blocked.mkdir()

    result = box.run(HOOK)

    assert result.returncode != 0
    assert blocked.is_dir()


def test_a_temp_file_the_hook_cannot_create_costs_the_user_no_user_js(box: Box) -> None:
    """The failure the guard in merge_user_js is for: `user.js.$$.tmp` cannot
    be created at all (an unwritable profile directory, a stale root-owned
    temp). Bash 5.3.15 gives a failed redirection status 1 and `!` does not
    invert it, so a guard written `if ! { ...; } > "$tmp"` never fires and the
    empty temp reads as "user.js held nothing but ours".

    The temp name is `$$`-derived, so the case is staged by a wrapper that
    takes the name and then `exec`s the hook — exec keeps the pid. That is
    root-proof, unlike an unwritable directory (AGENTS.md > Tests: root
    bypasses DAC)."""
    root = firefox(box)
    rendered(box)
    profile = root / "aaa.default-release"
    profile.joinpath("user.js").write_text(FOREIGN + "\n")
    wrapper = box.tmp / "same-pid"
    wrapper.write_text(f'mkdir "{profile}/user.js.$$.tmp"\nexec bash "{HOOK}"\n')

    result = box.run(wrapper)

    assert result.returncode != 0
    assert profile.joinpath("user.js").read_text() == FOREIGN + "\n"


def test_the_hook_rewrites_a_stale_copy_and_leaves_a_current_one_alone(box: Box) -> None:
    root = firefox(box)
    render_path = rendered(box)
    css = root / "aaa.default-release" / "chrome" / "userChrome.css"
    css.parent.mkdir(parents=True)
    css.write_text("/* last theme */\n")

    box.run(HOOK)
    assert css.read_bytes() == render_path.read_bytes()
    stamp = css.stat().st_mtime_ns
    box.reset()

    box.run(HOOK)

    assert css.stat().st_mtime_ns == stamp
    assert "omarchy-notification-send" not in box.commands


def test_the_hook_is_a_no_op_without_a_render(box: Box) -> None:
    firefox(box)
    before = snapshot(box)

    result = box.run(HOOK, "dracula")

    assert result.returncode == 0
    assert "omarchy theme refresh" in result.stderr
    assert snapshot(box) == before
    assert box.commands == []


# -- what is shipped -------------------------------------------------------


def test_the_template_declares_the_mode_the_hook_reads_back() -> None:
    assert "--hyprconf-theme-mode: {{ mode }};" in TPL.read_text()


@pytest.mark.parametrize(
    "dead",
    [
        # Absent from Firefox 155.0.1-1's stylesheets entirely (grep of both
        # omni.ja archives), or read only under :root[lwtheme], which the
        # inApp built-in themes never turn on.
        "--lwt-accent-color",
        "--lwt-text-color",
        "--lwt-sidebar-background-color",
        "--lwt-sidebar-text-color",
        "--toolbar-bgcolor",
        "--toolbar-color:",
        "--tab-selected-bgcolor",
        "--toolbar-field-color:",
        "--toolbar-field-focus-background-color",
    ],
)
def test_the_template_sets_no_variable_firefox_155_ignores(dead: str) -> None:
    assert dead not in TPL.read_text()


@pytest.mark.parametrize(
    "live_token",
    ["--toolbar-field-background-color", "--toolbar-field-focus-color", "--focus-outline-color"],
)
def test_the_template_keeps_the_variables_firefox_155_still_reads(live_token: str) -> None:
    assert f"{live_token}: {{{{" in TPL.read_text()


# What bin/omarchy-theme-set-templates:195-207 substitutes into the template:
# one `s|{{ <key> }}|<value>|g` per palette key (:200). `mode`, `background`,
# `foreground` and `accent` come straight out of the theme's colors.toml (all
# 22 shipped themes define `accent`); `lighter_background` (:226) and
# `dark_background` (:236) are derived when a theme omits them.
PALETTE = {
    "mode": "dark",
    "background": "#282a36",
    "foreground": "#f8f8f2",
    "accent": "#bd93f9",
    "dark_background": "#1e2029",
    "lighter_background": "#44475a",
}


def test_the_template_renders_with_no_token_left_over() -> None:
    """A token Omarchy does not resolve — a typo, or a name no colors.toml
    carries — ships as a literal `{{ ... }}` into every profile's
    userChrome.css, which nothing else here would catch."""
    css = TPL.read_text()
    for key, value in PALETTE.items():
        css = css.replace(f"{{{{ {key} }}}}", value)

    assert "{{" not in css
    for value in PALETTE.values():
        assert value in css


def test_the_hook_carries_nothing_of_the_checkout() -> None:
    """omarchy-hook-install COPIES the file (bin/omarchy-hook-install:28), so
    the installed hook must stand alone: no @HYPRCONF_DIR@, no PYTHONPATH,
    no python."""
    text = HOOK.read_text()
    for token in ("@HYPRCONF_DIR@", "PYTHONPATH", "python3", "hyprconf-firefox-theme"):
        assert token not in text


def test_every_omarchy_command_the_module_calls_has_a_fake(box: Box) -> None:
    """Code only: a comment's `omarchy-theme-set:341` is a citation, not a call."""
    called = {
        name
        for path in (INSTALL, HOOK)
        for line in path.read_text().splitlines()
        for name in re.findall(r"\bomarchy(?:-[a-z0-9]+)+\b", line.split("#", 1)[0])
    }
    assert called
    assert called <= box.fakes
