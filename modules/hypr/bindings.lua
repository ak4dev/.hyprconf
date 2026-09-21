-- hyprconf hotkey overlay for Omarchy: ~/.config/hypr/bindings.lua, require'd
-- after Omarchy's own bindings (config/hypr/hyprland.lua:21), so only the keys
-- hyprconf takes over appear here — each unbound first (Hyprland does not
-- replace a bind on a repeat of the same combo; both would fire), then
-- rebound. Every other key keeps Omarchy's default.

local mainMod = "SUPER"

-- No app names here: `{ omarchy = "terminal" }` is whatever Omarchy's default
-- says (the idiom: README.md in this folder).

-- Omarchy declares the digits and -/= by KEYCODE (`SUPER + SHIFT + code:20`,
-- default/hypr/bindings/tiling.lua:20-25 and :52-55), which hl.unbind of the
-- keysym does not match — both binds would fire. US-layout codes; the unbind
-- below fires only for a key this file actually rebinds.
local KEYCODE = { ["1"] = 10, ["2"] = 11, ["3"] = 12, ["4"] = 13, ["5"] = 14,
                  ["6"] = 15, ["7"] = 16, ["8"] = 17, ["9"] = 18, ["0"] = 19,
                  minus = 20, equal = 21 }

-- o.bind, never hl.bind: only o.bind records the description Omarchy's
-- keybindings menu (SUPER+K) lists (default/hypr/helpers.lua:92-105).
local function rebind(keys, description, dispatcher, options)
  hl.unbind(keys)
  local mods, key = keys:match("^(.*) %+ ([^+]+)$")
  local code = KEYCODE[key or keys]
  if code then hl.unbind(mods and (mods .. " + code:" .. code) or ("code:" .. code)) end
  o.bind(keys, description, dispatcher, options)
end

rebind(mainMod .. " + T", "Terminal", { omarchy = "terminal" })
rebind(mainMod .. " + Q", "Close window", hl.dsp.window.close())
-- Omarchy's logout: its OSD, a real close request to every window, `uwsm stop`.
rebind(mainMod .. " + SHIFT + Q", "Log out", "omarchy-system-logout")
rebind(mainMod .. " + E", "File manager", { omarchy = "nautilus" })
rebind(mainMod .. " + V", "Toggle window floating", hl.dsp.window.float({ action = "toggle" }))
rebind(mainMod .. " + F", "Browser", { omarchy = "browser" })
rebind(mainMod .. " + C", "Editor", { omarchy = "editor" })
rebind(mainMod .. " + SHIFT + B", "Monitor preset: bedroom", "hyprconf-monitor-preset bedroom")
rebind(mainMod .. " + SHIFT + K", "Monitor preset: kitchen", "hyprconf-monitor-preset kitchen")

-- SUPER+D: Omarchy's own menu (its menu key is SUPER+SPACE; it binds nothing here).
rebind(mainMod .. " + D", "Omarchy menu", "omarchy-menu toggle")

-- Resize active window. `relative = true` is load-bearing: without it x/y are
-- an EXACT target size and a negative one is `error: Invalid size` — every
-- press resized nothing. Omarchy's own resize binds pass it too.
rebind(mainMod .. " + SHIFT + left",  "Shrink window left", hl.dsp.window.resize({ x = -40, y = 0, relative = true }),  { repeating = true })
rebind(mainMod .. " + SHIFT + right", "Expand window right", hl.dsp.window.resize({ x = 40,  y = 0, relative = true }),  { repeating = true })
rebind(mainMod .. " + SHIFT + up",    "Shrink window up", hl.dsp.window.resize({ x = 0,   y = -40, relative = true }), { repeating = true })
rebind(mainMod .. " + SHIFT + down",  "Expand window down", hl.dsp.window.resize({ x = 0,   y = 40, relative = true }),  { repeating = true })

