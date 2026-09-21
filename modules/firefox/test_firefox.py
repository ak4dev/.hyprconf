"""modules/firefox — the /etc policy, Omarchy's installer, the default browser."""

import json
import re
from pathlib import Path

import pytest

from conftest import NEEDS_OMARCHY, OMARCHY, OMARCHY_TREE, REPO_ROOT, SUDO_RUNS, Box

MODULE = REPO_ROOT / "modules" / "firefox"
INSTALL = MODULE / "install"
POLICIES = json.loads((MODULE / "policies.json").read_text(encoding="utf-8"))["policies"]
# The merge's left-hand layer, absent in CI; keyed on OMARCHY_PATH, so an empty one reproduces CI.
OMARCHY_POLICY = OMARCHY / "default/firefox/policies.json"

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
        # saved placements beat default_area (CustomizableUI.sys.mjs:4074-4111, Firefox 155.0.1).
        widget = re.sub(r"[^a-z0-9_-]", "_", addon_id.lower()) + "-browser-action"
        assert widget in nav_bar, addon_id


def test_the_toolbar_seed_is_one_firefox_will_adopt() -> None:
    """A fresh profile's first window is built from this default-branch string (CustomizableUI:3543-3544)."""
    entry = POLICIES["Preferences"]["browser.uiCustomization.state"]
    assert isinstance(entry["Value"], str)  # Preferences takes bool/number/string only (:2744-2778)
    state = json.loads(entry["Value"])
    assert set(state) == {"placements", "currentVersion"}  # no seen/dirtyAreaCache/newElementCount
    # At 0 the migration ladder rewrites the seed and its v<21 step throws on a missing nav-bar.
    # kVersion is 26 (:71); its <26 step (:902-926) is a no-op on an empty TabsToolbar.
    assert state["currentVersion"] == 25
    assert state["placements"]["nav-bar"]
    everywhere = [wid for area in state["placements"].values() for wid in area]
    assert len(everywhere) == len(set(everywhere)), "a duplicate placement is a corrupt capture"
    # updateForNewProtonVersion (CustomizableUI.sys.mjs:935-987, the step at :977-984) strips
    # sidebar-button from a nav-bar unless browser.engagement.sidebar-button.has-used says so.
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
    """One home: firefox-theme's per-profile user.js — no sudo."""
    assert "toolkit.legacyUserProfileCustomizations.stylesheets" not in POLICIES["Preferences"]


# omarchy-default-browser: with a name it records the pick, bare it prints it back
# (bin/omarchy-default-browser:7-19 / 35). DEAF: the set never takes (a TTY or SSH run).
# NOISY: it takes and the command still fails — its closing notification's status (:35-37).
BROWSER = 'p=$HOME/.default-browser\nif (($#)); then printf "%s\\n" "$1" >"$p"; exit 0; fi\ncat "$p" 2>/dev/null || echo chromium\n'
BROWSER_DEAF = "if (($#)); then exit 0; fi\necho chromium\n"
BROWSER_NOISY = BROWSER.replace("exit 0", "exit 1")


FOREIGN = '{\n  "policies": { "BlockAboutConfig": true }\n}\n'  # nothing in this repo writes it
# Omarchy's own layer after an omarchy-update: the merge moves, hyprconf's half does not.
OMARCHY_MOVED = '{"policies": {"Preferences": {"apz.overscroll.enabled": {"Value": false}}}}'


def _policy(box: Box) -> Path:
    return box.etc / "firefox" / "policies" / "policies.json"


def _bak(box: Box) -> Path:
    """The copy the install leaves of a policy it did not write."""
    return _policy(box).with_name("policies.json.bak")


def _marker(box: Box) -> Path:
    return box.home / ".local" / "state" / "hyprconf" / "browser-applied"


def _ours(box: Box) -> Path:
    """The record that the policy in /etc is this module's — what undo removes it on."""
    return _marker(box).with_name("firefox-policy")


def _run(box: Box, *args: str, setter: str = BROWSER, sudo: str = SUDO_RUNS, **kw):
    """The module against the box, with the seam that keeps the root write inside it."""
    box.stub("sudo", sudo)
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
    assert not _bak(box).exists(), "hyprconf's own policy is never copied aside"


def test_a_second_run_writes_nothing_and_calls_no_mutating_command(box: Box) -> None:
    """Byte-stable, and a settled box never reaches sudo — what makes the hook's run silent."""
    assert _run(box).returncode == 0
    before = box.snapshot()
    box.reset()
    proc = _run(box)
    assert proc.returncode == 0, proc.stderr
    assert box.snapshot() == before
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
    """The hook passes --no-packages: under omarchy-update every child has a pty
    (bin/omarchy-update:10-12), so a prompt would stall the update."""
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


def test_the_default_browser_is_seeded_once_and_the_v7_marker_is_migrated(box: Box) -> None:
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
    assert _marker(box).is_file()


