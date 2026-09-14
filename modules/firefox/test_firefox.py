"""modules/firefox — the /etc policy, Omarchy's installer, the default browser."""

import json
import os
import re
from pathlib import Path

import pytest

from conftest import OMARCHY_TREE, REPO_ROOT, SUDO_RUNS, Box

MODULE = REPO_ROOT / "modules" / "firefox"
INSTALL = MODULE / "install"
POLICIES = json.loads((MODULE / "policies.json").read_text(encoding="utf-8"))["policies"]
# The merge's left-hand layer, absent in CI; keyed on OMARCHY_PATH, so an empty one reproduces CI.
OMARCHY_POLICY = (
    Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "default/firefox/policies.json"
)

# Firefox's own allowlist for the Preferences policy, verbatim from
# `Preferences.onBeforeAddons` (Policies.sys.mjs:2632-2674, Firefox 155.0.1) — a
# `preference.startsWith(prefix)` match (:2726-2727). Outside it a pref is dropped to the
# browser console and never applies. Pinned, not derived (omni.ja defeats zipfile);
# re-derive on a Firefox major bump with:
#   unzip -p /usr/lib/firefox/browser/omni.ja modules/policies/Policies.sys.mjs \
#     | sed -n '/let allowedPrefixes = \[/,/\];/p'
ALLOWED_PREFIXES = tuple(
    """accessibility. alerts. app.update. browser. datareporting.policy. devtools. dom.
    extensions. general.autoScroll general.smoothScroll geo. gfx.
    identity.fxaccounts.toolbar. intl. keyword.enabled layers. layout. mathml.disabled
    media. network. pdfjs. places. pref. print. privacy.baselineFingerprintingProtection
    privacy.fingerprintingProtection privacy.globalprivacycontrol.enabled
    privacy.userContext.enabled privacy.userContext.ui.enabled sidebar. signon.
    spellchecker. svg.context-properties.content.enabled svg.disabled
    toolkit.legacyUserProfileCustomizations.stylesheets ui. webgl.disabled
    webgl.force-enabled widget. xpinstall.enabled xpinstall.whitelist.required""".split()
)
# Checked before the allowlist and rejected "for security reasons" (:2705-2710).
# `security.*` is never a prefix match but an exact list of its own (:2678-2704).
BLOCKED_PREFS = """app.update.channel app.update.lastUpdateTime app.update.migrated
    browser.vpn_promo.disallowed_regions""".split()


def test_every_extension_is_force_installed_and_pinned_to_the_nav_bar() -> None:
    """default_area is the fallback for a profile whose saved layout does not know the button."""
    seed = json.loads(POLICIES["Preferences"]["browser.uiCustomization.state"]["Value"])
    nav_bar = seed["placements"]["nav-bar"]
    for addon_id, entry in POLICIES["ExtensionSettings"].items():
        assert entry["installation_mode"] == "force_installed", addon_id
        assert entry["install_url"].startswith(
            "https://addons.mozilla.org/firefox/downloads/latest/"
        ), addon_id
        assert entry["default_area"] == "navbar", addon_id
        # private_browsing at ANY value takes the about:addons toggle away (XPIDatabase.sys.mjs).
        assert "private_browsing" not in entry, addon_id
        # makeWidgetId (ExtensionCommon.sys.mjs:201-205) + "-browser-action" (ext-browserAction.js:45);
        # saved placements beat default_area (CustomizableUI.sys.mjs:4028-4062).
        widget = re.sub(r"[^a-z0-9_-]", "_", addon_id.lower()) + "-browser-action"
        assert widget in nav_bar, addon_id


def test_the_toolbar_seed_is_one_firefox_will_adopt() -> None:
    """A fresh profile's first window is built from this default-branch string (CustomizableUI:3495)."""
    entry = POLICIES["Preferences"]["browser.uiCustomization.state"]
    assert isinstance(entry["Value"], str)  # Preferences takes bool/number/string only (:2744-2778)
    state = json.loads(entry["Value"])
    assert set(state) == {"placements", "currentVersion"}  # no seen/dirtyAreaCache/newElementCount
    # At 0 the migration ladder rewrites the seed and its v<21 step throws on a missing nav-bar.
    assert state["currentVersion"] == 25
    assert state["placements"]["nav-bar"]
    everywhere = [wid for area in state["placements"].values() for wid in area]
    assert len(everywhere) == len(set(everywhere)), "a duplicate placement is a corrupt capture"
    # updateForNewProtonVersion (CustomizableUI.sys.mjs:886-938) strips sidebar-button from a
    # nav-bar unless browser.engagement.sidebar-button.has-used says it was used.
    assert "sidebar-button" in state["placements"]["nav-bar"]
    assert POLICIES["Preferences"]["browser.engagement.sidebar-button.has-used"]["Value"] is True


