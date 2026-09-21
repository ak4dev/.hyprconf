# idle

## What

Omarchy's screensaver starts after 150 s (`config/omarchy/shell.json`, `idle.screensaver`);
this module sets it to **900 s**, once, behind `~/.local/state/hyprconf/idle-applied` —
shell.json is your file, so a later change stays yours. `idle.lock` (300 s) is untouched, so
the lock fires first and stops the screensaver timer (`shell/plugins/services/idle/Service.qml:23-25,72-75,94-97`;
`:69` refuses a launch while locked): the effect is **no screensaver ahead of the 5-minute
lock**, not one at 15 minutes.

No Omarchy command writes an idle timeout (`omarchy commands --json` routes only branding /
launch / toggle screensaver; `omarchy toggle idle` is a stay-awake state file,
`bin/omarchy-toggle-idle:8-9`), so the seam is the sourceable helper every Omarchy
shell.json writer uses — `bin/omarchy-bar:10` sources it the same way. `commit()` is
`jq -S -e` over your shell.json (or, when you have none yet, over the shipped defaults, so
the first run creates one), `mktemp`, `mv`, then `omarchy-shell shell reloadConfig` falling
back to `omarchy-shell -q shell rescanPlugins` (`bin/omarchy-shell-config:14-26,53-62`).

## Requires

`jq` and `omarchy-shell-config`, both in a stock Omarchy. No packages, no `sudo`, no prompt —
nothing here is gated by `--no-packages` or a missing terminal.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/idle && bash ~/.hyprconf/modules/idle/install
```

## Settings

Edit `.idle.screensaver` (seconds) in `~/.config/omarchy/shell.json` — the shell watches the
file and reloads (`shell/shell.qml:134-143`); past the marker nothing re-asserts it. A
screensaver only ever shows while `.idle.screensaver` is below `.idle.lock`.

## Undo

`bash ~/.hyprconf/modules/idle/install undo` drops the key through the same helper and removes the
marker; the shell's own stock 150 s then applies (`shell/plugins/services/idle/Service.qml:17,21`).
The file stays — one the first run created is Omarchy's shipped defaults, key-sorted, minus this key.

## Verified against Omarchy 4.0.4-1
