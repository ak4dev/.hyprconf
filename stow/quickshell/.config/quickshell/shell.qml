import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

ShellRoot {
    Variants {
        id: bars
        model: Quickshell.screens
        delegate: Bar {}
    }

    Osd { id: osd }

    Variants {
        model: Quickshell.screens
        delegate: ScreenCorners {}
    }

    // `qs ipc call popouts toggle <calendar|volume|network>` — also usable
    // from hyprland keybinds. Argument is validated in Bar.ipcToggle and
    // never executed.
    IpcHandler {
        target: "popouts"

        function toggle(name: string): string {
            const focused = Quickshell.screens.find(
                s => Hyprland.monitorFor(s) === Hyprland.focusedMonitor)
            const b = bars.instances.find(i => i.screen === focused)
                ?? bars.instances[0]
            if (!b)
                return "no bar"
            return b.ipcToggle(name)
        }
    }

    // `qs ipc call osd brightness 42` — hyprconf-brightness reports the level
    // it just set, so the backlight keys get the feedback the volume keys get
    // from pipewire. Clamped in Osd.showBrightness; nothing here is executed.
    IpcHandler {
        target: "osd"

        function brightness(percent: int): string {
            return osd.showBrightness(percent)
        }
    }
}
