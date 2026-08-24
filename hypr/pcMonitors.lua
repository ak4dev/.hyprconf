-- Desktop monitor preset: `switch_monitor.sh pc`. See https://wiki.hypr.land/Configuring/Basics/Monitors/
hl.monitor({ output = "DP-3", disabled = true })
hl.monitor({ output = "DP-2", disabled = true })
hl.monitor({ output = "DP-1", mode = "3840x2160@240.00Hz", position = "auto-right", scale = 1.0, vrr = 0 })
hl.monitor({ output = "HDMI-A-1", mode = "3840x2160@119.88Hz", position = "0x0", scale = 2, vrr = 0 })

hl.config({
    render = {
        direct_scanout = 1,
        cm_auto_hdr = 1,
    },
})

hl.workspace_rule({ workspace = "1", monitor = "HDMI-A-1" })
hl.workspace_rule({ workspace = "2", monitor = "DP-1" })
hl.workspace_rule({ workspace = "3", monitor = "HDMI-A-1" })
hl.workspace_rule({ workspace = "4", monitor = "DP-1" })
hl.workspace_rule({ workspace = "5", monitor = "HDMI-A-1" })
hl.workspace_rule({ workspace = "6", monitor = "HDMI-A-1" })
