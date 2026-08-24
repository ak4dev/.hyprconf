-- Bedroom monitor preset (Lua). Apply manually: `switch_monitor.sh bedroom`.
hl.monitor({ output = "HDMI-A-1", mode = "3840x2160@119.88", position = "0x0", scale = 1.5, vrr = 2, bitdepth = 10, cm = "dcip3", sdrbrightness = 1.3 })
hl.monitor({ output = "DP-1", disabled = true })
hl.monitor({ output = "DP-2", disabled = true })
hl.monitor({ output = "DP-3", mode = "3840x2160@60.00", position = "auto-down", scale = 3.0, vrr = 0 })

hl.config({
    render = {
        direct_scanout = 1,
    },
})

hl.workspace_rule({ workspace = "1", monitor = "HDMI-A-1" })
hl.workspace_rule({ workspace = "2", monitor = "HDMI-A-1" })
hl.workspace_rule({ workspace = "3", monitor = "HDMI-A-1" })
hl.workspace_rule({ workspace = "4", monitor = "HDMI-A-1" })
hl.workspace_rule({ workspace = "5", monitor = "HDMI-A-1" })
hl.workspace_rule({ workspace = "6", monitor = "HDMI-A-1" })
