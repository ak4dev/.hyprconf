import QtQuick
import Quickshell
import Quickshell.Wayland

// Rounded screen corners (fake bezel), one window per screen. Fullscreen
// overlay with an EMPTY input region: clicks pass straight through; this
// surface is purely cosmetic.
PanelWindow {
    id: win

    required property var modelData
    screen: modelData

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"
    WlrLayershell.namespace: "quickshell:corners"
    mask: Region {}

    readonly property int r: 12

    Repeater {
        model: [
            { ax: 0, ay: 0 },  // top-left
            { ax: 1, ay: 0 },  // top-right
            { ax: 0, ay: 1 },  // bottom-left
            { ax: 1, ay: 1 }   // bottom-right
        ]

        delegate: Canvas {
            required property var modelData
            width: win.r
            height: win.r
            x: modelData.ax === 0 ? 0 : win.width - win.r
            y: modelData.ay === 0 ? 0 : win.height - win.r

            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                ctx.fillStyle = "black"
                ctx.fillRect(0, 0, width, height)
                ctx.globalCompositeOperation = "destination-out"
                ctx.beginPath()
                // circle centered on the inner corner
                ctx.arc(modelData.ax === 0 ? width : 0,
                        modelData.ay === 0 ? height : 0,
                        win.r, 0, Math.PI * 2)
                ctx.fill()
            }
        }
    }
}
