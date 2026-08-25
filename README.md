<p align="center">
  <img src="assets/banner.svg" width="920" alt=".hyprconf" />
</p>

<p align="center">
  <a href="https://hyprconf.sh"><img alt="installer" src="https://img.shields.io/badge/installer-hyprconf.sh-0ea5e9?style=for-the-badge" /></a>
  <img alt="arch linux" src="https://img.shields.io/badge/arch-linux-1793d1?style=for-the-badge&logo=archlinux&logoColor=white" />
  <img alt="hyprland" src="https://img.shields.io/badge/hyprland-wayland-111827?style=for-the-badge&logo=wayland&logoColor=white" />
  <a href="https://omarchy.org"><img alt="omarchy overlay" src="https://img.shields.io/badge/omarchy-overlay-3a7f2e?style=for-the-badge" /></a>
</p>

<p align="center">
  <img src="assets/screenshot.svg" width="920" alt=".hyprconf — screenshot coming soon" />
</p>

<p align="center"><sub>A desktop capture is coming; the placeholder holds its place.</sub></p>

# .hyprconf

**hyprconf** is an overlay for [Omarchy](https://omarchy.org): one idempotent
`install.sh` plus the files it ships. Omarchy owns the base system (packages,
session, shell, theme engine, lock/idle, bar); hyprconf layers one person's
preferences on top, always through Omarchy's own tools and documented seams:

| Layer | What you get |
|---|---|
| Hotkeys | hyprconf's keymap in `~/.config/hypr/bindings.lua`, with descriptions so it shows in Omarchy's `SUPER+K` menu |
| Look'n'feel + input | Tighter gaps, hairline rounding, blur/shadow, fade workspace animation, natural scroll, 3-finger swipe; Steam tiles like every other window |
| Monitor presets | `bedroom` / `kitchen` / `K` / `pc` / `laptop`, hot-swapped with a hotkey (`hyprconf-monitor-preset`) through Omarchy's Hyprland toggles directory — Omarchy's `monitors.lua` is never touched |
| Bar widgets | A clock that ticks seconds, active-only workspaces on two lines with a Pac-Man on the focused one, the focused window's title, a CPU/temp/mem/GPU/net readout — all as Omarchy shell plugins |
| Terminal + shell | kitty as the default terminal, running zsh + Oh My Zsh + Powerlevel10k *inside* the terminal; the login shell stays bash |
| Greeting | hyprconf's `fastfetch` layout |
| Firefox + VS Code | Installed through Omarchy's own installers (`omarchy install browser firefox`, `omarchy install editor vscode`), set as the default browser and editor once |
| Theme reach | Every `omarchy theme set` also lands in Firefox, which Omarchy's own fan-out misses — a user template Omarchy's own engine renders |
| Firefox settings | One system policy — Omarchy's own prefs plus hyprconf's — carries the lot: telemetry off, tracking protection on, **uBlock Origin and Proton Pass** force-installed and pinned to the toolbar, **DuckDuckGo** the default engine, compact density, vertical tabs, a bare Firefox Home, DRM playback on. Policy *defaults*, not user values — any profile comes up configured, it all stays yours to change, and dropping the file puts it back to stock ([details](#firefox-settings)) |
| YubiKey | `hyprconf-yubikey`: unlock the LUKS root at boot with a FIDO2 key (Omarchy's own `omarchy-setup-security-fido2` covers sudo/polkit) |
| Dual-GPU gaming | `hyprconf-vulkan-gpu`: on a box with two GPUs, pins Vulkan (Steam/Proton under Xwayland) to the GPU that drives the displays — session environment in uwsm's `env.d`, which `install.sh` offers to write |
| VPN | **Proton VPN** in Omarchy's menu — Install → Service, beside NordVPN — installed from Arch's official repos with `omarchy-pkg-add` |

---

## Requirements

- A running [Omarchy](https://omarchy.org) install. Verified against Omarchy 4.0.0-1 (Hyprland 0.56, Lua config — hyprlang `.conf` is gone). `install.sh` refuses to run when `/usr/share/omarchy` or `omarchy-pkg-add` is missing.
- `git`, and a terminal for the three stages that need `sudo` (packages, Firefox, VS Code).

## Install

```bash
bash <(curl -fsSL hyprconf.sh)
```

`hyprconf.sh` serves `install.sh` itself to curl. Run with no payload beside it, it refuses a box without Omarchy before touching anything, clones the `stable` branch into `~/.hyprconf` — or uses the checkout already there, without pulling it — and hands over to that checkout's `install.sh` with the same options. `HYPRCONF_REPO` (`https://github.com/ak4dev/.hyprconf`), `HYPRCONF_BRANCH` (`stable`) and `HYPRCONF_DIR` (`~/.hyprconf`) override those three. The same by hand:

```bash
git clone -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf
bash ~/.hyprconf/install.sh
```

`stable` is the branch users get; `dev` is the working branch until `scripts/publish` promotes it. On a terminal every run opens with the `.hyprconf` ASCII banner (the art of `assets/banner.svg`, naming the branch); the post-update hook's run inside `omarchy-update` stays quiet.

| Flag | Effect |
|---|---|
| *(none)* | Apply every stage once. Idempotent — re-running is how you pick up changes. |
| `--sync` | `git pull --ff-only` the checkout, re-apply, then run `omarchy-update`. This is what the `hyprsync` alias runs. |
| `--no-update` | Apply only; never invoke `omarchy-update`. Used by the post-update hook, which already runs inside an update. |
| `--no-packages` | Skip the three stages that need `sudo`: packages, Firefox (and its policy) and VS Code. The hook passes this too. |
| `-h`, `--help` | Usage: both forms and the three variables. On the curl path it answers from the served copy — nothing is cloned. |

### What each stage does

| Stage | Changes | Mechanism |
|---|---|---|
| packages | Installs the `packages` list (official repos only) | `omarchy-pkg-add` — idempotent, never bare `pacman -Syu` (Omarchy's ALPM hook blocks it) |
| firefox | Firefox when absent; `/etc/firefox/policies/policies.json` = Omarchy's `default/firefox/policies.json` merged **under** `infra/firefox/policies.json` (extensions, search engine, privacy and UI settings — [Firefox settings](#firefox-settings)) | `omarchy-install-browser firefox` — Omarchy's own flow: `omarchy-pkg-add firefox`, its prefs to `/usr/lib/firefox/distribution/policies.json`, `MOZ_ENABLE_WAYLAND=1` in `~/.config/environment.d/`. The policy is a `jq` recursive merge (`*`, ours wins on a shared key) written with `sudo install` only when the bytes differ: `/etc/firefox/policies` takes precedence over `distribution/`, so Omarchy's prefs (VA-API, fractional scaling, overscroll) ride along instead of being shadowed. Skipped when there is no terminal for the password prompt. The overlay's one write outside `$HOME` |
| editor | VS Code (`visual-studio-code-bin`, from Omarchy's own `[omarchy]` pacman repository) when absent; Arch's `code` (Code - OSS, what v4.0.0–v4.2.0 installed) removed first — the two packages conflict. Not set-once: any interactive run that finds VS Code absent installs it (dropping Code - OSS again if it is back); Code - OSS's settings and extensions (`~/.config/Code - OSS`, `~/.vscode-oss`) stay, not migrated | `omarchy-pkg-drop code` (Omarchy's remover: `pacman -Rns --noconfirm`, only for names that are installed), then `omarchy-install-editor-vscode` — Omarchy's own flow: the package, `~/.vscode/argv.json`, `update.mode none`, `omarchy-theme-set-vscode`, and it **opens VS Code once** when done, by design. Skipped without a terminal; the result is read back with `omarchy-pkg-present` |
| terminal | kitty becomes the default terminal; `~/.config/kitty/hyprconf.conf` (cursor trail, 0.85 opacity, `shell <zsh>`) plus one `include hyprconf.conf` line appended to `kitty.conf` | `omarchy-default-terminal kitty`; Omarchy's `kitty.conf` stays authoritative (theme include, `listen_on`, font lines). The setter's exit status is its closing notification's, so with no shell (a TTY first run) it warns and the re-run finds kitty already current |
| theme | `~/.config/omarchy/themes/dracula` → `themes/dracula` (hyprconf's Dracula palette + wallpaper) | Symlinked user theme, **installed, never activated** — pick it with `omarchy theme set dracula` or `SUPER+SHIFT+CTRL+SPACE`. A real `themes/dracula` directory (a theme you installed yourself) is left alone with a warning |
| defaults | Browser `firefox`, editor `code` — **set once** | `omarchy-default-browser` / `omarchy-default-editor`; marker `~/.local/state/hyprconf/defaults-applied` |
| backgrounds | `wallpapers/gruvbox.jpg` → `~/.config/omarchy/backgrounds/gruvbox/` | Copied when absent (Omarchy's picker only scans the active theme's dirs) |
| font | System monospace → GeistMono Nerd Font — **set once** | `omarchy-font-set`; marker `~/.local/state/hyprconf/font-applied` |
| idle | Screensaver after **15 min** (`idle.screensaver = 900` in `~/.config/omarchy/shell.json`; Omarchy's default is 150 s; the lock timeout is left alone) — **set once** | Omarchy 4.0.0-1 has no command for these keys, so `jq` edits the file the way `omarchy-shell-config`'s `commit` does (seeded from Omarchy's shipped defaults when you have no `shell.json` yet), then `omarchy-shell shell reloadConfig`; marker `idle-applied` |
| hotkeys | `~/.config/hypr/bindings.lua` → `hypr/bindings.lua` | Symlink (stock file backed up to `bindings.lua.stock`). The hotkey tools are `bin/` commands (below); the `~/.config/hypr/scripts/` copies v4.0.0–v4.2.0 made are swept once |
| looknfeel | `~/.config/hypr/looknfeel.lua` and `input.lua` → the repo's | Symlinks (`.stock` backups) |
| monitors | Seeds the five presets into `~/.config/hypr/` | Seeded, never overwritten — a preset is machine-local; delete one to re-seed. Omarchy's `monitors.lua` is never replaced; one left as a symlink by v4.0.0–v4.2.0 is migrated once (its preset becomes the toggles file, `monitors.lua` comes back from `monitors.lua.stock`, else Omarchy's template) |
| fastfetch | `~/.config/fastfetch/config.jsonc` → `fastfetch/config.jsonc` | Symlink (an existing file backed up to `config.jsonc.stock`). fastfetch reads the user directory before `/etc/fastfetch/` (`fastfetch --list-config-paths`), so Omarchy's own layout, `/etc/fastfetch/config.jsonc` (`omarchy-settings`), stays untouched as the fallback |
| bin | Every `bin/hyprconf-*` tool → `~/.local/bin/`: `hyprconf-monitor-preset`, `hyprconf-gaps` (the hotkey tools), `hyprconf-stats`, `hyprconf-gpu-info` (bar-widget feeders), `hyprconf-yubikey`, `hyprconf-vulkan-gpu`, `hyprconf-firefox-theme`, `hyprconf-install-service-protonvpn` | Copied, with `@HYPRCONF_DIR@` substituted for the checkout path; `bindings.lua` binds the hotkey tools by name, the way Omarchy binds its own commands |
| vulkan_gpu | On a box with two GPUs whose display GPU is not Vulkan device 0: **Fix / Alt / Ignore** (gum), asked on every terminal run until you choose — nothing on one GPU, when the display GPU already is device 0, when a Vulkan setting is already configured, or after Ignore | `hyprconf-vulkan-gpu prompt`, right after `bin` installs it (below). With no terminal, or inside `omarchy-update` (the hook's run), it prints one pointer line. A tool error is a warning, never a failed install |
| menu | A **Proton VPN** row in Omarchy's menu, Install → Service, beside NordVPN — hidden once `proton-vpn-gtk-app` is installed (below) | A managed block (`// >>> hyprconf >>>` … `// <<< hyprconf <<<`) before the closing brace of `~/.config/omarchy/extensions/omarchy-menu.jsonc`, Omarchy's own menu extension file: seeded from its template when absent, written through a symlink, rewritten only when the bytes differ. A file with no closing-brace line is left alone with a warning |
| bar_plugin | `hyprconf.resources` widget in the bar's right section | `plugins/hyprconf-resources/` synced into `~/.config/omarchy/plugins/` on every run; enabled **once**, with no placement argument — the manifest's `barWidget.defaultSection: right` places it (the shell's `defaultBarWidgetSection`) |
| clock | `hyprconf.clock`: a copy of `omarchy.clock` patched to tick seconds, format `hh:mm:ss AP` — **set once** | Same copy mechanics as `omarchy plugin clone` (project namespace instead of `<username>.`); `omarchy-bar set`; the bar's `centerAnchor` follows only if it still pointed at `omarchy.clock` |
| workspaces | `hyprconf.workspaces`: the overlay's own workspaces widget — only workspaces that exist, on two lines, Pac-Man on the focused one | `plugins/hyprconf-workspaces/` synced on every run (a `clonedFrom` copy the shell swaps into the stock widget's slot); enabled **once** |
| window_title | `hyprconf.active-window`: the focused window's title after the workspaces, on **two lines** | `plugins/hyprconf-active-window/` synced on every run (a `clonedFrom` copy the shell swaps into the stock `omarchy.active-window` slot); enabled **once** with no placement of its own: the manifest's `defaultSection: left` and the shell's own anchor after `omarchy.workspaces` — resolved to the `hyprconf.workspaces` copy while it is on the bar — place it |
| shell | Oh My Zsh + Powerlevel10k cloned into `~/.oh-my-zsh`; `~/.p10k.zsh` → `zsh/.p10k.zsh`; managed block in `~/.zshrc` | Plain `git clone`, no `chsh` |
| hooks | `~/.config/omarchy/hooks/post-update.d/10-hyprconf` and `theme-set.d/10-hyprconf` | `omarchy hook install <type> <file>` (Omarchy's own: mkdir, copy under the file's basename, `chmod 755`) on a copy rendered with `@HYPRCONF_DIR@` substituted. The first re-runs `install.sh --no-update --no-packages` after every `omarchy-update`; the second extends every `omarchy theme set` to Firefox (below) |
| themed | `~/.config/omarchy/themed/userChrome.css.tpl` → `themed/userChrome.css.tpl` | Copied when the bytes differ into Omarchy's user-template directory: every `<name>.tpl` there is rendered by `omarchy-theme-set-templates` on each theme set into `~/.local/state/omarchy/current/theme/<name>`. When the template changed or its render is missing, `omarchy-theme-refresh` (`omarchy theme refresh`: re-sets the current theme, wallpaper kept) renders it now; with no active theme the next `omarchy theme set` does |
| theme_apps | Firefox `userChrome.css`/`user.js` match the **active** theme right away | Runs the theme-set hook once for `~/.local/state/omarchy/current/theme.name`; a no-op with no active theme |
| *(end)* | `hyprctl reload`; with `--sync`, `omarchy-update` | A widget whose files changed is picked up as it is synced: `omarchy-shell shell rescanPlugins` (the hot reload `omarchy plugin update` uses), `omarchy-restart-shell` only when no shell answers — both tolerated failing (no shell on a TTY) |

### What it deliberately leaves alone

- The **login shell** — no `chsh`. zsh runs inside kitty only; `~/.zshrc` sources Omarchy's own `envs`/`aliases`, so its updates flow through.
- The body of `~/.config/kitty/kitty.conf`, `~/.bashrc`, `/usr/share/omarchy`, and everything under `/etc` except the Firefox policy (and, only when you run it, `hyprconf-yubikey enroll`'s two drop-ins — see below).
- Installed packages — nothing is removed, with one exception: Arch's `code` (Code - OSS) goes when Omarchy's VS Code is installed, because the two packages conflict.
- The **active theme**, Omarchy's **`monitors.lua`** (a preset loads beside it from the toggles directory and never replaces it), and every set-once choice (font, default apps, idle, clock, widget enables) after the first run — change them with Omarchy's own commands and hyprconf will not take them back.
- Omarchy's keyboard layout logic in `input.lua`, and its volume / brightness / media keys, `SUPER+K` (keybindings menu), `SUPER+3`/`4`, `SUPER+SHIFT+3`.
- A Vulkan GPU setting you already have — `VK_LOADER_DEVICE_ID_FILTER` or `PROTON_ENABLE_WAYLAND` in `~/.config/environment.d/*.conf`, `~/.config/uwsm/env`, `~/.config/uwsm/env.d/*` or the live session: the dual-GPU check reports where and asks nothing.

## Sync

```bash
hyprsync            # the checkout's install.sh --sync (found through the ~/.p10k.zsh link, so a relocated checkout works)
bash install.sh     # after any `omarchy refresh` or when you just want to re-apply
```

- **After `omarchy-update`** the post-update hook re-applies the overlay automatically (a migration replaces `bindings.lua` when it hash-matches stock; `omarchy refresh config kitty/kitty.conf` drops the `include` line).
- **`omarchy refresh config hypr/<file>` / `omarchy refresh hyprland` write *through* the symlinks** into the checkout. `install.sh` detects a `hypr/*.lua` that is byte-identical to Omarchy's stock template and restores it with `git checkout`. `monitors.lua` is Omarchy's own real file, so a refresh of it lands where it should.
- **Edit workflow:** the files in `~/.hyprconf/hypr/` *are* the live files — edit them there, then `bash install.sh` (or `hyprsync`) after a pull or a refresh.

## Repository layout

The tree is in [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md). What reaches your machine: `hypr/`, `bin/`, `plugins/`, `themes/`, `themed/`, `wallpapers/`, `zsh/`, `kitty/`, `fastfetch/` and `hooks/` land in `$HOME` (the `hypr/*.lua` overrides, the theme, `.p10k.zsh` and the fastfetch config as symlinks into the checkout; the template into `~/.config/omarchy/themed/`; `lib/hyprconf/` is used in place), and `infra/firefox/policies.json` is the one system file, merged over Omarchy's own.

## Monitor presets

| Preset | File | Hotkey |
|---|---|---|
| `bedroom` | `~/.config/hypr/pcMonitors.bedroom.lua` | `SUPER+SHIFT+B` |
| `kitchen` | `~/.config/hypr/pcMonitors.kitchen.lua` | `SUPER+SHIFT+K` |
| `K` | `~/.config/hypr/pcMonitors.K.lua` | — |
| `pc` | `~/.config/hypr/pcMonitors.lua` | — |
| `laptop` | `~/.config/hypr/laptopMonitors.lua` | — |
| `stock` (or `omarchy`) | — (removes the toggle file; Omarchy's `monitors.lua` alone speaks) | — |

```bash
hyprconf-monitor-preset <preset>
```

`hyprconf-monitor-preset` copies the preset (never links it) to `~/.local/state/omarchy/toggles/hypr/hyprconf-monitor-preset.lua` — Omarchy's Hyprland toggles directory, which its `default/hypr/toggles.lua` loads (`require_all`, reloaded on every `hyprctl reload`) *after* `~/.config/hypr/monitors.lua` in `hyprland.lua`, so a later `hl.monitor` for the same output wins; it is the seam Omarchy's own `omarchy-hyprland-monitor-internal` toggle writes to. Then `hyprctl reload`, then it walks the preset's `hl.workspace_rule` lines and moves each existing workspace to its monitor (a reload only places *future* workspaces). Dark outputs get a `dpms` wake retry. Feedback goes through `omarchy-osd` and `omarchy-notification-send`. `stock` deletes the toggle file and reloads. Omarchy's `monitors.lua` is never touched, so `omarchy-hyprland-monitor-scaling` and `omarchy refresh` keep working on their own file. Each preset carries its workspace-to-monitor rules, and edits to a preset survive re-selecting it.

Upgrading from v4.0.0–v4.2.0, whose `switch_monitor.sh` symlinked the preset over `monitors.lua`: `install.sh` migrates that link once — the preset it pointed at becomes the toggle file, and `monitors.lua` comes back as a real file from `monitors.lua.stock` (or Omarchy's template). `monitors.lua.stock` is left for you to delete.

## Bar widgets

| Plugin id | What | Revert |
|---|---|---|
| `hyprconf.clock` | Copy of `omarchy.clock` sampling at `SystemClock.Seconds`, format `hh:mm:ss AP` | `omarchy plugin disable hyprconf.clock` |
| `hyprconf.workspaces` | The overlay's own workspaces widget: only workspaces that exist (no fixed 1–5 pills, no id cap), stacked on two lines like the resources widget, hyprconf's Pac-Man (`󰮯`) on the focused workspace; click focuses | `omarchy plugin disable hyprconf.workspaces` |
| `hyprconf.resources` | Two aligned lines fed by `hyprconf-stats` and `hyprconf-gpu-info` (long-lived JSON streams): top **CPU temp / util · RAM · ↑ upload**, bottom **GPU temp / util · VRAM · ↓ download**. Columns are fixed-width (sized from their widest value) with a hairline gap between them, so nothing shifts as the numbers change. On a multi-GPU box the **active** card is shown — the one with the most VRAM in use (ties: utilization, then index), re-evaluated every sample. Click opens `btop` via `omarchy-launch-or-focus-tui` | `omarchy plugin disable hyprconf.resources` |
| `hyprconf.active-window` | The focused window's title after the workspaces — the overlay's own two-line version of Omarchy's `omarchy.active-window` (a `clonedFrom` copy, so it takes the stock slot) that lays the same character budget (`maxWidth`, 280 px of body text by default) out on **two caption-size lines**, so it takes about half the width; hover for the full title, click focuses, middle-click closes; budget via `omarchy bar set hyprconf.active-window maxWidth 400` | `omarchy plugin disable hyprconf.active-window` |

The clock copy is set once, and every widget is *enabled* once — disabling any of them sticks. The three plugins the overlay ships (`plugins/hyprconf-resources`, `plugins/hyprconf-workspaces`, `plugins/hyprconf-active-window`) are re-synced on every run, so a `git pull` updates them — staged in a sibling temp dir and moved into place, the way `omarchy plugin clone` lands a copy, then `omarchy-shell shell rescanPlugins` hot-reloads them; the clock is the one copy of a stock plugin `install.sh` makes. `omarchy bar set hyprconf.clock format 'HH:mm'` reformats the clock.

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
| `SUPER+SHIFT+A / D / W / S` | Swap window left / right / up / down |
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

**Left to Omarchy on purpose:** volume, brightness and media keys (Omarchy's drive its OSD and media service), `SUPER+K`, `SUPER+SPACE`, `SUPER+3`/`4`, `SUPER+SHIFT+3` — and its own `SUPER+P` (pseudo), `SUPER+← → ↑ ↓` (focus), `SUPER+scroll` (workspace scroll) and `SUPER+LMB`/`RMB` drag (move/resize), which hyprconf does not restate (`default/hypr/bindings/tiling.lua`). **Displaced Omarchy defaults** (Omarchy 4.0.0-1, `/usr/share/omarchy/default/hypr/bindings/*.lua`; each still reachable by command or by another Omarchy key):

| Key | Omarchy's binding | Still available as |
|---|---|---|
| `SUPER+T` | Toggle window floating | hyprconf's `SUPER+V` |
| `SUPER+F` | Full screen | hyprconf's `SUPER+SHIFT+F` |
| `SUPER+C` / `SUPER+V` | Universal copy / paste | `CTRL+C` / `CTRL+V` in the app |
| `SUPER+SHIFT+F` | File manager (`omarchy-launch-nautilus`) | hyprconf's `SUPER+E`; Omarchy's `SUPER+ALT+SHIFT+F` (cwd) |
| `SUPER+SHIFT+B` | Browser (`omarchy-launch-browser`) | hyprconf's `SUPER+F`; Omarchy's `SUPER+SHIFT+RETURN` |
| `SUPER+SHIFT+← → ↑ ↓` | Swap window | hyprconf's `SUPER+SHIFT+A / D / W / S` |
| `SUPER+SHIFT+-` / `SUPER+SHIFT+=` | Shrink window up / expand window down (keycode binds `code:20`/`code:21`) | Omarchy's `SUPER+SHIFT+ALT+-`/`=` (a little) and `SUPER+CTRL+SHIFT+-`/`=` (a lot) |
| `SUPER+SHIFT+4` | Move window to workspace 4 (`SUPER+SHIFT+code:13`) | hyprconf's `SUPER+SHIFT+F2` |
| `SUPER+SHIFT+SPACE` | Toggle top bar | `omarchy toggle bar` |
| `SUPER+L` | Toggle workspace layout | `omarchy-hyprland-workspace-layout-toggle`; lock stays on Omarchy's `SUPER+CTRL+L` too |
| `SUPER+SHIFT+BACKSPACE` | Toggle window gaps | `omarchy-hyprland-window-gaps-toggle` |
| `SUPER+SHIFT+A` / `D` / `W` / `S` / `M` | ChatGPT / Docker / Omawrite / Google Maps / Music — only while Omarchy's preinstalled-app bindings are on (`o.preinstalled_bindings_enabled()`: until `~/.local/state/omarchy/preinstalls-removed` exists) | `omarchy-launch-webapp`, `omarchy-launch-tui lazydocker`, `omawrite`, `omarchy-launch-spotify` |

## Look'n'feel and input deltas

Only what differs from `/usr/share/omarchy/default/hypr/`:

| File | Setting | hyprconf | Omarchy |
|---|---|---|---|
| `looknfeel.lua` | `general.gaps_in` / `gaps_out` | 3 / 3 | 5 / 10 |
| | `decoration.rounding` / `rounding_power` | 1 / 3 | 0 / – |
| | `decoration.inactive_opacity` | 0.8 | 1 |
| | `decoration.shadow` | on (range 4, power 3) | off |
| | `decoration.blur` | on (size 3, passes 4, vibrancy 0.1696) | off |
| | animations | `windows` easeOutQuint 4.79; `workspaces`/`In`/`Out` fade | workspaces animation off |
| | `dwindle.force_split` / `precise_mouse_move` / `smart_split` | 0 / true / true | 2 / – / – |
| | `misc.force_default_wallpaper` | 0 | – |
| | window rules: class `steam` | **tiled** (`o.window("steam", { tile = true })`; the Friends List stays floating) | every Steam window floats (`default/hypr/apps/steam.lua`) |
| `input.lua` | `input.natural_scroll` + `touchpad.natural_scroll` | true | false |
| | `hl.gesture` 3-finger horizontal → workspace, plus swipe tuning | on | – |

Border colours stay with the active Omarchy theme; keyboard layout stays with Omarchy's `input.lua` logic.

## Packages

From `packages`, installed via `omarchy-pkg-add` — **official repositories only, never the AUR**:

| Package | Why |
|---|---|
| `kitty` | Default terminal |
| `otf-geist-mono-nerd` | System monospace font (set once) |
| `zsh`, `zsh-autosuggestions`, `zsh-syntax-highlighting` | Shell inside kitty |

Firefox (`SUPER+F`) and VS Code (`SUPER+C`) are not in `packages`: they come through Omarchy's own installers (the `firefox` and `editor` stages), which set up what a bare package would not. `visual-studio-code-bin` is from Omarchy's own `[omarchy]` pacman repository (`pacman -Si`: *Repository: omarchy*; it provides `code` and conflicts with Arch's `code`) — the one package the overlay takes from outside Arch's official repositories, and only through `omarchy-install-editor-vscode`; no AUR helper is ever called. `hyprconf-yubikey enroll` adds `libfido2` on demand, through `omarchy-pkg-add`.

## zsh

The `~/.zshrc` managed block (`# >>> hyprconf >>>` … `# <<< hyprconf <<<`, source `zsh/zshrc.block`) sources Omarchy's `default/bash/{env-bootstrap,envs,aliases}`, initialises `zoxide` (Omarchy aliases `cd` to it), loads Oh My Zsh with the `powerlevel10k` theme and `~/.p10k.zsh`, `zsh-autosuggestions`, the `hyprsync` alias, a `fastfetch` greeting, and `zsh-syntax-highlighting` last. Everything outside the markers is preserved.

## Firefox settings

Every setting below rides in the one system policy the `firefox` stage installs — `/etc/firefox/policies/policies.json`, Omarchy's own `default/firefox/policies.json` merged **under** [`infra/firefox/policies.json`](infra/firefox/policies.json). Firefox reads it at every startup, so any profile, a fresh one included, comes up configured, and none of it is written into a profile. (The theme is the one thing that *is* — [Theme → Firefox](#theme--firefox) below.)

| What | How |
|---|---|
| **uBlock Origin** and **Proton Pass**, both pinned to the toolbar | `ExtensionSettings`: `force_installed` by the id each signed XPI declares, from the AMO `.../downloads/latest/<slug>/latest.xpi` URL, with `default_area: "navbar"` — Firefox's own knob for where a browser action lands (without it an extension falls into the overflow menu). Neither entry sets `private_browsing`: its presence at *any* value would take the about:addons toggle away from you |
| **DuckDuckGo** as the default search engine | `SearchEngines`. Despite what Mozilla's docs still say, this is **not** ESR-only — verified applying on release Firefox 154.0. The name has to be exactly the one Firefox knows — on a miss Firefox logs `Search engine lookup failed` to the Browser Console and leaves the default engine alone, which on a fresh profile means the region default (Google) and so *looks* like a silent fallback |
| **Compact density**, **vertical tabs**, the revamped sidebar | `browser.uidensity` (with `browser.compactmode.show`, which is what makes the density reachable in the UI), `sidebar.verticalTabs`, `sidebar.revamp` |
| A **bare Firefox Home** — no shortcuts, no web search, no sponsored tiles, no stories, no weather | the `browser.newtabpage.activity-stream.*` block |
| **DRM playback** on | `EncryptedMediaExtensions` |
| Telemetry, studies and feedback off; tracking protection on with cryptominer and fingerprinter blocking; `userChrome.css` loading on (what [Theme → Firefox](#theme--firefox) needs) | the rest of the policy |

Every captured pref is a `Status: "default"` — it seeds the profile and then gets out of the way; the one locked pref is `browser.discovery.enabled`, off. (Firefox locks a few of its own besides: `OverrideFirstRunPage` and `OverridePostUpdatePage` lock the welcome-page prefs they set. Dropping the policy file unlocks all of them.)

**Two settings are deliberately not shipped**, because Firefox has no mechanism that would make them stick:

- **The find bar's *Highlight All*.** `findbar.highlightAll` is outside Firefox's allowlist for the `Preferences` policy and there is no policy for it, so it is a per-profile checkbox. Tick it once in the find bar.
- **The exact toolbar button order.** `browser.uiCustomization.state` *is* accepted by the policy, and it still does not work: CustomizableUI re-serializes the layout over it on every start. The part of it that was a real choice — the two extension buttons in the nav bar — comes from `default_area` above instead, and the empty tab strip follows from `sidebar.verticalTabs`.

Firefox drops any pref outside its own allowlist **silently** — the policy still loads, the pref simply never applies — so `tests/unit/test_firefox.py` pins that allowlist and checks every pref against it. (Omarchy's own policy trips this: `apz.overscroll.enabled` is rejected on every start. That one is Omarchy's to fix, and the overlay does not touch it.)

Undo: `sudo rm /etc/firefox/policies/policies.json`, then restart Firefox — see [Reverting to stock](#reverting-to-stock). Force-installed extensions are removed by policy, not by hand; drop the file and they become ordinary add-ons you can uninstall.

## Theme → Firefox

Omarchy's `omarchy theme set` fans the theme out to kitty, btop, VS Code (`omarchy-theme-set-vscode`, one of its own post-theme commands — one reason the editor comes through Omarchy's installer) and Chromium-family browsers, but not to Firefox (`omarchy-theme-set-browser` writes a Chromium policy colour). The overlay closes that gap with Omarchy's own template engine and one hook:

| Piece | What |
|---|---|
| `themed/userChrome.css.tpl` → `~/.config/omarchy/themed/` | A user template: Firefox's `--lwt-*`/`--toolbar-*` theme variables **and** direct rules for the toolbox, tabs, URL bar and sidebar, from `{{ background }}`, `{{ foreground }}`, `{{ accent }}`, `{{ dark_background }}`, `{{ lighter_background }}`, plus `--hyprconf-theme-mode: {{ mode }}` — the mode Omarchy resolved (`mode = "light"` in the theme's `colors.toml`, the legacy `light.mode` file, else dark). `omarchy-theme-set-templates` renders it on every theme set into `~/.local/state/omarchy/current/theme/userChrome.css` |
| `theme-set.d/10-hyprconf` hook | Runs after every theme switch (`omarchy-hook theme-set <name>` at the end of `omarchy-theme-set`) and once from `install.sh`: `lib/hyprconf/firefox_theme.py` copies the rendered file byte-for-byte into `chrome/userChrome.css` of the default profile (`[Install…] Default` wins, then `Default=1`) and merges **three** prefs into `user.js`: `toolkit.legacyUserProfileCustomizations.stylesheets` (stylesheet loading), **`extensions.activeThemeID` = Firefox's built-in Dark or Light theme** for the declared mode (the `--lwt-*` overrides only apply under a lightweight theme — under the default *System theme* they do nothing) and `ui.systemUsesDarkTheme`. Nothing else in `user.js` is touched. A missing render is an error naming `omarchy theme refresh`; the `themed` stage renders it before `theme_apps` runs the hook |

**Takes effect on the next Firefox start** — Firefox reads `userChrome.css` and `user.js` only at startup, so whenever the files change you get an Omarchy notification saying so. Closing the last window is not enough while a Firefox process is still running. `hyprconf-firefox-theme --status` prints the rendered file and its mode, the profile it wrote to (`written` / `STALE` / `MISSING`) and whether Firefox has restarted since (it checks `prefs.js`, which Firefox rewrites from its live state). `hyprconf-firefox-theme` with no argument re-applies now.

Undo: delete `~/.config/omarchy/hooks/theme-set.d/10-hyprconf`, `~/.config/omarchy/themed/userChrome.css.tpl`, `~/.local/state/omarchy/current/theme/userChrome.css`, the profile's `chrome/userChrome.css`, and the three `user_pref` lines it added (`toolkit.legacyUserProfileCustomizations.stylesheets`, `extensions.activeThemeID`, `ui.systemUsesDarkTheme`), then restart Firefox — `hyprconf-firefox-theme --status` shows which profile they are in.

## YubiKey: LUKS unlock at boot (`hyprconf-yubikey`)

Omarchy's `omarchy-setup-security-fido2` enrols a FIDO2 key for `sudo` and polkit. What it does not do is let the key unlock the encrypted root at boot. `hyprconf-yubikey` is that missing half, on Omarchy's own boot chain (Limine + `limine-update`, mkinitcpio drop-ins, `omarchy snapshot`):

```bash
hyprconf-yubikey status            # devices, token slot, both drop-ins, kernel cmdline (legacy inline parameters?), key present?
hyprconf-yubikey enroll            # the whole setup (prompts: LUKS passphrase, FIDO2 PIN, touch)
hyprconf-yubikey sudo              # = omarchy-setup-security-fido2 (sudo + polkit)
hyprconf-yubikey disable           # back to passphrase-only boot; the LUKS slot stays
hyprconf-yubikey remove            # wipe the FIDO2 slot, then disable
# flags for enroll/disable/remove: --device /dev/X  --yes  --no-snapshot
# enroll only: --allow-non-latin-layout (see `hyprconf-yubikey help`)
```

`enroll` installs `libfido2` (`omarchy-pkg-add`), waits for a key (`fido2-token -L`), picks the LUKS2 device (refuses LUKS1), offers an `omarchy snapshot create` first, enrols the key with `systemd-cryptenroll --fido2-device=auto --fido2-with-client-pin=yes`, and then makes the initramfs able to use it. Omarchy boots through the classic busybox `encrypt` hook (`/etc/mkinitcpio.conf.d/omarchy_hooks.conf`, `cryptdevice=PARTUUID=…` on the Limine cmdline), and FIDO2 unlock needs systemd's `sd-encrypt`, so the tool:

- writes its **own** drop-in `/etc/mkinitcpio.conf.d/zz-hyprconf-fido2.conf`, sourced after Omarchy's, that rewrites the hook set (`udev`→`systemd`, `encrypt`→`sd-encrypt`, `keymap`→`sd-vconsole`, `btrfs-overlayfs`→`sd-btrfs-overlayfs` when installed; `consolefont` and `resume` dropped — `sd-vconsole` covers the font and systemd resumes on its own) — Omarchy can rewrite its drop-in on an update without undoing this;
- writes a **limine-entry-tool drop-in**, `/etc/limine-entry-tool.d/zz-hyprconf-fido2.conf`: `KERNEL_CMDLINE[default]+=" rd.luks.name=<UUID>=<mapper> rd.luks.options=<UUID>=fido2-device=auto"` — the way Omarchy's own `omarchy-hibernation-setup` adds `resume=` through `resume.conf` in that directory (limine-entry-tool loads the drop-ins before `/etc/default/limine`; `+=` appends). `/etc/default/limine` is only **read** (for the mapper name `cryptdevice=` opens; the one-time migration below is the exception) and keeps `cryptdevice=`, so the box still boots if the hook set ever reverts (each hook ignores the other's parameters). `enroll` refuses a plain `KERNEL_CMDLINE[default]=` there (it would replace every drop-in's parameters, Omarchy's included) and a competing `rd.luks.options=` for the device;
- runs `limine-update`, which rebuilds every initramfs/UKI (`limine-mkinitcpio`) and the Limine entries.

At boot: plug the key in, enter its PIN, touch it; with no key present systemd waits `token-timeout` (30 s) and falls back to the passphrase. `enroll` refuses a `/etc/vconsole.conf` whose first `XKBLAYOUT` is non-Latin (the systemd initramfs always bundles it, so a Latin passphrase could become untypeable) unless `--allow-non-latin-layout` is given. Your passphrase stays as a fallback — no passphrase slot is ever touched. Limine's read-only **snapshot** boot entries keep their writable overlay through `sd-btrfs-overlayfs` (limine-mkinitcpio-hook ≥ 1.37 ships it; an older hook package without it loses the overlay under systemd init — normal boots are unaffected either way). `disable` removes both drop-ins; `remove` also wipes the FIDO2 slot. **Upgrading from v4.0.0–v4.2.0:** those releases put the two parameters on `/etc/default/limine`'s line itself (and left a `limine.bak.<epoch>`); the next `enroll` or `disable` moves them out once — logged as a migration, the rest of the line byte-identical — and `status` reports them as *legacy inline parameters* until then.

## Dual-GPU Vulkan (Proton) fix (`hyprconf-vulkan-gpu`)

**Symptom:** on a box with two GPUs, a Steam/Proton game dies right after start with `CreateSwapChainForHwnd` → `E_INVALIDARG` (DXVK / vkd3d-proton; the game log may say "No display detected for current GPU") while the launcher itself works. **Cause, two independent halves:** Xwayland exposes no RandR providers, so Wine binds every monitor to Vulkan physical device 0 — the first GPU by PCI order, not the one the displays are plugged into — and a game on any other GPU has no output on its adapter (reordering with `VK_LOADER_DEVICE_SELECT` alone is not enough: the other GPU must leave Vulkan enumeration). And NVIDIA's driver presents to Xwayland only from its own GPU 0 unless PRIME render offload is on — two variables, both required.

`hyprconf-vulkan-gpu` reads the GPUs from sysfs (`/sys/bus/pci/devices/*/class` `0x03…`), takes the card with the most `connected` connectors under `/sys/class/drm` as the display GPU, and Vulkan device 0 from `vulkaninfo --summary` (`vulkan-tools`) when installed — otherwise it assumes PCI order and says so. `install.sh` runs `prompt`; the rest is yours:

```bash
hyprconf-vulkan-gpu status [--quiet]   # GPUs, display GPU, Vulkan device 0, configuration; exit 0 nothing to do, 3 at risk, 1 error
hyprconf-vulkan-gpu prompt     # the install-time question: Fix / Alt / Ignore; silent unless at risk and unconfigured
hyprconf-vulkan-gpu fix        # write the file below; drops the Ignore marker
hyprconf-vulkan-gpu alt        # the same file with `export PROTON_ENABLE_WAYLAND=1` only
hyprconf-vulkan-gpu ignore     # ~/.local/state/hyprconf/vulkan-gpu-ignored: never ask again
hyprconf-vulkan-gpu remove     # delete the file and the marker
```

**Fix** writes `~/.config/uwsm/env.d/50-hyprconf-vulkan-gpu`: uwsm sources every file there at login (`/usr/lib/uwsm/prepare-env.sh`), and Omarchy's own `/usr/share/uwsm/env.d/10-omarchy` names it as the place for user overrides — so every launcher and game inherits it. For the box it was verified on (displays on the second of two NVIDIA GPUs, `10de:2b85`) the file is exactly:

```sh
# hyprconf-vulkan-gpu: pin Vulkan to the display GPU 0000:0a:00.0 (NVIDIA 10de:2b85);
# hidden from Vulkan: 0000:04:00.0 (NVIDIA 10de:2484). Undo: hyprconf-vulkan-gpu remove
export VK_LOADER_DEVICE_ID_FILTER=0x2b85
export VK_LOADER_DEVICE_SELECT=10de:2b85
export __NV_PRIME_RENDER_OFFLOAD=1
export __VK_LAYER_NV_optimus=NVIDIA_only
```

The two loader lines (`vulkan-icd-loader` ≥ 1.4.3xx; verified against 1.4.357) expose only the display GPU to Vulkan and make it device 0. The NVIDIA pair is written only when the display GPU is NVIDIA *and* another NVIDIA GPU precedes it in PCI order (the driver's GPU 0); an AMD or Intel display GPU gets the two loader lines alone. The filter hides the other GPU from **Vulkan only** — the compositor (KMS/EGL) still drives monitors plugged into it; Vulkan compute no longer sees it. `MESA_VK_DEVICE_SELECT` is not used (Mesa 25 dropped that layer). **Alt** is the fallback when Xwayland presentation still fails: `PROTON_ENABLE_WAYLAND=1` for a Wayland-capable Proton, which presents natively from either GPU — no filter. **Ignore** writes the marker; `fix` stays available.

**Re-login** (or restart Steam with the variables set): apps started through uwsm / `systemd-run --scope` inherit the compositor's environment, so `systemctl --user set-environment` alone does not reach them mid-session. Undo with `hyprconf-vulkan-gpu remove`, then re-login.

## Proton VPN

Omarchy's menu installs NordVPN from Install → Service; the `menu` stage puts a **Proton VPN** row beside it through Omarchy's own seam for user rows, `~/.config/omarchy/extensions/omarchy-menu.jsonc` (merged over the default menu and watched, so the row appears without a shell restart). It is shaped like Omarchy's NordVPN row: hidden once `proton-vpn-gtk-app` is installed, and it runs `hyprconf-install-service-protonvpn` in the floating presentation terminal, where the package prompt is on screen.

That script is one `omarchy-pkg-add proton-vpn-gtk-app proton-vpn-cli` — both from Arch's `extra` repository, never the AUR; `proton-vpn-daemon` comes with them. Nothing is enabled and no group is joined: the daemon's `proton.VPN.service` is D-Bus-activated (`me.proton.vpn.split_tunneling.service`), so unlike NordVPN there is no `systemctl enable` and no reboot. Sign in with `protonvpn login` (the CLI) or in the Proton VPN app (`protonvpn-app`).

Remove: delete the managed block from `omarchy-menu.jsonc` (the `sed` under Reverting to stock — the parser drops the comma it leaves before `}`), then `omarchy pkg drop proton-vpn-gtk-app proton-vpn-cli` (`pacman -Rns`, so the daemon goes too) or Omarchy's picker, `omarchy pkg remove` (menu → Remove → Package).

## Reverting to stock

```bash
hyprconf-yubikey remove   # only if you enrolled a key — first, while the tool is still on PATH; both drop-ins go (and a v4.0.0–v4.2.0 enroll's inline parameters)
hyprconf-vulkan-gpu remove   # the uwsm env.d file and the Ignore marker, if you chose either; re-login after
omarchy plugin disable hyprconf.clock
omarchy plugin disable hyprconf.workspaces
omarchy plugin disable hyprconf.resources
omarchy plugin disable hyprconf.active-window
hyprconf-monitor-preset stock   # removes ~/.local/state/omarchy/toggles/hypr/hyprconf-monitor-preset.lua
for f in bindings input looknfeel; do mv ~/.config/hypr/$f.lua.stock ~/.config/hypr/$f.lua; done
rm ~/.config/hypr/{pcMonitors*,laptopMonitors}.lua; rm -f ~/.config/hypr/monitors.lua.stock   # the .stock is a v4.0.0–v4.2.0 leftover
rm ~/.config/omarchy/hooks/{post-update,theme-set}.d/10-hyprconf
rm ~/.config/omarchy/themed/userChrome.css.tpl ~/.local/state/omarchy/current/theme/userChrome.css   # the theme-set hook's source; the profile copy is under Theme → Firefox
sed -i '/^# hyprconf overlay$/d; /^include hyprconf.conf$/d' ~/.config/kitty/kitty.conf; rm ~/.config/kitty/hyprconf.conf
sed -i '/^  \/\/ >>> hyprconf >>>$/,/^  \/\/ <<< hyprconf <<<$/d' ~/.config/omarchy/extensions/omarchy-menu.jsonc  # the Proton VPN row
rm ~/.config/omarchy/themes/dracula ~/.p10k.zsh ~/.local/bin/hyprconf-*
rm -r ~/.config/omarchy/plugins/hyprconf.* ~/.local/state/hyprconf
rm ~/.config/omarchy/backgrounds/gruvbox/gruvbox.jpg; rmdir ~/.config/omarchy/backgrounds/gruvbox 2>/dev/null   # your own wallpapers there stay
rm ~/.config/fastfetch/config.jsonc; [ -e ~/.config/fastfetch/config.jsonc.stock ] && mv ~/.config/fastfetch/config.jsonc.stock ~/.config/fastfetch/config.jsonc   # Omarchy's own /etc/fastfetch/config.jsonc is the default again
omarchy default terminal <name>; omarchy font set <name>; omarchy theme set <name>
sudo rm /etc/firefox/policies/policies.json   # Omarchy's prefs are in /usr/lib/firefox/distribution/policies.json only if Omarchy's installer put Firefox there (a v4.0.0–v4.2.0 install did not) — else: omarchy install browser firefox
# ^ this also un-manages uBlock Origin and Proton Pass (they stay installed, as ordinary add-ons you can now remove). Every captured pref was a default, never a user value, so the prefs you had changed yourself are untouched — except the search engine, which the policy records as the profile's choice: dropping the file hands it to Firefox's region default, not to whatever you had picked before. Set it again in Settings › Search
# Firefox and VS Code are Omarchy's installs and stay; `omarchy pkg drop visual-studio-code-bin firefox` if you want them gone
```

Then delete the managed block from `~/.zshrc` (`# >>> hyprconf >>>` … `# <<< hyprconf <<<`), `~/.oh-my-zsh` if you no longer want it, and `~/.hyprconf`. `idle.screensaver` in `~/.config/omarchy/shell.json` stays at 900 s until you edit it. Do not `omarchy refresh hyprland` instead of the `mv` line: it also overwrites `hyprland.lua`, `autostart.lua` and `monitors.lua` with Omarchy's templates.

## Testing & development

`make test` runs the hermetic unit + integration suites; `make lint` and `make shellcheck` are the other two CI gates. The test tree, the publish flow and the website upload are in [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md); [`AGENTS.md`](AGENTS.md) holds the rules, gates and CI recipe that bind every change.
