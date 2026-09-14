# firefox-theme

## What

Omarchy's theme fan-out is Chromium-only (`omarchy-theme-set-browser:8-13`). `userChrome.css.tpl` goes to
`~/.config/omarchy/themed/`, rendered ahead of the built-ins (`omarchy-theme-set-templates:375,390-399`) to
`~/.local/state/omarchy/current/theme/userChrome.css` on every theme set, and `hook` to
`~/.config/omarchy/hooks/theme-set.d/10-hyprconf`, which `omarchy-theme-set:341` runs after every set. It copies that
render to `<profile>/chrome/userChrome.css` when the bytes differ and rewrites the three prefs below in
`<profile>/user.js`, its other lines untouched. The profile is the one Firefox starts: an `[Install<hash>]`
`Default=`, else `[Profile*]` `Default=1`, else the first listed, in `~/.mozilla/firefox/profiles.ini` or its XDG twin
(LibreWolf: add its ini to `inis=`). Firefox reads both at startup only, so it lands at the next start.

## Requires

Nothing — no packages, no sudo, no path outside `$HOME`; a no-op until a Firefox profile exists.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/firefox-theme && bash ~/.hyprconf/modules/firefox-theme/install
```

## Settings

`toolkit.legacyUserProfileCustomizations.stylesheets` loads the stylesheet; `extensions.activeThemeID` and
`ui.systemUsesDarkTheme` follow the mode the render declares in `--hyprconf-theme-mode`. The theme id buys the colour
scheme alone: both built-in ids are `inApp` (`BuiltInThemeConfig.sys.mjs:29,38`), so `:root[lwtheme]` never turns on
(`LightweightThemeConsumer.sys.mjs:424,537`) — the chrome is painted by the template's direct `#navigator-toolbox` /
`#nav-bar` / `#urlbar-background` / `#sidebar-box` rules plus the three variables Firefox 155 still reads.

## Undo

`bash modules/firefox-theme/install undo`: hook, template, render and each profile's `chrome/userChrome.css` go, and the
three `user_pref` lines come back out of `user.js` (removed when it held nothing else). Restart Firefox. `chrome/userChrome.css`
is this module's file outright — one you wrote yourself is replaced, not merged, and removed by the undo; move it aside
first. A profile file that will not go makes the undo exit non-zero and say so, the module's own three files gone regardless.

## Verified against Omarchy 4.0.3-1 — Firefox 155.0.1-1, Bash 5.3
