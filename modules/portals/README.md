# portals

## What

Closes two desktop-portal holes that let any app, sandboxed or not, reach past its own windows:

- **Input capture, off for every app.** Hyprland's portal backend gives keyboard and pointer
  capture to any app that asks, with no prompt (xdg-desktop-portal-hyprland 1.4.1,
  `src/portals/InputCapture.cpp:241-273,429-440`), and the portal frontend adds none
  (xdg-desktop-portal 1.22.1, `src/input-capture.c`). An app sets an invisible barrier on a screen
  edge; once your pointer crosses it, the cursor is gone and your keystrokes go to that app until
  it lets go. Only screen-edge sharing tools (Deskflow, Synergy) use it. The fix is xdg-desktop-portal's
  own per-user config, `~/.config/xdg-desktop-portal/hyprland-portals.conf`: the portal reads the one
  highest-precedence file, `~/.config` first (`portals.conf(5)`), so ours is the `hyprland` package's
  `/usr/share/xdg-desktop-portal/hyprland-portals.conf` plus
  `org.freedesktop.impl.portal.InputCapture=none` ("do not provide", same page) — rebuilt on any run
  that finds the packaged file changed, so its routing never drifts.
- **Screen sharing asks every time.** Omarchy seeds `allow_token_by_default = true` in
  `~/.config/hypr/xdph.conf` (`config/hypr/xdph.conf:2`), so a share you approve once hands that app
  a token to resume sharing later with no picker. That line is set to `false`, xdph's own default
  (`src/core/PortalManager.cpp:76`); the rest of the file is left as it is.

Both daemons read their config once at start (`default/agents/skills/omarchy/hyprland.md:31`) and
Omarchy has no restart for either, so a run that changed something restarts them with
`systemctl --user try-restart` — only those already running, and only then.

## Requires

The `hyprland` package's portal config and Omarchy's `xdph.conf`, both in a stock Omarchy. No
packages, no `sudo`, no prompt.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/portals && bash ~/.hyprconf/modules/portals/install
```

## Settings

Not set-once: these are hyprconf's own deltas, like the `hypr` copies, so any run — `hyprsync`, a
plain `hyprconf`, the hook after every `omarchy-update` — puts a `true` back to `false` (`1`, `yes`
and `on` too, in its block or as `screencopy:allow_token_by_default`) and rebuilds the portal config.
A portal config of your own in `~/.config/xdg-desktop-portal/` (either name) is left alone, with one
line on each run saying what to add to its `[preferred]` group.

## Undo

`bash ~/.hyprconf/modules/portals/install undo` deletes our `hyprland-portals.conf` (never one of
yours) and its directory if that leaves it empty, puts `allow_token_by_default` back to `true` when
Omarchy's seed has it so, and restarts the portals once.

## Verified against Omarchy 4.0.6-1
xdg-desktop-portal 1.22.1, xdg-desktop-portal-hyprland 1.4.1, `hyprland` 0.56.2's packaged portal config.
