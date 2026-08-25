-- hyprconf hotkey overlay for Omarchy: loaded by ~/.config/hypr/hyprland.lua
-- AFTER Omarchy's own bindings, so only the keys hyprconf takes over appear
-- here — each unbound first (Hyprland does not replace a bind on a repeat of
-- the same combo; both would fire), then rebound. Every other key keeps
-- Omarchy's default.

local mainMod = "SUPER"

-- No app names here: which terminal, browser and editor these keys open is an
-- Omarchy DEFAULT (`omarchy default browser zen` moves the key with it), and
-- the launchers add the cwd-inheriting terminal launch and uwsm-app scoping.
-- The launchers are named the way Omarchy's own bindings name them:
-- `{ omarchy = "terminal" }` is `omarchy-launch-terminal`
-- (default/hypr/helpers.lua, command_from; bindings/applications.lua).
-- hyprconf's own tools are bound by command name, like Omarchy's — install.sh
-- puts bin/hyprconf-* on ~/.local/bin, which is on the session PATH.

-- o.bind, never hl.bind: only o.bind records the description Omarchy's
-- keybindings menu (SUPER+K) lists.
local function rebind(keys, description, dispatcher, options)
  hl.unbind(keys)
  o.bind(keys, description, dispatcher, options)
end

-- Omarchy declares digits and -/= by KEYCODE (`SUPER + SHIFT + code:20` in
-- default/hypr/bindings/tiling.lua), which hl.unbind of the keysym does not
-- match — both would fire. US-layout codes; "3" is absent on purpose (nothing
-- here binds SUPER+SHIFT+3), "4" is for the screenshot key.
local KEYCODE = { ["1"] = 10, ["2"] = 11, ["4"] = 13, ["5"] = 14, ["6"] = 15,
                  ["7"] = 16, ["8"] = 17, ["9"] = 18, ["0"] = 19,
                  minus = 20, equal = 21 }

local function unbind_keycode(mods, key)
  local code = KEYCODE[key]
  if code then hl.unbind(mods .. " + code:" .. code) end
end

rebind(mainMod .. " + T", "Terminal", { omarchy = "terminal" })
rebind(mainMod .. " + Q", "Close window", hl.dsp.window.close())
-- Omarchy's logout: its OSD, a real close request to every window, `uwsm stop`.
hl.unbind(mainMod .. " + SHIFT + Q")
o.bind(mainMod .. " + SHIFT + Q", "Log out", "omarchy-system-logout")
rebind(mainMod .. " + E", "File manager", { omarchy = "nautilus" })
rebind(mainMod .. " + V", "Toggle window floating", hl.dsp.window.float({ action = "toggle" }))
rebind(mainMod .. " + F", "Browser", { omarchy = "browser" })
rebind(mainMod .. " + C", "Editor", { omarchy = "editor" })
-- Monitor presets (bin/hyprconf-monitor-preset).
hl.unbind(mainMod .. " + SHIFT + B")
hl.unbind(mainMod .. " + SHIFT + K")
o.bind(mainMod .. " + SHIFT + B", "Monitor preset: bedroom", "hyprconf-monitor-preset bedroom")
o.bind(mainMod .. " + SHIFT + K", "Monitor preset: kitchen", "hyprconf-monitor-preset kitchen")

-- SUPER+D: Omarchy's own menu (its menu key is SUPER+SPACE; it binds nothing here).
hl.unbind(mainMod .. " + D")
o.bind(mainMod .. " + D", "Omarchy menu", "omarchy-menu toggle")

-- SUPER+arrows (focus), SUPER+P (pseudo), SUPER+scroll (workspace scroll)
-- and SUPER+LMB/RMB drag (move/resize) are Omarchy's own binds already
-- (default/hypr/bindings/tiling.lua) and are not restated here.

-- Resize active window
rebind(mainMod .. " + SHIFT + left",  "Shrink window left", hl.dsp.window.resize({ x = -40, y = 0 }),  { repeating = true })
rebind(mainMod .. " + SHIFT + right", "Expand window right", hl.dsp.window.resize({ x = 40,  y = 0 }),  { repeating = true })
rebind(mainMod .. " + SHIFT + up",    "Shrink window up", hl.dsp.window.resize({ x = 0,   y = -40 }), { repeating = true })
rebind(mainMod .. " + SHIFT + down",  "Expand window down", hl.dsp.window.resize({ x = 0,   y = 40 }),  { repeating = true })

-- Adjust window gaps (inner + outer, proportionate). Omarchy binds these two
-- keys by keycode to window resizing: cleared first, or every press does both.
unbind_keycode(mainMod .. " + SHIFT", "equal")
unbind_keycode(mainMod .. " + SHIFT", "minus")
rebind(mainMod .. " + SHIFT + equal", "Increase window gaps", "hyprconf-gaps +")
rebind(mainMod .. " + SHIFT + minus", "Decrease window gaps", "hyprconf-gaps -")

-- Switch workspaces with mainMod + [0-9]; move the active window with
-- mainMod + SHIFT + [0-9]. Workspaces 3 and 4 sit on F1/F2; SUPER+3 / SUPER+4
-- keep Omarchy's binds. One bind per line on purpose (greppable, diffable),
-- Omarchy's keycode bind cleared first for every number hyprconf takes.
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

-- Volume, brightness and media keys stay Omarchy's on purpose: its commands
-- raise its OSD and drive the shell's own media service.

-- Clipboard history: Omarchy's overlay. NOT omarchy-clipboard-open — that is
-- the hidden --history-index callback, which run bare exits 1 silently.
hl.unbind(mainMod .. " + SHIFT + V")
o.bind(mainMod .. " + SHIFT + V", "Clipboard history", "omarchy-menu-clipboard")

-- Screenshots through Omarchy's own capture (frozen pick, click-to-edit, no
-- software cursor in the frame, a second press cancels). The keycode unbind
-- is load-bearing: Omarchy's move-to-workspace-4 is SUPER+SHIFT+code:13, and
-- without it the shot was of workspace 4.
unbind_keycode(mainMod .. " + SHIFT", "4")
hl.unbind(mainMod .. " + SHIFT + 4")
o.bind(mainMod .. " + SHIFT + 4", "Screenshot region", "omarchy-capture-screenshot region")

-- Screen lock through Omarchy's own (a Quickshell session lock reachable only
-- over IPC; `loginctl lock-session` only sets LockedHint here). SUPER+L
-- displaces Omarchy's "Toggle workspace layout", still available as
-- omarchy-hyprland-workspace-layout-toggle.
hl.unbind(mainMod .. " + L")
o.bind(mainMod .. " + L",              "Lock system", "omarchy-system-lock")
o.bind(mainMod .. " + SHIFT + Escape", "Lock system", "omarchy-system-lock")

-- Toggle the built-in laptop display through Omarchy's own command (refuses
-- to disable the only active display, persists as a toggle flag, has a
-- `recover` path). Displaces Omarchy's "Toggle window gaps", still available
-- as `omarchy hyprland window gaps toggle`.
hl.unbind(mainMod .. " + SHIFT + BACKSPACE")
o.bind(mainMod .. " + SHIFT + BACKSPACE", "Toggle laptop display", "omarchy-hyprland-monitor-internal toggle")
