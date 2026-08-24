-- hyprconf hotkey overlay for Omarchy.
--
-- Ported from ~/.hyprconf's own stow/hypr/.config/hypr/keybinds.lua, adapted
-- to live inside Omarchy's bindings.lua override point (loaded after
-- Omarchy's own defaults, per ~/.config/hypr/hyprland.lua). Every key
-- hyprconf also binds is unbound first (Hyprland does not replace a bind on
-- a repeat `hl.bind` to the same combo — both would fire), then rebound to
-- hyprconf's target, so hotkeys not touched here keep Omarchy's own default.
--
-- Two deliberate exceptions, per the porting plan:
--   * SUPER+D stays on Omarchy's own menu, not hyprconf's hyprlauncher.
--   * SUPER+SHIFT+V (clipboard) is repointed at omarchy-clipboard-open,
--     since hyprconf's version shells out to hyprlauncher --dmenu, which
--     isn't installed here.
--
-- NOT ported: SUPER+SHIFT+C / SUPER+SHIFT+N (hyprconf's calendar / control
-- center popouts). Both call hyprconf's own quickshell bar IPC
-- (~/.config/quickshell/launch.sh), which has no equivalent under Omarchy's
-- shell without porting hyprconf's bar itself (see omarchy/plugins/ for the
-- one piece of that, the resource-usage widget, that has been ported).

local mainMod = "SUPER"

local terminal    = "kitty"
local fileManager = "dolphin"
local browser     = "firefox"

local function rebind(keys, dispatcher, options)
  hl.unbind(keys)
  hl.bind(keys, dispatcher, options)
end

rebind(mainMod .. " + T", hl.dsp.exec_cmd(terminal))
rebind(mainMod .. " + Q", hl.dsp.window.close())
rebind(mainMod .. " + SHIFT + Q", hl.dsp.exit())
rebind(mainMod .. " + E", hl.dsp.exec_cmd(fileManager))
rebind(mainMod .. " + V", hl.dsp.window.float({ action = "toggle" }))
rebind(mainMod .. " + P", hl.dsp.window.pseudo())
rebind(mainMod .. " + F", hl.dsp.exec_cmd(browser))
rebind(mainMod .. " + C", hl.dsp.exec_cmd("code"))
rebind(mainMod .. " + SHIFT + B", hl.dsp.exec_cmd("~/.config/hypr/scripts/switch_monitor.sh bedroom"))
rebind(mainMod .. " + SHIFT + K", hl.dsp.exec_cmd("~/.config/hypr/scripts/switch_monitor.sh kitchen"))

-- SUPER+D: Omarchy's own menu, not hyprconf's hyprlauncher.
hl.unbind(mainMod .. " + D")
o.bind(mainMod .. " + D", "Omarchy menu", "omarchy-menu toggle")

-- Move focus with mainMod + arrow keys
rebind(mainMod .. " + left",  hl.dsp.focus({ direction = "left" }))
rebind(mainMod .. " + right", hl.dsp.focus({ direction = "right" }))
rebind(mainMod .. " + up",    hl.dsp.focus({ direction = "up" }))
rebind(mainMod .. " + down",  hl.dsp.focus({ direction = "down" }))

-- Resize active window
rebind(mainMod .. " + SHIFT + left",  hl.dsp.window.resize({ x = -40, y = 0 }),  { repeating = true })
rebind(mainMod .. " + SHIFT + right", hl.dsp.window.resize({ x = 40,  y = 0 }),  { repeating = true })
rebind(mainMod .. " + SHIFT + up",    hl.dsp.window.resize({ x = 0,   y = -40 }), { repeating = true })
rebind(mainMod .. " + SHIFT + down",  hl.dsp.window.resize({ x = 0,   y = 40 }),  { repeating = true })

-- Adjust window gaps (inner + outer, proportionate)
rebind(mainMod .. " + SHIFT + equal", hl.dsp.exec_cmd("~/.config/hypr/scripts/adjust-gaps +"))
rebind(mainMod .. " + SHIFT + minus", hl.dsp.exec_cmd("~/.config/hypr/scripts/adjust-gaps -"))

