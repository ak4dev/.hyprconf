#!/usr/bin/env bash
# Run quickshell (`qs "$@"`): prefer the system package, else fall back to
# the user-local tree under ~/.local/opt/quickshell (pre-package installs).
# No arguments runs the shell itself; arguments are forwarded, so keybinds
# can use `launch.sh ipc call popouts toggle <name>` regardless of which
# runtime is present.
set -u

if command -v qs &>/dev/null; then
    exec qs "$@"
fi

QS_ROOT="$HOME/.local/opt/quickshell"
if [[ -x "$QS_ROOT/usr/bin/quickshell" ]]; then
    export LD_LIBRARY_PATH="$QS_ROOT/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export QML_IMPORT_PATH="$QS_ROOT/usr/lib/qt6/qml${QML_IMPORT_PATH:+:$QML_IMPORT_PATH}"
    export QML2_IMPORT_PATH="$QS_ROOT/usr/lib/qt6/qml${QML2_IMPORT_PATH:+:$QML2_IMPORT_PATH}"
    exec "$QS_ROOT/usr/bin/quickshell" "$@"
fi

echo "quickshell not found: install 'quickshell' from extra, or place a package tree at $QS_ROOT" >&2
exit 1
