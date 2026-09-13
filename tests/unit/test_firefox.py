"""Tests for infra/firefox/policies.json — the system Firefox policy install.sh ships.

The policy is one of the overlay's two writes outside $HOME (see stage_firefox;
the other is the Keychron udev rule): Firefox reads enterprise policies only
from root-owned paths. What it says is the JSON's to state and README ›
Firefox settings' to explain; these are the conditions under which Firefox
does something other than what it says.

The load-bearing one is test_every_pref_is_one_firefox_will_accept: the
Preferences policy silently drops any pref outside Firefox's own allowlist, so
a plausible-looking entry can do nothing at all and never say so. The merge
with Omarchy's own policy is exercised with the real jq inside the installer
(test_omarchy_install.py), which is what runs it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
POLICIES_JSON = REPO_ROOT / "infra" / "firefox" / "policies.json"
POLICIES = json.loads(POLICIES_JSON.read_text(encoding="utf-8"))["policies"]

# Firefox's own allowlist for the Preferences policy, verbatim from
# `Preferences.onBeforeAddons` (Policies.sys.mjs:2632-2674, Firefox
# 155.0.1) — a prefix match, `preference.startsWith(prefix)` (:2726-2727).
# A pref outside it is dropped with "Preference not allowed for stability
# reasons" logged to the browser console and nothing else: the policy still
# loads, the pref just never applies. Pinned rather than derived because
# omni.ja is a zip with a patched central directory that Python's zipfile
# refuses (unzip reads it, and is not one of the tools the suite may
# assume). Re-derived against 155.0.1 on the 4.0.3-1 pin bump: byte-identical
# to the 154.0 list, 41 prefixes in the same order, blockedPrefs unchanged.
# Re-derive on the next Firefox major bump with:
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


def test_every_extension_is_force_installed_into_the_nav_bar() -> None:
    """The policy's extension entries, checked as a shape rather than by id.

    `default_area` is Firefox's own knob for where a browser action lands
    (ExtensionActions.sys.mjs: the policy value beats the manifest's, and
    without one an extension falls into the overflow menu) — the fallback for
    a profile whose saved layout does not know the button. `private_browsing`
    is deliberately absent: its presence at ANY value takes the about:addons
    toggle away from the user (XPIDatabase.sys.mjs). What is installed, and
    from where, is README › Firefox settings.
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
    JSON's to state, and README › Firefox settings the user's home for it.

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
