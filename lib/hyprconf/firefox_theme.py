"""hyprconf.firefox_theme — Omarchy's rendered Firefox chrome into each profile.

Omarchy 4.0.0-1 themes Chromium-family browsers only (omarchy-theme-set-browser:
a managed-policy ``BrowserThemeColor``; ``grep -il firefox
/usr/share/omarchy/bin/*`` finds no theming). The overlay's bridge is a user
template, ``themed/userChrome.css.tpl`` in ``~/.config/omarchy/themed/``, which
Omarchy's own ``omarchy-theme-set-templates`` renders into
``~/.local/state/omarchy/current/theme/userChrome.css`` on every ``omarchy
theme set`` (bin/omarchy-theme-set:156 renders, :165 swaps the directory in).
Palette and light/dark mode are Omarchy's resolution (bin/omarchy-theme-color,
which the renderer calls for every key); the mode comes back through the
``--hyprconf-theme-mode`` declaration the template carries, so nothing here
parses colors.toml.

Run from the theme-set hook (``hooks/theme-set.d/10-hyprconf``) after Omarchy's
own fan-out, this copies the rendered file byte-for-byte into each Firefox /
LibreWolf profile's ``chrome/userChrome.css`` (same profile layout) and merges
the ``user.js`` prefs that make Firefox load it and follow the mode. Verified
on Firefox 154 (2026-08-24) with a throwaway headless profile carrying exactly
this ``user.js``: ``extensions.activeThemeID`` does select the built-in theme.
Firefox reads both files at startup only, so the chrome recolours on the next
launch. Rendering is Omarchy's alone: nothing here renders, and a missing
render is reported with the command that produces it (``omarchy theme
refresh`` — omarchy-theme-set of the current theme.name, the wallpaper kept —
which is also what install.sh's stage_themed runs). The system policy the
installer ships (``infra/firefox/policies.json``) is unrelated and untouched.
"""

from __future__ import annotations

