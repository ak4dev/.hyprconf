-- Laptop/portable monitor preset: `hyprconf-monitor-preset laptop`. Connector-
-- keyed on purpose: it describes no particular hardware (hypr/README.md).
hl.monitor({ output = "eDP-1",    mode = "preferred", position = "auto",       scale = "auto" })
hl.monitor({ output = "DP-1",     mode = "preferred", position = "auto-right", scale = 2 })
hl.monitor({ output = "DP-2",     mode = "preferred", position = "auto-right", scale = 2 })
hl.monitor({ output = "HDMI-A-1", mode = "preferred", position = "auto-left",  scale = 2 })
-- Catchall: any other connector not covered above.
hl.monitor({ output = "",         mode = "preferred", position = "auto",       scale = "auto" })
