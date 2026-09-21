# firefox

## What

Firefox through Omarchy's own installer, one system policy, and firefox as the default browser once.

| | |
|---|---|
| Firefox when absent | `omarchy-install-browser firefox` — Omarchy's own flow: `omarchy-pkg-add firefox`, its prefs to `/usr/lib/firefox/distribution/policies.json`, `MOZ_ENABLE_WAYLAND=1` (`bin/omarchy-install-browser:67-74` → `install/helpers/browser-policy.sh:161-168`). Never a bare `omarchy-pkg-add firefox` |
| `/etc/firefox/policies/policies.json` | Omarchy's `default/firefox/policies.json` merged **under** [`policies.json`](policies.json) (`jq '*'`, ours wins on a shared key), written with `sudo install -Dm644 --` only when the bytes differ. Firefox reads enterprise policies only from root-owned paths and `/etc/firefox` outranks `distribution/`, so the merge is what keeps Omarchy's VA-API and scaling prefs alive — nothing in Omarchy writes `/etc/firefox`. A file already there is hyprconf's when merging [`policies.json`](policies.json) over it changes nothing (recorded as `firefox-policy`); anyone else's is copied to `policies.json.bak` once, before it is replaced |
| Default browser | `omarchy-default-browser firefox`, **once** Firefox is installed (marker `browser-applied`; a v7 `defaults-applied` is migrated to it) — never a default pointing at an absent browser. The value is read back, never the setter's exit status — that status is its closing notification's |

What the policy carries: telemetry, studies and feedback off; tracking protection with cryptominer and fingerprinter blocking; **uBlock Origin** and **Proton Pass** force-installed and pinned to the toolbar; **DuckDuckGo** the default engine; compact density, vertical tabs, a bare Firefox Home; DRM playback on. Every captured pref is a `Status: "default"` — it seeds a profile and then gets out of the way; only `browser.discovery.enabled` is locked.

The find bar's *Highlight All* is deliberately absent: `findbar.highlightAll` is outside Firefox's allowlist and has no policy of its own. Tick it once in the find bar.

Three Firefox behaviours the file rides on — the `Preferences` allowlist's silent drop, its `"Type"` rule and the `browser.uiCustomization.state` seeding semantics — are pinned with their sources and the recipe to re-derive them in [`test_firefox.py`](test_firefox.py); `SearchEngines` applies on release, not ESR only (`policies-schema.json`: `firefox.version_added` 139, no `enterprise_only`; Firefox 155.0.1). Read it before editing `policies.json`.

## Requires

`jq`, `sudo` and a terminal for the password prompt. `toolkit.legacyUserProfileCustomizations.stylesheets` is **not** here: the `firefox-theme` module writes it per profile, which is the half that works without sudo.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/firefox && bash ~/.hyprconf/modules/firefox/install
```

## Settings

`HYPRCONF_NO_SUDO` (what `--no-packages` and the post-update hook set) or no terminal: the install and the policy are skipped with a pointer line — the default-browser seed still runs (once Firefox is there), because on a settled box the hook's run is the only one there is. `HYPRCONF_STATE` moves the state directory.

## Undo

`bash modules/firefox/install undo` — removes the `browser-applied` marker, and the policy (`sudo`) if hyprconf wrote it: a `policies.json.bak` goes back in its place, and a policy hyprconf never wrote is left alone. A v7 `defaults-applied` is left, because it is `vscode`'s too, so on an upgraded box a re-install seeds no default browser until you delete it. Firefox stays installed, and the two extensions become ordinary add-ons you can remove. Dropping the policy hands the search engine to Firefox's region default rather than back to your old pick, because setting it by policy cleared the profile's record: set it again in Settings › Search. Choose a browser with `omarchy default browser <name>`.

## Verified against Omarchy 4.0.4-1

Firefox 155.0.1-1, jq 1.8.2.
