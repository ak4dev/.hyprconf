import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland

// Frosted popout panel hanging below the bar (macOS-menu style). Positioned
// by the horizontal center of the module that opened it; dismissed by
// clicking anywhere outside (Hyprland focus grab).
PanelWindow {
    id: win

    required property var bar
    property real anchorX: 0
    property bool open: false
    property Component contentComponent: null

    function close() {
        open = false
    }

    visible: open && contentComponent !== null

    WlrLayershell.namespace: "quickshell:popouts"
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    anchors {
        top: true
        left: true
    }

    // 12px breathing room for the drop shadow on every side.
    readonly property int pad: 12
    implicitWidth: (content.item ? content.item.implicitWidth + 24 : 0) + pad * 2
    implicitHeight: (content.item ? content.item.implicitHeight + 24 : 0) + pad * 2

    margins {
        top: 24 + 4 - pad
        left: Math.round(Math.max(
                  8 - pad,
                  Math.min(win.anchorX - win.implicitWidth / 2,
                           win.screen.width - win.implicitWidth - 8 + pad)))
    }

    HyprlandFocusGrab {
        active: win.visible
        windows: [win, win.bar]
        onCleared: win.close()
    }

    Item {
        id: frame
        anchors.fill: parent
        anchors.margins: win.pad
        opacity: win.open ? 1 : 0
        scale: win.open ? 1 : 0.97
        transformOrigin: Item.Top

        Behavior on opacity {
            NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic }
        }
        Behavior on scale {
            NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic }
        }

        RectangularShadow {
            anchors.fill: panel
            radius: panel.radius
            blur: 24
            spread: 0
            color: Theme.shadow
            offset: Qt.vector2d(0, 4)
        }

        Rectangle {
            id: panel
            anchors.fill: parent
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.surfaceBorder
        }

        Loader {
            id: content
            active: win.open && win.contentComponent !== null
            sourceComponent: win.contentComponent
            anchors.centerIn: parent
        }
    }
}
