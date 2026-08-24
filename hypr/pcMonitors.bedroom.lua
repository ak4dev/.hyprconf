-- Bedroom monitor preset (Lua). Apply manually: `switch_monitor.sh bedroom`.
-- Output names verified against this desk's `hyprctl monitors all`: the LG TV
-- enumerates as HDMI-A-2, the kitchen pair (off in this layout) as DP-4/DP-5,
-- and the small secondary panel as DP-6.
hl.monitor({ output = "HDMI-A-2", mode = "3840x2160@119.88", position = "0x0", scale = 1.5, vrr = 2, bitdepth = 10, cm = "dcip3", sdrbrightness = 1.3 })
hl.monitor({ output = "DP-4", disabled = true })
hl.monitor({ output = "DP-5", disabled = true })
hl.monitor({ output = "DP-6", mode = "3840x2160@60.00", position = "auto-down", scale = 3.0, vrr = 0 })

hl.config({
    render = {
        direct_scanout = 1,
    },
})

hl.workspace_rule({ workspace = "1", monitor = "HDMI-A-2" })
hl.workspace_rule({ workspace = "2", monitor = "HDMI-A-2" })
hl.workspace_rule({ workspace = "3", monitor = "HDMI-A-2" })
hl.workspace_rule({ workspace = "4", monitor = "HDMI-A-2" })
hl.workspace_rule({ workspace = "5", monitor = "HDMI-A-2" })
hl.workspace_rule({ workspace = "6", monitor = "HDMI-A-2" })