def test_every_pref_is_one_firefox_will_accept() -> None:
    """Ours only: Omarchy's own apz.overscroll.enabled is off-allowlist and theirs to fix."""
    locked = set()
    for pref, value in POLICIES["Preferences"].items():
        assert pref not in BLOCKED_PREFS, pref
        assert not pref.startswith("security."), pref
        assert any(pref.startswith(prefix) for prefix in ALLOWED_PREFIXES), pref
        assert value["Status"] in ("default", "locked"), pref
        if value["Status"] == "locked":
            locked.add(pref)
        # A 0/1 int lands as a boolean unless the policy says otherwise.
        if isinstance(value["Value"], int) and not isinstance(value["Value"], bool):
            assert value.get("Type") == "number", pref
    assert locked == {"browser.discovery.enabled"}


def test_the_stylesheet_pref_belongs_to_the_theme_module_not_the_policy() -> None:
    """One home: firefox-theme's per-profile user.js — no sudo, and it covers LibreWolf."""
    assert "toolkit.legacyUserProfileCustomizations.stylesheets" not in POLICIES["Preferences"]


# omarchy-default-browser: with a name it records the pick, bare it prints it back
# (bin/omarchy-default-browser:7-19 / 35). DEAF: the set never takes (a TTY or SSH run).
# NOISY: it takes and the command still fails — its closing notification's status (:35-37).
BROWSER = 'p=$HOME/.default-browser\nif (($#)); then printf "%s\\n" "$1" >"$p"; exit 0; fi\ncat "$p" 2>/dev/null || echo chromium\n'
BROWSER_DEAF = "if (($#)); then exit 0; fi\necho chromium\n"
BROWSER_NOISY = BROWSER.replace("exit 0", "exit 1")


def _policy(box: Box) -> Path:
    return box.etc / "firefox" / "policies" / "policies.json"


def _marker(box: Box) -> Path:
    return box.home / ".local" / "state" / "hyprconf" / "browser-applied"


def _files(box: Box) -> dict[Path, bytes]:
    return {p: p.read_bytes() for d in (box.home, box.etc) for p in d.rglob("*") if p.is_file()}


def _run(box: Box, *args: str, setter: str = BROWSER, **kw):
    """The module against the box, with the seam that keeps the root write inside it."""
    box.stub("sudo", SUDO_RUNS)
    box.stub("omarchy-default-browser", setter)
    kw.setdefault("tty", True)
    return box.run(INSTALL, *args, **kw)


def test_the_policy_is_omarchys_merged_under_ours_through_sudo(box: Box) -> None:
    """jq `*` with Omarchy's file as the left layer: theirs survives, ours wins on a shared key."""
    shared = "browser.compactmode.show"
    assert POLICIES["Preferences"][shared]["Value"] is True
    theirs = {"media.ffmpeg.vaapi.enabled": {"Value": True}, shared: {"Value": False}}
    box.omarchy_write(
        "default/firefox/policies.json", json.dumps({"policies": {"Preferences": theirs}})
    )
    proc = _run(box)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-install-browser" not in box.commands, "Firefox is present"
    installed = json.loads(_policy(box).read_text())["policies"]
    assert installed == {**POLICIES, "Preferences": {**theirs, **POLICIES["Preferences"]}}
    assert _policy(box).stat().st_mode & 0o777 == 0o644, "install -Dm644"
    # The freshness gate is a cmp of those bytes, not the file's existence.
    _policy(box).write_text("{}\n")
    _run(box)
    assert json.loads(_policy(box).read_text())["policies"]["DisableTelemetry"] is True


def test_a_second_run_writes_nothing_and_calls_no_mutating_command(box: Box) -> None:
    """Byte-stable, and a settled box never reaches sudo — what makes the hook's run silent."""
    assert _run(box).returncode == 0
    before = _files(box)
    box.reset()
    proc = _run(box)
    assert proc.returncode == 0, proc.stderr
    assert _files(box) == before
    for command in ("sudo", "omarchy-install-browser", "omarchy-default-browser"):
        assert command not in box.commands, command


