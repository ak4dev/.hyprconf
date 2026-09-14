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

**hyprconf** is an overlay for [Omarchy](https://omarchy.org): one idempotent
`install.sh` plus the files it ships. Omarchy owns the base system (packages,
session, shell, theme engine, lock/idle, bar); hyprconf layers one person's
preferences on top, always through Omarchy's own tools and documented seams:

| Layer | What you get |
|---|---|
| Hyprland | hyprconf's keymap in `~/.config/hypr/bindings.lua` (with descriptions, so it shows in Omarchy's `SUPER+K` menu); tighter gaps, hairline rounding, blur/shadow, fade workspace animation, natural scroll, 3-finger swipe, Steam tiled like every other window; the `bedroom` / `kitchen` / `laptop` monitor presets, hot-swapped on a hotkey through Omarchy's Hyprland toggles directory — Omarchy's `monitors.lua` is never touched ([`modules/hypr`](modules/hypr/README.md)) |
| Bar widgets | A clock that ticks seconds, active-only workspaces on two lines with a Pac-Man on the focused one, the focused window's title, a CPU/temp/mem/GPU/net readout — all as Omarchy shell plugins |
| Terminal + shell | kitty as the default terminal, with two preferences as an include ([`modules/terminal-kitty`](modules/terminal-kitty/README.md)), running zsh + Powerlevel10k *inside* the terminal, no framework in between ([`modules/shell-zsh`](modules/shell-zsh/README.md)) |
| Greeting | hyprconf's `fastfetch` layout in the shell, at a path of its own — Omarchy's About screen stays stock ([`modules/fastfetch`](modules/fastfetch/README.md)) |
| Firefox + VS Code | Installed through Omarchy's own installers (`omarchy install browser firefox`, `omarchy install editor vscode`), set as the default browser and editor once ([`modules/firefox`](modules/firefox/README.md), [`modules/vscode`](modules/vscode/README.md)) |
| Theme reach | Every `omarchy theme set` also lands in Firefox, which Omarchy's own fan-out misses — a user template Omarchy's own engine renders ([`modules/firefox-theme`](modules/firefox-theme/README.md)) |
| Firefox settings | One system policy — Omarchy's own prefs plus hyprconf's — carries the lot: telemetry off, tracking protection on, **uBlock Origin and Proton Pass** force-installed, the toolbar seeded button-for-button, **DuckDuckGo** the default engine, compact density, vertical tabs, a bare Firefox Home, DRM playback on. Policy *defaults*, not user prefs — any profile comes up configured and it all stays yours to change ([`modules/firefox`](modules/firefox/README.md)) |
| YubiKey | `hyprconf-yubikey`: unlock the LUKS root at boot with a FIDO2 key — the half Omarchy's own `omarchy-setup-security-fido2` (sudo/polkit) leaves out ([`modules/yubikey`](modules/yubikey/README.md)) |
| Dual-GPU gaming | `hyprconf-vulkan-gpu`: on a box with two GPUs, pins Vulkan (Steam/Proton under Xwayland) to the GPU that drives the displays — `fix` writes it into uwsm's `env.d`, `use` pins either card, `run` lends one to a single command ([`modules/vulkan-gpu`](modules/vulkan-gpu/README.md)) |
| Keychron / Lemokey | One udev rule so [launcher.keychron.com](https://launcher.keychron.com) can reach your boards and mice over WebHID — a `hidraw` node is `0600 root:root` until something says otherwise ([`modules/keychron`](modules/keychron/README.md)) |

---

## Requirements

- A running [Omarchy](https://omarchy.org) install. Verified against Omarchy 4.0.3-1 (Lua config — hyprlang `.conf` is gone); the full pin, Hyprland version included, is in [`AGENTS.md`](AGENTS.md). `install.sh` refuses to run when `/usr/share/omarchy` or `omarchy-pkg-add` is missing.
- `git`, and a terminal for anything that needs `sudo`: every module that installs packages or writes outside `$HOME` (Modules, below). `install.sh` itself asks for none.

## Install

```bash
bash <(curl -fsSL --proto '=https' https://hyprconf.sh)
```

Run it as your regular user — `install.sh` asks for no sudo at all, the modules that need it ask for themselves, and it refuses to run as root (a sudo-prefixed bootstrap would half-install the overlay into `/root`).

`hyprconf.sh` serves `install.sh` itself to curl. Run with no payload beside it, it refuses a box without Omarchy before touching anything, clones the `stable` branch into `~/.hyprconf` — or uses the checkout already there, without pulling it — and hands over to that checkout's `install.sh` with the same options. `HYPRCONF_REPO` (`https://github.com/ak4dev/.hyprconf`), `HYPRCONF_BRANCH` (`stable`) and `HYPRCONF_DIR` (`~/.hyprconf`) override those three. The same by hand:

```bash
git clone -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf
bash ~/.hyprconf/install.sh
```

`stable` is the branch users get; `dev` is the working branch until `scripts/publish` promotes it.

| Flag | Effect |
|---|---|
| *(none)* | Apply every module once. Idempotent — re-running is how you pick up changes. |
| `<module>…` | Apply only the modules named — the re-apply after an edit to that module's files, e.g. `hyprconf hypr`. A name that is not a directory under `modules/` is refused before anything runs. |
| `--sync` | `git pull --ff-only` the checkout, re-apply, then run `omarchy-update` — whose post-update hook re-applies the overlay once more, after Omarchy's migrations. This is what the `hyprsync` alias runs. It applies whatever `stable` now carries with no review step — the two root writes (the Keychron udev rule, the Firefox policy) included, which is the trade-off of a clone-only, https-pinned overlay (AGENTS.md rule 8). |
| `--no-update` | Apply only; never invoke `omarchy-update`. Used by the post-update hook, which already runs inside an update. |
| `--no-packages` | Skip everything that needs `sudo`: every module's packages and its own root work. `install.sh` itself asks for none. Exported to the modules as `HYPRCONF_NO_SUDO`, which each one honours itself — they say so in one line and carry on. The hook passes this too. |
| `-h`, `--help` | Usage: both forms and the three variables. On the curl path it answers from the served copy — nothing is cloned. |

### What each stage does

| Stage | Changes | Mechanism |
|---|---|---|
| link | `~/.local/bin/hyprconf` → `install.sh` | A symlink, re-pointed only when it is wrong: what `hyprsync` (`hyprconf --sync`) and `hyprconf <module>` run. Every `hyprconf-*` tool is a module's, linked into the same directory by that module ([`hypr`](modules/hypr/README.md), [`vulkan-gpu`](modules/vulkan-gpu/README.md), [`yubikey`](modules/yubikey/README.md)) |
| hooks | `~/.config/omarchy/hooks/post-update.d/10-hyprconf` | `omarchy hook install <type> <file>` (Omarchy's own: mkdir, copy under the file's basename, `chmod 755`) on a copy rendered with `@HYPRCONF_DIR@` substituted. It re-runs `install.sh --no-update --no-packages` after every `omarchy-update`. The theme-set hook is [`modules/firefox-theme`](modules/firefox-theme/README.md)'s, which installs its own |
| *(end)* | with `--sync`, `omarchy-update` | Nothing else: [`modules/hypr`](modules/hypr/README.md) reloads Hyprland itself when a copy changed, and each `bar-*` module rescans the shell as it syncs its own folder |

### Modules

Each row is a self-contained directory under `modules/` — its own `install`, `README.md`, tests and payload. `install.sh` runs every one of them; from a checkout, `hyprconf <name>` re-runs just one. To install one on its own, take `<name>` from the first column:

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/<name> && bash ~/.hyprconf/modules/<name>/install
```

| Module | What | Undo |
|---|---|---|
| [`bar-active-window`](modules/bar-active-window/README.md) | The focused window's title after the workspaces, on **two** caption-size lines, as the `hyprconf.active-window` plugin — Omarchy's own widget is the same thing on one. Symlinked and enabled **once**, with no placement of its own | `bash ~/.hyprconf/modules/bar-active-window/install undo` |
| [`bar-clock`](modules/bar-clock/README.md) | Omarchy's own bar clock, ticking seconds, as the `hyprconf.clock` plugin — the stock widget samples once a minute. The folder is symlinked into `~/.config/omarchy/plugins/`, so a `git pull` is the update; enabled and formatted `hh:mm:ss AP` **once**, and the bar's centre anchor follows the swap and is repaired whenever it names nothing | `bash ~/.hyprconf/modules/bar-clock/install undo` — disable, the stock format and anchor back, link and marker gone |
| [`bar-resources`](modules/bar-resources/README.md) | A CPU/temp/mem/GPU/net readout in the bar's right section as the `hyprconf.resources` plugin, fed by two long-lived JSON streams the plugin ships in its own `bin/` and Omarchy's shell loads **once** for the session. Symlinked and enabled **once** | `bash ~/.hyprconf/modules/bar-resources/install undo` |
| [`bar-workspaces`](modules/bar-workspaces/README.md) | The overlay's own workspaces widget as the `hyprconf.workspaces` plugin — only the workspaces that exist, on two lines, Pac-Man on the focused one; the stock widget hardcodes pills 1-5 and reads no settings. Symlinked and enabled **once** | `bash ~/.hyprconf/modules/bar-workspaces/install undo` |
| [`fastfetch`](modules/fastfetch/README.md) | The shell greeting's layout, copied to `~/.config/hyprconf/fastfetch.jsonc` — a path only the shell reads, so Omarchy's About screen keeps its own | `bash ~/.hyprconf/modules/fastfetch/install undo` |
| [`firefox`](modules/firefox/README.md) | Firefox through Omarchy's own installer when it is absent, one system policy at `/etc/firefox/policies/policies.json` — Omarchy's own `default/firefox/policies.json` merged **under** hyprconf's (extensions, search engine, privacy and UI settings) — and `firefox` as the default browser, **set once**. The policy needs `sudo` and a terminal | `bash ~/.hyprconf/modules/firefox/install undo` — drops the policy and the marker; Firefox stays installed |
| [`firefox-theme`](modules/firefox-theme/README.md) | Every `omarchy theme set` reaches Firefox too — Omarchy's fan-out is Chromium-only. A user template Omarchy's own engine renders, a `theme-set` hook that copies the render into the profile Firefox starts and rewrites three `user_pref` lines. Takes effect at the next Firefox start | `bash ~/.hyprconf/modules/firefox-theme/install undo` — hook, template, render and each profile's `chrome/userChrome.css` and three prefs |
| [`hypr`](modules/hypr/README.md) | The keymap, the look'n'feel and input deltas and the three monitor presets: `bindings.lua`, `input.lua` and `looknfeel.lua` **copied** into `~/.config/hypr/` (`require`d after Omarchy's defaults, deltas only; an `omarchy refresh` lands on the copy and the next run puts it back — edit in the checkout, then `hyprconf hypr`), the `*Monitors*.lua` presets seeded once and never overwritten, and `hyprconf-gaps` / `hyprconf-monitor-preset` linked into `~/.local/bin`. Omarchy's `monitors.lua` is never touched | `bash ~/.hyprconf/modules/hypr/install undo` — `stock` layout, Omarchy's own template back at each of the three paths (no `.bak`), presets and tool links gone |
| [`font`](modules/font/README.md) | The system monospace becomes GeistMono Nerd Font — **set once**. Installs `otf-geist-mono-nerd` (official repos, `omarchy-pkg-add`) when it is missing, which needs `sudo` and a terminal | `bash ~/.hyprconf/modules/font/install undo` — drops the marker and prints the `omarchy font set 'JetBrainsMono Nerd Font'` to run (the setter restarts the shell, so it stays yours) |
| [`idle`](modules/idle/README.md) | The screensaver starts after **15 min** instead of Omarchy's 150 s (`idle.screensaver` in `~/.config/omarchy/shell.json`; the lock timeout is left alone) — **set once** | `bash ~/.hyprconf/modules/idle/install undo` |
| [`keychron`](modules/keychron/README.md) | One udev rule at `/etc/udev/rules.d/70-keychron.rules` so the WebHID launcher can reach Keychron (`0x3434`) and Lemokey (`0x362d`) boards and mice. Needs `sudo` and a terminal | `bash ~/.hyprconf/modules/keychron/install undo` |
| [`shell-zsh`](modules/shell-zsh/README.md) | zsh and Powerlevel10k inside the terminal, with no framework in between: one grep-guarded `source` line in `~/.zshrc`, the module's own `zshrc` as the whole interactive shell, `~/.p10k.zsh` → the module's (a file or a link of your own there is kept as `.p10k.zsh.stock`), one pinned Powerlevel10k clone in `~/.local/share/powerlevel10k` (never pulled), and `shell zsh` in its own kitty include. Installs `zsh`, `zsh-autosuggestions`, `zsh-syntax-highlighting` | `bash ~/.hyprconf/modules/shell-zsh/install undo` — the `~/.zshrc` line, the kitty include, the `~/.p10k.zsh` link (restoring your `.stock`) and the clone it made; a `powerlevel10k` of your own and the packages stay |
| [`terminal-kitty`](modules/terminal-kitty/README.md) | kitty as Omarchy's default terminal — **set once**, so `omarchy default terminal <name>` later is yours to keep — plus `~/.config/kitty/hyprconf.conf` (cursor trail, 0.85 opacity) and one `include` line at the end of `kitty.conf`, which is seeded from Omarchy's own stub when you have none (from 4.0.3 the user file is optional; the real defaults live in `/etc/xdg/kitty/kitty.conf`). Installs `kitty`, which needs `sudo` and a terminal | `bash ~/.hyprconf/modules/terminal-kitty/install undo` — the include, `hyprconf.conf` and the marker go, and the default hands back to Omarchy's stock `foot` while kitty is still current |
| [`themes`](modules/themes/README.md) | The `dracula` user theme, symlinked into Omarchy's theme menu and **never activated**, plus extra wallpapers filed under the Omarchy theme each belongs to | `bash ~/.hyprconf/modules/themes/install undo` |
| [`vscode`](modules/vscode/README.md) | VS Code through Omarchy's own installer when it is absent, and `code` as the default editor — **set once**, and only once the package is really there. Installing needs `sudo` and a terminal | `bash ~/.hyprconf/modules/vscode/install undo` — the editor goes back to `nvim`; VS Code stays installed |
| [`vulkan-gpu`](modules/vulkan-gpu/README.md) | `hyprconf-vulkan-gpu` on PATH (one symlink) — the dual-GPU Vulkan pin for Steam/Proton under Xwayland. Installing decides nothing: run `hyprconf-vulkan-gpu status`, then `fix`, on a box with two GPUs | `hyprconf-vulkan-gpu remove` first if you wrote a pin (it is yours, not the module's), then `bash ~/.hyprconf/modules/vulkan-gpu/install undo` |
| [`yubikey`](modules/yubikey/README.md) | `hyprconf-yubikey` on PATH (one symlink) — FIDO2 unlock of the LUKS2 root at boot, the half `omarchy-setup-security-fido2` leaves out. Installing changes nothing: the tool is run by hand, and `enroll` is what writes the two `/etc` drop-ins and adds `libfido2` | `hyprconf-yubikey remove` **first**, while the tool is still on PATH, then `bash ~/.hyprconf/modules/yubikey/install undo` |

### What it deliberately leaves alone

- The **login shell** — no `chsh`; why, and what zsh does get, is in [`modules/shell-zsh`](modules/shell-zsh/README.md).
- The body of `~/.config/kitty/kitty.conf`, `~/.bashrc`, `/usr/share/omarchy`, and everything under `/etc` except the Firefox policy and the Keychron udev rule (and, only when you run it, `hyprconf-yubikey enroll`'s two drop-ins).
- Installed packages — nothing is removed, ever (`omarchy-pkg-drop` is never called).
- The **active theme**, Omarchy's **`monitors.lua`** (a preset loads beside it from the toggles directory and never replaces it), and every set-once choice (font, default apps, idle, clock, widget enables) after the first run — change them with Omarchy's own commands and hyprconf will not take them back.
- Omarchy's keyboard layout logic in `input.lua`, and its volume / brightness / media keys, `SUPER+K` (keybindings menu), `SUPER+3`/`4`, `SUPER+SHIFT+3`.

## Sync

```bash
hyprsync            # `hyprconf --sync` — the ~/.local/bin/hyprconf link, so a relocated checkout works after one re-apply
bash install.sh     # after any `omarchy refresh` or when you just want to re-apply
```

- **After `omarchy-update`** the post-update hook re-applies the overlay automatically (a migration replaces `bindings.lua` when it hash-matches stock; `omarchy refresh config kitty/kitty.conf` drops the `include` line) — under `hyprsync` too, where that second apply is the one that outlives the migrations, which run between `--sync`'s own apply and the hook.
- **`omarchy refresh config hypr/<file>` / `omarchy refresh hyprland`** land on the copies in `~/.config/hypr/` — the checkout is never touched — and the next run puts hyprconf's back: `hyprconf hypr`, or the post-update hook.
- **Edit workflow:** the Hyprland files are copies of `~/.hyprconf/modules/hypr/*.lua` — edit them in the checkout, then `hyprconf hypr`; `bash install.sh` (or `hyprsync`) re-applies everything after a pull.

## Repository layout

The tree is in [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md). What reaches your machine: `install.sh` itself puts only the `hooks/` post-update hook and the `~/.local/bin/hyprconf` link in `$HOME`; `modules/` is one directory per module, each shipping its own payload — what it writes and how to undo it is in that module's own `README.md`, the system Firefox policy ([`modules/firefox`](modules/firefox/README.md)) included.

## Bar widgets

| Plugin id | What | Revert |
|---|---|---|
| `hyprconf.clock` | Omarchy's own clock widget sampling seconds instead of minutes, format `hh:mm:ss AP` — [`modules/bar-clock`](modules/bar-clock/README.md) | `omarchy plugin disable hyprconf.clock`, then the format and the centre anchor — [Reverting to stock](#reverting-to-stock) |
| `hyprconf.workspaces` | The overlay's own workspaces widget: only workspaces that exist (no fixed 1–5 pills, no id cap), stacked on two lines like the resources widget, hyprconf's Pac-Man (`󰮯`) on the focused workspace; click focuses — [`modules/bar-workspaces`](modules/bar-workspaces/README.md) | `omarchy plugin disable hyprconf.workspaces` |
| `hyprconf.resources` | Two aligned lines: top **CPU temp / util · RAM · ↑ upload**, bottom **GPU temp / util · VRAM · ↓ download**, fixed-width columns so nothing shifts as the numbers change. NVIDIA, AMD and Intel, the active card on a multi-GPU box; click opens `btop` — [`modules/bar-resources`](modules/bar-resources/README.md) and its [plugin README](modules/bar-resources/plugin/README.md) | `omarchy plugin disable hyprconf.resources` |
| `hyprconf.active-window` | The focused window's title after the workspaces — the overlay's own two-line version of Omarchy's `omarchy.active-window` (a `clonedFrom` copy, so it takes the stock slot) that lays the same character budget (`maxWidth`, 280 px of body text by default) out on **two caption-size lines**, so it takes about half the width; hover for the full title, click focuses, middle- or right-click closes; budget via `omarchy bar set hyprconf.active-window maxWidth 400` — [`modules/bar-active-window`](modules/bar-active-window/README.md) | `omarchy plugin disable hyprconf.active-window` |

Every widget is *enabled* once, and the clock's format and anchor are set once — disabling any of them sticks. Each of the four modules **symlinks** its plugin folder into `~/.config/omarchy/plugins/` and asks the shell to rescan on every run, so a `git pull` in the checkout is the update: the third-party scan follows a link but the shell's own file watch does not descend one, and the rescan is what carries a change into the running bar. `omarchy bar set hyprconf.clock format 'HH:mm'` reformats the clock.

Each `modules/bar-*/plugin` folder is also a plugin on its own — `manifest.json` at its root, a `README.md` with its install line, dependencies and settings, and where the code is Omarchy's a `NOTICE` with its MIT notice — installable on any Omarchy box on its own: today by Omarchy's by-hand path (copy the folder to `~/.config/omarchy/plugins/hyprconf.<id>`, `omarchy-shell shell rescanPlugins`, `omarchy plugin enable hyprconf.<id>` — `/usr/share/omarchy/shell/README.md` › Installing by hand), and with `omarchy plugin add <url> --enable --yes` once the repositories are split out (CONTRIBUTING › Publishing a plugin) — `--yes` there because `omarchy-plugin-add`'s bar-section question would otherwise move a `clonedFrom` widget out of the stock slot it just took. A folder `omarchy plugin add` cloned (it has a `.git`) is Omarchy's — `omarchy plugin update` fast-forwards it and the module leaves it alone with a note. To take a widget off the bar use `omarchy plugin disable <id>` (a `clonedFrom` copy hands its slot back to the stock widget); `omarchy plugin remove <id>` unlinks the module's folder rather than deleting it, and the next run links it back — disabled, since the enable was set once.

## Packages

Every package belongs to the module that wants it — one `packages` file beside that module's `install`, installed with `omarchy-pkg-add` from **official repositories only, never the AUR**, and skipped with one pointer line under `--no-packages` or with no terminal for `sudo`. `install.sh` itself installs nothing.

| Package | Module |
|---|---|
| `kitty` | [`terminal-kitty`](modules/terminal-kitty/README.md) |
| `zsh`, `zsh-autosuggestions`, `zsh-syntax-highlighting` | [`shell-zsh`](modules/shell-zsh/README.md) |
| `otf-geist-mono-nerd` | [`font`](modules/font/README.md) |

Powerlevel10k is not in any of them: it is AUR-only as a package, so `shell-zsh` clones it at a reviewed commit instead (AGENTS.md rule 8). Firefox (`SUPER+F`) and VS Code (`SUPER+C`) are not either: they come through Omarchy's own installers ([`modules/firefox`](modules/firefox/README.md) and [`modules/vscode`](modules/vscode/README.md)), which set up what a bare package would not. `visual-studio-code-bin` is from Omarchy's own `[omarchy]` pacman repository (`pacman -Si`: *Repository: omarchy*; it provides `code` and conflicts with Arch's `code`) — the one package the overlay takes from outside Arch's official repositories, and only through `omarchy-install-editor-vscode`; no AUR helper is ever called.

## Proton VPN

hyprconf installs nothing for it. `omarchy pkg add proton-vpn-gtk-app proton-vpn-cli` — both from Arch's `extra` repository, never the AUR; `proton-vpn-daemon` comes with them. Nothing is enabled and no group is joined: the daemon's `proton.VPN.service` is D-Bus-activated (`me.proton.vpn.split_tunneling.service`), so unlike NordVPN there is no `systemctl enable` and no reboot. Sign in with `protonvpn login` (the CLI) or in the Proton VPN app (`protonvpn-app`). Remove with `omarchy pkg drop proton-vpn-gtk-app proton-vpn-cli` (`pacman -Rns`, so the daemon goes too).

## Reverting to stock

```bash
hyprconf-yubikey remove   # only if you enrolled a key — first, while the tool is still on PATH; both drop-ins go with it
# enrolled by 4.0.0-4.2.0? that version put rd.luks.* INLINE on /etc/default/limine, which this tool only reads: status names them, remove leaves them — delete the two parameters by hand, keep cryptdevice=
bash ~/.hyprconf/modules/bar-clock/install undo   # disable, `omarchy.clock`'s format back to 'dddd HH:mm' and the bar's centre anchor back to it — one command, not three: the disable copies the clone's WHOLE entry back onto omarchy.clock and rewrites only its id, so 'hh:mm:ss AP' would otherwise ride along onto a widget that samples once a minute, and the anchor edit has to wait out the shell's own asynchronous shell.json write first
bash ~/.hyprconf/modules/bar-workspaces/install undo
bash ~/.hyprconf/modules/bar-resources/install undo
bash ~/.hyprconf/modules/bar-active-window/install undo
bash ~/.hyprconf/modules/hypr/install undo   # the `stock` layout, Omarchy's own template back at each of the three override paths, the seeded presets and the two tool links gone
rm -f ~/.config/hypr/{bindings,input,looknfeel}.lua.stock   # only a machine installed before 8.0 has them: the backups the symlink era kept, dead now — as is ~/.local/state/hyprconf/stock/, which the rm -rf below removes
rm ~/.config/omarchy/hooks/post-update.d/10-hyprconf
rm ~/.local/bin/hyprconf ~/.local/bin/hyprconf-*
rm -rf ~/.config/omarchy/plugins/{hyprconf.*,.hyprconf.*.bak.*} ~/.local/state/hyprconf   # the four hyprconf.* entries are symlinks into the checkout; the dot-prefixed .bak.<timestamp> dirs are folders a module moved aside, or what `omarchy plugin remove` leaves of a non-git one
omarchy default terminal <name>; omarchy default editor <name>; omarchy font set <name>; omarchy theme set <name>
# Firefox and VS Code are Omarchy's installs and stay; `omarchy pkg drop visual-studio-code-bin firefox` if you want them gone
```

Each module undoes itself: the Undo column of the Modules table above, or `bash ~/.hyprconf/modules/<name>/install undo`.

Then delete `~/.hyprconf` — and `~/.oh-my-zsh`, if a hyprconf 7.x or earlier put one there (nothing installs or uses it now). Do not `omarchy refresh hyprland` instead of the hypr module's undo: it also overwrites `hyprland.lua`, `autostart.lua` and `monitors.lua` with Omarchy's templates.

## Testing & development

`make test` runs the hermetic unit + integration suites; `make lint` and `make shellcheck` are the other two CI gates. The test tree, the publish flow and the website upload are in [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md); [`AGENTS.md`](AGENTS.md) holds the rules, gates and CI recipe that bind every change.
