import QtQuick

// Month calendar (upgrade of waybar's clock tooltip). Click the title to
// jump back to the current month.
Column {
    id: root
    spacing: 8

    property date shown: new Date()

    function monthShift(delta) {
        const d = new Date(shown)
        d.setDate(1)
        d.setMonth(d.getMonth() + delta)
        root.shown = d
    }

    // header: ‹ July 2026 ›
    Item {
        width: grid.width
        height: 24

        BarText {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: "󰅁"
            color: navL.containsMouse ? Theme.cyan : Theme.comment
            MouseArea {
                id: navL
                anchors.fill: parent
                anchors.margins: -6
                hoverEnabled: true
                onClicked: root.monthShift(-1)
            }
        }

        BarText {
            anchors.centerIn: parent
            text: Qt.formatDate(root.shown, "MMMM yyyy")
            color: titleM.containsMouse ? Theme.cyan : Theme.accent
            MouseArea {
                id: titleM
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.shown = new Date()
            }
        }

        BarText {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "󰅂"
            color: navR.containsMouse ? Theme.cyan : Theme.comment
            MouseArea {
                id: navR
                anchors.fill: parent
                anchors.margins: -6
                hoverEnabled: true
                onClicked: root.monthShift(1)
            }
        }
    }

    Grid {
        id: grid
        columns: 7
        spacing: 2

        // day-of-week header, Sunday first (en_US, matching the clock format)
        Repeater {
            model: ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
            delegate: Item {
                required property string modelData
                width: 30
                height: 22
                BarText {
                    anchors.centerIn: parent
                    text: parent.modelData
                    font.pixelSize: 12
                    color: Theme.comment
                }
            }
        }

        Repeater {
            model: {
                const y = root.shown.getFullYear()
                const m = root.shown.getMonth()
                const first = new Date(y, m, 1)
                const start = new Date(y, m, 1 - first.getDay())
                const today = new Date()
                const cells = []
                for (let i = 0; i < 42; i++) {
                    const d = new Date(start)
                    d.setDate(start.getDate() + i)
                    cells.push({
                        day: d.getDate(),
                        inMonth: d.getMonth() === m,
                        today: d.getFullYear() === today.getFullYear()
                            && d.getMonth() === today.getMonth()
                            && d.getDate() === today.getDate()
                    })
                }
                return cells
            }

            delegate: Rectangle {
                id: cell
                required property var modelData
                width: 30
                height: 26
                radius: 8
                color: modelData.today ? Theme.accent : "transparent"

                BarText {
                    anchors.centerIn: parent
                    text: String(cell.modelData.day)
                    font.pixelSize: 12
                    color: cell.modelData.today ? "#282828"
                         : cell.modelData.inMonth ? Theme.fg
                         : "#66928374"
                }
            }
        }
    }
}