import argparse
import configparser
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Every profiles.ini Firefox and LibreWolf may keep (legacy, then XDG — modern
# Arch Firefox uses the XDG one).
BROWSER_INIS = {
    "firefox": (".mozilla/firefox/profiles.ini", ".config/mozilla/firefox/profiles.ini"),
    "librewolf": (".librewolf/profiles.ini", ".config/librewolf/profiles.ini"),
}

# Where omarchy-theme-set leaves the active theme (bin/omarchy-theme-set:12),
# rendered templates included, and the one file the overlay's template yields.
THEME_DIR_REL = ".local/state/omarchy/current/theme"
RENDERED_NAME = "userChrome.css"

# Firefox's built-in Dark / Light themes. Setting one forces the colour
# scheme: their manifests carry nothing but ``color_scheme``, and a fresh
# profile runs "System theme — auto" (default-theme@mozilla.org) instead.
#
# They are NOT lightweight themes on 154: BuiltInThemeConfig.sys.mjs marks
# both ``inApp: true``, so LightweightThemeConsumer.sys.mjs's
# ``hasTheme = id != DEFAULT_THEME_ID && !builtinThemeConfig?.inApp`` is
# false and ``:root[lwtheme]`` never turns on. The template's ``--lwt-*``
# block is therefore inert; its direct #navigator-toolbox / #nav-bar /
# #urlbar-background / #sidebar-box rules are what paint the chrome, which
# is what that half of the template was written for. (``-moz-lwtheme`` is
# gone from FF 154 entirely — the selector is the attribute now.)
THEME_ID_DARK = "firefox-compact-dark@mozilla.org"
THEME_ID_LIGHT = "firefox-compact-light@mozilla.org"

# The template's own declaration of the mode Omarchy resolved for the theme
# (``{{ mode }}``: bin/omarchy-theme-color:120-135 — the colors.toml ``mode``
# key, the legacy ``theme_type`` key, a ``light.mode`` file beside it, then
# background luminance, then dark).
_MODE_RE = re.compile(r"--hyprconf-theme-mode:\s*(light|dark)\s*;")

# A user_pref line, either quote style Firefox's parser accepts, split into
# key, the rest of the statement, and whatever trails the ``;`` (an inline
# ``//`` or ``/* */`` comment the user wrote — kept when the line is rewritten).
_PREF_RE = re.compile(
    r"""^\s*user_pref\(\s*(?P<q>["'])(?P<key>.*?)(?P=q)\s*,(?P<value>.*?)\)\s*;(?P<tail>\s*(?://|/\*).*)?$"""
)


def profile_inis(home: Path) -> list[tuple[str, Path]]:
    """(browser, ini) for every profiles.ini that exists under *home*."""
    return [
        (browser, home / rel)
        for browser, rels in BROWSER_INIS.items()
        for rel in rels
        if (home / rel).is_file()
    ]


def default_profiles(ini: Path) -> list[Path]:
    """The default profile directories a Firefox-style profiles.ini names.

    Firefox keys ``[Install<hash>]`` sections by the hash of its own install
    directory and honours only its own; two builds sharing one profiles.ini
    (say the package and a Developer Edition) each name their own profile, and
    there is no telling from here which will start next — so every distinct
    existing profile any ``[Install…]`` ``Default=`` names is returned. Only
    when none does: the ``[Profile…]`` with ``Default=1``, failing that the
    first profile listed. ``IsRelative=1`` paths are relative to the ini's
    directory.
    """
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(ini, encoding="utf-8")
    except configparser.Error:
        return []

    def resolve(path: str, relative: bool) -> Path:
        return ini.parent / path if relative else Path(path)

    installed: dict[Path, None] = {}
    for section in parser.sections():
        if section.startswith("Install") and parser.has_option(section, "Default"):
            value = parser.get(section, "Default")
            candidate = resolve(value, not Path(value).is_absolute())
            if candidate.is_dir():
                installed.setdefault(candidate, None)
    if installed:
        return list(installed)
    profiles = [
        s for s in parser.sections() if s.startswith("Profile") and parser.has_option(s, "Path")
    ]
    flagged = [s for s in profiles if parser.get(s, "Default", fallback="") == "1"]
    return [
        resolve(parser.get(s, "Path"), parser.get(s, "IsRelative", fallback="1") == "1")
        for s in (flagged or profiles)[:1]
    ]


def rendered_mode(css: bytes) -> str:
    """The theme mode the rendered stylesheet declares — dark unless it says light."""
    m = _MODE_RE.search(css.decode("utf-8", errors="replace"))
    return m.group(1) if m else "dark"


def theme_prefs(mode: str) -> dict[str, object]:
    """user.js prefs the stylesheet needs, plus the theme's light/dark mode.

    ``extensions.activeThemeID`` activates the built-in Dark or Light theme —
    the stylesheet's ``--lwt-*`` overrides only take effect under a lightweight
    theme, and a fresh profile runs the default (system) theme, under which
    the same file changes nothing (verified on Firefox 154, see the module
    docstring). ``ui.systemUsesDarkTheme`` is what Firefox consults for
    prefers-color-scheme when it does not trust the desktop's answer. The
    ``browser.theme.content-theme`` / ``toolbar-theme`` prefs are deliberately
    not set: Firefox writes them itself from the active theme, so they are
    outputs of the theme switch, not inputs to it.
    """
    dark = mode != "light"
    return {
        "toolkit.legacyUserProfileCustomizations.stylesheets": True,
        "extensions.activeThemeID": THEME_ID_DARK if dark else THEME_ID_LIGHT,
        "ui.systemUsesDarkTheme": 1 if dark else 0,
    }


def format_pref(key: str, value: object) -> str:
    if isinstance(value, bool):
        literal = "true" if value else "false"
    elif isinstance(value, (int, float)):
        literal = str(value)
    else:
        literal = '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f'user_pref("{key}", {literal});'


def _pref_key(line: str) -> str | None:
    """The key of a ``user_pref("…"| '…', …);`` line, either quote style."""
    m = _PREF_RE.match(line)
    return m.group("key") if m else None


def _read_raw(path: Path, errors: str = "strict") -> str:
    """The file as written, CRLF and all (read_text would fold it to LF)."""
    return path.read_bytes().decode("utf-8", errors)


def _write_if_changed(path: Path, data: bytes) -> bool:
    """Write *data* to *path* byte-for-byte; True when the file did not already say that."""
    if path.exists() and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


def merge_user_js(path: Path, prefs: dict[str, object]) -> bool:
    """Rewrite the managed prefs in *path*, keeping every other line as it is.

    A managed pref already present is rewritten in place, its inline comment
    kept; later duplicates go; prefs not yet there are appended. The file's
    own line ending (LF or CRLF) is preserved, and so are non-UTF-8 bytes in
    lines this does not manage (surrogateescape round-trips them exactly —
    a user.js with a latin-1 comment must not kill theming). Returns True
    when the file changed.
    """
    raw = _read_raw(path, "surrogateescape") if path.exists() else ""
    newline = "\r\n" if "\r\n" in raw else "\n"
    pending = dict(prefs)
    kept: list[str] = []
    for line in raw.splitlines():
        m = _PREF_RE.match(line)
        key = m.group("key") if m else None
        if key not in prefs:
            kept.append(line)
        elif key in pending:
            kept.append(format_pref(key, pending.pop(key)) + (m.group("tail") or ""))
    kept.extend(format_pref(k, v) for k, v in pending.items())
    return _write_if_changed(
        path, (newline.join(kept) + newline).encode("utf-8", "surrogateescape")
    )


def apply(profile: Path, css: bytes) -> bool:
    """The rendered stylesheet and its prefs into one profile. True when anything changed."""
    chrome = profile / "chrome"
    chrome.mkdir(parents=True, exist_ok=True)
    changed = _write_if_changed(chrome / RENDERED_NAME, css)
    return merge_user_js(profile / "user.js", theme_prefs(rendered_mode(css))) or changed


def notify(message: str) -> None:
    """A desktop notification through Omarchy's own command, when there is one.

    Firefox only reads userChrome.css at startup, and a theme switch gives no
    other sign that the browser is now behind — this is the one place the
    user learns a restart is due. Silent when the command is absent (a TTY
    run, a test) or fails: cosmetic, never an error.
    """
    cmd = shutil.which("omarchy-notification-send")
    if cmd is None:
        return
    try:
        subprocess.run(
            [cmd, "Firefox theme", message], check=False, timeout=10, capture_output=True
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _pref_value(path: Path, key: str) -> str | None:
    """The value Firefox last wrote for *key* into prefs.js (None when absent)."""
    if not path.exists():
        return None
    for line in _read_raw(path, errors="replace").splitlines():
        m = _PREF_RE.match(line)
        if m and m.group("key") == key:
            return m.group("value").strip().strip('"')
    return None


def _pref_key_present(path: Path, key: str) -> bool:
    raw = _read_raw(path, errors="replace") if path.exists() else ""
    return any(_pref_key(line) == key for line in raw.splitlines())


def status(home: Path) -> int:
    """Say what is in place and — the usual question — whether Firefox has
    restarted since: prefs.js is rewritten by Firefox from its live state, so
    once it carries our activeThemeID, user.js has been read."""
    rendered = home / THEME_DIR_REL / RENDERED_NAME
    css = rendered.read_bytes() if rendered.is_file() else None
    if css is None:
        print(f"rendered: MISSING ({rendered}) — `omarchy theme refresh` renders the template")
    else:
        print(f"rendered: {rendered} ({rendered_mode(css)})")
    wanted = str(theme_prefs(rendered_mode(css))["extensions.activeThemeID"]) if css else None
    managed = list(theme_prefs("dark"))
    found = False
    for browser, ini in profile_inis(home):
        profiles = [p for p in default_profiles(ini) if p.is_dir()]
        if not profiles:
            print(f"{browser}: {ini} names no usable default profile")
            continue
        found = True
        for profile in profiles:
            copy = profile / "chrome" / RENDERED_NAME
            js = profile / "user.js"
            print(f"{browser}: profile {profile}")
            if not copy.is_file():
                state = "MISSING"
            elif css is not None and copy.read_bytes() != css:
                state = "STALE (differs from the rendered file)"
            else:
                state = "written"
            print(f"  userChrome.css: {state}")
            have = sum(1 for k in managed if _pref_key_present(js, k))
            print(f"  user.js: {have}/{len(managed)} managed prefs present")
            active = _pref_value(profile / "prefs.js", "extensions.activeThemeID")
            if wanted and active == wanted:
                print(f"  restarted since the files were written: yes (active theme {active})")
            else:
                print(
                    "  restarted since the files were written: NO — prefs.js says "
                    f"{active or 'nothing'}; close every Firefox window and start it again"
                )
    if not found:
        print("no Firefox/LibreWolf profile found under", home)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m hyprconf.firefox_theme",
        description="Copy Omarchy's rendered userChrome.css into Firefox/LibreWolf profiles.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="report what is written where and whether Firefox has restarted since",
    )
    args = parser.parse_args(argv)

    home = Path(os.environ.get("HOME", Path.home()))
    if args.status:
        return status(home)
    rendered = home / THEME_DIR_REL / RENDERED_NAME
    if not rendered.is_file():
        # Every theme set leaves every rendered template in current/theme
        # (bin/omarchy-theme-set:156 renders, :165 swaps the dir in), so the
        # file is missing only with no theme set, no template installed, or
        # a failed refresh — all Omarchy's own command mends. Never rendered
        # here: the renderer's staging dir and lock are omarchy-theme-set's.
        print(
            f"hyprconf firefox theme: no {rendered} — is a theme active and "
            "~/.config/omarchy/themed/userChrome.css.tpl installed? "
            "`omarchy theme refresh` renders it",
            file=sys.stderr,
        )
        return 1
    css = rendered.read_bytes()

    applied = 0
    changed: dict[str, None] = {}  # browsers, in order, without repeats
    for browser, ini in profile_inis(home):
        for profile in default_profiles(ini):
            if not profile.is_dir():
                continue
            if apply(profile, css):
                changed.setdefault(browser, None)
            print(f"{browser}: {profile / 'chrome' / RENDERED_NAME} ({rendered_mode(css)})")
            applied += 1
    if not applied:
        print("hyprconf firefox theme: no Firefox/LibreWolf profile found — nothing to do")
    elif changed:
        print(
            "restart "
            + " and ".join(changed)
            + " to see the new theme (userChrome.css loads at startup)"
        )
        notify("Restart " + " and ".join(changed) + " to apply the new theme")
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised through the hook tests
    sys.exit(main())
