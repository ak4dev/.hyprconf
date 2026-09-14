# hyprconf/shell-zsh — powerlevel10k: the pinned classic template, plus this
# overlay's overrides. Transcribed from `diff <pin>/config/p10k-classic.zsh`
# against the 1,739-line wizard dump this replaces, so a pin bump now carries
# template drift — reviewed at the bump, like the pin itself. Never run
# `p10k configure`: it writes another 1,739-line dump over this file.
# ~/.p10k.zsh is a link to this file; `install` holds the pin and clones it.
_p10k_template="$HOME/.local/share/powerlevel10k/config/p10k-classic.zsh"
# Guarded: a clone that failed, or one the user removed, must not break zsh.
[ -r "$_p10k_template" ] && source "$_p10k_template"
unset _p10k_template

# One line, os_icon on, no prompt_char. The template's second line is dropped.
typeset -g POWERLEVEL9K_LEFT_PROMPT_ELEMENTS=(os_icon dir vcs)
# The template's right-hand list, on the same line: `newline` out, vi_mode and
# time in, per_directory_history gone with Oh My Zsh (its plugin is what fed it).
typeset -g POWERLEVEL9K_RIGHT_PROMPT_ELEMENTS=(
  status command_execution_time background_jobs direnv asdf virtualenv anaconda
  pyenv goenv nodenv nvm nodeenv rbenv rvm fvm luaenv jenv plenv perlbrew phpenv
  scalaenv haskell_stack kubecontext terraform aws aws_eb_env azure gcloud
  google_app_cred toolbox context nordvpn ranger yazi nnn lf xplr vim_shell
  midnight_commander nix_shell chezmoi_shell vi_mode todo timewarrior taskwarrior
  time
)
typeset -g POWERLEVEL9K_MODE=nerdfont-v3
# The Arch logo (Nerd Font U+F303) — a prompt setting, so it lives here and
# not, as it used to, in the shell rc file beside the theme's source line.
typeset -g POWERLEVEL9K_OS_ICON_CONTENT_EXPANSION=$'\uf303'
typeset -g POWERLEVEL9K_PROMPT_ADD_NEWLINE=false
typeset -g POWERLEVEL9K_MULTILINE_FIRST_PROMPT_PREFIX='%238F╭─'
typeset -g POWERLEVEL9K_MULTILINE_NEWLINE_PROMPT_PREFIX='%238F├─'
typeset -g POWERLEVEL9K_MULTILINE_LAST_PROMPT_PREFIX='%238F╰─'
typeset -g POWERLEVEL9K_MULTILINE_FIRST_PROMPT_SUFFIX='%238F─╮'
typeset -g POWERLEVEL9K_MULTILINE_NEWLINE_PROMPT_SUFFIX='%238F─┤'
typeset -g POWERLEVEL9K_MULTILINE_LAST_PROMPT_SUFFIX='%238F─╯'
typeset -g POWERLEVEL9K_BACKGROUND=234
typeset -g POWERLEVEL9K_LEFT_SUBSEGMENT_SEPARATOR='%242F\u2571'
typeset -g POWERLEVEL9K_RIGHT_SUBSEGMENT_SEPARATOR='%242F\u2571'
typeset -g POWERLEVEL9K_LEFT_SEGMENT_SEPARATOR='\uE0BC'
typeset -g POWERLEVEL9K_RIGHT_SEGMENT_SEPARATOR='\uE0BA'
typeset -g POWERLEVEL9K_LEFT_PROMPT_LAST_SEGMENT_END_SYMBOL='\uE0BC'
typeset -g POWERLEVEL9K_RIGHT_PROMPT_FIRST_SEGMENT_START_SYMBOL='\uE0BA'
typeset -g POWERLEVEL9K_LEFT_PROMPT_FIRST_SEGMENT_START_SYMBOL='░▒▓'
typeset -g POWERLEVEL9K_RIGHT_PROMPT_LAST_SEGMENT_END_SYMBOL='▓▒░'
typeset -g POWERLEVEL9K_VCS_BRANCH_ICON='\uF126 '
unset POWERLEVEL9K_BATTERY_STAGES   # an array in the template, a string of glyphs here
typeset -g POWERLEVEL9K_BATTERY_STAGES='\UF008E\UF007A\UF007B\UF007C\UF007D\UF007E\UF007F\UF0080\UF0081\UF0082\UF0079'
typeset -g POWERLEVEL9K_TIME_FORMAT='%D{%I:%M:%S %p}'
typeset -g POWERLEVEL9K_INSTANT_PROMPT=off
# One override of the dump is deliberately NOT carried: its my_git_formatter
# painted an up-to-date git segment's meta text grey 244 where the template
# uses 248. Reaching it means copying the template's 60-line function, and
# rewriting the live one through functions[my_git_formatter] corrupts every
# multibyte glyph in the body (zsh 5.9.2 re-metafies it: U+21E3 comes back as
# U+20E7 + a stray byte) — verified, not assumed.
# `p10k configure` would otherwise target the template this file just sourced.
typeset -g POWERLEVEL9K_CONFIG_FILE=${${(%):-%x}:a}
