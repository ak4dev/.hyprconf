# hyprconf/shell-zsh — powerlevel10k: the pinned classic template plus this
# overlay's overrides, so a pin bump carries template drift. ~/.p10k.zsh links
# here. Never run `p10k configure`: it writes another dump over this file.
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
# The Arch logo (Nerd Font U+F303).
typeset -g POWERLEVEL9K_OS_ICON_CONTENT_EXPANSION=$'\uf303'
typeset -g POWERLEVEL9K_PROMPT_ADD_NEWLINE=false
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
typeset -g POWERLEVEL9K_TIME_FORMAT='%D{%I:%M:%S %p}'
typeset -g POWERLEVEL9K_INSTANT_PROMPT=off
# `p10k configure` would otherwise target the template this file just sourced.
typeset -g POWERLEVEL9K_CONFIG_FILE=${${(%):-%x}:a}
