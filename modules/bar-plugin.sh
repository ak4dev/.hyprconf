#!/usr/bin/env bash
# What the four modules/bar-*/install share: the link, the rescan, the one
# enable, the shell.json fallback and the undo. SOURCED, never run — the shebang
# and the exec bit are deliberate: they are what put this file under the
# `make shellcheck` pass, tests/test_scans.py and conftest's fake derivation,
# so a command named only here still gets a recording fake. A cone-mode sparse
# checkout of one module brings it along, beside that module's directory.
#
# Seams, stated once for all four: ~/.config/omarchy/plugins/<id>, a folder the
# third-party scan follows through a symlink (shell/services/PluginRegistry.qml:712-713)
# while `inotifywait -r` never descends one (:663-674) — hence the explicit
# rescan every run, which is what picks a `git pull` up. The enable carries NO
# placement: that is what lets a clonedFrom copy keep the stock widget's slot
# (:529-534; a --section would splice it straight back out, :545-546) and leaves
# anything else in its manifest's barWidget.defaultSection (:194-196). The wait
# before it is omarchy-plugin-add's own (bin/omarchy-plugin-add:163-170), since
# an enable issued before the rescan lands fails "not known"
# (bin/omarchy-plugin-enable:86-87).
set -euo pipefail
: "${dir:?}" "${id:?}" "${marker:?}"   # set by the sourcing install, never run alone
plugins=$HOME/.config/omarchy/plugins link=$plugins/$id
json=$HOME/.config/omarchy/shell.json
# Layout entries are bare strings or objects with an id (bin/omarchy-bar:178).
ids='[.bar.layout // {} | .[]? | .[]? | if type == "string" then . else (.id // "") end]'

rescan() { omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true; }
on_bar() { jq -e --arg id "$1" "$ids | any(. == \$id)" "$json" >/dev/null 2>&1; }

# A failing left operand of an && list is exempt from set -e: `jq … > tmp && mv`
# would report success whichever way jq went and leave the stale tmp behind.
# Direct, because neither write has a command: `bar.centerAnchor` has none at all
# (omarchy commands --json; bin/omarchy-bar has no anchor verb), and the swap
# below is the running shell's own, done here only when nothing answers.
# omarchy-shell-config's commit (:53-62) cannot stand in: its bare `mv` reports
# success when sourced inside a conditional, and `jq -S` re-sorts the user's
# whole file. The shell's own FileView picks the rename up (shell.qml:134-142).
edit() {
    local what=$1
    shift
    if jq "$@" "$json" > "$json.tmp"; then
        mv "$json.tmp" "$json"
    else
        rm -f "$json.tmp" || true
        echo "  could not set $what in $json" >&2
    fi
}

# The swap a disable does — the clone's entry back to the id it took the slot
# from, its other settings kept (PluginRegistry.qml:555 -> restoreCloneSource:441),
# or a plain splice for anything else (:556) — done in the file, for when nothing
# answered: there is then no in-memory copy to take the edit back, and an entry
# naming a plugin that is gone is a 0-width slot next session (Bar.qml:1795, :1814).
# $1 the id the slot goes back to, empty to take the entry off; $2 a format with it.
hand_back() {
    [[ -f $json ]] || return 0
    edit "the bar entry for $id" --arg id "$id" --arg s "${1:-}" --arg f "${2:-}" \
        ".bar.layout[]? |= map(if (if type == \"object\" then .id else . end) == \$id then
            (if \$s == \"\" then empty
             else (objects // {}) + {id: \$s} + (if \$f == \"\" then {} else {format: \$f} end)
             end)
        else . end)"
}

plugin_disable() { omarchy-plugin-disable "$id" >/dev/null 2>&1 || hand_back "$@"; }

plugin_link() {
    mkdir -p "$plugins" "${marker%/*}"
    # Moved aside under omarchy-plugin-remove's own backup name (:106), never deleted.
    [[ -d $link && ! -L $link ]] && mv "$link" "$plugins/.$id.bak.$(date -u +%Y%m%d%H%M%S)"
    [[ $(readlink "$link" 2>/dev/null) == "$dir/plugin" ]] || ln -sfn "$dir/plugin" "$link"
    rescan
}

plugin_unlink() {
    # Only this module's link: a real directory here is someone else's, and
    # `rm -f` on one fails, taking the undo down with it.
    [[ -L $link ]] && rm -f "$link"
    rm -f "$marker"
    rescan
}

# Leaves $list — the answer the wait ended on — to a caller that reads it.
plugin_enable() {
    local i
    for (( i = 0; i < 40; i++ )); do   # no shell answering → the list exits 1 → no wait
        list=$(omarchy-plugin-list --json 2>/dev/null) || break
        jq -e --arg id "$id" 'any(.[]?; .id == $id)' <<<"$list" >/dev/null 2>&1 && break
        sleep 0.05
    done
    omarchy-plugin-enable "$id" >/dev/null 2>&1 || {
        echo "  no shell answering — enabled on the next run"
        exit 0
    }
}

# `omarchy plugin update` fast-forwards a same-id checkout and refuses a non-git
# one (bin/omarchy-plugin-update:111-112): it is the user's, so neither path
# touches it — undo drops hyprconf's own marker and nothing else.
if [[ -d $link/.git ]]; then
    if [[ ${1:-} == undo ]]; then
        rm -f "$marker"
    else
        echo "  $id is an \`omarchy plugin add\` checkout — left to: omarchy plugin update $id"
    fi
    exit 0
fi
