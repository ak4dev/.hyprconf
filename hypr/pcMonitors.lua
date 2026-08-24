-- Desktop monitor preset (Lua). Symlinked to monitors.lua by the retired standalone setup's
-- chassis detection / switch_monitor.sh. See https://wiki.hypr.land/Configuring/Basics/Monitors/
--
-- NOTE: the DP-1 and HDMI-A-1 calls near the bottom intentionally re-declare
-- those same outputs with different (vrr=0) settings — later hl.monitor()
-- calls for the same `output` override earlier ones, same as hyprlang's
-- last-`monitor=`-line-wins behavior. Preserved as-is from the .conf original;
-- not something this migration changes.
hl.monitor({ output = "HDMI-A-1", mode = "3840x2160@120.00", position = "auto", scale = 2.0, vrr = 2, bitdepth = 10, cm = "hdr", sdrbrightness = 1.4 })
hl.monitor({ output = "DP-3", disabled = true })
hl.monitor({ output = "DP-2", disabled = true })
hl.monitor({ output = "DP-1", mode = "3840x2160@240.00", position = "auto-right", scale = 1.0, vrr = 2, bitdepth = 10, sdrbrightness = 1.4 })

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

hl.monitor({ output = "DP-1", mode = "3840x2160@240.00Hz", position = "auto-right", scale = 1.0, vrr = 0 })

hl.monitor({ output = "HDMI-A-1", mode = "3840x2160@119.88Hz", position = "0x0", scale = 2, vrr = 0 })
