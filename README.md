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
  <img src="assets/hyprconf.png" width="920" alt=".hyprconf desktop and TUI" />
</p>

<p align="center"><sub>Screenshot shows the pre-Omarchy hyprconf desktop; an Omarchy-era capture will replace it.</sub></p>

# .hyprconf

**hyprconf** is an overlay for [Omarchy](https://omarchy.org). Omarchy owns the
base system — packages, session, shell, theme engine, lock/idle, bar. hyprconf
layers one person's preferences on top of it, always through Omarchy's own tools
and documented seams:

| Layer | What you get |
|---|---|
| Hotkeys | hyprconf's keymap in `~/.config/hypr/bindings.lua`, with descriptions so it shows in Omarchy's `SUPER+K` menu |
| Look'n'feel + input | Tighter gaps, hairline rounding, blur/shadow, fade workspace animation, natural scroll, 3-finger swipe |
| Monitor presets | `bedroom` / `kitchen` / `K` / `pc` / `laptop`, hot-swapped with a hotkey (`switch_monitor.sh`) |
| Bar widgets | A clock that ticks seconds, active-only workspace pills, a CPU/temp/mem/GPU/net readout — all as Omarchy shell plugins |
| Terminal + shell | kitty as the default terminal, running zsh + Oh My Zsh + Powerlevel10k *inside* the terminal; the login shell stays bash |
| Greeting | hyprconf's `fastfetch` layout |
| Privacy | A system Firefox policy: telemetry off, tracking protection on, uBlock Origin force-installed |
| TUI | `hyprconf`, a Textual TUI for Hyprland options, keybinds, rules, monitors, and Omarchy's theme / background / idle settings |

hyprconf used to be a standalone Arch + Hyprland installer and dotfiles suite; that era is gone, and this repository is now only the overlay.

---

## Requirements

- A running [Omarchy](https://omarchy.org) install. Verified against Omarchy 4.0.0 (Hyprland 0.56, Lua config — hyprlang `.conf` is gone). `install.sh` refuses to run when `/usr/share/omarchy` or `omarchy-pkg-add` is missing.
- `git`, and a terminal for the two stages that need `sudo` (packages, Firefox policy).

## Install

```bash
git clone https://github.com/ak4dev/.hyprconf ~/.hyprconf && cd ~/.hyprconf
bash install.sh
```

`stable` is the branch users get; `omarchy` is the working branch until `scripts/publish` promotes it.

| Flag | Effect |
|---|---|
| *(none)* | Apply every stage once. Idempotent — re-running is how you pick up changes. |
| `--sync` | `git pull --ff-only` the checkout, re-apply, then run `omarchy-update`. This is what the `hyprsync` alias runs. |
| `--no-update` | Apply only; never invoke `omarchy-update`. Used by the post-update hook, which already runs inside an update. |
| `--no-packages` | Skip the two stages that need `sudo`: packages and the Firefox policy. The hook passes this too. |

### What each stage does

| Stage | Changes | Mechanism |
|---|---|---|
| packages | Installs the `packages` list (official repos only) | `omarchy-pkg-add` — idempotent, never bare `pacman -Syu` (Omarchy's ALPM hook blocks it) |
| firefox | `/etc/firefox/policies/policies.json` from `infra/firefox/policies.json` | `sudo install`; skipped when there is no terminal for the password prompt. The overlay's one write outside `$HOME` |
| terminal | kitty becomes the default terminal; `~/.config/kitty/hyprconf.conf` (cursor trail, 0.85 opacity, `shell <zsh>`) plus one `include hyprconf.conf` line appended to `kitty.conf` | `omarchy-default-terminal kitty`; Omarchy's `kitty.conf` stays authoritative (theme include, `listen_on`, font lines) |
| theme | `~/.config/omarchy/themes/hyprconf` → `themes/hyprconf` (Dracula palette + wallpaper) | Symlinked user theme, **installed, never activated** — pick it with `omarchy theme set hyprconf` or `SUPER+SHIFT+CTRL+SPACE` |
| defaults | Browser `firefox`, editor `code` — **set once** | `omarchy-default-browser` / `omarchy-default-editor`; marker `~/.local/state/hyprconf/defaults-applied` |
| backgrounds | `wallpapers/gruvbox.jpg` → `~/.config/omarchy/backgrounds/gruvbox/` | Copied when absent (Omarchy's picker only scans the active theme's dirs) |
| font | System monospace → GeistMono Nerd Font — **set once** | `omarchy-font-set`; marker `~/.local/state/hyprconf/font-applied` |
| hotkeys | `~/.config/hypr/bindings.lua` → `hypr/bindings.lua`; `switch_monitor.sh` + `adjust-gaps` → `~/.config/hypr/scripts/` | Symlink (stock file backed up to `bindings.lua.stock`) |
| looknfeel | `~/.config/hypr/looknfeel.lua` and `input.lua` → the repo's | Symlinks (`.stock` backups) |
| monitors | Seeds the five presets into `~/.config/hypr/`; saves Omarchy's `monitors.lua` to `monitors.lua.stock` once | Seeded, never overwritten — a preset is machine-local; delete one to re-seed. The active `monitors.lua` is untouched until a hotkey is pressed |
| fastfetch | `~/.config/fastfetch/config.jsonc` → `fastfetch/config.jsonc` | Symlink |
| bin | `hyprconf-stats`, `hyprconf-gpu-info` → `~/.local/bin/` | Copied (bar-widget feeders) |
| tui | `hyprconf` launcher → `~/.local/bin/`; `tui/` → `~/.config/hypr/scripts/hyprconf-tui`; `lib/hyprconf/` → `~/.local/lib/hyprconf`; `hyprconf.desktop` app-menu entry; managed block at the tail of `~/.config/hypr/hyprland.lua` that loads `conf.d/{local,windowrules,workspacerules}.lua` | Symlinks + `omarchy-launch-or-focus-tui` |
| bar_plugin | `hyprconf.resources` widget in the bar's right section | `plugins/hyprconf-resources/` synced into `~/.config/omarchy/plugins/` on every run; enabled **once** |
| clock | `hyprconf.clock`: a copy of `omarchy.clock` patched to tick seconds, format `hh:mm:ss AP` — **set once** | Same copy mechanics as `omarchy plugin clone` (project namespace instead of `<username>.`); `omarchy-bar set`; the bar's `centerAnchor` follows only if it still pointed at `omarchy.clock` |
| workspaces | `hyprconf.workspaces`: the overlay's own workspaces widget — only workspaces that exist, on two lines, Pac-Man on the focused one | `plugins/hyprconf-workspaces/` synced on every run (a `clonedFrom` copy the shell swaps into the stock widget's slot); enabled **once** |
| window_title | The focused window's title after the workspaces — Omarchy's own `omarchy.active-window` widget, nothing shipped | `omarchy-plugin-enable omarchy.active-window --section left --after hyprconf.workspaces`, **once** |
| shell | Oh My Zsh + Powerlevel10k cloned into `~/.oh-my-zsh`; `~/.p10k.zsh` → `zsh/.p10k.zsh`; managed block in `~/.zshrc` | Plain `git clone`, no `chsh` |
| hooks | `~/.config/omarchy/hooks/post-update.d/10-hyprconf` and `theme-set.d/10-hyprconf` | The first re-runs `install.sh --no-update --no-packages` after every `omarchy-update`; the second extends every `omarchy theme set` to Firefox and Code - OSS (below) |
| theme_apps | Firefox `userChrome.css`/`user.js` and Code - OSS settings match the **active** theme right away | Runs the theme-set hook once for `~/.local/state/omarchy/current/theme.name`; a no-op with no active theme |
| *(end)* | `hyprctl reload`; with `--sync`, `omarchy-update` | |

### What it deliberately leaves alone

- The **login shell** — no `chsh`. zsh runs inside kitty only; `~/.zshrc` sources Omarchy's own `envs`/`aliases`, so its updates flow through.
- The body of `~/.config/kitty/kitty.conf`, `~/.bashrc`, `/usr/share/omarchy`, and everything under `/etc` except the Firefox policy.
- The **active theme**, the **active `monitors.lua`**, and every set-once choice (font, default apps, clock, workspaces) after the first run — change them with Omarchy's own commands and hyprconf will not take them back.
- Omarchy's keyboard layout logic in `input.lua`, and its volume / brightness / media keys, `SUPER+D` (menu) and `SUPER+K` (keybindings menu).

## Sync

```bash
hyprsync            # = bash ~/.hyprconf/install.sh --sync
bash install.sh     # after any `omarchy refresh` or when you just want to re-apply
```

- **After `omarchy-update`** the post-update hook re-applies the overlay automatically (Omarchy migrations replace `bindings.lua` when it hash-matches stock and strip the kitty `include`).
- **`omarchy refresh config hypr/<file>` / `omarchy refresh hyprland` write *through* the symlinks** into the checkout (`cp -f` follows links — observed on Omarchy 4.0.0). `install.sh` detects a `hypr/*.lua` that is byte-identical to Omarchy's stock template and restores it with `git checkout`; a monitor preset reset to the stock `monitors.lua` template is reported, with the pointer to Omarchy's own `monitors.lua.bak.<epoch>` backup of your edits.
- **Edit workflow:** the files in `~/.hyprconf/hypr/` *are* the live files — edit them there, then `bash install.sh` (or `hyprsync`) after a pull or a refresh.

## Repository layout

| Path | Purpose |
|---|---|
| `install.sh` | The overlay installer — idempotent stages, the only entry point |
| `packages` | Official-repo packages added via `omarchy-pkg-add` |
| `hypr/` | `bindings.lua`, `input.lua`, `looknfeel.lua` (symlinked over Omarchy's override points); `pcMonitors.*.lua` / `laptopMonitors.lua` presets; `hyprland.block.lua` (managed block for `hyprland.lua`); `scripts/switch_monitor.sh`, `scripts/adjust-gaps` |
| `bin/` | `hyprconf` (TUI launcher), `hyprconf-stats`, `hyprconf-gpu-info` (bar-widget feeders) |
| `lib/hyprconf/` | The Python library (schema, config, keybinds, rules, monitors, hyprctl, file_edit, lua_syntax, paths …) — symlinked to `~/.local/lib/hyprconf` |
| `tui/main.py` | The Textual TUI |
| `plugins/hyprconf-resources/` | Omarchy bar-widget plugin (QML): resource readout |
| `plugins/hyprconf-workspaces/` | Omarchy bar-widget plugin (QML): workspaces, replaces `omarchy.workspaces` |
| `themes/hyprconf/` | Omarchy user theme (`colors.toml` + background) |
| `wallpapers/` | Extra backgrounds, filed under the Omarchy theme each belongs to |
| `zsh/`, `kitty/`, `fastfetch/` | `zshrc.block` + `.p10k.zsh`; `hyprconf.conf` kitty include; `config.jsonc` |
| `hooks/post-update.d/10-hyprconf` | Omarchy post-update hook |
| `infra/firefox/policies.json` | System Firefox privacy policy |
| `tests/` | Tiers 1 unit / 2 integration / 3 TUI — hermetic, run in an `archlinux:latest` container in CI |
| `docs/`, `AGENTS.md`, `.github/` | Contributor docs, agent rules, CI |
| `scripts/publish` | Promotes `omarchy` → `stable` |
| `web/`, `assets/` | Static landing page (S3, managed manually); banner + screenshot |

## The `hyprconf` TUI

`SUPER+D` → Apps → hyprconf, or `hyprconf` in a terminal.

```bash
hyprconf                     # full TUI
hyprconf --section general   # open at a section (sidebar hidden)
hyprconf --slim              # hide the sidebar
```

| Section | Edits | Persists to | Live apply |
|---|---|---|---|
| Hyprland options (`general`, `decoration`, `animations`, `input`, `gestures`, `group`, `misc`, `layout`, `binds`, `cursor`, `render`, `opengl`, `xwayland`, `dwindle`, `master`, `scrolling`, `ecosystem`, `experimental`, `quirks`, `debug` and their subsections) | Schema-driven pickers and sliders | `~/.config/hypr/conf.d/local.lua` | `hyprctl eval` (`hl.config`) |
| `keybinds` | `o.bind` / `rebind` / `hl.bind` entries with descriptions; new binds are written as `o.bind` so they appear in `SUPER+K` | `~/.config/hypr/bindings.lua` | `hyprctl reload` |
| `window_rules`, `workspace_rules` | One `hl.window_rule` / `hl.workspace_rule` per line | `~/.config/hypr/conf.d/windowrules.lua`, `workspacerules.lua` | `hyprctl reload` |
| `monitors` | Output, mode, position, scale …; `ctrl+s` applies from anywhere in the editor | `~/.config/hypr/monitors.lua` (a symlink to the active preset after a hotkey switch) | `hyprctl eval` (`hl.monitor`) |
| `theme` | Pick an Omarchy theme | — | `omarchy-theme-list` / `-current` / `-set` |
| `background` | Backgrounds of the active theme | — | `omarchy-theme-bg-set` |
| `idle` | Screensaver / lock timeouts; stay-awake toggle | `idle` block of `~/.config/omarchy/shell.json` | `omarchy-shell shell reloadConfig`; `omarchy-toggle-idle` |

`hyprctl keyword` is a silent no-op on Hyprland 0.56's Lua parser, which is why live apply goes through `hyprctl eval`. The `conf.d/*.lua` files are loaded by the managed block `install.sh` appends to `~/.config/hypr/hyprland.lua`.

## Monitor presets

| Preset | File | Hotkey |
|---|---|---|
| `bedroom` | `~/.config/hypr/pcMonitors.bedroom.lua` | `SUPER+SHIFT+B` |
| `kitchen` | `~/.config/hypr/pcMonitors.kitchen.lua` | `SUPER+SHIFT+K` |
| `K` | `~/.config/hypr/pcMonitors.K.lua` | — |
| `pc` | `~/.config/hypr/pcMonitors.lua` | — |
| `laptop` | `~/.config/hypr/laptopMonitors.lua` | — |
| `stock` (or `omarchy`) | `~/.config/hypr/monitors.lua.stock` | — |

```bash
~/.config/hypr/scripts/switch_monitor.sh <preset>
```

`switch_monitor.sh` snapshots the live `monitors.lua` to `monitors.lua.stock`, symlinks the preset over `monitors.lua`, runs `hyprctl reload`, then walks the preset's `hl.workspace_rule` lines and moves each existing workspace to its monitor (a reload only places *future* workspaces). Dark outputs get a `dpms` wake retry. Feedback goes through `omarchy-osd` and `omarchy-notification-send`. `stock` restores Omarchy's own layout as a real file. Each preset carries its workspace-to-monitor rules, and edits to a preset survive re-selecting it.

## Bar widgets

| Plugin id | What | Revert |
|---|---|---|
| `hyprconf.clock` | Copy of `omarchy.clock` sampling at `SystemClock.Seconds`, format `hh:mm:ss AP` | `omarchy plugin disable hyprconf.clock` |
| `hyprconf.workspaces` | The overlay's own workspaces widget: only workspaces that exist (no fixed 1–5 pills, no id cap), stacked on two lines like the resources widget, hyprconf's Pac-Man (`󰮯`) on the focused workspace; click focuses | `omarchy plugin disable hyprconf.workspaces` |
| `hyprconf.resources` | Two-line CPU % + temp / GPU, memory / net readout fed by `hyprconf-stats` and `hyprconf-gpu-info` (long-lived JSON streams); click opens `btop` via `omarchy-launch-or-focus-tui` | `omarchy plugin disable hyprconf.resources` |
| `omarchy.active-window` | Omarchy's stock focused-window title (elided; hover for the full title; click focuses, middle-click closes), enabled after the workspaces the way hyprconf's bar drew it; width via `omarchy bar set omarchy.active-window maxWidth 400` | `omarchy plugin disable omarchy.active-window` |

The clock copy is set once, and every widget is *enabled* once — disabling any of them sticks. The two plugins the overlay ships (`plugins/hyprconf-*`) are re-synced on every run, so a `git pull` updates them. `omarchy bar set hyprconf.clock format 'HH:mm'` reformats the clock.

## Keybindings

`mainMod` is `SUPER`. Everything below is bound with `o.bind` (Omarchy's helper, which records the description for `SUPER+K`); keys hyprconf takes over are unbound first, including Omarchy's keycode-form binds (`code:10…21`), so only one binding fires.

### Applications

| Key | Action |
|---|---|
| `SUPER+T` | Terminal (`omarchy-launch-terminal` — follows `omarchy default terminal`) |
| `SUPER+F` | Browser (`omarchy-launch-browser`) |
| `SUPER+C` | Editor (`omarchy-launch-editor`) |
| `SUPER+E` | File manager (`omarchy-launch-nautilus`) |
| `SUPER+D` | Omarchy menu (`omarchy-menu toggle`) — left on Omarchy |

### Windows

| Key | Action |
|---|---|
| `SUPER+Q` | Close window |
| `SUPER+SHIFT+Q` | Log out (`omarchy-system-logout`) |
| `SUPER+V` / `SUPER+SHIFT+SPACE` | Toggle window floating |
| `SUPER+P` | Pseudo window |
| `SUPER+SHIFT+F` | Full screen |
| `SUPER+← → ↑ ↓` | Focus left / right / above / below |
| `SUPER+SHIFT+← → ↑ ↓` | Shrink/expand window (repeating) |
| `SUPER+SHIFT+A / D / W / S` | Swap window left / right / up / down |
| `SUPER+SHIFT+=` / `SUPER+SHIFT+-` | Increase / decrease window gaps (`adjust-gaps`) |
| `SUPER+LMB drag` / `SUPER+RMB drag` | Move / resize window |

### Workspaces

| Key | Action |
|---|---|
| `SUPER+1, 2, 5–0` | Switch to workspace 1, 2, 5–10 |
| `SUPER+F1` / `SUPER+F2` | Switch to workspace 3 / 4 |
| `SUPER+SHIFT+1, 2, 5–0` | Move window to workspace 1, 2, 5–10 |
| `SUPER+SHIFT+F1` / `SUPER+SHIFT+F2` | Move window to workspace 3 / 4 |
| `SUPER+3` / `SUPER+4` | Left to Omarchy (workspace 3 / 4) |
| `SUPER+M` / `SUPER+SHIFT+M` | Toggle magic scratchpad / move window to it |
| `SUPER+scroll` | Scroll workspace forward / backward |

### System

| Key | Action |
|---|---|
| `SUPER+L` / `SUPER+SHIFT+Escape` | Lock system (`omarchy-system-lock`) |
| `SUPER+SHIFT+4` | Screenshot region (`omarchy-capture-screenshot region`) |
| `SUPER+SHIFT+V` | Clipboard history (`omarchy-menu-clipboard`) |
| `SUPER+SHIFT+BACKSPACE` | Toggle laptop display (`omarchy-hyprland-monitor-internal toggle`) |
| `SUPER+SHIFT+B` / `SUPER+SHIFT+K` | Monitor preset bedroom / kitchen |

**Left to Omarchy on purpose:** volume, brightness and media keys (Omarchy's drive its OSD and media service), `SUPER+D`, `SUPER+K`, `SUPER+3`/`4`. `SUPER+L` displaces Omarchy's layout toggle (still `omarchy-hyprland-workspace-layout-toggle`) and `SUPER+SHIFT+BACKSPACE` its gaps toggle (still `omarchy hyprland window gaps toggle`).

## Look'n'feel and input deltas

Only what differs from `/usr/share/omarchy/default/hypr/`:

| File | Setting | hyprconf | Omarchy |
|---|---|---|---|
| `looknfeel.lua` | `general.gaps_in` / `gaps_out` | 3 / 3 | 5 / 10 |
| | `decoration.rounding` / `rounding_power` | 1 / 3 | 0 |
| | `decoration.inactive_opacity` | 0.8 | 1 |
| | `decoration.shadow` | on (range 4, power 3) | off |
| | `decoration.blur` | on (size 3, passes 4, vibrancy 0.1696) | off |
| | animations | `windows` easeOutQuint 4.79; `workspaces`/`In`/`Out` fade | workspaces animation off |
| | `dwindle.force_split` / `precise_mouse_move` / `smart_split` | 0 / true / true | 2 / – / – |
| | `misc.force_default_wallpaper` | 0 | – |
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
| `firefox`, `code` | `SUPER+F`, `SUPER+C` |
| `python-textual` | The TUI |

## zsh

The `~/.zshrc` managed block (`# >>> hyprconf >>>` … `# <<< hyprconf <<<`, source `zsh/zshrc.block`) sources Omarchy's `default/bash/{env-bootstrap,envs,aliases}`, initialises `zoxide` (Omarchy aliases `cd` to it), loads Oh My Zsh with the `powerlevel10k` theme and `~/.p10k.zsh`, `zsh-autosuggestions`, the `hyprsync` alias, a `fastfetch` greeting, and `zsh-syntax-highlighting` last. Everything outside the markers is preserved.

## Theme → Firefox and VS Code

Omarchy's `omarchy theme set` fans the theme out to kitty, btop, VS Code (Microsoft build, Insiders, VSCodium, Cursor) and Chromium-family browsers — not to Arch's `code` package (Code - OSS reads `~/.config/Code - OSS/User/settings.json` and `~/.vscode-oss/extensions`, which Omarchy maps to `codium`) and not to Firefox at all (`omarchy-theme-set-browser` writes a Chromium policy colour). The overlay's `theme-set.d/10-hyprconf` hook runs after every theme switch (Omarchy calls `omarchy-hook theme-set <name>` at the end of `omarchy-theme-set`) and closes both gaps:

| App | How | Notes |
|---|---|---|
| Code - OSS (`code`) | Omarchy's own `set_theme` from `omarchy-theme-set-vscode`, re-run with Code - OSS's paths | Live. A theme whose extension is not on Open VSX falls back to Omarchy's generated **Omarchy** theme. `omarchy toggle skip-vscode-theme-changes` turns it off, as for Omarchy's own editors |
| Firefox / LibreWolf | `lib/hyprconf/firefox_theme.py` writes `chrome/userChrome.css` (Firefox's `--lwt-*`/`--toolbar-*` theme variables, from Omarchy's rendered `colors.toml`) and merges four prefs into `user.js` (stylesheet loading, `ui.systemUsesDarkTheme`, light/dark chrome+content) in the default profile | Takes effect on the next Firefox start — Firefox reads `userChrome.css` only at startup. Nothing else in `user.js` is touched |

Undo: delete `~/.config/omarchy/hooks/theme-set.d/10-hyprconf`, the profile's `chrome/userChrome.css`, and the four `user_pref` lines it added; run `omarchy theme set` again for VS Code.

## Reverting to stock

```bash
omarchy plugin disable hyprconf.clock
omarchy plugin disable hyprconf.workspaces
omarchy plugin disable hyprconf.resources
omarchy plugin disable omarchy.active-window
~/.config/hypr/scripts/switch_monitor.sh stock
rm ~/.config/hypr/{bindings,input,looknfeel}.lua && omarchy refresh hyprland  # or mv the .stock files back
rm ~/.config/omarchy/hooks/post-update.d/10-hyprconf
sed -i '/^include hyprconf.conf$/d' ~/.config/kitty/kitty.conf
omarchy default terminal <name>; omarchy font set <name>; omarchy theme set <name>
sudo rm /etc/firefox/policies/policies.json
```

Then delete the managed blocks from `~/.zshrc` and `~/.config/hypr/hyprland.lua`, and `~/.hyprconf`.

## Testing & development

```bash
make test        # tiers 1-3: unit, integration, TUI (hermetic — no Hyprland, no host tools)
make lint        # ruff check + format check
make shellcheck  # every bash script, severity=warning
```

CI (`.github/workflows/test.yml`) runs the same three jobs in an `archlinux:latest` container on every push. See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for the test tree, coverage and the publish flow, and [`AGENTS.md`](AGENTS.md) for the rules that bind every change.
