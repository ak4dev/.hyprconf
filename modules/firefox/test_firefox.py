"""modules/firefox — the system policy, Omarchy's installer, the default browser.

Two halves. The first reads `policies.json` on its own: the `Preferences`
policy silently drops any pref outside Firefox's own allowlist, so a
plausible-looking entry can do nothing at all and never say so — that is the
load-bearing test, and the pinned lists below carry their sources and the
recipe to re-derive them on a Firefox major bump. The second runs the module
against a `box`: the jq merge with the real jq, the sudo gates, the set-once
default browser, idempotence and undo.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from conftest import OMARCHY_TREE, REPO_ROOT, Box

MODULE = REPO_ROOT / "modules" / "firefox"
POLICIES_JSON = MODULE / "policies.json"
POLICIES = json.loads(POLICIES_JSON.read_text(encoding="utf-8"))["policies"]

# What omarchy-install-browser copies to /usr/lib/firefox/distribution/ and
# what the module merges under its own file. Absent in CI (no Omarchy); keyed
# on OMARCHY_PATH like every needs-Omarchy probe, so an empty one reproduces CI.
OMARCHY_POLICY = (
    Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "default/firefox/policies.json"
)

# Firefox's own allowlist for the Preferences policy, verbatim from
# `Preferences.onBeforeAddons` (Policies.sys.mjs:2632-2674, Firefox
# 155.0.1) — a prefix match, `preference.startsWith(prefix)` (:2726-2727).
# A pref outside it is dropped with "Preference not allowed for stability
# reasons" logged to the browser console and nothing else: the policy still
# loads, the pref just never applies. Pinned rather than derived because
# omni.ja is a zip with a patched central directory that Python's zipfile
# refuses (unzip reads it, and is not one of the tools the suite may
# assume). Re-derived against 155.0.1: byte-identical to the 154.0 list, 41
# prefixes in the same order, blockedPrefs unchanged. Re-derive on the next
# Firefox major bump with:
#   unzip -p /usr/lib/firefox/browser/omni.ja modules/policies/Policies.sys.mjs \
#     | sed -n '/let allowedPrefixes = \[/,/\];/p'
ALLOWED_PREFIXES = (
    "accessibility.",
    "alerts.",
    "app.update.",
    "browser.",
    "datareporting.policy.",
    "devtools.",
    "dom.",
    "extensions.",
    "general.autoScroll",
    "general.smoothScroll",
    "geo.",
    "gfx.",
    "identity.fxaccounts.toolbar.",
    "intl.",
    "keyword.enabled",
    "layers.",
    "layout.",
    "mathml.disabled",
    "media.",
    "network.",
    "pdfjs.",
    "places.",
    "pref.",
    "print.",
    "privacy.baselineFingerprintingProtection",
    "privacy.fingerprintingProtection",
    "privacy.globalprivacycontrol.enabled",
    "privacy.userContext.enabled",
    "privacy.userContext.ui.enabled",
    "sidebar.",
    "signon.",
    "spellchecker.",
    "svg.context-properties.content.enabled",
    "svg.disabled",
    "toolkit.legacyUserProfileCustomizations.stylesheets",
    "ui.",
    "webgl.disabled",
    "webgl.force-enabled",
    "widget.",
    "xpinstall.enabled",
    "xpinstall.whitelist.required",
)
# Checked before the allowlist and rejected "for security reasons"
# (Policies.sys.mjs:2705-2710, Firefox 155.0.1). `security.*` is never a
# prefix match — it is tested against a separate exact-match list
# (allowedSecurityPrefs, :2678-2704), so no `security.` pref belongs in our
# policy without checking that list first.
BLOCKED_PREFS = (
    "app.update.channel",
    "app.update.lastUpdateTime",
    "app.update.migrated",
    "browser.vpn_promo.disallowed_regions",
)

# ---------------------------------------------------------------------------
# What the policy says
# ---------------------------------------------------------------------------


def test_every_extension_is_force_installed_into_the_nav_bar() -> None:
    """The policy's extension entries, checked as a shape rather than by id.

    `default_area` is Firefox's own knob for where a browser action lands
    (ExtensionActions.sys.mjs: the policy value beats the manifest's, and
    without one an extension falls into the overflow menu) — the fallback for
    a profile whose saved layout does not know the button. `private_browsing`
    is deliberately absent: its presence at ANY value takes the about:addons
    toggle away from the user (XPIDatabase.sys.mjs). What is installed, and
    from where, is README.md.
    """
    for addon_id, entry in POLICIES["ExtensionSettings"].items():
        assert entry["installation_mode"] == "force_installed", addon_id
        assert entry["install_url"].startswith(
            "https://addons.mozilla.org/firefox/downloads/latest/"
        ), addon_id
        assert entry["default_area"] == "navbar", addon_id
        assert "private_browsing" not in entry, addon_id


def test_toolbar_layout_seeds_a_fresh_profile_then_belongs_to_the_user() -> None:
    """The seeded layout's crash conditions — the arrangement itself is the
    JSON's to state, and README.md the user's home for it.

    CustomizableUI loads the layout with a plain effective-value read
    (`Services.prefs.getCharPref(kPrefCustomizationState, "")`,
    CustomizableUI.sys.mjs:3495, Firefox 154.0), so this default-branch string
    is what a fresh profile's first window is built from and a profile with a
    user-branch value ignores it. Verified live on 154.0 with fresh headless
    profiles under the real policy machinery (2026-08-30).
    """
    entry = POLICIES["Preferences"]["browser.uiCustomization.state"]
    # A string, not a nested object: the Preferences policy takes only
    # bool/number/string values (Policies.sys.mjs:2744-2778).
    assert isinstance(entry["Value"], str)
    state = json.loads(entry["Value"])
    # Placements and the version, nothing else — none of Firefox's own
    # bookkeeping (seen / dirtyAreaCache / newElementCount).
    assert set(state) == {"placements", "currentVersion"}
    # kVersion on Firefox 154.0. At 0 — the default when the field is
    # omitted — the whole migration ladder rewrites the seed, and the v<21
    # step dereferences placements["nav-bar"] unguarded: a TypeError out of
    # CustomizableUI's initialize. So the version rides, and nav-bar must.
    assert state["currentVersion"] == 25
    placements = state["placements"]
    assert placements["nav-bar"]
    # No widget twice: a duplicate placement is a corrupt capture.
    everywhere = [wid for area in placements.values() for wid in area]
    assert len(everywhere) == len(set(everywhere))
    # updateForNewProtonVersion (CustomizableUI.sys.mjs:886-938, Firefox
    # 154.0) runs on any profile whose browser.proton.toolbar.version is below
    # 3 — a fresh one is 0 — and strips sidebar-button from a saved nav-bar
    # unless browser.engagement.sidebar-button.has-used says it was used. So
    # the two ship together or the button moves to the end of the bar
    # (verified live on a fresh profile).
    assert "sidebar-button" in placements["nav-bar"]
    assert POLICIES["Preferences"]["browser.engagement.sidebar-button.has-used"]["Value"] is True


def test_toolbar_layout_places_every_managed_extension_button() -> None:
    """Each force-installed extension's button sits in the seeded nav-bar.

    The widget id is the extension id through Firefox's makeWidgetId —
    lowercase, then every char outside [a-z0-9_-] becomes "_"
    (ExtensionCommon.sys.mjs:201-205, Firefox 154.0) — plus "-browser-action"
    (actionWidgetId, ext-browserAction.js:45, called at :136). Deriving it
    here keeps ExtensionSettings and the layout in lockstep: an extension
    added or dropped there moves here too. CustomizableUI consults saved
    placements before default_area (createWidget,
    CustomizableUI.sys.mjs:4028-4062), so the seed pins the position even
    though the XPIs install asynchronously after the first window.
    """
    state = json.loads(POLICIES["Preferences"]["browser.uiCustomization.state"]["Value"])
    nav_bar = state["placements"]["nav-bar"]
    for addon_id in POLICIES["ExtensionSettings"]:
        widget = re.sub(r"[^a-z0-9_-]", "_", addon_id.lower()) + "-browser-action"
        assert widget in nav_bar, addon_id


def test_every_pref_is_one_firefox_will_accept() -> None:
    """No pref outside Firefox's allowlist — those are dropped in silence —
    and every captured setting a `default`, so it seeds a profile and then
    gets out of the way. Only the anti-feature lock stays locked.

    Only hyprconf's own file is checked. Omarchy's ships `apz.overscroll.enabled`,
    which is NOT on the allowlist and is rejected on every start (verified
    against Firefox 154.0 with the real merged policy); that is Omarchy's to
    fix, and asserting on it here would fail for something the overlay does
    not own.
    """
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
    """`toolkit.legacyUserProfileCustomizations.stylesheets` has ONE home, and
    it is modules/firefox-theme's per-profile user.js — the half that needs
    no sudo, survives --no-packages (which the post-update hook always
    passes) and covers LibreWolf, whose own policy directory this file is
    not. A `Status: "default"` here would also lose to a user who ever
    toggled the pref off."""
    assert "toolkit.legacyUserProfileCustomizations.stylesheets" not in POLICIES["Preferences"]


# ---------------------------------------------------------------------------
# The module against a box
# ---------------------------------------------------------------------------

INSTALL = MODULE / "install"

# A sudo that runs its argument list, so the root write lands in the box's
# own /etc rather than being merely recorded.
SUDO_RUNS = '"$@"\n'

# omarchy-default-browser: `omarchy-default-browser <name>` records the pick,
# a bare call prints it back (bin/omarchy-default-browser:7-19 / 35). The
# default answer is chromium — the box has no xdg-settings and no session.
BROWSER = """
pick="$HOME/.default-browser"
if (($#)); then printf '%s\\n' "$1" > "$pick"; exit 0; fi
cat "$pick" 2>/dev/null || echo chromium
"""
# The same, but the set never takes — what a TTY or SSH run looks like when
# xdg-settings has no session to talk to.
BROWSER_DEAF = """
if (($#)); then exit 0; fi
echo chromium
"""
# The set takes and the command still fails: bin/omarchy-default-browser has
# no `set -e` and its last line (:35-37) is an omarchy-notification-send, so
# its status is the notification's — which fails with no shell to notify.
BROWSER_NOISY = """
pick="$HOME/.default-browser"
if (($#)); then printf '%s\\n' "$1" > "$pick"; exit 1; fi
cat "$pick" 2>/dev/null || echo chromium
"""


def _env(box: Box) -> dict[str, str]:
    """The seam that keeps the root write inside the box."""
    return {"_HYPRCONF_FIREFOX_POLICIES": str(box.etc / "firefox" / "policies")}


def _policy(box: Box) -> Path:
    return box.etc / "firefox" / "policies" / "policies.json"


def _snapshot(box: Box) -> dict[str, bytes]:
    """Every file the box carries outside its fakes, by content."""
    roots = (box.home, box.etc)
    return {
        str(p): p.read_bytes()
        for root in roots
        for p in root.rglob("*")
        if p.is_file() and not p.name.startswith(".default-browser")
    }


def _run(box: Box, *args: str, **kw) -> object:
    box.stub("sudo", SUDO_RUNS)
    box.stub("omarchy-default-browser", BROWSER)
    return box.run(INSTALL, *args, tty=True, env={**_env(box), **kw.pop("env", {})}, **kw)


def test_policy_is_omarchys_merged_under_ours_through_sudo(box: Box) -> None:
    """Firefox reads enterprise policies only from root-owned paths, and
    /etc/firefox/policies takes precedence over the distribution/ file
    omarchy-install-browser writes — so what lands is Omarchy's policy merged
    UNDER ours, with the real jq. Firefox is present, so its installer never
    runs."""
    proc = _run(box)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-install-browser" not in box.commands

    installed = json.loads(_policy(box).read_text())["policies"]
    for key, value in POLICIES.items():
        if key != "Preferences":
            assert installed[key] == value, key
    for pref, value in POLICIES["Preferences"].items():
        assert installed["Preferences"][pref] == value, pref
    omarchys = box.omarchy / "default" / "firefox" / "policies.json"
    theirs = json.loads(omarchys.read_text())["policies"]["Preferences"]
    for pref, value in theirs.items():
        assert installed["Preferences"][pref] == value, pref
    assert _policy(box).stat().st_mode & 0o777 == 0o644, "install -Dm644"


def test_ours_wins_on_a_shared_key(box: Box) -> None:
    """jq `*` is a recursive object merge and ours is the right-hand layer:
    a pref both files name comes out with hyprconf's value."""
    shared = "browser.compactmode.show"
    box.omarchy_write(
        "default/firefox/policies.json",
        json.dumps({"policies": {"Preferences": {shared: {"Value": False, "Status": "default"}}}}),
    )
    assert POLICIES["Preferences"][shared]["Value"] is True
    _run(box)
    installed = json.loads(_policy(box).read_text())["policies"]["Preferences"]
    assert installed[shared] == POLICIES["Preferences"][shared]


def test_a_second_run_writes_nothing_and_calls_no_sudo(box: Box) -> None:
    """The whole contract in one test: byte-stable, and a settled box never
    reaches sudo — which is what makes the post-update hook's run silent."""
    assert _run(box).returncode == 0
    before = _snapshot(box)
    box.reset()
    proc = _run(box)
    assert proc.returncode == 0, proc.stderr
    assert _snapshot(box) == before
    for command in ("sudo", "omarchy-install-browser", "omarchy-default-browser"):
        assert command not in box.commands, command


def test_an_edited_policy_is_repaired(box: Box) -> None:
    """The freshness gate is a cmp of the merged bytes, not the file's
    existence: a hand-edited /etc policy is put back. Nothing else can catch
    a regression here — a byte-stability check over $HOME would not see it."""
    _run(box)
    _policy(box).write_text("{}\n")
    box.reset()
    _run(box)
    assert json.loads(_policy(box).read_text())["policies"]["DisableTelemetry"] is True


def test_firefox_is_installed_through_omarchys_installer_when_absent(box: Box) -> None:
    """`omarchy-install-browser firefox` — Omarchy's own flow: omarchy-pkg-add,
    its prefs under /usr/lib/firefox/distribution, MOZ_ENABLE_WAYLAND — runs
    before the policy lands; never a bare omarchy-pkg-add firefox."""
    box.stub("omarchy-pkg-present", '[ "$1" != firefox ]\n')
    proc = _run(box)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-install-browser firefox" in box.calls
    assert box.commands.index("omarchy-install-browser") < box.commands.index("sudo")
    assert _policy(box).is_file()
    assert "omarchy-pkg-add" not in box.commands


def test_a_failed_firefox_install_leaves_no_policy_and_no_default_behind(box: Box) -> None:
    """A failed install is a warning with Omarchy's retry command, and both
    halves stop there: a policy for a browser that is not installed would
    shadow nothing, and a default pointing at one is never set (rule 6). The
    module still exits 0 — the loop goes on — and the next run retries both."""
    box.stub("omarchy-pkg-present", '[ "$1" != firefox ]\n')
    box.stub("omarchy-install-browser", "exit 1\n")
    proc = _run(box)
    assert proc.returncode == 0, proc.stderr
    assert "retry with: omarchy install browser firefox" in proc.stderr
    assert not _policy(box).exists()
    assert "sudo" not in box.commands
    assert "omarchy-default-browser" not in box.commands
    assert not (box.home / ".local" / "state" / "hyprconf" / "browser-applied").exists()


def test_the_seed_waits_for_firefox_to_be_installed(box: Box) -> None:
    """A --no-packages run on a box without Firefox (the post-update hook's,
    before any terminal run) seeds nothing: xdg-settings has no
    firefox.desktop to record, and a setter that took it anyway would mark a
    default for an absent browser. The first run that finds it seeds."""
    flag = box.tmp / "firefox-installed"
    box.stub("omarchy-pkg-present", f'[ "$1" != firefox ] || [ -e "{flag}" ]\n')
    marker = box.home / ".local" / "state" / "hyprconf" / "browser-applied"

    proc = _run(box, env={"HYPRCONF_NO_SUDO": "1"})
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-default-browser" not in box.commands
    assert not marker.exists()

    flag.touch()
    box.reset()
    proc = _run(box, env={"HYPRCONF_NO_SUDO": "1"})
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-default-browser firefox" in box.calls
    assert marker.is_file()


def test_no_terminal_and_no_sudo_both_bow_out_but_still_seed_the_default(box: Box) -> None:
    """The post-update hook runs non-interactively with --no-packages inside
    omarchy-update, where a password prompt would stall the whole update. Both
    gates skip the root write — and neither skips the default-browser seed,
    which on a settled box has no other run to happen in."""
    for env in ({}, {"HYPRCONF_NO_SUDO": "1"}):
        b = box
        b.reset()
        b.stub("sudo", SUDO_RUNS)
        b.stub("omarchy-default-browser", BROWSER)
        proc = b.run(INSTALL, env={**_env(b), **env})  # tty=False: stdin is closed
        assert proc.returncode == 0, proc.stderr
        assert "sudo" not in b.commands
        assert "omarchy-install-browser" not in b.commands
        assert not _policy(b).exists()
        assert "omarchy-default-browser firefox" in b.calls
        (b.home / ".local" / "state" / "hyprconf" / "browser-applied").unlink()


def test_the_default_browser_is_seeded_once_and_read_back(box: Box) -> None:
    """Seeded to firefox on the first run that takes, then the user's. The
    marker waits for the VALUE, not the setter's exit status — that status is
    its closing omarchy-notification-send's, which fails on a TTY or SSH run
    long after xdg-settings wrote the value."""
    marker = box.home / ".local" / "state" / "hyprconf" / "browser-applied"
    box.stub("sudo", SUDO_RUNS)
    box.stub("omarchy-default-browser", BROWSER_DEAF)  # set succeeds, value does not move
    proc = box.run(INSTALL, tty=True, env=_env(box))
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-default-browser firefox" in box.calls
    assert not marker.exists(), "an unseeded default must retry on the next run"

    box.reset()
    _run(box)  # a setter that works
    assert marker.is_file()

    # And then it is the user's: a later run re-asserts nothing.
    (box.home / ".default-browser").write_text("zen\n")
    box.reset()
    _run(box)
    assert "omarchy-default-browser" not in box.commands
    assert (box.home / ".default-browser").read_text() == "zen\n"


def test_the_marker_survives_the_setters_failing_notification(box: Box) -> None:
    """The other side of the read-back: the value took and the setter still
    exited non-zero. Trusting that status left the marker unwritten on exactly
    the runs that had seeded, and the next run re-asserted firefox over a
    browser chosen in between."""
    marker = box.home / ".local" / "state" / "hyprconf" / "browser-applied"
    box.stub("sudo", SUDO_RUNS)
    box.stub("omarchy-default-browser", BROWSER_NOISY)
    proc = box.run(INSTALL, tty=True, env=_env(box))
    assert proc.returncode == 0, proc.stderr
    assert "not the default browser" not in proc.stderr
    assert marker.is_file()

    (box.home / ".default-browser").write_text("zen\n")
    box.reset()
    box.stub("omarchy-default-browser", BROWSER_NOISY)
    assert box.run(INSTALL, tty=True, env=_env(box)).returncode == 0
    assert "omarchy-default-browser" not in box.commands
    assert (box.home / ".default-browser").read_text() == "zen\n"


def test_every_root_call_carries_the_end_of_options_marker() -> None:
    """AGENTS.md rule 8: a path handed to a root call is never readable as an
    option. The same pin modules/keychron carries over the overlay's other
    write outside $HOME; the tree-wide scan lands with tests/test_scans.py."""
    root_calls = [
        ln.strip()
        for ln in INSTALL.read_text().splitlines()
        if re.search(r"(?:^|;|&&|\|\||\bif )\s*sudo\s", ln) and not ln.lstrip().startswith("#")
    ]
    assert root_calls
    for call in root_calls:
        assert " -- " in call, call


def test_the_v7_defaults_marker_is_honoured_for_one_release(box: Box) -> None:
    """An upgraded box carries `defaults-applied` from the stage that covered
    browser and editor together. Honoured, or the module would re-assert
    firefox over a browser chosen since."""
    state = box.home / ".local" / "state" / "hyprconf"
    state.mkdir(parents=True)
    (state / "defaults-applied").touch()
    _run(box)
    assert "omarchy-default-browser" not in box.commands


def test_undo_removes_the_policy_and_the_marker(box: Box) -> None:
    """Stock is no /etc/firefox/policies/policies.json — Omarchy's own prefs
    stay where its installer put them, under /usr/lib/firefox/distribution.
    Firefox itself is Omarchy's install and stays."""
    _run(box)
    marker = box.home / ".local" / "state" / "hyprconf" / "browser-applied"
    assert _policy(box).is_file() and marker.is_file()

    box.reset()
    box.stub("sudo", SUDO_RUNS)
    proc = box.undo("firefox", tty=True, env=_env(box))
    assert proc.returncode == 0, proc.stderr
    assert not _policy(box).exists()
    assert not marker.exists()
    assert "omarchy default browser <name>" in proc.stdout
    # Never a package removal: the browser is not the overlay's to uninstall.
    assert "omarchy-pkg-drop" not in box.commands

    box.reset()
    assert box.undo("firefox", tty=True, env=_env(box)).returncode == 0  # and again
    assert "sudo" not in box.commands


def test_undo_leaves_the_policy_alone_without_sudo(box: Box) -> None:
    """`--no-packages` is the hook's flag, and the hook must never prompt."""
    _run(box)
    box.reset()
    box.stub("sudo", SUDO_RUNS)
    proc = box.undo("firefox", tty=True, env={**_env(box), "HYPRCONF_NO_SUDO": "1"})
    assert proc.returncode == 0, proc.stderr
    assert _policy(box).is_file()
    assert "sudo" not in box.commands


def test_every_command_the_module_names_has_a_fake(box: Box) -> None:
    """A command the fakes do not cover would reach the developer's own
    machine from a test run."""
    named = set(re.findall(r"\bomarchy(?:-[a-z0-9]+)+\b", INSTALL.read_text()))
    assert named, "the scan is broken"
    assert named <= box.fakes, named - box.fakes


@pytest.mark.skipif(not OMARCHY_POLICY.is_file(), reason="needs the installed Omarchy")
def test_omarchy_still_ships_the_policy_this_module_merges_under() -> None:
    """The merge's left-hand layer, which is not optional: with the file gone
    the jq call fails and the module warns instead of writing. And the box's
    stand-in for it must name no pref Omarchy stopped shipping, or the merge
    tests above prove something Omarchy no longer does. Skipped in CI, where
    the stand-in is all there is."""
    theirs = json.loads(OMARCHY_POLICY.read_text())["policies"]["Preferences"]
    assert theirs, OMARCHY_POLICY
    stand_in = json.loads(OMARCHY_TREE["default/firefox/policies.json"])["policies"]["Preferences"]
    assert set(stand_in) <= set(theirs), set(stand_in) - set(theirs)
