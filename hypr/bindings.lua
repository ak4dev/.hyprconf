-- hyprconf hotkey overlay for Omarchy.
--
-- Ported from the keybinds.lua of hyprconf's retired standalone desktop, adapted
-- to live inside Omarchy's bindings.lua override point (loaded after
-- Omarchy's own defaults, per ~/.config/hypr/hyprland.lua). Every key
-- hyprconf also binds is unbound first (Hyprland does not replace a bind on
-- a repeat `hl.bind` to the same combo — both would fire), then rebound to
-- hyprconf's target, so hotkeys not touched here keep Omarchy's own default.
--
-- Two deliberate exceptions, per the porting plan:
--   * SUPER+D stays on Omarchy's own menu, not hyprconf's hyprlauncher.
--   * The app keys (T/E/F/C) launch through Omarchy's launchers, which resolve
--     the user's defaults, rather than naming binaries. hyprconf's dolphin
--     would have dragged a chunk of KDE onto an Omarchy system anyway.
--   * SUPER+SHIFT+V (clipboard) is repointed at omarchy-menu-clipboard,
--     since hyprconf's version shells out to hyprlauncher --dmenu, which
--     isn't installed here.
--
-- NOT ported: SUPER+SHIFT+C / SUPER+SHIFT+N (hyprconf's calendar / control
-- center popouts). Both call hyprconf's own quickshell bar IPC
-- (~/.config/quickshell/launch.sh), which has no equivalent under Omarchy's
-- shell without porting hyprconf's bar itself (see plugins/ for the
-- one piece of that, the resource-usage widget, that has been ported).

local mainMod = "SUPER"