def test_undo_removes_the_policy_and_the_marker(box: Box) -> None:
    """Stock is no /etc/firefox/policies/policies.json; Firefox is Omarchy's install and stays."""
    _run(box)
    assert _policy(box).is_file() and _marker(box).is_file()
    box.reset()
    proc = _run(box, "undo")
    assert proc.returncode == 0, proc.stderr
    assert not _policy(box).exists()
    assert not list(_marker(box).parent.iterdir()), "marker and record both"
    assert "omarchy default browser <name>" in proc.stdout
    assert "omarchy-pkg-drop" not in box.commands
    box.reset()
    assert _run(box, "undo").returncode == 0  # and again
    assert "sudo" not in box.commands


def test_a_policy_hyprconf_did_not_write_is_copied_aside_once_and_put_back(box: Box) -> None:
    """The root write replaces a file the user may own: one copy beside it, made once."""
    _policy(box).parent.mkdir(parents=True)
    _policy(box).write_text(FOREIGN)
    assert _run(box).returncode == 0
    assert box.calls_of("sudo")[0] == ["sudo", "cp", "-f", "--", str(_policy(box)), str(_bak(box))]
    assert _bak(box).read_text() == FOREIGN
    assert json.loads(_policy(box).read_text())["policies"]["DisableTelemetry"] is True
    # Omarchy's half moves: ours is rewritten, and the copy beside it stays the user's.
    box.omarchy_write("default/firefox/policies.json", OMARCHY_MOVED)
    box.reset()
    assert _run(box).returncode == 0
    assert _bak(box).read_text() == FOREIGN
    box.reset()
    assert _run(box, "undo").returncode == 0
    assert _policy(box).read_text() == FOREIGN and not _bak(box).exists()
    assert not list(_marker(box).parent.iterdir()), "marker and record both"


def test_a_copy_orphaned_from_its_record_is_refreshed_not_kept(box: Box) -> None:
    """`HYPRCONF_STATE` is relocatable, so /etc can outlive the record: the next
    foreign policy is still the one copied aside, not the one before it."""
    _policy(box).parent.mkdir(parents=True)
    _policy(box).write_text(FOREIGN)
    assert _run(box).returncode == 0
    _ours(box).unlink()  # the record moved with $HYPRCONF_STATE; /etc did not
    later = FOREIGN.replace("BlockAboutConfig", "BlockAboutProfiles")
    _policy(box).write_text(later)
    box.reset()
    assert _run(box).returncode == 0
    assert _bak(box).read_text() == later
    box.reset()
    assert _run(box, "undo").returncode == 0
    assert _policy(box).read_text() == later


def test_a_policy_that_cannot_be_copied_aside_is_left_where_it_is(box: Box) -> None:
    """A file the module cannot keep a copy of is never the one it overwrites."""
    _policy(box).parent.mkdir(parents=True)
    _policy(box).write_text(FOREIGN)
    proc = _run(box, sudo="case $1 in cp) exit 1 ;; esac\n" + SUDO_RUNS)
    assert proc.returncode == 0 and "could not copy" in proc.stderr
    assert _policy(box).read_text() == FOREIGN and not _bak(box).exists()


def test_undo_leaves_a_policy_hyprconf_never_wrote(box: Box) -> None:
    """No record, not ours — and no sudo to remove it with."""
    _policy(box).parent.mkdir(parents=True)
    _policy(box).write_text(FOREIGN)
    assert _run(box, "undo").returncode == 0
    assert _policy(box).read_text() == FOREIGN
    assert "sudo" not in box.commands


@pytest.mark.parametrize("omarchy_moved", [False, True])
def test_a_policy_from_before_the_record_is_adopted_without_sudo(
    box: Box, omarchy_moved: bool
) -> None:
    """Every box up to 8.2 has the policy and no record: adopting it is what keeps undo
    restoring stock, and `omarchy-update` moving Omarchy's half must not read as foreign."""
    assert _run(box).returncode == 0
    _ours(box).unlink()
    if omarchy_moved:
        box.omarchy_write("default/firefox/policies.json", OMARCHY_MOVED)
    box.reset()
    assert _run(box, tty=False, env={"HYPRCONF_NO_SUDO": "1"}).returncode == 0
    assert "sudo" not in box.commands and _ours(box).is_file()
    box.reset()
    assert _run(box).returncode == 0
    assert ("sudo" in box.commands) is omarchy_moved, "the rewrite, and nothing else"
    assert not _bak(box).exists()
    box.reset()
    assert _run(box, "undo").returncode == 0
    assert not _policy(box).exists()


def test_an_empty_omarchy_policy_warns_and_writes_nothing(box: Box) -> None:
    """`.[0] * .[1]` errors where `reduce` silently dropped Omarchy's whole layer."""
    box.omarchy_write("default/firefox/policies.json", "")
    proc = _run(box)
    assert proc.returncode == 0 and "could not merge" in proc.stderr
    assert not _policy(box).exists() and "sudo" not in box.commands


@pytest.mark.skipif(not OMARCHY_POLICY.is_file(), reason=NEEDS_OMARCHY)
def test_omarchy_still_ships_the_policy_this_module_merges_under() -> None:
    """With the file gone the jq call fails and the module warns instead of writing."""
    theirs = json.loads(OMARCHY_POLICY.read_text())["policies"]["Preferences"]
    assert theirs, OMARCHY_POLICY
    stand_in = json.loads(OMARCHY_TREE["default/firefox/policies.json"])["policies"]["Preferences"]
    assert set(stand_in) <= set(theirs), set(stand_in) - set(theirs)
