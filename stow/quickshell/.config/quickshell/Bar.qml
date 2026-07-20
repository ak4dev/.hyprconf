import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Services.SystemTray
import Quickshell.Services.Pipewire
import Quickshell.Widgets

// One bar per monitor; layout and styling carried over from the retired
// waybar setup, with quickshell-only extras: frosted popouts, volume OSD,
// screencast indicator, scroll gestures.
PanelWindow {
    id: bar

    required property var modelData
    screen: modelData

    anchors {
        top: true
        left: true
        right: true
    }
    implicitHeight: 24
    color: "transparent"
    WlrLayershell.namespace: "quickshell:bar"

    readonly property string home: Quickshell.env("HOME")

    // ---- clock (left-click: calendar popout, middle-click: alt format)
    SystemClock {
        id: clock
        precision: SystemClock.Seconds
    }
    property bool clockAlt: false

    function fmtClock(): string {
        const d = clock.date
        if (bar.clockAlt)
            return "󰥔 " + Qt.formatDateTime(d, "ddd, MMM dd HH:mm")
        let h = d.getHours() % 12
        if (h === 0)
            h = 12
        const p = n => String(n).padStart(2, "0")
        return "󰥔 " + p(h) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds())
    }

    // Hyprland.activeToplevel only populates from focus events, so seed the
    // initial title via IPC; events take over after the first focus change.
    property string seedTitle: ""
    property int seedTries: 0

    // screencast indicator state (hyprland "screencast" event)
    property bool casting: false

    Process {
        id: seedProc
        running: true
        command: ["hyprctl", "-j", "activewindow"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    bar.seedTitle = JSON.parse(text).title ?? ""
                } catch (e) {}
            }
        }
    }

    // The one-shot seed can race a Hyprland config reload (empty IPC reply
    // when the bar is relaunched by the exec line), so retry a few times.
    Timer {
        interval: 700
        repeat: true
        running: bar.seedTries < 5 && bar.seedTitle === "" && Hyprland.activeToplevel === null
        onTriggered: {
            bar.seedTries++
            seedProc.running = true
        }
    }

    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (event.name === "activewindow")
                bar.seedTitle = ""
            else if (event.name === "screencast")
                bar.casting = event.data.split(",")[0] === "1"
        }
    }

    // ---- pipewire default sink (replaces waybar's pulseaudio module)
    PwObjectTracker {
        objects: [Pipewire.defaultAudioSink]
    }
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property real vol: sink?.audio?.volume ?? 0
    readonly property bool muted: sink?.audio?.muted ?? false

    // ---- cpu/mem/net/temp stats: fed by the Services singleton (ONE
    // long-lived sampler for all screens — a per-bar Process here meant one
    // sampler per monitor). Bridged as bar properties so the module items
    // below keep their bar.* references.
    readonly property int cpuPct: Services.cpuPct
    readonly property string memText: Services.memText
    readonly property string netKind: Services.netKind
    readonly property string netDown: Services.netDown
    readonly property string netUp: Services.netUp
    readonly property string cpuTemp: Services.cpuTemp

    // ---- popouts
    readonly property var popoutNames: ["calendar", "volume", "controlcenter"]
    property string openPopout: ""

    function itemCenterX(it): real {
        return it.mapToItem(null, it.width / 2, 0).x
    }

    property var trayHandle: null

    function openTrayMenu(trayItem, anchorX) {
        bar.trayHandle = trayItem.menu
        bar.togglePopout("tray", anchorX)
    }

    function togglePopout(name, anchorX) {
        if (popout.open && bar.openPopout === name) {
            popout.close()
            return
        }
        bar.openPopout = name
        popout.anchorX = anchorX
        popout.open = true
    }

    // Entry point for `qs ipc call popouts toggle <name>` — names are
    // validated against the fixed list; the argument is never executed.
    function ipcToggle(name): string {
        const anchorItems = {
            calendar: clockItem,
            volume: volItem,
            controlcenter: netItem
        }
        if (!bar.popoutNames.includes(name))
            return "unknown popout: " + name
        bar.togglePopout(name, bar.itemCenterX(anchorItems[name]))
        return "ok"
    }

    PopoutWindow {
        id: popout
        bar: bar
        screen: bar.screen
        onOpenChanged: {
            if (!open)
                bar.openPopout = ""
        }
        contentComponent: bar.openPopout === "calendar" ? calComp
                        : bar.openPopout === "volume" ? volComp
                        : bar.openPopout === "controlcenter" ? ccComp
                        : bar.openPopout === "tray" ? trayComp
                        : null
    }

    Component { id: calComp; CalendarPopout {} }
    Component { id: volComp; VolumePopout {} }
    Component { id: ccComp; ControlCenter {} }
    Component {
        id: trayComp
        TrayMenuPopout {
            handle: bar.trayHandle
            onDismissed: popout.close()
        }
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.bgAlpha

        // ================= left: workspaces island + window title
        Row {
            anchors.left: parent.left
            height: parent.height

            Item { width: 8; height: 1 } // island margin-left

            Rectangle {
                id: island
                anchors.verticalCenter: parent.verticalCenter
                width: wsRow.width + 16 // island padding 0 8
                height: 24
                radius: 12
                color: Theme.bgAlpha

                Behavior on width {
                    NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic }
                }

                // scroll on the island cycles workspaces on this monitor
                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.NoButton
                    onWheel: wheel => Hyprland.dispatch(
                        wheel.angleDelta.y < 0 ? "workspace m+1" : "workspace m-1")
                }

                Row {
                    id: wsRow
                    anchors.centerIn: parent

                    Repeater {
                        model: Hyprland.workspaces

                        delegate: Item {
                            id: wsButton
                            required property var modelData
                            visible: modelData.id > 0 // hide special workspaces
                            width: visible ? pill.width + 8 : 0 // button margin 0 4
                            height: 20

                            Behavior on width {
                                NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic }
                            }

                            Rectangle {
                                id: pill
                                x: 4
                                width: wsLabel.implicitWidth + 16 // button padding 0 8
                                height: 20
                                radius: 8
                                color: wsButton.modelData.focused ? Theme.purpleAlpha
                                     : wsMouse.containsMouse ? Theme.cyanAlpha
                                     : "transparent"

                                Behavior on width {
                                    NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic }
                                }
                                Behavior on color {
                                    ColorAnimation { duration: Theme.animFast }
                                }

                                BarText {
                                    id: wsLabel
                                    anchors.centerIn: parent
                                    text: wsButton.modelData.focused ? "󰮯" : String(wsButton.modelData.id)
                                    color: wsButton.modelData.focused ? Theme.accent
                                         : wsMouse.containsMouse ? Theme.cyan
                                         : Theme.comment

                                    Behavior on color {
                                        ColorAnimation { duration: Theme.animFast }
                                    }
                                }

                                MouseArea {
                                    id: wsMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onClicked: wsButton.modelData.activate()
                                }
                            }
                        }
                    }
                }
            }

            Item { width: 8; height: 1 } // island margin-right

            Item { // hyprland/window, max-length 50
                id: titleItem
                width: titleText.text === "" ? 0 : titleText.width + 20
                height: parent.height

                BarText {
                    id: titleText
                    x: 10
                    anchors.verticalCenter: parent.verticalCenter
                    // Cap the width so the title elides instead of running
                    // into the clock (waybar overlaps on narrow portrait
                    // monitors). implicitWidth is the natural text width, so
                    // this binding is not circular with titleItem.width.
                    width: Math.min(implicitWidth, Math.max(0, clockItem.x - titleItem.x - 24))
                    elide: Text.ElideRight
                    text: {
                        const t = Hyprland.activeToplevel?.title || bar.seedTitle
                        return t.length > 50 ? t.substring(0, 50) + "…" : t
                    }
                }
            }
        }

        // ================= center: clock
        Item {
            id: clockItem
            width: clockText.implicitWidth
            height: parent.height
            // Centered, but slides left instead of colliding with the right
            // block on narrow (portrait) monitors.
            x: Math.min((parent.width - width) / 2,
                        parent.width - rightRow.width - width - 8)

            BarText {
                id: clockText
                anchors.centerIn: parent
                text: bar.fmtClock()
                color: Theme.accent
            }

            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                onClicked: mouse => {
                    if (mouse.button === Qt.MiddleButton)
                        bar.clockAlt = !bar.clockAlt
                    else
                        bar.togglePopout("calendar", bar.itemCenterX(clockItem))
                }
            }
        }

        // ================= right
        Row {
            id: rightRow
            anchors.right: parent.right
            height: parent.height

            Item { // screencast indicator
                visible: bar.casting
                width: visible ? 18 : 0
                height: parent.height

                Rectangle {
                    anchors.centerIn: parent
                    width: 8
                    height: 8
                    radius: 4
                    color: Theme.red

                    SequentialAnimation on opacity {
                        running: bar.casting
                        loops: Animation.Infinite
                        NumberAnimation { from: 1; to: 0.35; duration: 700 }
                        NumberAnimation { from: 0.35; to: 1; duration: 700 }
                    }
                }
            }

            Item { // tray: padding 0 8, icon 16, spacing 8
                id: trayBox
                // Bluetooth (blueman) and NetworkManager (nm-applet) icons are
                // filtered out — both are managed by the Control Center now, so
                // their tray icons are redundant. The applets keep running as
                // the Bluetooth pairing agent / network secret agent.
                readonly property var trayHidden: ["blueman", "nm-applet", "nm_applet"]
                readonly property var trayItems: SystemTray.items.values.filter(i => {
                    const id = (i.id ?? "").toLowerCase()
                    return !trayBox.trayHidden.some(h => id.includes(h))
                })
                visible: trayItems.length > 0
                width: visible ? trayRow.width + 16 : 0
                height: parent.height

                Row {
                    id: trayRow
                    x: 8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8

                    Repeater {
                        model: trayBox.trayItems

                        delegate: Item {
                            id: trayIcon
                            required property var modelData
                            width: 16
                            height: 16

                            IconImage {
                                anchors.fill: parent
                                source: trayIcon.modelData.icon
                            }

                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
                                onClicked: mouse => {
                                    const item = trayIcon.modelData
                                    const ax = trayIcon.mapToItem(null, trayIcon.width / 2, 0).x
                                    if (mouse.button === Qt.RightButton
                                            || (mouse.button === Qt.LeftButton && item.onlyMenu)) {
                                        if (item.hasMenu)
                                            bar.openTrayMenu(item, ax)
                                    } else if (mouse.button === Qt.MiddleButton) {
                                        item.secondaryActivate()
                                    } else {
                                        item.activate()
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item { // cpu (fused with cpu_temp: padding-right 2)
                width: cpuText.implicitWidth + 8 + 2
                height: parent.height

                BarText {
                    id: cpuText
                    x: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: "󰻠 " + bar.cpuPct + "%"
                    color: Theme.green
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: Quickshell.execDetached(["kitty", "-e", "htop"])
                }
            }

            Item { // custom/cpu_temp — fed by the stats.sh stream (padding-left
                   // 2). Was a 2s polled ScriptModule spawning bash+sensors
                   // (~28 ms) per tick; the sampler reads hwmon directly.
                visible: bar.cpuTemp !== ""
                width: visible ? tempText_.implicitWidth + 7 : 0
                height: parent.height

                BarText {
                    id: tempText_
                    x: 2
                    anchors.verticalCenter: parent.verticalCenter
                    text: bar.cpuTemp
                    color: Theme.green
                }
            }

            Item { // memory
                width: memText_.implicitWidth + 16
                height: parent.height

                BarText {
                    id: memText_
                    x: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: bar.memText === "" ? "" : "󰘚 " + bar.memText
                    color: Theme.yellow
                }
            }

            ScriptModule { // custom/gpu — Services' long-lived stream
                           // (nvidia-smi --loop / AMD sysfs loop)
                height: parent.height
                text: Services.gpuText
                prefix: "󰾲 "
                textColor: Theme.purple
            }

            ScriptModule { // custom/vpn (Services polls every 5s)
                height: parent.height
                text: Services.vpnText
                klass: Services.vpnClass
                textColor: Theme.comment
                classColors: ({
                    "connected": Theme.green,
                    "connected-killswitch": Theme.cyan,
                    "disconnected": Theme.comment
                })
                onModuleClicked: Quickshell.execDetached([bar.home + "/.local/bin/hyprconf-vpn", "toggle"])
            }

            Item { // network — FIXED width so changing rates don't reflow the
                    // rest of the right side (the annoying jitter). Left-
                    // aligned; extreme values elide rather than push.
                id: netItem
                width: 172
                height: parent.height

                BarText {
                    id: netText
                    x: 6
                    width: parent.width - 12
                    anchors.verticalCenter: parent.verticalCenter
                    elide: Text.ElideRight
                    color: Theme.cyan
                    // "/s" is implied for a rate; dropping it keeps the fixed
                    // width from eliding when both directions are in kB/s.
                    text: bar.netKind === "off" ? "󰖪 Disconnected"
                        : (bar.netKind === "wifi" ? "󰖩" : "󰈀")
                          + " ↓" + bar.netDown.replace("/s", "")
                          + " ↑" + bar.netUp.replace("/s", "")
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: bar.togglePopout("controlcenter", bar.itemCenterX(netItem))
                }
            }

            Item { // pulseaudio: click popout, middle mute, right pavucontrol, wheel ±5%
                id: volItem
                width: volText.implicitWidth + 16
                height: parent.height

                BarText {
                    id: volText
                    x: 8
                    anchors.verticalCenter: parent.verticalCenter
                    color: bar.muted ? Theme.red : Theme.pink
                    text: bar.muted ? "󰝟 Muted"
                        : (bar.vol <= 0.33 ? "󰕿" : bar.vol <= 0.66 ? "󰖀" : "󰕾")
                          + " " + Math.round(bar.vol * 100) + "%"
                }

                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
                    onClicked: mouse => {
                        if (mouse.button === Qt.MiddleButton && bar.sink?.audio)
                            bar.sink.audio.muted = !bar.sink.audio.muted
                        else if (mouse.button === Qt.RightButton)
                            Quickshell.execDetached(["pavucontrol"])
                        else
                            bar.togglePopout("volume", bar.itemCenterX(volItem))
                    }
                    onWheel: wheel => {
                        if (!bar.sink?.audio)
                            return
                        const step = wheel.angleDelta.y > 0 ? 0.05 : -0.05
                        bar.sink.audio.volume =
                            Math.max(0, Math.min(1, bar.sink.audio.volume + step))
                    }
                }
            }

            ScriptModule { // custom/power_status (Services polls at 1s; stops
                           // entirely on battery-less desktops via "once")
                height: parent.height
                text: Services.batText
                klass: Services.batClass
                textColor: Theme.fg
                // Theme tokens, not literals: hardcoded #ffffff "normal" text
                // was invisible on light themes.
                classColors: ({
                    "normal": Theme.fg,
                    "warning": Theme.yellow,
                    "critical": Theme.red,
                    "charging": Theme.green
                })
            }
        }
    }
}