-- No app names here. Which terminal, browser and editor these keys open is an
-- Omarchy DEFAULT (~/.local/state/omarchy/defaults/*, and XDG for the browser),
-- seeded once by install.sh to hyprconf's picks — kitty, firefox, code
-- — and owned by the user from then on. `omarchy default browser zen` and the
-- key follows, which is the entire point of going through the launchers.
--
-- The launchers do more than exec the binary, too: omarchy-launch-terminal
-- opens in the active terminal's working directory (what Omarchy's own
-- SUPER+RETURN does), and every one of them goes through `uwsm-app` so the app
-- lands in its own systemd scope rather than as a child of the compositor.

-- Every hyprconf key goes through o.bind, Omarchy's own binding helper, rather
-- than hl.bind. The difference is the description: o.bind records one, and
-- that is what Omarchy's keybindings menu (SUPER+K) lists. Bound with hl.bind,
-- hyprconf's whole keymap was invisible there — the menu showed only the
-- Omarchy defaults hyprconf had replaced, which is worse than showing nothing.
local function rebind(keys, description, dispatcher, options)
  hl.unbind(keys)
  o.bind(keys, description, dispatcher, options)
end

-- Omarchy declares a chunk of its bindings by KEYCODE rather than keysym
-- (`o.bind("SUPER + SHIFT + code:20", …)` in default/hypr/bindings/tiling.lua),
-- and hl.unbind only matches what was actually declared. Unbinding the keysym
-- therefore leaves Omarchy's keycode bind live and BOTH fire on the same press.
-- The collisions on a US layout:
--   code:20 / code:21  = minus / equal  (Omarchy: shrink/expand window)
--   code:10 … code:19  = 1 … 0          (Omarchy: switch/move workspace)
-- "4" is here for the screenshot key, not for a workspace: hyprconf puts
-- workspace 4 on F2 but takes SUPER+SHIFT+4 for a region capture, and Omarchy
-- declares move-to-workspace-4 as SUPER+SHIFT+code:13. "3" is deliberately
-- absent — hyprconf binds nothing on SUPER+SHIFT+3, so Omarchy's belongs there.
local KEYCODE = { ["1"] = 10, ["2"] = 11, ["4"] = 13, ["5"] = 14, ["6"] = 15,
                  ["7"] = 16, ["8"] = 17, ["9"] = 18, ["0"] = 19,
                  minus = 20, equal = 21 }

local function unbind_keycode(mods, key)
  local code = KEYCODE[key]
  if code then hl.unbind(mods .. " + code:" .. code) end
end

rebind(mainMod .. " + T", "Terminal", hl.dsp.exec_cmd("omarchy-launch-terminal"))
rebind(mainMod .. " + Q", "Close window", hl.dsp.window.close())
-- Log out through Omarchy's command rather than the bare exit dispatcher: it
-- draws the logout OSD, sends every window a real close request first
-- (omarchy-hyprland-window-close-all) and stops the session with `uwsm stop`
-- instead of killing the compositor out from under it.
hl.unbind(mainMod .. " + SHIFT + Q")
o.bind(mainMod .. " + SHIFT + Q", "Log out", "omarchy-system-logout")
rebind(mainMod .. " + E", "File manager", hl.dsp.exec_cmd("omarchy-launch-nautilus"))
rebind(mainMod .. " + V", "Toggle window floating", hl.dsp.window.float({ action = "toggle" }))
rebind(mainMod .. " + P", "Pseudo window", hl.dsp.window.pseudo())
rebind(mainMod .. " + F", "Browser", hl.dsp.exec_cmd("omarchy-launch-browser"))
rebind(mainMod .. " + C", "Editor", hl.dsp.exec_cmd("omarchy-launch-editor"))
-- Monitor presets. o.bind rather than hl.bind so they carry a description and
-- turn up in Omarchy's keybindings menu (SUPER+K) instead of being invisible.
hl.unbind(mainMod .. " + SHIFT + B")
hl.unbind(mainMod .. " + SHIFT + K")
o.bind(mainMod .. " + SHIFT + B", "Monitor preset: bedroom", "~/.config/hypr/scripts/switch_monitor.sh bedroom")
o.bind(mainMod .. " + SHIFT + K", "Monitor preset: kitchen", "~/.config/hypr/scripts/switch_monitor.sh kitchen")

-- SUPER+D: Omarchy's own menu, not hyprconf's hyprlauncher.
hl.unbind(mainMod .. " + D")
o.bind(mainMod .. " + D", "Omarchy menu", "omarchy-menu toggle")

-- Move focus with mainMod + arrow keys
rebind(mainMod .. " + left",  "Focus left window", hl.dsp.focus({ direction = "left" }))
rebind(mainMod .. " + right", "Focus right window", hl.dsp.focus({ direction = "right" }))
rebind(mainMod .. " + up",    "Focus window above", hl.dsp.focus({ direction = "up" }))
rebind(mainMod .. " + down",  "Focus window below", hl.dsp.focus({ direction = "down" }))

-- Resize active window
rebind(mainMod .. " + SHIFT + left",  "Shrink window left", hl.dsp.window.resize({ x = -40, y = 0 }),  { repeating = true })
rebind(mainMod .. " + SHIFT + right", "Expand window right", hl.dsp.window.resize({ x = 40,  y = 0 }),  { repeating = true })
rebind(mainMod .. " + SHIFT + up",    "Shrink window up", hl.dsp.window.resize({ x = 0,   y = -40 }), { repeating = true })
rebind(mainMod .. " + SHIFT + down",  "Expand window down", hl.dsp.window.resize({ x = 0,   y = 40 }),  { repeating = true })

-- Adjust window gaps (inner + outer, proportionate). Omarchy binds these two
-- keys by keycode to vertical window resizing, so clear those first or every
-- press both resizes the window and moves the gaps.
unbind_keycode(mainMod .. " + SHIFT", "equal")
unbind_keycode(mainMod .. " + SHIFT", "minus")
rebind(mainMod .. " + SHIFT + equal", "Increase window gaps", hl.dsp.exec_cmd("~/.config/hypr/scripts/adjust-gaps +"))
rebind(mainMod .. " + SHIFT + minus", "Decrease window gaps", hl.dsp.exec_cmd("~/.config/hypr/scripts/adjust-gaps -"))

-- Switch workspaces with mainMod + [0-9]; move the active window with
-- mainMod + SHIFT + [0-9]. Workspaces 3 and 4 sit on F1/F2, as hyprconf's
-- keymap always has. One bind per line on purpose: the file is edited by
-- hand, and a loop hides which keys are really bound behind a table.
--
-- Omarchy binds SUPER+code:10…19 / SUPER+SHIFT+code:10…19 for workspaces
-- 1-10. Same destination as ours for the number keys, so the duplicate is
-- harmless in effect — but it doubles the bind table and hides which
-- binding is really in force. SUPER+3 / SUPER+4 are deliberately left
-- alone: hyprconf puts workspaces 3 and 4 on F1/F2 and binds neither
-- number, so Omarchy's are the only thing on those keys.
unbind_keycode(mainMod, "1")
unbind_keycode(mainMod .. " + SHIFT", "1")
rebind(mainMod .. " + 1",          "Switch to workspace 1", hl.dsp.focus({ workspace = 1 }))
rebind(mainMod .. " + SHIFT + 1",  "Move window to workspace 1", hl.dsp.window.move({ workspace = 1 }))
unbind_keycode(mainMod, "2")
unbind_keycode(mainMod .. " + SHIFT", "2")
rebind(mainMod .. " + 2",          "Switch to workspace 2", hl.dsp.focus({ workspace = 2 }))
rebind(mainMod .. " + SHIFT + 2",  "Move window to workspace 2", hl.dsp.window.move({ workspace = 2 }))
rebind(mainMod .. " + F1",         "Switch to workspace 3", hl.dsp.focus({ workspace = 3 }))
rebind(mainMod .. " + SHIFT + F1", "Move window to workspace 3", hl.dsp.window.move({ workspace = 3 }))
rebind(mainMod .. " + F2",         "Switch to workspace 4", hl.dsp.focus({ workspace = 4 }))
rebind(mainMod .. " + SHIFT + F2", "Move window to workspace 4", hl.dsp.window.move({ workspace = 4 }))
unbind_keycode(mainMod, "5")
unbind_keycode(mainMod .. " + SHIFT", "5")
rebind(mainMod .. " + 5",          "Switch to workspace 5", hl.dsp.focus({ workspace = 5 }))
rebind(mainMod .. " + SHIFT + 5",  "Move window to workspace 5", hl.dsp.window.move({ workspace = 5 }))
unbind_keycode(mainMod, "6")
unbind_keycode(mainMod .. " + SHIFT", "6")
rebind(mainMod .. " + 6",          "Switch to workspace 6", hl.dsp.focus({ workspace = 6 }))
rebind(mainMod .. " + SHIFT + 6",  "Move window to workspace 6", hl.dsp.window.move({ workspace = 6 }))
unbind_keycode(mainMod, "7")
unbind_keycode(mainMod .. " + SHIFT", "7")
rebind(mainMod .. " + 7",          "Switch to workspace 7", hl.dsp.focus({ workspace = 7 }))
rebind(mainMod .. " + SHIFT + 7",  "Move window to workspace 7", hl.dsp.window.move({ workspace = 7 }))
unbind_keycode(mainMod, "8")
unbind_keycode(mainMod .. " + SHIFT", "8")
rebind(mainMod .. " + 8",          "Switch to workspace 8", hl.dsp.focus({ workspace = 8 }))
rebind(mainMod .. " + SHIFT + 8",  "Move window to workspace 8", hl.dsp.window.move({ workspace = 8 }))
unbind_keycode(mainMod, "9")
unbind_keycode(mainMod .. " + SHIFT", "9")
rebind(mainMod .. " + 9",          "Switch to workspace 9", hl.dsp.focus({ workspace = 9 }))
rebind(mainMod .. " + SHIFT + 9",  "Move window to workspace 9", hl.dsp.window.move({ workspace = 9 }))
unbind_keycode(mainMod, "0")
unbind_keycode(mainMod .. " + SHIFT", "0")
rebind(mainMod .. " + 0",          "Switch to workspace 10", hl.dsp.focus({ workspace = 10 }))
rebind(mainMod .. " + SHIFT + 0",  "Move window to workspace 10", hl.dsp.window.move({ workspace = 10 }))

rebind(mainMod .. " + SHIFT + SPACE", "Toggle window floating", hl.dsp.window.float({ action = "toggle" }))
rebind(mainMod .. " + SHIFT + F",     "Full screen", hl.dsp.window.fullscreen())

-- Swap window position
rebind(mainMod .. " + SHIFT + A", "Swap window left", hl.dsp.window.swap({ direction = "left" }))
rebind(mainMod .. " + SHIFT + D", "Swap window right", hl.dsp.window.swap({ direction = "right" }))
rebind(mainMod .. " + SHIFT + W", "Swap window up", hl.dsp.window.swap({ direction = "up" }))
rebind(mainMod .. " + SHIFT + S", "Swap window down", hl.dsp.window.swap({ direction = "down" }))

-- Special workspace (scratchpad)
rebind(mainMod .. " + M",         "Toggle magic scratchpad", hl.dsp.workspace.toggle_special("magic"))
rebind(mainMod .. " + SHIFT + M", "Move window to magic scratchpad", hl.dsp.window.move({ workspace = "special:magic" }))

-- Scroll through existing workspaces with mainMod + scroll
rebind(mainMod .. " + mouse_down", "Scroll workspace forward", hl.dsp.focus({ workspace = "e+1" }))
rebind(mainMod .. " + mouse_up",   "Scroll workspace backward", hl.dsp.focus({ workspace = "e-1" }))

-- Move/resize windows with mainMod + LMB/RMB and dragging
rebind(mainMod .. " + mouse:272", "Move window", hl.dsp.window.drag(),   { mouse = true })
rebind(mainMod .. " + mouse:273", "Resize window", hl.dsp.window.resize(), { mouse = true })

-- Volume and brightness are DELIBERATELY NOT REBOUND — Omarchy's own bindings
-- are left in place, and this is the one case where doing nothing is the fix.
--
-- hyprconf drove these keys through raw `wpctl` and `hyprconf-brightness`,
-- whose only job beyond the adjustment was reporting the new level to
-- hyprconf's quickshell OSD. That OSD does not exist here, so rebinding them
-- bought nothing and cost the on-screen indicator: Omarchy's own
-- `omarchy-audio-output-volume` and `omarchy-brightness-display` end by
-- calling `omarchy-osd`, which is the bottom-centre readout hyprconf used to
-- draw. Adjusting volume through wpctl changed the level with no feedback at
-- all, which is exactly what it looked like.
--
-- Omarchy's versions also match or beat hyprconf's on their own terms: the
-- same 5% step (omarchy-audio-output-volume: raise = +5), brightness that
-- follows the focused display over DDC rather than only the internal panel,
-- and ALT/SHIFT variants for precise and min/max steps that hyprconf never had.

-- Media keys are NOT rebound either, for the same reason as volume: Omarchy
-- binds them to "omarchy-shell media next|playPause|previous", which drives the
-- shell's own media service — the bar's media widget, its source selection and
-- its OSD all follow from that. hyprconf's `playerctl next` talks to MPRIS
-- directly, so it moved the track while leaving Omarchy's shell unaware of it.
--
-- Leaving them alone also keeps the variants hyprconf never had:
-- SHIFT+XF86AudioPlay switches media source, ALT+XF86AudioPlay skips forward,
-- and XF86Eject is bound.

-- Clipboard history — Omarchy's own clipboard overlay (the omarchy.clipboard
-- shell plugin it binds to SUPER+CTRL+V), since hyprconf's version shells out
-- to hyprlauncher --dmenu, which isn't installed here.
--
-- NOT omarchy-clipboard-open: that is the hidden callback the overlay invokes
-- with --history-index to open an already-chosen entry. Run bare it fails its
-- argument check and exits 1 without printing anything, so this key did
-- nothing at all — while the keybindings menu advertised it as working.
hl.unbind(mainMod .. " + SHIFT + V")
o.bind(mainMod .. " + SHIFT + V", "Clipboard history", "omarchy-menu-clipboard")

-- Screenshots. Omarchy's own capture, not hyprshot: the freeze hyprconf's
-- `--freeze` asked for is still there (omarchy-capture-region runs
-- `hyprpicker -r -z`) and is held across grim rather than torn down the instant
-- slurp exits; it also restores the click-to-edit notification, keeps a
-- software cursor out of the frame, and makes a second press cancel the pick.
--
-- The keycode unbind is load-bearing: Omarchy declares move-to-workspace-4 as
-- SUPER+SHIFT+code:13, so without it BOTH fire — the press moved the focused
-- window to workspace 4 and followed it there before capturing, so the shot was
-- of workspace 4. hyprconf's own move-to-workspace-4 stays on SUPER+SHIFT+F2,
-- and plain SUPER+4 keeps Omarchy's workspace switch.
unbind_keycode(mainMod .. " + SHIFT", "4")
hl.unbind(mainMod .. " + SHIFT + 4")
o.bind(mainMod .. " + SHIFT + 4", "Screenshot region", "omarchy-capture-screenshot region")

-- Screen lock. NOT hyprconf's `loginctl lock-session`: that only emits logind's
-- Lock signal, which on hyprconf's own desktop was caught by hypridle's
-- lock_cmd and turned into hyprlock. Neither is installed under Omarchy, whose
-- lock is a Quickshell session-lock surface reachable only over IPC — so the
-- ported binding set LockedHint and left the screen unlocked.
--
-- omarchy-system-lock also resets the keyboard to layout 0, so a non-Latin
-- secondary layout cannot lock you out of your own password field, locks
-- 1Password, and stops the screensaver.
--
-- SUPER+L displaces Omarchy's "Toggle workspace layout", as hyprconf's keymap
-- intends; it stays available as omarchy-hyprland-workspace-layout-toggle.
hl.unbind(mainMod .. " + L")
o.bind(mainMod .. " + L",              "Lock system", "omarchy-system-lock")
o.bind(mainMod .. " + SHIFT + Escape", "Lock system", "omarchy-system-lock")

-- Toggle the built-in laptop display. Omarchy's own command, not hyprconf's
-- toggle-native-display script: that one drove `hyprctl keyword monitor`, which
-- Hyprland 0.56 answers with "keyword can't work with non-legacy parsers" and
-- an exit status of 0 — a silent no-op. Omarchy's version is also simply
-- better: it refuses to disable the only active display, persists the state as
-- a toggle flag so it survives a reload, and has a `recover` path for outputs
-- that come back dark. Bound through o.bind so it appears in the keybindings
-- menu (SUPER+K) with a description, the way Omarchy's own entries do.
--
-- This displaces Omarchy's "Toggle window gaps" from SUPER+SHIFT+BACKSPACE,
-- as hyprconf's keymap intends; that toggle is still available as
-- `omarchy hyprland window gaps toggle`.
hl.unbind(mainMod .. " + SHIFT + BACKSPACE")
o.bind(mainMod .. " + SHIFT + BACKSPACE", "Toggle laptop display", "omarchy-hyprland-monitor-internal toggle")