-- Adjust window gaps (inner + outer, proportionate); the tool ships beside
-- this file. Omarchy binds these two keys by keycode to window resizing.
rebind(mainMod .. " + SHIFT + equal", "Increase window gaps", "hyprconf-gaps +")
rebind(mainMod .. " + SHIFT + minus", "Decrease window gaps", "hyprconf-gaps -")

-- Switch workspaces with mainMod + [0-9]; move the active window with
-- mainMod + SHIFT + [0-9]. Workspaces 3 and 4 sit on F1/F2, so SUPER+3 and
-- SUPER+4 keep Omarchy's binds. The loop is the shape Omarchy's own
-- tiling.lua:20-25 uses for the same ten keys.
for _, entry in ipairs({ { "1", 1 }, { "2", 2 }, { "F1", 3 }, { "F2", 4 }, { "5", 5 },
                         { "6", 6 }, { "7", 7 }, { "8", 8 }, { "9", 9 }, { "0", 10 } }) do
  local key, ws = entry[1], entry[2]
  rebind(mainMod .. " + " .. key, "Switch to workspace " .. ws, hl.dsp.focus({ workspace = ws }))
  rebind(mainMod .. " + SHIFT + " .. key, "Move window to workspace " .. ws, hl.dsp.window.move({ workspace = ws }))
end

rebind(mainMod .. " + SHIFT + SPACE", "Toggle window floating", hl.dsp.window.float({ action = "toggle" }))
rebind(mainMod .. " + SHIFT + F",     "Full screen", hl.dsp.window.fullscreen())

-- Move, not swap: move also carries the window to the next monitor, which
-- swap refuses.
rebind(mainMod .. " + SHIFT + A", "Move window left", hl.dsp.window.move({ direction = "left" }))
rebind(mainMod .. " + SHIFT + D", "Move window right", hl.dsp.window.move({ direction = "right" }))
rebind(mainMod .. " + SHIFT + W", "Move window up", hl.dsp.window.move({ direction = "up" }))
rebind(mainMod .. " + SHIFT + S", "Move window down", hl.dsp.window.move({ direction = "down" }))

rebind(mainMod .. " + M",         "Toggle magic scratchpad", hl.dsp.workspace.toggle_special("magic"))
rebind(mainMod .. " + SHIFT + M", "Move window to magic scratchpad", hl.dsp.window.move({ workspace = "special:magic" }))

-- Volume, brightness and media keys stay Omarchy's on purpose: its commands
-- end by raising its OSD (bin/omarchy-audio-output-volume:86,
-- bin/omarchy-brightness-display:87) and drive the shell's own media service.

-- Clipboard history: Omarchy's overlay (never omarchy-clipboard-open — the hidden --history-index callback, which run bare exits 1 silently).
rebind(mainMod .. " + SHIFT + V", "Clipboard history", "omarchy-menu-clipboard")

-- Screenshots through Omarchy's own capture (frozen pick, click-to-edit, no
-- software cursor in the frame, a second press cancels). The keycode unbind
-- rebind() does is load-bearing here: Omarchy's move-to-workspace-4 is
-- SUPER+SHIFT+code:13, and without it the shot was of workspace 4.
rebind(mainMod .. " + SHIFT + 4", "Screenshot region", "omarchy-capture-screenshot region")

-- Screen lock through Omarchy's own (a Quickshell session lock, reachable only over IPC); SUPER+L displaces "Toggle workspace layout" (tiling.lua:13), still omarchy-hyprland-workspace-layout-toggle.
rebind(mainMod .. " + L",              "Lock system", "omarchy-system-lock")
rebind(mainMod .. " + SHIFT + Escape", "Lock system", "omarchy-system-lock")

-- The built-in laptop display through Omarchy's own toggle (refuses to disable the only active display); displaces "Toggle window gaps" (utilities.lua:20), still omarchy-hyprland-window-gaps-toggle.
rebind(mainMod .. " + SHIFT + BACKSPACE", "Toggle laptop display", "omarchy-hyprland-monitor-internal toggle")
