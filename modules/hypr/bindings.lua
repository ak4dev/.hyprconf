-- hyprconf hotkey overlay for Omarchy: ~/.config/hypr/bindings.lua, require'd
-- after Omarchy's own bindings (config/hypr/hyprland.lua:21), so only the keys
-- hyprconf takes over appear here — each unbound first (Hyprland does not
-- replace a bind on a repeat of the same combo; both would fire), then
-- rebound. Every other key keeps Omarchy's default.

local mainMod = "SUPER"

-- No app names here: `{ omarchy = "terminal" }` is whatever Omarchy's default
-- says (the idiom: README.md in this folder).

-- Omarchy declares the digits and -/= by KEYCODE (`SUPER + SHIFT + code:20`,
-- default/hypr/bindings/tiling.lua:23-28 and :65-68), which hl.unbind of the
-- keysym does not match — both binds would fire. US-layout codes; the unbind
-- below fires only for a key this file actually rebinds.
local KEYCODE = { ["1"] = 10, ["2"] = 11, ["3"] = 12, ["4"] = 13, ["5"] = 14,
                  ["6"] = 15, ["7"] = 16, ["8"] = 17, ["9"] = 18, ["0"] = 19,
                  minus = 20, equal = 21 }

-- Omarchy's o.rebind (default/hypr/helpers.lua:154-157) unbinds the keysym and
-- goes through o.bind, never hl.bind: only o.bind records the description the
-- keybindings menu (SUPER+K) lists (:138-152). The keycode form is cleared here.
local function rebind(keys, ...)
  local mods, key = keys:match("^(.*) %+ ([^+]+)$")
  local code = KEYCODE[key or keys]
  if code then hl.unbind(mods and (mods .. " + code:" .. code) or ("code:" .. code)) end
  o.rebind(keys, ...)
end

rebind(mainMod .. " + T", "Terminal", { omarchy = "terminal" })
-- Omarchy's logout: its OSD, a real close request to every window, `uwsm stop`.
rebind(mainMod .. " + SHIFT + Q", "Log out", "omarchy-system logout")
rebind(mainMod .. " + E", "File manager", { omarchy = "nautilus" })
rebind(mainMod .. " + V", "Toggle window floating", hl.dsp.window.float({ action = "toggle" }))
rebind(mainMod .. " + F", "Browser", { omarchy = "browser" })
rebind(mainMod .. " + C", "Editor", { omarchy = "editor" })
rebind(mainMod .. " + SHIFT + B", "Monitor preset: bedroom", "hyprconf-monitor-preset bedroom")
rebind(mainMod .. " + SHIFT + K", "Monitor preset: kitchen", "hyprconf-monitor-preset kitchen")

-- SUPER+D: Omarchy's own menu, as its SUPER+SPACE opens it (bindings/utilities.lua:1; it binds nothing here).
rebind(mainMod .. " + D", "Omarchy menu", { menu = "root" })

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

-- Workspaces 3 and 4 also sit on F1/F2 — SUPER+SHIFT+4 is the screenshot below —
-- through Omarchy's own per-monitor slots, as its digit keys go (tiling.lua:23-28):
-- every monitor has workspaces 1-10 of its own (default/hypr/monitor-workspaces.lua).
for key, slot in pairs({ F1 = 3, F2 = 4 }) do
  rebind(mainMod .. " + " .. key, "Switch to workspace " .. slot, o.workspaces.focus(slot))
  rebind(mainMod .. " + SHIFT + " .. key, "Move window to workspace " .. slot, o.workspaces.move_window(slot))
end

rebind(mainMod .. " + SHIFT + SPACE", "Toggle window floating", hl.dsp.window.float({ action = "toggle" }))
rebind(mainMod .. " + SHIFT + F",     "Full screen", hl.dsp.window.fullscreen())

-- Move, not swap: move also carries the window to the next monitor, which
-- swap refuses.
rebind(mainMod .. " + SHIFT + A", "Move window left", hl.dsp.window.move({ direction = "left" }))
rebind(mainMod .. " + SHIFT + D", "Move window right", hl.dsp.window.move({ direction = "right" }))
rebind(mainMod .. " + SHIFT + W", "Move window up", hl.dsp.window.move({ direction = "up" }))
rebind(mainMod .. " + SHIFT + S", "Move window down", hl.dsp.window.move({ direction = "down" }))

-- SUPER+M displaces "Minimize window to the dock" (tiling.lua:33), still omarchy-hyprland-window-minimize.
rebind(mainMod .. " + M",         "Toggle magic scratchpad", hl.dsp.workspace.toggle_special("magic"))
rebind(mainMod .. " + SHIFT + M", "Move window to magic scratchpad", hl.dsp.window.move({ workspace = "special:magic" }))

-- Volume, brightness and media keys stay Omarchy's on purpose: they reach the
-- shell's own shortcuts (default/hypr/bindings/media.lua:2-7,29-33), which
-- raise its OSD and drive its media service.

-- Clipboard history: Omarchy's panel, as its SUPER+CTRL+V opens it (bindings/clipboard.lua:49).
rebind(mainMod .. " + SHIFT + V", "Clipboard history", { panel = "omarchy.clipboard" })

-- Screenshots through Omarchy's own capture (frozen pick, click-to-edit, no
-- software cursor in the frame, a second press cancels). The keycode unbind
-- rebind() does is load-bearing here: Omarchy's move-to-workspace-4 is
-- SUPER+SHIFT+code:13, and without it the shot was of workspace 4.
rebind(mainMod .. " + SHIFT + 4", "Screenshot region", "omarchy-capture-screenshot region")

-- Screen lock through Omarchy's own (a Quickshell session lock, reachable only over IPC); SUPER+L displaces "Cycle workspace layout" (tiling.lua:14), still omarchy-hyprland-workspace-layout-toggle.
rebind(mainMod .. " + L",              "Lock system", "omarchy-system-lock")
rebind(mainMod .. " + SHIFT + Escape", "Lock system", "omarchy-system-lock")

-- The built-in laptop display through Omarchy's own toggle (refuses to disable the only active display); displaces "Toggle window gaps" (utilities.lua:19), still omarchy-hyprland-window-gaps-toggle.
rebind(mainMod .. " + SHIFT + BACKSPACE", "Toggle laptop display", "omarchy-hyprland-monitor-internal toggle")