@pytest.mark.parametrize("installs", [True, False])
def test_firefox_when_absent_goes_through_omarchys_installer(box: Box, installs: bool) -> None:
    """Omarchy's own flow (bin/omarchy-install-browser:67-74); a failure stops both halves."""
    flag = box.tmp / "firefox-installed"  # the installer is what puts Firefox there
    box.stub("omarchy-pkg-present", f'[ "$1" != firefox ] || [ -e "{flag}" ]\n')
    box.stub("omarchy-install-browser", f'touch "{flag}"\n' if installs else "exit 1\n")
    proc = _run(box)
    assert proc.returncode == 0, proc.stderr  # the module loop goes on; the next run retries
    assert "omarchy-install-browser firefox" in box.calls
    assert "omarchy-pkg-add" not in box.commands, "never a bare package add"
    assert ("retry with: omarchy install browser firefox" in proc.stderr) is not installs
    # No policy for a browser that is not there to read it, and no default pointing at one.
    assert _policy(box).is_file() is installs
    assert ("omarchy-default-browser" in box.commands) is installs
    assert _marker(box).is_file() is installs
    if installs:
        assert box.commands.index("omarchy-install-browser") < box.commands.index("sudo")


@pytest.mark.parametrize(
    ("env", "pointer"),
    [({}, "no terminal for sudo"), ({"HYPRCONF_NO_SUDO": "1"}, "--no-packages")],
)
def test_the_sudo_gates_skip_the_root_write_but_still_seed_the_default(
    box: Box, env: dict[str, str], pointer: str
) -> None:
    """The hook runs non-interactively inside omarchy-update, where a prompt stalls the update."""
    proc = _run(box, tty=False, env=env)  # no tty: stdin is closed
    assert proc.returncode == 0, proc.stderr
    assert pointer in proc.stdout
    assert "sudo" not in box.commands
    assert "omarchy-install-browser" not in box.commands
    assert not _policy(box).exists()
    assert "omarchy-default-browser firefox" in box.calls, "a settled box has no other run"


@pytest.mark.parametrize(("setter", "seeded"), [(BROWSER_DEAF, False), (BROWSER_NOISY, True)])
def test_the_marker_follows_the_value_not_the_setters_exit_status(
    box: Box, setter: str, seeded: bool
) -> None:
    """bin/omarchy-default-browser has no `set -e` and its last line (:35-37) is a notification."""
    proc = _run(box, setter=setter)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-default-browser firefox" in box.calls
    assert _marker(box).is_file() is seeded
    assert ("not the default browser" in proc.stderr) is not seeded


def test_the_default_browser_is_seeded_once_and_the_v7_marker_is_honoured(box: Box) -> None:
    """Seeded on the run that takes, then the user's; v7's defaults-applied covered browser+editor."""
    _run(box)
    assert "omarchy-default-browser firefox" in box.calls
    assert _marker(box).is_file()
    (box.home / ".default-browser").write_text("zen\n")
    box.reset()
    _run(box)
    assert "omarchy-default-browser" not in box.commands
    assert (box.home / ".default-browser").read_text() == "zen\n"
    _marker(box).unlink()
    (_marker(box).parent / "defaults-applied").touch()
    box.reset()
    _run(box)
    assert "omarchy-default-browser" not in box.commands


def test_undo_removes_the_policy_and_the_marker(box: Box) -> None:
    """Stock is no /etc/firefox/policies/policies.json; Firefox is Omarchy's install and stays."""
    _run(box)
    assert _policy(box).is_file() and _marker(box).is_file()
    box.reset()
    proc = _run(box, "undo")
    assert proc.returncode == 0, proc.stderr
    assert not _policy(box).exists()
    assert not _marker(box).exists()
    assert "omarchy default browser <name>" in proc.stdout
    assert "omarchy-pkg-drop" not in box.commands
    box.reset()
    assert _run(box, "undo").returncode == 0  # and again
    assert "sudo" not in box.commands


def test_every_root_call_carries_the_end_of_options_marker() -> None:
    """AGENTS.md rule 8: a path handed to a root call is never readable as an option."""
    root_calls = [
        ln.strip()
        for ln in INSTALL.read_text().splitlines()
        if re.search(r"(?:^|;|&&|\|\||\bif )\s*sudo\s", ln) and not ln.lstrip().startswith("#")
    ]
    assert root_calls
    for call in root_calls:
        assert " -- " in call, call


@pytest.mark.skipif(not OMARCHY_POLICY.is_file(), reason="needs the installed Omarchy")
def test_omarchy_still_ships_the_policy_this_module_merges_under() -> None:
    """With the file gone the jq call fails and the module warns instead of writing."""
    theirs = json.loads(OMARCHY_POLICY.read_text())["policies"]["Preferences"]
    assert theirs, OMARCHY_POLICY
    stand_in = json.loads(OMARCHY_TREE["default/firefox/policies.json"])["policies"]["Preferences"]
    assert set(stand_in) <= set(theirs), set(stand_in) - set(theirs)
