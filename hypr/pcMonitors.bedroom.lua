-- Bedroom monitor preset: `hyprconf-monitor-preset bedroom` (SUPER+SHIFT+B). See https://wiki.hypr.land/Configuring/Basics/Monitors/
-- Outputs are named by DESCRIPTION, not connector. `desc:` prefix-matches
-- Hyprland's "<make> <model> <serial>" string, so the make+model is enough and
-- the serial stays out of a tracked file. Verified against this desk's
-- `hyprctl monitors all` on Hyprland 0.56.2. Connector names are deliberately
-- not used: DP-N/HDMI-A-N follow the GPU the session drives the displays
-- through (probe order / AQ_DRM_DEVICES / cabling), so recabling renumbers
-- them — moving these three panels from the RTX 3070 to the RTX 5090 turned
-- HDMI-A-1/DP-1/DP-2 into HDMI-A-2/DP-4/DP-5 and blacked out every preset.
-- A description follows the panel.
-- The TV tops out at 3840x2160@119.88 over the 5090's HDMI 2.1 link (its mode
-- list advertises no 4K@120.00 — 120.00 exists only at 2560x1440 and below).
hl.monitor({ output = "desc:LG Electronics LG TV SSCR2", mode = "3840x2160@119.88", position = "0x0", scale = 1.6, vrr = 2, bitdepth = 10, cm = "dcip3", sdrbrightness = 1.3 })
hl.monitor({ output = "desc:Samsung Electric Company Odyssey G8", disabled = true })
hl.monitor({ output = "desc:Acer Technologies CB282K", disabled = true })

hl.config({
    render = {
        direct_scanout = 1,
    },
})

hl.workspace_rule({ workspace = "1", monitor = "desc:LG Electronics LG TV SSCR2" })
hl.workspace_rule({ workspace = "2", monitor = "desc:LG Electronics LG TV SSCR2" })
hl.workspace_rule({ workspace = "3", monitor = "desc:LG Electronics LG TV SSCR2" })
hl.workspace_rule({ workspace = "4", monitor = "desc:LG Electronics LG TV SSCR2" })
hl.workspace_rule({ workspace = "5", monitor = "desc:LG Electronics LG TV SSCR2" })
hl.workspace_rule({ workspace = "6", monitor = "desc:LG Electronics LG TV SSCR2" })

-- Safety net: any panel not named above comes up at its preferred mode rather
-- than staying dark. Named rules win over the catch-all whatever the order —
-- the disables above included — so this only fires for an unknown display.
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = "auto" })
