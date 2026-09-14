-- Laptop/portable monitor preset: `hyprconf-monitor-preset laptop`.
-- Connector-keyed on purpose: it describes no particular hardware, only "an
-- external is plugged in" (a desk preset uses desc:, README.md in this folder).
-- Deltas only — the internal panel and every other connector come up from
-- Omarchy's own catch-all, which this toggle loads after
-- (config/hypr/monitors.lua:8, `output = ""`, preferred/auto/auto).
hl.monitor({ output = "DP-1",     mode = "preferred", position = "auto-right", scale = 2 })
hl.monitor({ output = "DP-2",     mode = "preferred", position = "auto-right", scale = 2 })
hl.monitor({ output = "HDMI-A-1", mode = "preferred", position = "auto-left",  scale = 2 })
