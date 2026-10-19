# proton-vpn

## What

Installs Proton VPN's app and command line, starts the app minimized to the tray at every login,
and sets its **Auto connect** to the fastest server once, so the VPN is up before anything else
talks to the network.

The start is one line in `~/.config/hypr/autostart.lua`, the file Omarchy keeps for "Extra
autostart processes" (`config/hypr/autostart.lua:1-2`, required by `config/hypr/hyprland.lua:23`):

```lua
o.launch_on_start("protonvpn-app --start-minimized") -- hyprconf/proton-vpn
```

Omarchy's helper runs that through `uwsm-app` once, when Hyprland starts
(`default/hypr/helpers.lua:108-120`), so reloading the config starts no second copy.
`--start-minimized` hides the window only while a tray is up (`proton/vpn/app/gtk/app.py:130-148`),
which Omarchy's bar provides. The line is added only once the app is installed, and put back on any
run that finds it gone — `omarchy refresh hyprland` rewrites `autostart.lua`.

## Requires

Omarchy's `autostart.lua` and bar tray, and `jq` (in Omarchy's base) for the app's config.
`proton-vpn-gtk-app` and `proton-vpn-cli`, both official `extra`, installed through
`omarchy-pkg-add`; with `--no-packages` (`HYPRCONF_NO_SUDO`) or no terminal for `sudo` they are
skipped with one line, and no autostart line or Auto connect lands until the app is there. An
install that fails fails the module.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/proton-vpn && bash ~/.hyprconf/modules/proton-vpn/install
```

## Settings

Starting is not connecting: that is the app's **Auto connect** setting, off by default
(`proton/vpn/app/gtk/config.py:31`). It is a text field, not a toggle. It takes `Fastest`, a country
code (`US`) or a server (`NL#42`), and anything else is looked up as a country
(`controller.py:218-231`). Typing `On` therefore fails every start with "No server available in the
current tier" (`session/servers/logicals.py:306`). The module sets it to `FASTEST` once, in the
app's own `~/.config/Proton/VPN/app-config.json`, behind
`~/.local/state/hyprconf/autoconnect-applied`, and keeps the app's other settings. A file that is not
JSON is left alone and retried on the next run. A value you type in the app afterwards is yours and
is never put back. The app reads the file when it starts and saves all of it on any change
(`controller.py:457-474`), so a setting changed in an app that was open during the install puts the
old value back. Turn on the **kill switch** in the app yourself: it stops traffic leaving outside
the tunnel when the VPN drops, and hyprconf does not set it.

## Undo

`bash ~/.hyprconf/modules/proton-vpn/install undo` removes the autostart line and the marker. It
also takes Auto connect back to Off, but only while it still reads `FASTEST`: a value set in the app
since stays. The packages stay (hyprconf removes none), and an `autostart.lua` that did not end in
a newline keeps the one the install added. The next login starts no VPN.

## Verified against Omarchy 4.0.4-1
proton-vpn-gtk-app 4.18.6, proton-vpn-cli 1.0.5.
