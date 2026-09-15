<p align="center">
  <img src="assets/banner.svg" width="920" alt=".hyprconf" />
</p>

<p align="center">
  <a href="https://hyprconf.sh"><img alt="installer" src="https://img.shields.io/badge/installer-hyprconf.sh-0ea5e9?style=for-the-badge" /></a>
  <img alt="arch linux" src="https://img.shields.io/badge/arch-linux-1793d1?style=for-the-badge&logo=archlinux&logoColor=white" />
  <img alt="hyprland" src="https://img.shields.io/badge/hyprland-wayland-111827?style=for-the-badge&logo=wayland&logoColor=white" />
  <a href="https://omarchy.org"><img alt="omarchy overlay" src="https://img.shields.io/badge/omarchy-overlay-3a7f2e?style=for-the-badge" /></a>
</p>

# .hyprconf

**hyprconf** is an overlay for [Omarchy](https://omarchy.org): one `install.sh` that runs seventeen self-contained modules — hotkeys, look'n'feel and monitor presets, four bar widgets, kitty with zsh + Powerlevel10k, a Dracula theme and Firefox theming, a Firefox policy, VS Code, a FIDO2 boot unlock, a dual-GPU Vulkan fix, a Keychron udev rule — each through Omarchy's own tools and seams, each installable and undoable on its own. Omarchy owns the base system; hyprconf layers one person's preferences on top and disturbs the install as little as possible.
A personal Omarchy overlay, shared as-is — fork it, take what's useful; feature requests and issues may not be taken.

## Requirements

- A running [Omarchy](https://omarchy.org) install — the version each release is verified against is the pin line in [`AGENTS.md`](AGENTS.md). `install.sh` refuses a box with no Omarchy tree at `/usr/share/omarchy` (`$OMARCHY_PATH`), and refuses to run as root.
- `git`, and a terminal for anything that needs `sudo` — the modules that install packages or write outside `$HOME` are marked *sudo* in the table below. `install.sh` itself asks for none.

## Install

```bash
bash <(curl -fsSL --proto '=https' https://hyprconf.sh)
```

`hyprconf.sh` serves `install.sh` itself to curl. Run with no payload beside it, it clones the `stable` branch into `~/.hyprconf` — or uses the checkout already there, without pulling it — and hands over to that checkout's `install.sh` with the same arguments; `HYPRCONF_REPO`, `HYPRCONF_BRANCH` and `HYPRCONF_DIR` override the three. Run it as your regular user: the modules ask for `sudo` themselves, and a `sudo`-prefixed bootstrap would half-install into `/root`. The same by hand:

```bash
git clone -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf
bash ~/.hyprconf/install.sh
```

That first run makes `~/.local/bin/hyprconf`, the command from then on — `hyprconf -h` is the whole contract:

| Flag | Effect |
|---|---|
| *(none)* | Apply every module once. Idempotent — re-running is how you pick up changes |
| `<module>…` | Only the modules named — the re-apply after an edit, e.g. `hyprconf hypr`. An unknown name is refused before anything runs |
| `--sync` | `git pull --ff-only` the checkout, re-apply, then `omarchy-update` (whose post-update hook re-applies once more, after Omarchy's migrations). What the `hyprsync` alias runs. It applies whatever `stable` now carries, root writes included — the trade-off of a clone-only, https-pinned overlay (AGENTS.md rule 8) |
| `--no-update` | Apply only; never invoke `omarchy-update`. What the post-update hook passes, since it already runs inside an update |
| `--no-packages` | Skip everything that needs `sudo`: exported to the modules as `HYPRCONF_NO_SUDO`, which each honours in one line and carries on. The hook passes this too |
| `--undo` | Every module's `install undo` in reverse order, then the hook and the `~/.local/bin/hyprconf` link. With module names, only those |

Beyond running the modules, `install.sh` puts two things in `$HOME`: that link (a symlink into the checkout, re-pointed only when wrong) and Omarchy's own post-update hook — `omarchy hook install post-update hooks/10-hyprconf`, which runs `hyprconf --no-update --no-packages` after every `omarchy-update` and bows out when the link is gone. A module that fails does not stop the others: it is named at the end, and with `--sync` it stops `omarchy-update`.

## Modules

Every row is a directory under `modules/` — its own `install`, `README.md` (what it changes and the Omarchy seam it rides, settings, undo), tests and payload. `install.sh` runs them all, in no particular order; `hyprconf <name>` re-runs one. Each installs alone from a sparse checkout of just that directory, and every `bash modules/…` below is `bash ~/.hyprconf/modules/…`:

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/<name> && bash ~/.hyprconf/modules/<name>/install
```

| Module | What | Install alone | Undo |
|---|---|---|---|
| [`bar-active-window`](modules/bar-active-window/README.md) | The focused window's title on two caption-size lines, as the `hyprconf.active-window` plugin | `bash modules/bar-active-window/install` | `bash modules/bar-active-window/install undo` |
| [`bar-clock`](modules/bar-clock/README.md) | Omarchy's own clock ticking seconds, as `hyprconf.clock` — format `hh:mm:ss AP`, set once | `bash modules/bar-clock/install` | `bash modules/bar-clock/install undo` |
| [`bar-resources`](modules/bar-resources/README.md) | CPU / temp / RAM / GPU / net on two aligned lines in the bar's right section, as `hyprconf.resources` | `bash modules/bar-resources/install` | `bash modules/bar-resources/install undo` |
| [`bar-workspaces`](modules/bar-workspaces/README.md) | Only the workspaces that exist, on two lines, Pac-Man on the focused one, as `hyprconf.workspaces` | `bash modules/bar-workspaces/install` | `bash modules/bar-workspaces/install undo` |
| [`fastfetch`](modules/fastfetch/README.md) | The shell greeting's layout at `~/.config/hyprconf/fastfetch.jsonc` — Omarchy's About screen stays stock | `bash modules/fastfetch/install` | `bash modules/fastfetch/install undo` |
| [`firefox`](modules/firefox/README.md) | Firefox through Omarchy's installer, one system policy (Omarchy's prefs merged under hyprconf's), the default browser once — *sudo* | `bash modules/firefox/install` | `bash modules/firefox/install undo` |
| [`firefox-theme`](modules/firefox-theme/README.md) | Every `omarchy theme set` reaches Firefox: a user template Omarchy renders, a theme-set hook, three `user_pref` lines | `bash modules/firefox-theme/install` | `bash modules/firefox-theme/install undo` |
| [`font`](modules/font/README.md) | GeistMono Nerd Font as the system monospace, once; installs `otf-geist-mono-nerd` — *sudo* | `bash modules/font/install` | `bash modules/font/install undo` |
| [`hypr`](modules/hypr/README.md) | The keymap, the look'n'feel and input deltas (copies in `~/.config/hypr/`), the monitor presets (seeded once, yours to edit — a run says when this checkout's copy has moved since), `hyprconf-gaps` and `hyprconf-monitor-preset` | `bash modules/hypr/install` | `bash modules/hypr/install undo` |
| [`idle`](modules/idle/README.md) | The screensaver after 15 min instead of 150 s (`idle.screensaver` in `shell.json`), once | `bash modules/idle/install` | `bash modules/idle/install undo` |
| [`keychron`](modules/keychron/README.md) | One udev rule so launcher.keychron.com reaches Keychron and Lemokey boards over WebHID — *sudo* | `bash modules/keychron/install` | `bash modules/keychron/install undo` |
| [`shell-zsh`](modules/shell-zsh/README.md) | zsh + Powerlevel10k inside the terminal, no framework: one `source` line in `~/.zshrc`, a pinned p10k clone; installs `zsh` and two plugins — *sudo* | `bash modules/shell-zsh/install` | `bash modules/shell-zsh/install undo` |
| [`terminal-kitty`](modules/terminal-kitty/README.md) | kitty as the default terminal, once, plus two preferences as a kitty include; installs `kitty` — *sudo* | `bash modules/terminal-kitty/install` | `bash modules/terminal-kitty/install undo` |
| [`themes`](modules/themes/README.md) | The `dracula` user theme in Omarchy's theme menu, never activated, plus extra wallpapers filed per theme | `bash modules/themes/install` | `bash modules/themes/install undo` |
| [`vscode`](modules/vscode/README.md) | VS Code through Omarchy's installer, `code` as the default editor once — *sudo* | `bash modules/vscode/install` | `bash modules/vscode/install undo` |
| [`vulkan-gpu`](modules/vulkan-gpu/README.md) | `hyprconf-vulkan-gpu` on PATH: pins Vulkan (Steam/Proton) to the display GPU on a two-GPU box, run by hand | `bash modules/vulkan-gpu/install` | `bash modules/vulkan-gpu/install undo` |
| [`yubikey`](modules/yubikey/README.md) | `hyprconf-yubikey` on PATH: FIDO2 unlock of the LUKS root at boot; `enroll`, run by hand, writes the two `/etc` drop-ins | `bash modules/yubikey/install` | `bash modules/yubikey/install undo` |

What it deliberately leaves alone: the login shell (no `chsh` — why, in [`shell-zsh`](modules/shell-zsh/README.md)); the body of `~/.config/kitty/kitty.conf`, `~/.bashrc`, `/usr/share/omarchy`, and everything under `/etc` except the Firefox policy, the Keychron rule and — only when you run it — `hyprconf-yubikey enroll`'s two drop-ins; installed packages (nothing is removed, ever); the active theme, Omarchy's `monitors.lua`, and every set-once choice (font, default apps, idle, clock, widget enables) after the first run — change them with Omarchy's own commands and hyprconf will not take them back; Omarchy's keyboard-layout logic and its volume / brightness / media keys.

Proton VPN: hyprconf installs nothing for it — `omarchy pkg add proton-vpn-gtk-app proton-vpn-cli` (both Arch `extra`, D-Bus-activated: nothing to enable, no reboot).

## Sync

```bash
hyprsync            # `hyprconf --sync`: pull the checkout, re-apply, omarchy-update
hyprconf            # re-apply everything — after an `omarchy refresh`, or just because
hyprconf hypr       # re-apply one module: the edit workflow for the Hyprland copies
```

After `omarchy-update` the post-update hook re-applies the overlay by itself — a migration that rewrites `bindings.lua`, or an `omarchy refresh config kitty/kitty.conf` that drops the `include`, is put back — under `hyprsync` too, where that second apply is the one that outlives the migrations. `omarchy refresh config hypr/<file>` / `omarchy refresh hyprland` land on the copies in `~/.config/hypr/`; the checkout is never touched. Edit `modules/hypr/*.lua` in the checkout, then `hyprconf hypr`.

## Reverting to stock

```bash
hyprconf-yubikey remove   # only if you enrolled a key — first, while the tool is still on PATH; both drop-ins go with it
hyprconf --undo           # every module's `install undo` in reverse order, then the hook and the ~/.local/bin/hyprconf link (the Firefox policy and the udev rule need sudo)
hyprconf --undo <name>    # one module — the same as `bash ~/.hyprconf/modules/<name>/install undo`
rm -rf ~/.local/state/hyprconf ~/.config/omarchy/plugins/.hyprconf.*.bak.* ~/.oh-my-zsh   # leftovers: the emptied state dir, folders a bar module moved aside, and the Oh My Zsh a hyprconf 7.x install left behind
sed -i '/^  \/\/ >>> hyprconf >>>$/,/^  \/\/ <<< hyprconf <<<$/d' ~/.config/omarchy/extensions/omarchy-menu.jsonc   # a 7.x install's Proton VPN menu row, whose installer is gone (8.0 manages no menu block)
```

What each undo puts back — the Undo section of its README:

- [`bar-active-window`](modules/bar-active-window/README.md#undo), [`bar-resources`](modules/bar-resources/README.md#undo), [`bar-workspaces`](modules/bar-workspaces/README.md#undo) — the plugin disabled (Omarchy's stock widget back where there is one), the link and the marker gone
- [`bar-clock`](modules/bar-clock/README.md#undo) — disabled, `omarchy.clock`'s format and the centre anchor back, link and marker gone
- [`fastfetch`](modules/fastfetch/README.md#undo) — the copy gone; a link a 7.x install left at `~/.config/fastfetch/config.jsonc` cleared and its `.stock` put back
- [`firefox`](modules/firefox/README.md#undo) — the policy and the marker gone; Firefox stays, and the search engine falls to Firefox's regional default
- [`firefox-theme`](modules/firefox-theme/README.md#undo) — hook, template, render, each profile's `chrome/userChrome.css` and the three prefs gone
- [`font`](modules/font/README.md#undo) — the marker gone; it prints the `omarchy font set` that restores Omarchy's family (the setter restarts the shell)
- [`hypr`](modules/hypr/README.md#undo) — `stock` layout, then at each of the three paths the file of your own the first run kept as `.stock`, else Omarchy's own template; presets and tool links gone
- [`idle`](modules/idle/README.md#undo) — the key dropped, Omarchy's 150 s back
- [`keychron`](modules/keychron/README.md#undo) — the rule removed and reloaded (`sudo`)
- [`shell-zsh`](modules/shell-zsh/README.md#undo) — the `~/.zshrc` line, the kitty include, the `~/.p10k.zsh` link (a `.stock` restored) and the clone it made; the packages stay
- [`terminal-kitty`](modules/terminal-kitty/README.md#undo) — the include, `hyprconf.conf` and the marker gone; the default handed to Omarchy's `foot` while kitty is still current
- [`themes`](modules/themes/README.md#undo) — the theme link and the seeded wallpapers gone
- [`vscode`](modules/vscode/README.md#undo) — the editor back to `nvim`; VS Code stays
- [`vulkan-gpu`](modules/vulkan-gpu/README.md#undo), [`yubikey`](modules/yubikey/README.md#undo) — the `~/.local/bin` link gone and nothing else: a pin or an enrolment is yours, so `hyprconf-vulkan-gpu remove` / `hyprconf-yubikey remove` come first

Then delete `~/.hyprconf`. Do not `omarchy refresh hyprland` instead of the hypr undo — it also overwrites `hyprland.lua`, `autostart.lua` and `monitors.lua` with Omarchy's templates.

## Testing & development

`make check` runs the three CI gates — `make lint`, `make shellcheck` and `make test` (one hermetic suite beside each module, and `tests/` for the core and the tree-wide guards). The tree, the test harness, the publish flow and the website upload are in [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md); the rules that bind every change are in [`AGENTS.md`](AGENTS.md).