-- Switch workspaces with mainMod + [0-9]
-- Move active window to a workspace with mainMod + SHIFT + [0-9]
local workspaceKeys = { "1", "2", "F1", "F2", "5", "6", "7", "8", "9", "0" }
local workspaceIds  = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 }
for i, key in ipairs(workspaceKeys) do
    rebind(mainMod .. " + " .. key,             hl.dsp.focus({ workspace = workspaceIds[i] }))
    rebind(mainMod .. " + SHIFT + " .. key,     hl.dsp.window.move({ workspace = workspaceIds[i] }))
end

rebind(mainMod .. " + SHIFT + SPACE", hl.dsp.window.float({ action = "toggle" }))
rebind(mainMod .. " + SHIFT + F",     hl.dsp.window.fullscreen())

-- Swap window position
rebind(mainMod .. " + SHIFT + A", hl.dsp.window.swap({ direction = "left" }))
rebind(mainMod .. " + SHIFT + D", hl.dsp.window.swap({ direction = "right" }))
rebind(mainMod .. " + SHIFT + W", hl.dsp.window.swap({ direction = "up" }))
rebind(mainMod .. " + SHIFT + S", hl.dsp.window.swap({ direction = "down" }))

-- Special workspace (scratchpad)
rebind(mainMod .. " + M",         hl.dsp.workspace.toggle_special("magic"))
rebind(mainMod .. " + SHIFT + M", hl.dsp.window.move({ workspace = "special:magic" }))

-- Scroll through existing workspaces with mainMod + scroll
rebind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
rebind(mainMod .. " + mouse_up",   hl.dsp.focus({ workspace = "e-1" }))

-- Move/resize windows with mainMod + LMB/RMB and dragging
rebind(mainMod .. " + mouse:272", hl.dsp.window.drag(),   { mouse = true })
rebind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- Volume controls
rebind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"), { locked = true, repeating = true })
rebind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),      { locked = true, repeating = true })
rebind("XF86AudioMute",        hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),     { locked = true, repeating = true })
rebind("XF86AudioMicMute",     hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"),   { locked = true, repeating = true })

-- Brightness controls. hyprconf-brightness wraps brightnessctl so the keys
-- stay on the backlight, never reach 0%, and (when hyprconf's own quickshell
-- bar is present) report the new level to its OSD; under Omarchy's own shell
-- the OSD call no-ops gracefully and just the brightness change applies.
rebind("XF86MonBrightnessUp",   hl.dsp.exec_cmd("hyprconf-brightness up"),   { locked = true, repeating = true })
rebind("XF86MonBrightnessDown", hl.dsp.exec_cmd("hyprconf-brightness down"), { locked = true, repeating = true })

-- Media controls (requires playerctl)
rebind("XF86AudioNext",  hl.dsp.exec_cmd("playerctl next"),       { locked = true })
rebind("XF86AudioPause", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
rebind("XF86AudioPlay",  hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
rebind("XF86AudioPrev",  hl.dsp.exec_cmd("playerctl previous"),   { locked = true })

-- Clipboard history — repointed at Omarchy's own clipboard picker
-- (omarchy-clipboard-open) since hyprconf's version shells out to
-- hyprlauncher --dmenu, which isn't installed under Omarchy.
hl.unbind(mainMod .. " + SHIFT + V")
o.bind(mainMod .. " + SHIFT + V", "Clipboard history", "omarchy-clipboard-open")

-- Screenshots. `--freeze` grabs the screen the moment the selection starts, so
-- what gets captured is what was on screen when the key was pressed.
rebind(mainMod .. " + SHIFT + 4", hl.dsp.exec_cmd("hyprshot -m region --freeze"))

-- Screen lock
rebind(mainMod .. " + L",              hl.dsp.exec_cmd("loginctl lock-session"))
rebind(mainMod .. " + SHIFT + Escape", hl.dsp.exec_cmd("loginctl lock-session"))

-- Toggle native laptop display
rebind(mainMod .. " + SHIFT + BACKSPACE", hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-native-display"))
