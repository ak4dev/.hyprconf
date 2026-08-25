"""Tests for infra/firefox/policies.json — the system Firefox policy install.sh ships.

The policy is the overlay's one write outside $HOME (see stage_firefox): Firefox
reads enterprise policies only from root-owned paths. This pins what it must
keep saying: telemetry and studies off, tracking protection on, uBlock Origin
and Proton Pass force-installed, DuckDuckGo the default engine, and the UI
settings captured from the machine hyprconf is a config of.

The load-bearing test here is test_every_pref_is_one_firefox_will_accept: the
Preferences policy silently drops any pref outside Firefox's own allowlist, so
a plausible-looking entry can do nothing at all and never say so.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.test_omarchy_install import OMARCHY_FIREFOX_POLICY

REPO_ROOT = Path(__file__).parent.parent.parent
POLICIES_JSON = REPO_ROOT / "infra" / "firefox" / "policies.json"
POLICIES = json.loads(POLICIES_JSON.read_text(encoding="utf-8"))["policies"]
# What omarchy-install-browser copies to /usr/lib/firefox/distribution/ —
# read when Omarchy is installed (never written); the install suite's fixture
# of it stands in elsewhere (CI), so the merge check never skips.
OMARCHY_POLICY = Path("/usr/share/omarchy/default/firefox/policies.json")

UBLOCK_ID = "uBlock0@raymondhill.net"
PROTON_PASS_ID = "78272b6fa58f4a1abaac99321d503a20@proton.me"

# Firefox's own allowlist for the Preferences policy, verbatim from
# `Preferences.onBeforeAddons` (Policies.sys.mjs:2617-2659, Firefox 154.0) —
# a prefix match, `preference.startsWith(prefix)`. A pref outside it is
# dropped with "Preference not allowed for stability reasons" logged to the
# browser console and nothing else: the policy still loads, the pref just
# never applies. Pinned rather than derived because omni.ja is a zip with a
# patched central directory that Python's zipfile refuses (unzip reads it,
# and is not one of the tools the suite may assume). Re-derive on a Firefox
# major bump with:
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
# (Policies.sys.mjs:2690-2695). `security.*` is never a prefix match — it is
# tested against a separate exact-match list, so no `security.` pref belongs
# in our policy without checking that list first.
BLOCKED_PREFS = (
    "app.update.channel",
    "app.update.lastUpdateTime",
    "app.update.migrated",
    "browser.vpn_promo.disallowed_regions",
)


def test_policy_keeps_the_privacy_defaults() -> None:
    assert POLICIES["DisableTelemetry"] is True
    assert POLICIES["DisableFirefoxStudies"] is True
    etp = POLICIES["EnableTrackingProtection"]
    assert etp["Value"] is True and etp["Cryptomining"] is True and etp["Fingerprinting"] is True


def test_both_extensions_are_force_installed_into_the_toolbar() -> None:
    """uBlock Origin and Proton Pass, by the ids their signed XPIs declare.

    `default_area` is Firefox's own knob for where a browser action lands
    (ExtensionActions.sys.mjs: the policy value beats the manifest's, and
    without one an extension falls into the overflow menu) — which is why the
    machine's `browser.uiCustomization.state` is not shipped: the deliberate
    part of that blob is these two buttons, and this puts them there without
    pinning a serialized layout Firefox rewrites on every start.

    `private_browsing` is deliberately absent: its presence at ANY value takes
    the about:addons toggle away from the user (XPIDatabase.sys.mjs), and
    neither extension is enabled in private windows on the machine this is a
    config of.
    """
    extensions = POLICIES["ExtensionSettings"]
    assert set(extensions) == {UBLOCK_ID, PROTON_PASS_ID}
    for addon_id, slug in ((UBLOCK_ID, "ublock-origin"), (PROTON_PASS_ID, "proton-pass")):
        entry = extensions[addon_id]
        assert entry["installation_mode"] == "force_installed", addon_id
        assert entry["install_url"] == (
            f"https://addons.mozilla.org/firefox/downloads/latest/{slug}/latest.xpi"
        ), addon_id
        assert entry["default_area"] == "navbar", addon_id
        assert "private_browsing" not in entry, addon_id


def test_captured_ui_settings_are_the_ones_the_machine_has() -> None:
    """The settings a person picked in Firefox's own UI, not what it wrote itself.

    Everything else in the profile that differs from stock is Firefox's own
    bookkeeping — a find-bar flash counter, uBlock's prefetch prefs, a
    login-backend migration, a sidebar tool list identical to the built-in
    default — and is deliberately not pinned here.

    That includes prefs an active Nimbus rollout wrote, which look exactly
    like settings: `ExperimentStoreData.json` is the receipt. The sports
    widget is the one that nearly got through — a `prefFlips` rollout sets
    `widgets.sportsWidget.enabled` false on the user branch, and its toggle
    is gated on `widgets.system.sportsWidget.enabled`, which ships false, so
    it was never on screen to switch off. Pinning it would have flipped
    Firefox's own default for something nobody chose.
    """
    prefs = POLICIES["Preferences"]
    # Compact density. Only reachable because browser.compactmode.show is on,
    # so the two travel together. Type is explicit as a matter of course: the
    # policy engine coerces a bare 0/1 to boolean unless the entry says
    # "number" — browser.uidensity's own default is already an int, so here
    # it is belt-and-braces, but the rule is easier to keep than to check.
    assert prefs["browser.compactmode.show"]["Value"] is True
    assert prefs["browser.uidensity"] == {"Value": 1, "Status": "default", "Type": "number"}
    # Firefox Home: every panel the machine has switched off.
    for pref in (
        "browser.newtabpage.activity-stream.feeds.topsites",
        "browser.newtabpage.activity-stream.showSearch",
        "browser.newtabpage.activity-stream.showSponsored",
        "browser.newtabpage.activity-stream.showSponsoredTopSites",
        "browser.newtabpage.activity-stream.showSponsoredCheckboxes",
        "browser.newtabpage.activity-stream.feeds.section.topstories",
        "browser.newtabpage.activity-stream.showWeather",
        "browser.newtabpage.activity-stream.widgets.weather.enabled",
    ):
        assert prefs[pref]["Value"] is False, pref
    # Vertical tabs and the revamped sidebar.
    assert prefs["sidebar.revamp"]["Value"] is True
    assert prefs["sidebar.verticalTabs"]["Value"] is True
    # "Play DRM-controlled content", through Firefox's own policy for it
    # rather than a raw media.eme.enabled pref (they do the same thing).
    assert POLICIES["EncryptedMediaExtensions"] == {"Enabled": True, "Locked": False}
    # The default search engine. The name must be exactly the one Firefox
    # knows: a miss falls back to Google silently, with nothing logged.
    assert POLICIES["SearchEngines"]["Default"] == "DuckDuckGo"


def test_nothing_is_locked_that_should_stay_the_users_to_change() -> None:
    """Every captured UI setting is a `default`, so it seeds a profile and then
    gets out of the way. Only the anti-feature lock stays locked."""
    locked = {p for p, v in POLICIES["Preferences"].items() if v.get("Status") == "locked"}
    assert locked == {"browser.discovery.enabled"}
    assert POLICIES["EnableTrackingProtection"]["Locked"] is False
    assert POLICIES["EncryptedMediaExtensions"]["Locked"] is False


def test_every_pref_is_one_firefox_will_accept() -> None:
    """No pref outside Firefox's allowlist — those are dropped in silence.

    Only hyprconf's own file is checked. Omarchy's ships `apz.overscroll.enabled`,
    which is NOT on the allowlist and is rejected on every start (verified
    against Firefox 154.0 with the real merged policy); that is Omarchy's to
    fix, and asserting on it here would fail for something the overlay does
    not own.
    """
    for pref, value in POLICIES["Preferences"].items():
        assert pref not in BLOCKED_PREFS, pref
        assert not pref.startswith("security."), pref
        assert any(pref.startswith(prefix) for prefix in ALLOWED_PREFIXES), pref
        assert value["Status"] in ("default", "locked"), pref
        # A 0/1 int lands as a boolean unless the policy says otherwise.
        if isinstance(value["Value"], int) and not isinstance(value["Value"], bool):
            assert value.get("Type") == "number", pref


def _merge(base: dict, over: dict) -> dict:
    """jq's `*` (what stage_firefox runs): a recursive object merge, the
    right-hand side winning on a shared key."""
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(out.get(k), dict) and isinstance(v, dict) else v
    return out


def test_merged_with_omarchys_policy_it_keeps_every_omarchy_pref() -> None:
    """The installed file is Omarchy's own default/firefox/policies.json
    merged under ours (stage_firefox), because /etc/firefox/policies takes
    precedence over the distribution/ copy omarchy-install-browser writes
    and would otherwise shadow it. Checked against the installed Omarchy
    when there is one (read-only) — and then the install suite's fixture of
    that file may name no pref Omarchy no longer ships — else against the
    fixture, so CI exercises the merge too. On a shared pref ours wins."""
    ours_prefs = POLICIES.get("Preferences", {})
    if OMARCHY_POLICY.is_file():
        theirs = json.loads(OMARCHY_POLICY.read_text(encoding="utf-8"))
        fixture_only = set(OMARCHY_FIREFOX_POLICY["policies"]["Preferences"]) - set(ours_prefs)
        assert fixture_only <= set(theirs["policies"]["Preferences"]), fixture_only
    else:
        theirs = OMARCHY_FIREFOX_POLICY
    ours = json.loads(POLICIES_JSON.read_text(encoding="utf-8"))
    merged = _merge(theirs, ours)["policies"]
    for pref, value in theirs["policies"].get("Preferences", {}).items():
        assert pref in merged["Preferences"], pref
        assert merged["Preferences"][pref] == ours_prefs.get(pref, value), pref
    for key in POLICIES:
        assert key in merged, key
    assert merged["DisableTelemetry"] is True
