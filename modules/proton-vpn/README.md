# proton-vpn

## What

Installs Proton VPN's app and command line, and starts the app minimized to the tray at every
login, so the VPN can be up before anything else talks to the network.

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

Omarchy's `autostart.lua` and bar tray. `proton-vpn-gtk-app` and `proton-vpn-cli`, both official
`extra`, installed through `omarchy-pkg-add`; with `--no-packages` (`HYPRCONF_NO_SUDO`) or no
terminal for `sudo` they are skipped with one line, and no autostart line lands until the app is
there. An install that fails fails the module.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/proton-vpn && bash ~/.hyprconf/modules/proton-vpn/install
```

## Settings

Starting is not connecting: whether the app connects when it starts is its own **Connect at app
startup** setting, off by default (`proton/vpn/app/gtk/config.py:31`). Turn it on once in the app,
with the **kill switch**, which stops traffic leaving outside the tunnel when the VPN drops. Both are
the app's, in its own config; hyprconf sets neither.

## Undo

`bash ~/.hyprconf/modules/proton-vpn/install undo` removes the autostart line and nothing else: the
packages stay (hyprconf removes none), and an `autostart.lua` that did not end in a newline keeps
the one the install added. The next login starts no VPN.

## Verified against Omarchy 4.0.4-1
proton-vpn-gtk-app 4.18.1, proton-vpn-cli 1.0.3.
