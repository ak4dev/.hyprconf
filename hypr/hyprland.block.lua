-- >>> hyprconf >>>
-- Managed block — regenerate with: bash ~/.hyprconf/install.sh
-- Everything between these markers is replaced on each run; edit the source
-- at hypr/hyprland.block.lua instead. Anything outside is preserved.
--
-- Loads the machine-local files the hyprconf TUI writes at runtime. On the
-- standalone desktop hyprconf's own hyprland.lua did this (try_require over
-- an extended package.path); Omarchy's hyprland.lua knows nothing of conf.d,
-- so the overlay loads them from the "personal configuration" tail Omarchy's
-- own file invites additions in. loadfile, not require: "conf.d" carries a
-- dot in its directory name, which a dotted module name would split. A
-- missing file is a no-op.
for _, name in ipairs({ "local", "windowrules", "workspacerules" }) do
  local chunk = loadfile(
    (os.getenv("XDG_CONFIG_HOME") or (os.getenv("HOME") .. "/.config"))
      .. "/hypr/conf.d/" .. name .. ".lua"
  )
  if chunk then
    pcall(chunk)
  end
end
-- <<< hyprconf <<<
