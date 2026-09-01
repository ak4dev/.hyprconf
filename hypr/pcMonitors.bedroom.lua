-- Bedroom monitor preset: `hyprconf-monitor-preset bedroom` (SUPER+SHIFT+B). See https://wiki.hypr.land/Configuring/Basics/Monitors/
-- Output names verified against this desk's `hyprctl monitors all`: the LG TV
-- enumerates as HDMI-A-1, the kitchen pair (off in this layout) as DP-1/DP-2,
-- and the small secondary panel as DP-3. The DP-N/HDMI-A-N numbering follows
-- the GPU the session drives the displays through (probe order /
-- AQ_DRM_DEVICES / cabling) — re-verify it whenever that changes.
-- 4K tops out at 60 Hz here: the TV hangs off the RTX 3070's HDMI 2.0 link
-- (18 Gbps), and hyprctl advertises 119.88 only at 2560x1440 and below —
-- the old 4K@119.88 line needs the 5090's HDMI 2.1, so recabling the TV
-- there (and re-verifying the output names) is what restores it.
hl.monitor({ output = "HDMI-A-1", mode = "3840x2160@60.00", position = "0x0", scale = 1.6, vrr = 2, bitdepth = 10, cm = "dcip3", sdrbrightness = 1.3 })
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
