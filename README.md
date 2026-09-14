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
| Hotkeys | hyprconf's keymap in `~/.config/hypr/bindings.lua`, with descriptions so it shows in Omarchy's `SUPER+K` menu |
| Look'n'feel + input | Tighter gaps, hairline rounding, blur/shadow, fade workspace animation, natural scroll, 3-finger swipe; Steam tiles like every other window |
| Monitor presets | `bedroom` / `kitchen` / `laptop`, hot-swapped with a hotkey (`hyprconf-monitor-preset`) through Omarchy's Hyprland toggles directory — Omarchy's `monitors.lua` is never touched |
| Bar widgets | A clock that ticks seconds, active-only workspaces on two lines with a Pac-Man on the focused one, the focused window's title, a CPU/temp/mem/GPU/net readout — all as Omarchy shell plugins |
| Terminal + shell | kitty as the default terminal, running zsh + Oh My Zsh + Powerlevel10k *inside* the terminal; the login shell stays bash |
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
- `git`, and a terminal for anything that needs `sudo`: the `packages` stage, and the modules that install packages or write outside `$HOME` (Modules, below).

## Install

```bash
bash <(curl -fsSL --proto '=https' https://hyprconf.sh)
```

Run it as your regular user — it asks for sudo itself where a stage needs it, and refuses to run as root (a sudo-prefixed bootstrap would half-install the overlay into `/root`).

`hyprconf.sh` serves `install.sh` itself to curl. Run with no payload beside it, it refuses a box without Omarchy before touching anything, clones the `stable` branch into `~/.hyprconf` — or uses the checkout already there, without pulling it — and hands over to that checkout's `install.sh` with the same options. `HYPRCONF_REPO` (`https://github.com/ak4dev/.hyprconf`), `HYPRCONF_BRANCH` (`stable`) and `HYPRCONF_DIR` (`~/.hyprconf`) override those three. The same by hand:

```bash
git clone -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf
bash ~/.hyprconf/install.sh
```

`stable` is the branch users get; `dev` is the working branch until `scripts/publish` promotes it.

| Flag | Effect |
|---|---|
| *(none)* | Apply every stage once. Idempotent — re-running is how you pick up changes. |
| `--sync` | `git pull --ff-only` the checkout (after undoing any `omarchy refresh` that landed on it — see Sync), re-apply, then run `omarchy-update` — whose post-update hook re-applies the overlay once more, after Omarchy's migrations. This is what the `hyprsync` alias runs. It applies whatever `stable` now carries with no review step — the two root writes (the Keychron udev rule, the Firefox policy) included, which is the trade-off of a clone-only, https-pinned overlay (AGENTS.md rule 8). |
| `--no-update` | Apply only; never invoke `omarchy-update`. Used by the post-update hook, which already runs inside an update. |
| `--no-packages` | Skip everything that needs `sudo`: the `packages` stage here, and every module's own root work. Exported to the modules as `HYPRCONF_NO_SUDO`, which each one honours itself — they say so in one line and carry on. The hook passes this too. |
| `-h`, `--help` | Usage: both forms and the three variables. On the curl path it answers from the served copy — nothing is cloned. |

### What each stage does

