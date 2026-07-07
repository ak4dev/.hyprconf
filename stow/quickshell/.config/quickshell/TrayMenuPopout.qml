import QtQuick
import Quickshell
import Quickshell.Widgets

// Custom-rendered SNI/dbusmenu tray menu in the frosted popout style.
// Submenus push onto a stack (with a back row) instead of spawning nested
// windows. Labels are external strings — rendered PlainText only, never
// interpolated into commands.
Column {
    id: root
    spacing: 2
    width: 240

    required property var handle   // QsMenuHandle from SystemTrayItem.menu
    signal dismissed()

    property var stack: [handle]

    QsMenuOpener {
        id: opener
        menu: root.stack[root.stack.length - 1]
    }

    // back row when inside a submenu
    Rectangle {
        visible: root.stack.length > 1
        width: parent.width
        height: 26
        radius: 6
        color: backM.containsMouse ? Theme.hover : "transparent"

        BarText {
            x: 6
            anchors.verticalCenter: parent.verticalCenter
            font.pixelSize: 12
            text: "󰅁  Back"
            color: Theme.cyan
        }

        MouseArea {
            id: backM
            anchors.fill: parent
            hoverEnabled: true
            onClicked: root.stack = root.stack.slice(0, -1)
        }
    }

    Repeater {
        model: opener.children

        delegate: Rectangle {
            id: entryRow
            required property var modelData

            width: parent.width
            height: modelData.isSeparator ? 9 : 28
            radius: 6
            color: !modelData.isSeparator && entryM.containsMouse && modelData.enabled
                 ? Theme.hover : "transparent"

            // separator
            Rectangle {
                visible: entryRow.modelData.isSeparator
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 12
                x: 6
                height: 1
                color: Theme.divider
            }

            Row {
                visible: !entryRow.modelData.isSeparator
                x: 8
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                // checkbox / radio state
                BarText {
                    visible: entryRow.modelData.buttonType !== QsMenuButtonType.None
                    font.pixelSize: 12
                    text: {
                        const e = entryRow.modelData
                        if (e.buttonType === QsMenuButtonType.CheckBox)
                            return e.checkState === Qt.Checked ? "󰄲" : "󰄱"
                        return e.checkState === Qt.Checked ? "󰐾" : "󰄰"
                    }
                    color: entryRow.modelData.checkState === Qt.Checked ? Theme.green : Theme.comment
                }

                IconImage {
                    visible: entryRow.modelData.icon !== ""
                    implicitSize: 14
                    anchors.verticalCenter: parent.verticalCenter
                    source: entryRow.modelData.icon
                }

                BarText {
                    font.pixelSize: 12
                    width: root.width - 40
                    elide: Text.ElideRight
                    text: entryRow.modelData.text
                    color: entryRow.modelData.enabled ? Theme.fg : "#66928374"
                }
            }

            // submenu chevron
            BarText {
                visible: !entryRow.modelData.isSeparator && entryRow.modelData.hasChildren
                anchors.right: parent.right
                anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                font.pixelSize: 12
                text: "󰅂"
                color: Theme.comment
            }

            MouseArea {
                id: entryM
                anchors.fill: parent
                hoverEnabled: true
                enabled: !entryRow.modelData.isSeparator && entryRow.modelData.enabled
                onClicked: {
                    const e = entryRow.modelData
                    if (e.hasChildren) {
                        root.stack = root.stack.concat([e])
                    } else {
                        e.triggered()
                        root.dismissed()
                    }
                }
            }
        }
    }

    BarText {
        visible: opener.children.values.length === 0 && root.stack.length === 1
        font.pixelSize: 12
        text: "(no menu)"
        color: Theme.comment
    }
}
