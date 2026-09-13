-- Bedroom monitor preset: `hyprconf-monitor-preset bedroom` (SUPER+SHIFT+B).
-- Outputs by desc:<make> <model>: never a connector (renumbers across GPUs),
-- never a serial (PII); the output = "" line below is the catch-all. Why:
-- README.md > Monitor presets; the syntax: hypr/README.md > Monitor presets.
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

-- Safety net: an unknown panel comes up at its preferred mode, not dark.
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = "auto" })