| Stage | Changes | Mechanism |
|---|---|---|
| packages | Installs the `packages` list (official repos only) | `omarchy-pkg-add` — idempotent, never bare `pacman -Syu` (Omarchy's ALPM hook blocks it) |
| terminal | kitty becomes the default terminal; `~/.config/kitty/hyprconf.conf` (cursor trail, 0.85 opacity, `shell <zsh>`) plus one `include hyprconf.conf` line appended to `kitty.conf`, which is created if you do not have one (from 4.0.3 Omarchy's own defaults live in `/etc/xdg/kitty/kitty.conf`, so the user file is optional) | `omarchy-default-terminal kitty`; Omarchy's defaults live in `/etc/xdg/kitty/kitty.conf` (kitty merges it below the user file), and `~/.config/kitty/kitty.conf` — the theme include, plus whatever `omarchy-font-set` appends — stays authoritative above it. The setter's exit status is its closing notification's, so with no shell (a TTY first run) it warns and the re-run finds kitty already current |
| hotkeys | `~/.config/hypr/bindings.lua` → `hypr/bindings.lua` | Symlink (whatever was there first — Omarchy's stock file, or a dotfiles link of your own, copied as a link — backed up to `bindings.lua.stock`). The hotkey tools are `bin/` commands (below) |
| looknfeel | `~/.config/hypr/looknfeel.lua` and `input.lua` → the repo's | Symlinks (`.stock` backups, a link of your own kept as a link) |
| monitors | Seeds the three presets into `~/.config/hypr/` | Seeded, never overwritten — a preset is machine-local; delete one to re-seed. Omarchy's `monitors.lua` is never touched, a symlinked one included (a stow-style dotfiles link is yours) |
| bin | Every `bin/hyprconf-*` tool → `~/.local/bin/`: `hyprconf-monitor-preset` and `hyprconf-gaps`, the two hotkey tools | Copied, with `@HYPRCONF_DIR@` substituted for the checkout path; `bindings.lua` binds the hotkey tools by name, the way Omarchy binds its own commands. The resources widget's two feeders are not here: they ship inside its plugin folder and land with it (below) |
| bar_plugin | `hyprconf.resources` widget in the bar's right section | `plugins/hyprconf-resources/` synced into `~/.config/omarchy/plugins/` on every run; enabled **once**, with no placement argument — the manifest's `barWidget.defaultSection: right` places it (the shell's `defaultBarWidgetSection`). The manifest also declares `service`, so the shell loads its feeders once for the session instead of once per monitor; one id still, so the same enable and the same disable cover both |
| workspaces | `hyprconf.workspaces`: the overlay's own workspaces widget — only workspaces that exist, on two lines, Pac-Man on the focused one | `plugins/hyprconf-workspaces/` synced on every run (a `clonedFrom` copy the shell swaps into the stock widget's slot); enabled **once** |
| window_title | `hyprconf.active-window`: the focused window's title after the workspaces, on **two lines** | `plugins/hyprconf-active-window/` synced on every run (a `clonedFrom` copy the shell swaps into the stock `omarchy.active-window` slot); enabled **once** with no placement of its own: the manifest's `defaultSection: left` and the shell's own anchor after `omarchy.workspaces` — resolved to the `hyprconf.workspaces` copy while it is on the bar — place it |
| shell | Oh My Zsh + Powerlevel10k into `~/.oh-my-zsh`, each pinned to a reviewed commit (no auto-update — bumping a pin is a deliberate release); `~/.p10k.zsh` → `zsh/.p10k.zsh` (a file or a link of your own there is backed up to `.p10k.zsh.stock` first); managed block in `~/.zshrc` | `git` at exact shas, no `chsh` |
| hooks | `~/.config/omarchy/hooks/post-update.d/10-hyprconf` | `omarchy hook install <type> <file>` (Omarchy's own: mkdir, copy under the file's basename, `chmod 755`) on a copy rendered with `@HYPRCONF_DIR@` substituted. It re-runs `install.sh --no-update --no-packages` after every `omarchy-update`. The theme-set hook is [`modules/firefox-theme`](modules/firefox-theme/README.md)'s, which installs its own |
| *(end)* | `hyprctl reload`; with `--sync`, `omarchy-update` | A widget whose files changed is picked up as it is synced: `omarchy-shell shell rescanPlugins` (the hot reload `omarchy plugin update` uses), `omarchy-restart-shell` only when no shell answers — both tolerated failing (no shell on a TTY) |

### Modules

Each row is a self-contained directory under `modules/` — its own `install`, `README.md`, tests and payload. `install.sh` runs every one of them; to install (or re-install) just one, take `<name>` from the first column:

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/<name> && bash ~/.hyprconf/modules/<name>/install
```

| Module | What | Undo |
|---|---|---|
| [`bar-clock`](modules/bar-clock/README.md) | Omarchy's own bar clock, ticking seconds, as the `hyprconf.clock` plugin — the stock widget samples once a minute. The folder is symlinked into `~/.config/omarchy/plugins/`, so a `git pull` is the update; enabled and formatted `hh:mm:ss AP` **once**, and the bar's centre anchor follows the swap and is repaired whenever it names nothing | `bash ~/.hyprconf/modules/bar-clock/install undo` — disable, the stock format and anchor back, link and marker gone |
| [`fastfetch`](modules/fastfetch/README.md) | The shell greeting's layout, copied to `~/.config/hyprconf/fastfetch.jsonc` — a path only the shell reads, so Omarchy's About screen keeps its own | `bash ~/.hyprconf/modules/fastfetch/install undo` |
| [`firefox`](modules/firefox/README.md) | Firefox through Omarchy's own installer when it is absent, one system policy at `/etc/firefox/policies/policies.json` — Omarchy's own `default/firefox/policies.json` merged **under** hyprconf's (extensions, search engine, privacy and UI settings) — and `firefox` as the default browser, **set once**. The policy needs `sudo` and a terminal | `bash ~/.hyprconf/modules/firefox/install undo` — drops the policy and the marker; Firefox stays installed |
| [`firefox-theme`](modules/firefox-theme/README.md) | Every `omarchy theme set` reaches Firefox too — Omarchy's fan-out is Chromium-only. A user template Omarchy's own engine renders, a `theme-set` hook that copies the render into the profile Firefox starts and rewrites three `user_pref` lines. Takes effect at the next Firefox start | `bash ~/.hyprconf/modules/firefox-theme/install undo` — hook, template, render and each profile's `chrome/userChrome.css` and three prefs |
| [`font`](modules/font/README.md) | The system monospace becomes GeistMono Nerd Font — **set once**. Installs `otf-geist-mono-nerd` (official repos, `omarchy-pkg-add`) when it is missing, which needs `sudo` and a terminal | `bash ~/.hyprconf/modules/font/install undo` — drops the marker and prints the `omarchy font set 'JetBrainsMono Nerd Font'` to run (the setter restarts the shell, so it stays yours) |
| [`idle`](modules/idle/README.md) | The screensaver starts after **15 min** instead of Omarchy's 150 s (`idle.screensaver` in `~/.config/omarchy/shell.json`; the lock timeout is left alone) — **set once** | `bash ~/.hyprconf/modules/idle/install undo` |
| [`keychron`](modules/keychron/README.md) | One udev rule at `/etc/udev/rules.d/70-keychron.rules` so the WebHID launcher can reach Keychron (`0x3434`) and Lemokey (`0x362d`) boards and mice. Needs `sudo` and a terminal | `bash ~/.hyprconf/modules/keychron/install undo` |
| [`themes`](modules/themes/README.md) | The `dracula` user theme, symlinked into Omarchy's theme menu and **never activated**, plus extra wallpapers filed under the Omarchy theme each belongs to | `bash ~/.hyprconf/modules/themes/install undo` |
| [`vscode`](modules/vscode/README.md) | VS Code through Omarchy's own installer when it is absent, and `code` as the default editor — **set once**, and only once the package is really there. Installing needs `sudo` and a terminal | `bash ~/.hyprconf/modules/vscode/install undo` — the editor goes back to `nvim`; VS Code stays installed |
| [`vulkan-gpu`](modules/vulkan-gpu/README.md) | `hyprconf-vulkan-gpu` on PATH (one symlink) — the dual-GPU Vulkan pin for Steam/Proton under Xwayland. Installing decides nothing: run `hyprconf-vulkan-gpu status`, then `fix`, on a box with two GPUs | `hyprconf-vulkan-gpu remove` first if you wrote a pin (it is yours, not the module's), then `bash ~/.hyprconf/modules/vulkan-gpu/install undo` |
| [`yubikey`](modules/yubikey/README.md) | `hyprconf-yubikey` on PATH (one symlink) — FIDO2 unlock of the LUKS2 root at boot, the half `omarchy-setup-security-fido2` leaves out. Installing changes nothing: the tool is run by hand, and `enroll` is what writes the two `/etc` drop-ins and adds `libfido2` | `hyprconf-yubikey remove` **first**, while the tool is still on PATH, then `bash ~/.hyprconf/modules/yubikey/install undo` |

### What it deliberately leaves alone

- The **login shell** — no `chsh`. zsh runs inside kitty only; `~/.zshrc` sources Omarchy's own `envs`/`aliases`, so its updates flow through.
- The body of `~/.config/kitty/kitty.conf`, `~/.bashrc`, `/usr/share/omarchy`, and everything under `/etc` except the Firefox policy and the Keychron udev rule (and, only when you run it, `hyprconf-yubikey enroll`'s two drop-ins).
- Installed packages — nothing is removed, ever (`omarchy-pkg-drop` is never called).
- The **active theme**, Omarchy's **`monitors.lua`** (a preset loads beside it from the toggles directory and never replaces it), and every set-once choice (font, default apps, idle, clock, widget enables) after the first run — change them with Omarchy's own commands and hyprconf will not take them back.
- Omarchy's keyboard layout logic in `input.lua`, and its volume / brightness / media keys, `SUPER+K` (keybindings menu), `SUPER+3`/`4`, `SUPER+SHIFT+3`.

## Sync

```bash
hyprsync            # the checkout's install.sh --sync (the path is rendered into the ~/.zshrc block, so a relocated checkout works after one re-apply)
bash install.sh     # after any `omarchy refresh` or when you just want to re-apply
```

- **After `omarchy-update`** the post-update hook re-applies the overlay automatically (a migration replaces `bindings.lua` when it hash-matches stock; `omarchy refresh config kitty/kitty.conf` drops the `include` line) — under `hyprsync` too, where that second apply is the one that outlives the migrations, which run between `--sync`'s own apply and the hook.
- **`omarchy refresh config hypr/<file>` / `omarchy refresh hyprland` write *through* the symlinks** into the checkout. `install.sh` detects a `hypr/*.lua` that is byte-identical to Omarchy's stock template (the installed one, or the last one the installer saw — cached under `~/.local/state/hyprconf/stock/`, so an Omarchy release that changes the template cannot turn an unrepaired refresh into a permanent one; the cache is best-effort — one it cannot write is a warning, not a failed run, and the guard falls back to the installed template) and restores it with `git checkout` — `--sync` does this before its pull, so a refreshed file never blocks the fast-forward. `monitors.lua` is Omarchy's own real file, so a refresh of it lands where it should.
- **Edit workflow:** the files in `~/.hyprconf/hypr/` *are* the live files — edit them there, then `bash install.sh` (or `hyprsync`) after a pull or a refresh.

## Repository layout

The tree is in [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md). What reaches your machine: `hypr/`, `bin/`, `plugins/`, `zsh/`, `kitty/` and `hooks/` land in `$HOME` (the `hypr/*.lua` overrides and `.p10k.zsh` as symlinks into the checkout). `modules/` is one directory per module, each shipping its own payload — what it writes and how to undo it is in that module's own `README.md`, the system Firefox policy ([`modules/firefox`](modules/firefox/README.md)) included.

## Monitor presets

| Preset | File | Hotkey |
|---|---|---|
| `bedroom` | `~/.config/hypr/pcMonitors.bedroom.lua` | `SUPER+SHIFT+B` |
| `kitchen` | `~/.config/hypr/pcMonitors.kitchen.lua` | `SUPER+SHIFT+K` |
| `laptop` | `~/.config/hypr/laptopMonitors.lua` | — |
| `stock` | — (`omarchy-hyprland-toggle hyprconf-monitor-preset off` removes the toggle file; Omarchy's `monitors.lua` alone speaks) | — |

```bash
hyprconf-monitor-preset <preset>
```

`hyprconf-monitor-preset` copies the preset (never links it) to `~/.local/state/omarchy/toggles/hypr/hyprconf-monitor-preset.lua` — Omarchy's Hyprland toggles directory, which its `default/hypr/toggles.lua` loads (`require_all`, reloaded on every `hyprctl reload`) *after* `~/.config/hypr/monitors.lua` in `hyprland.lua`, so a later `hl.monitor` for the same output wins; it is the seam Omarchy's own `omarchy-hyprland-monitor-internal` toggle writes to. Then `hyprctl reload`, then it walks the preset's `hl.workspace_rule` lines and moves each existing workspace to its monitor (a reload only places *future* workspaces). Dark outputs get a `dpms` wake retry. Feedback goes through `omarchy-osd` and `omarchy-notification-send`. `stock` is that toggle's own `off`, so it runs `omarchy-hyprland-toggle hyprconf-monitor-preset off` rather than a copy of it (the `on` half cannot be reused: it reads only `$OMARCHY_PATH/default/hypr/toggles/`). Omarchy's `monitors.lua` is never touched, so `omarchy-hyprland-monitor-scaling` and `omarchy refresh` keep working on their own file. Each preset carries its workspace-to-monitor rules, and edits to a preset survive re-selecting it.

The two desk presets name their displays by **description** (`output = "desc:<make> <model>"`), not by connector. `DP-N`/`HDMI-A-N` numbering follows the GPU the session drives the displays through — probe order, `AQ_DRM_DEVICES`, cabling — so moving a cable between two GPUs renumbers every connector and a connector-keyed preset lights nothing. A description follows the panel. `desc:` prefix-matches Hyprland's `"<make> <model> <serial>"` string, so make + model is enough and the serial stays out of a tracked file. Both presets end with an `output = ""` catch-all so an unrecognised display comes up at its preferred mode rather than staying dark; named rules win over it whatever the order, disables included. `laptop` stays connector-keyed — it describes no particular hardware.

## Bar widgets

| Plugin id | What | Revert |
|---|---|---|
| `hyprconf.clock` | Omarchy's own clock widget sampling seconds instead of minutes, format `hh:mm:ss AP` — [`modules/bar-clock`](modules/bar-clock/README.md) | `omarchy plugin disable hyprconf.clock`, then the format and the centre anchor — [Reverting to stock](#reverting-to-stock) |
| `hyprconf.workspaces` | The overlay's own workspaces widget: only workspaces that exist (no fixed 1–5 pills, no id cap), stacked on two lines like the resources widget, hyprconf's Pac-Man (`󰮯`) on the focused workspace; click focuses | `omarchy plugin disable hyprconf.workspaces` |
| `hyprconf.resources` | Two aligned lines fed by the two feeders bundled in the plugin's own `bin/` — `hyprconf-stats` and `hyprconf-gpu-info`, long-lived JSON streams run by absolute path from the plugin folder, nothing on `PATH`. They belong to the plugin's `service` entry point, which Omarchy's shell loads **once** however many monitors the bar is drawn on (the widget itself is per monitor). A stream that dies after producing output is restarted on a capped backoff — 1 s, 2 s, 4 s, 8 s, 16 s, 32 s, then parked until the shell restarts, refilled by the next line that arrives — and one that exits without ever producing output is left alone (no such hardware): top **CPU temp / util · RAM · ↑ upload**, bottom **GPU temp / util · VRAM · ↓ download**. The network rates are the first wired link that is up, else the default-route interface from `/proc/net/route` (Wi-Fi, a tunnel — no `ip` call). Columns are fixed-width (sized from their widest value) with a hairline gap between them, so nothing shifts as the numbers change. On a multi-GPU box the **active** card is shown — the one with the most VRAM in use (ties: utilization, then index), re-evaluated every sample. NVIDIA (`nvidia-smi --loop` — on a hybrid laptop that stream holds the discrete GPU open for the session, out of runtime D3; disable the widget on battery if that matters), AMD (`gpu_busy_percent`) and Intel (the `xe` driver's GT idle residency — Panther Lake and every other Xe2/Xe3 part) in that order; an Intel iGPU has no VRAM of its own, so it reads `shared` and ranks on utilization, and its tooltip carries the GT clock where NVIDIA's carries power draw. An Intel card in runtime suspend is left asleep — residency, hwmon and clock all resume an `xe` device on read, so a tick that finds `power/runtime_status` saying `suspended` or `suspending` reads nothing off that card and ranks it idle; every other value, a missing file included, is measured. Click opens `btop` via `omarchy-launch-or-focus-tui` | `omarchy plugin disable hyprconf.resources` |
| `hyprconf.active-window` | The focused window's title after the workspaces — the overlay's own two-line version of Omarchy's `omarchy.active-window` (a `clonedFrom` copy, so it takes the stock slot) that lays the same character budget (`maxWidth`, 280 px of body text by default) out on **two caption-size lines**, so it takes about half the width; hover for the full title, click focuses, middle- or right-click closes; budget via `omarchy bar set hyprconf.active-window maxWidth 400` | `omarchy plugin disable hyprconf.active-window` |

Every widget is *enabled* once, and the clock's format and anchor are set once — disabling any of them sticks. `modules/bar-clock` **symlinks** its folder into `~/.config/omarchy/plugins/` and asks the shell to rescan on every run, so a `git pull` is the update (the shell's own watch does not follow a link). The three still shipped from `plugins/` (`plugins/hyprconf-resources`, `plugins/hyprconf-workspaces`, `plugins/hyprconf-active-window`) are re-synced on every run, so a `git pull` updates them — the comparison is bytes **and** file modes, so a feeder that lost its exec bit (a restore of `~/.config` without permissions) is put back too — staged in a sibling temp dir and moved into place, the way `omarchy plugin clone` lands a copy, then `omarchy-shell shell rescanPlugins` hot-reloads them. `omarchy bar set hyprconf.clock format 'HH:mm'` reformats the clock.

Each folder is also a plugin on its own — `manifest.json` at its root, a `README.md` with its install line, dependencies and settings, and where the code is Omarchy's a `NOTICE` with its MIT notice — installable on any Omarchy box on its own: today by Omarchy's by-hand path (copy the folder to `~/.config/omarchy/plugins/hyprconf.<id>`, `omarchy-shell shell rescanPlugins`, `omarchy plugin enable hyprconf.<id>` — `/usr/share/omarchy/shell/README.md` › Installing by hand), and with `omarchy plugin add <url> --enable --yes` once the repositories are split out of `plugins/` (CONTRIBUTING › Publishing a plugin) — `--yes` there because `omarchy-plugin-add`'s bar-section question would otherwise move a `clonedFrom` widget out of the stock slot it just took. Two install channels, one rule: a folder `omarchy plugin add` cloned (it has a `.git`) is Omarchy's — `omarchy plugin update` fast-forwards it and `install.sh` leaves it alone with a note — while the overlay's own copy is the one `install.sh` syncs. To take a widget off the bar use `omarchy plugin disable <id>` (a `clonedFrom` copy hands its slot back to the stock widget). `omarchy plugin remove <id>` deletes a git checkout but moves a synced folder to `~/.config/omarchy/plugins/.<id>.bak.<timestamp>`, and the next run (the post-update hook's, after every `omarchy-update`) syncs the folder back — disabled, since the enable was set once.

## Keybindings

`mainMod` is `SUPER`. Everything below is bound with `o.bind` (Omarchy's helper, which records the description for `SUPER+K`); keys hyprconf takes over from Omarchy are unbound first, including Omarchy's keycode-form binds (`code:10…21`), so only one binding fires. Omarchy's launchers are named the way Omarchy's own bindings name them (`{ omarchy = "terminal" }` → `omarchy-launch-terminal`), and hyprconf's own tools by command name from `~/.local/bin`, the way Omarchy binds its commands. The keymap is `hypr/bindings.lua` — edit it there, one bind per line.

### Applications

| Key | Action |
|---|---|
| `SUPER+T` | Terminal (`omarchy-launch-terminal` — follows `omarchy default terminal`) |
| `SUPER+F` | Browser (`omarchy-launch-browser`) |
| `SUPER+C` | Editor (`omarchy-launch-editor`) |
| `SUPER+E` | File manager (`omarchy-launch-nautilus`) |
| `SUPER+D` | Omarchy menu (`omarchy-menu toggle`) — Omarchy's own menu key is `SUPER+SPACE`, which stays |

### Windows

| Key | Action |
|---|---|
| `SUPER+Q` | Close window |
| `SUPER+SHIFT+Q` | Log out (`omarchy-system-logout`) |
| `SUPER+V` / `SUPER+SHIFT+SPACE` | Toggle window floating |
| `SUPER+SHIFT+F` | Full screen |
| `SUPER+SHIFT+← → ↑ ↓` | Shrink/expand window (repeating) |
| `SUPER+SHIFT+A / D / W / S` | Move window left / right / up / down — and onto the neighbouring monitor when there is no window that way |
| `SUPER+SHIFT+=` / `SUPER+SHIFT+-` | Increase / decrease window gaps (`hyprconf-gaps`, runtime only — a reload restores the configured values) |

### Workspaces

| Key | Action |
|---|---|
| `SUPER+1, 2, 5–0` | Switch to workspace 1, 2, 5–10 |
| `SUPER+F1` / `SUPER+F2` | Switch to workspace 3 / 4 |
| `SUPER+SHIFT+1, 2, 5–0` | Move window to workspace 1, 2, 5–10 |
| `SUPER+SHIFT+F1` / `SUPER+SHIFT+F2` | Move window to workspace 3 / 4 |
| `SUPER+3` / `SUPER+4` / `SUPER+SHIFT+3` | Left to Omarchy (workspace 3 / 4; move window to 3) |
| `SUPER+M` / `SUPER+SHIFT+M` | Toggle magic scratchpad / move window to it |

### System

| Key | Action |
|---|---|
| `SUPER+L` / `SUPER+SHIFT+Escape` | Lock system (`omarchy-system-lock`) |
| `SUPER+SHIFT+4` | Screenshot region (`omarchy-capture-screenshot region`) |
| `SUPER+SHIFT+V` | Clipboard history (`omarchy-menu-clipboard`) |
| `SUPER+SHIFT+BACKSPACE` | Toggle laptop display (`omarchy-hyprland-monitor-internal toggle`) |
| `SUPER+SHIFT+B` / `SUPER+SHIFT+K` | Monitor preset bedroom / kitchen |

**Left to Omarchy on purpose:** volume, brightness and media keys (Omarchy's drive its OSD and media service), `SUPER+K`, `SUPER+SPACE`, `SUPER+3`/`4`, `SUPER+SHIFT+3` — and its own `SUPER+P` (pseudo), `SUPER+← → ↑ ↓` (focus), `SUPER+scroll` (workspace scroll) and `SUPER+LMB`/`RMB` drag (move/resize), which hyprconf does not restate (`default/hypr/bindings/tiling.lua`). **Displaced Omarchy defaults** (`/usr/share/omarchy/default/hypr/bindings/*.lua`; each still reachable by command or by another Omarchy key):

| Key | Omarchy's binding | Still available as |
|---|---|---|
| `SUPER+T` | Toggle window floating | hyprconf's `SUPER+V` |
| `SUPER+F` | Full screen | hyprconf's `SUPER+SHIFT+F` |
| `SUPER+C` / `SUPER+V` | Universal copy / paste | `CTRL+C` / `CTRL+V` in the app |
| `SUPER+SHIFT+F` | File manager (`omarchy-launch-nautilus`) | hyprconf's `SUPER+E`; Omarchy's `SUPER+ALT+SHIFT+F` (cwd) |
| `SUPER+SHIFT+B` | Browser (`omarchy-launch-browser`) | hyprconf's `SUPER+F`; Omarchy's `SUPER+SHIFT+RETURN` |
| `SUPER+SHIFT+← → ↑ ↓` | Swap window | Nothing binds swap any more — hyprconf's `SUPER+SHIFT+A / D / W / S` *moves* the window in the layout instead, which in a two-window split reads the same and, unlike swap, also crosses to the next monitor |
| `SUPER+SHIFT+-` / `SUPER+SHIFT+=` | Shrink window up / expand window down (keycode binds `code:20`/`code:21`) | Omarchy's `SUPER+SHIFT+ALT+-`/`=` (a little) and `SUPER+CTRL+SHIFT+-`/`=` (a lot) |
| `SUPER+SHIFT+4` | Move window to workspace 4 (`SUPER+SHIFT+code:13`) | hyprconf's `SUPER+SHIFT+F2` |
| `SUPER+SHIFT+SPACE` | Toggle top bar | `omarchy toggle bar` |
| `SUPER+L` | Toggle workspace layout | `omarchy-hyprland-workspace-layout-toggle`; lock stays on Omarchy's `SUPER+CTRL+L` too |
| `SUPER+SHIFT+BACKSPACE` | Toggle window gaps | `omarchy-hyprland-window-gaps-toggle` |
| `SUPER+SHIFT+A` / `D` / `W` / `S` / `M` | ChatGPT / Docker / Omawrite / Google Maps / Music — only while Omarchy's preinstalled-app bindings are on (`o.preinstalled_bindings_enabled()`: until `~/.local/state/omarchy/preinstalls-removed` exists) | `omarchy-launch-webapp`, `omarchy-launch-docker-tui` (lazydocker behind Omarchy's polkit gate — the socket is root-owned), `omawrite`, `omarchy-launch-spotify` |

## Look'n'feel and input deltas

Only what differs from `/usr/share/omarchy/default/hypr/`:

| File | Setting | hyprconf | Omarchy |
|---|---|---|---|
| `looknfeel.lua` | `general.gaps_in` / `gaps_out` | 3 / 3 | 5 / 10 |
| | `decoration.rounding` / `rounding_power` | 1 / 3 | 0 / – |
| | `decoration.inactive_opacity` | 0.8 | 1 |
| | `decoration.shadow` | on | off |
| | `decoration.blur` | on (size 3, passes 4) | off |
| | animations | `windows` easeOutQuint 4.79; `workspaces`/`In`/`Out` fade | workspaces animation off |
| | `dwindle.force_split` / `precise_mouse_move` / `smart_split` | 0 / true / true | 2 / – / – |
| | window rules: class `steam` | **tiled** (`o.window("steam", { tile = true })`; the Friends List stays floating) | every Steam window floats (`default/hypr/apps/steam.lua`) |
| `input.lua` | `input.natural_scroll` + `touchpad.natural_scroll` | true | false |
| | `hl.gesture` 3-finger horizontal → workspace | on | – |
| | `gestures.workspace_swipe_min_speed_to_force` / `workspace_swipe_forever` | 15 / true | – (Hyprland: 30 / false) |

`inactive_opacity` is not what you see: Omarchy tags every window `+default-opacity` and applies `opacity = "0.985 0.96"` to the tag (`default/hypr/windows.lua:6, 25`), and a window rule's `opacity` multiplies the global setting unless `override` is given — so an ordinary inactive window lands near 0.77, and only the apps Omarchy opts out of the tag (`opacity = "1 1"`: steam, qemu) show the full 0.8.

Border and shadow colours stay with the active Omarchy theme; keyboard layout stays with Omarchy's `input.lua` logic.

## Packages

From `packages`, installed via `omarchy-pkg-add` — **official repositories only, never the AUR**. A module with packages of its own ships them in its own `packages` file and installs them the same way (`otf-geist-mono-nerd`, [`modules/font`](modules/font/README.md)):

| Package | Why |
|---|---|
| `kitty` | Default terminal |
| `zsh`, `zsh-autosuggestions`, `zsh-syntax-highlighting` | Shell inside kitty |

Firefox (`SUPER+F`) and VS Code (`SUPER+C`) are not in `packages`: they come through Omarchy's own installers ([`modules/firefox`](modules/firefox/README.md) and [`modules/vscode`](modules/vscode/README.md)), which set up what a bare package would not. `visual-studio-code-bin` is from Omarchy's own `[omarchy]` pacman repository (`pacman -Si`: *Repository: omarchy*; it provides `code` and conflicts with Arch's `code`) — the one package the overlay takes from outside Arch's official repositories, and only through `omarchy-install-editor-vscode`; no AUR helper is ever called.

## zsh

The `~/.zshrc` managed block (`# >>> hyprconf >>>` … `# <<< hyprconf <<<`, source `zsh/zshrc.block`) sources Omarchy's `default/bash/{env-bootstrap,envs,aliases}`, initialises `zoxide` (Omarchy aliases `cd` to it), loads Oh My Zsh with the `powerlevel10k` theme and `~/.p10k.zsh`, `zsh-autosuggestions`, the `hyprsync` alias, a `fastfetch` greeting (the `fastfetch` module's layout when it is installed, fastfetch's own default otherwise), and `zsh-syntax-highlighting` last. Everything outside the markers is preserved in place: a re-run replaces the block where it stands, so a line you add after the end marker stays after it. Both marker lines have to be there, in that order — with only one of the pair, or the two swapped, the installer leaves `~/.zshrc` untouched and says so, rather than rewriting a file it cannot bound; put the missing line back (or delete the odd one) and re-run.

## Proton VPN

hyprconf installs nothing for it. `omarchy pkg add proton-vpn-gtk-app proton-vpn-cli` — both from Arch's `extra` repository, never the AUR; `proton-vpn-daemon` comes with them. Nothing is enabled and no group is joined: the daemon's `proton.VPN.service` is D-Bus-activated (`me.proton.vpn.split_tunneling.service`), so unlike NordVPN there is no `systemctl enable` and no reboot. Sign in with `protonvpn login` (the CLI) or in the Proton VPN app (`protonvpn-app`). Remove with `omarchy pkg drop proton-vpn-gtk-app proton-vpn-cli` (`pacman -Rns`, so the daemon goes too).

## Reverting to stock

```bash
hyprconf-yubikey remove   # only if you enrolled a key — first, while the tool is still on PATH; both drop-ins go with it
# enrolled by 4.0.0-4.2.0? that version put rd.luks.* INLINE on /etc/default/limine, which this tool only reads: status names them, remove leaves them — delete the two parameters by hand, keep cryptdevice=
bash ~/.hyprconf/modules/bar-clock/install undo   # disable, `omarchy.clock`'s format back to 'dddd HH:mm' and the bar's centre anchor back to it — one command, not three: the disable copies the clone's WHOLE entry back onto omarchy.clock and rewrites only its id, so 'hh:mm:ss AP' would otherwise ride along onto a widget that samples once a minute, and the anchor edit has to wait out the shell's own asynchronous shell.json write first
omarchy plugin disable hyprconf.workspaces
omarchy plugin disable hyprconf.resources
omarchy plugin disable hyprconf.active-window
hyprconf-monitor-preset stock   # removes ~/.local/state/omarchy/toggles/hypr/hyprconf-monitor-preset.lua
for f in bindings input looknfeel; do mv ~/.config/hypr/$f.lua.stock ~/.config/hypr/$f.lua; done
rm ~/.config/hypr/{pcMonitors*,laptopMonitors}.lua
rm ~/.config/omarchy/hooks/post-update.d/10-hyprconf
sed -i '/^# hyprconf overlay$/d; /^include hyprconf.conf$/d' ~/.config/kitty/kitty.conf; rm ~/.config/kitty/hyprconf.conf
rm ~/.p10k.zsh ~/.local/bin/hyprconf-*; { [ -e ~/.p10k.zsh.stock ] || [ -L ~/.p10k.zsh.stock ]; } && mv ~/.p10k.zsh.stock ~/.p10k.zsh   # your own .p10k.zsh, file or dotfiles link, if you had one
rm -rf ~/.config/omarchy/plugins/{hyprconf.*,.hyprconf.*.bak.*} ~/.local/state/hyprconf   # the dot-prefixed .bak.<timestamp> dirs are what `omarchy plugin remove` leaves of a non-git plugin folder
omarchy default terminal <name>; omarchy default editor <name>; omarchy font set <name>; omarchy theme set <name>
# Firefox and VS Code are Omarchy's installs and stay; `omarchy pkg drop visual-studio-code-bin firefox` if you want them gone
```

Each module undoes itself: the Undo column of the Modules table above, or `bash ~/.hyprconf/modules/<name>/install undo`.

Then delete the managed block from `~/.zshrc` (`# >>> hyprconf >>>` … `# <<< hyprconf <<<`), `~/.oh-my-zsh` if you no longer want it, and `~/.hyprconf`. Do not `omarchy refresh hyprland` instead of the `mv` line: it also overwrites `hyprland.lua`, `autostart.lua` and `monitors.lua` with Omarchy's templates.

## Testing & development

`make test` runs the hermetic unit + integration suites; `make lint` and `make shellcheck` are the other two CI gates. The test tree, the publish flow and the website upload are in [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md); [`AGENTS.md`](AGENTS.md) holds the rules, gates and CI recipe that bind every change.
