-- Keybindings (Lua). Sourced via `require("keybinds")` from hyprland.lua.
-- See https://wiki.hypr.land/Configuring/Basics/Binds/

local mainMod = "SUPER" -- Sets "Windows" key as main modifier

-- Programs used below (only consumed by this file, so defined here rather
-- than in hyprland.lua — Lua `require`d modules don't share locals).
local terminal    = "kitty"
local fileManager = "dolphin"
local menu        = "hyprlauncher"
local browser     = "firefox"

hl.bind(mainMod .. " + T", hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + Q", hl.dsp.window.close())
hl.bind(mainMod .. " + SHIFT + Q", hl.dsp.exit())
hl.bind(mainMod .. " + E", hl.dsp.exec_cmd(fileManager))
hl.bind(mainMod .. " + V", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mainMod .. " + D", hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + P", hl.dsp.window.pseudo())
hl.bind(mainMod .. " + F", hl.dsp.exec_cmd(browser))
hl.bind(mainMod .. " + C", hl.dsp.exec_cmd("code"))
hl.bind(mainMod .. " + SHIFT + B", hl.dsp.exec_cmd("~/.config/hypr/scripts/switch_monitor.sh bedroom"))
hl.bind(mainMod .. " + SHIFT + K", hl.dsp.exec_cmd("~/.config/hypr/scripts/switch_monitor.sh kitchen"))

-- Move focus with mainMod + arrow keys
hl.bind(mainMod .. " + left",  hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + right", hl.dsp.focus({ direction = "right" }))
hl.bind(mainMod .. " + up",    hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + down",  hl.dsp.focus({ direction = "down" }))

-- Resize active window
hl.bind(mainMod .. " + SHIFT + left",  hl.dsp.window.resize({ x = -40, y = 0 }),  { repeating = true })
hl.bind(mainMod .. " + SHIFT + right", hl.dsp.window.resize({ x = 40,  y = 0 }),  { repeating = true })
hl.bind(mainMod .. " + SHIFT + up",    hl.dsp.window.resize({ x = 0,   y = -40 }), { repeating = true })
hl.bind(mainMod .. " + SHIFT + down",  hl.dsp.window.resize({ x = 0,   y = 40 }),  { repeating = true })

-- Adjust window gaps (inner + outer, proportionate)
hl.bind(mainMod .. " + SHIFT + equal", hl.dsp.exec_cmd("~/.config/hypr/scripts/adjust-gaps +"))
hl.bind(mainMod .. " + SHIFT + minus", hl.dsp.exec_cmd("~/.config/hypr/scripts/adjust-gaps -"))

-- Switch workspaces with mainMod + [0-9]
-- Move active window to a workspace with mainMod + SHIFT + [0-9]
local workspaceKeys = { "1", "2", "F1", "F2", "5", "6", "7", "8", "9", "0" }
local workspaceIds  = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 }
for i, key in ipairs(workspaceKeys) do
    hl.bind(mainMod .. " + " .. key,             hl.dsp.focus({ workspace = workspaceIds[i] }))
    hl.bind(mainMod .. " + SHIFT + " .. key,     hl.dsp.window.move({ workspace = workspaceIds[i] }))
end

hl.bind(mainMod .. " + SHIFT + SPACE", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mainMod .. " + SHIFT + F",     hl.dsp.window.fullscreen())

-- Swap window position
hl.bind(mainMod .. " + SHIFT + A", hl.dsp.window.swap({ direction = "left" }))
hl.bind(mainMod .. " + SHIFT + D", hl.dsp.window.swap({ direction = "right" }))
hl.bind(mainMod .. " + SHIFT + W", hl.dsp.window.swap({ direction = "up" }))
hl.bind(mainMod .. " + SHIFT + S", hl.dsp.window.swap({ direction = "down" }))

-- Special workspace (scratchpad)
hl.bind(mainMod .. " + M",         hl.dsp.workspace.toggle_special("magic"))
hl.bind(mainMod .. " + SHIFT + M", hl.dsp.window.move({ workspace = "special:magic" }))

-- Scroll through existing workspaces with mainMod + scroll
hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mainMod .. " + mouse_up",   hl.dsp.focus({ workspace = "e-1" }))

-- Move/resize windows with mainMod + LMB/RMB and dragging
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(),   { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- Volume controls
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"), { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),      { locked = true, repeating = true })
hl.bind("XF86AudioMute",        hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),     { locked = true, repeating = true })
hl.bind("XF86AudioMicMute",     hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"),   { locked = true, repeating = true })

-- Brightness controls. `-n2` floors the backlight at 2%: a plain `set 5%-`
-- walks all the way to 0 and leaves a black panel that the brightness-up key
-- cannot always bring back. `-e4` uses a perceptual (exponential) curve, so a
-- step at the dim end changes as much as a step at the bright end.
hl.bind("XF86MonBrightnessUp",   hl.dsp.exec_cmd("brightnessctl -e4 -n2 set 5%+"), { locked = true, repeating = true })
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("brightnessctl -e4 -n2 set 5%-"), { locked = true, repeating = true })

-- Media controls (requires playerctl)
hl.bind("XF86AudioNext",  hl.dsp.exec_cmd("playerctl next"),       { locked = true })
hl.bind("XF86AudioPause", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPlay",  hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPrev",  hl.dsp.exec_cmd("playerctl previous"),   { locked = true })

-- Quickshell popouts (calendar / control center) — launch.sh resolves the
-- quickshell binary and forwards the ipc call to the running bar.
hl.bind(mainMod .. " + SHIFT + C", hl.dsp.exec_cmd("~/.config/quickshell/launch.sh ipc call popouts toggle calendar"))
hl.bind(mainMod .. " + SHIFT + N", hl.dsp.exec_cmd("~/.config/quickshell/launch.sh ipc call popouts toggle controlcenter"))

-- Screenshots. `--freeze` grabs the screen the moment the selection starts, so
-- what gets captured is what was on screen when the key was pressed — without
-- it, anything that redraws while the region is dragged (a video, a clock, a
-- notification arriving) lands in the shot instead.
hl.bind(mainMod .. " + SHIFT + 4", hl.dsp.exec_cmd("hyprshot -m region --freeze"))

-- Screen lock — routed through hypridle's guarded lock_cmd (single lock path;
-- it wipes cliphist and refuses to start a second hyprlock instance)
hl.bind(mainMod .. " + L",              hl.dsp.exec_cmd("loginctl lock-session"))
hl.bind(mainMod .. " + SHIFT + Escape", hl.dsp.exec_cmd("loginctl lock-session"))

-- Clipboard history
hl.bind(mainMod .. " + SHIFT + V", hl.dsp.exec_cmd("cliphist list | hyprlauncher --dmenu | cliphist decode | wl-copy"))

-- Toggle native laptop display
hl.bind(mainMod .. " + SHIFT + BACKSPACE", hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-native-display"))
