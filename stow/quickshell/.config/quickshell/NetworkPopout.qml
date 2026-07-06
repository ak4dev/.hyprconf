import QtQuick

// Network details (upgrade of waybar's network tooltip): interface, IP,
// live rates and session totals, fed by stats.sh via the bar.
Column {
    id: root
    spacing: 6
    width: 260

    required property var barWin

    component InfoRow: Row {
        property string label
        property string value
        property color valueColor: Theme.fg
        width: parent.width

        BarText {
            width: 96
            font.pixelSize: 12
            text: parent.label
            color: Theme.comment
        }
        BarText {
            width: parent.width - 96
            font.pixelSize: 12
            elide: Text.ElideRight
            text: parent.value
            color: parent.valueColor
        }
    }

    BarText {
        text: barWin.netKind === "off" ? "󰖪  Disconnected"
            : barWin.netKind === "wifi" ? "󰖩  Wi-Fi" : "󰈀  Ethernet"
        color: barWin.netKind === "off" ? Theme.comment : Theme.cyan
    }

    Rectangle { width: parent.width; height: 1; color: Theme.divider }

    InfoRow { label: "Interface"; value: barWin.netIface || "—" }
    InfoRow { label: "IPv4"; value: barWin.netIp || "—" }
    InfoRow { label: "Download"; value: "↓ " + barWin.netDown; valueColor: Theme.green }
    InfoRow { label: "Upload"; value: "↑ " + barWin.netUp; valueColor: Theme.orange }

    Rectangle { width: parent.width; height: 1; color: Theme.divider }

    InfoRow { label: "Session ↓"; value: barWin.netRxTotal || "—" }
    InfoRow { label: "Session ↑"; value: barWin.netTxTotal || "—" }
}
