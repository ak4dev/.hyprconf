// CPU / RAM / net and GPU / VRAM readout. Two aligned lines:
//
//     <cpu>  <thermo>41°   3%   <mem> 12.7/94.2G   ↑ 12.3kB/s
//     <gpu>  <thermo>36°   7%   <mem>  2.3/32.6G   ↓ 1.2MB/s
//
// Layout only. The numbers come from Service.qml, this plugin's other entry
// point, which the shell loads ONCE for the session (see its header for the
// seam and why): the bar is built per monitor (Bar.qml's `Variants { model:
// Quickshell.screens }`), so anything owned by this file runs once per bar
// surface, and two long-lived feeder processes per screen for globally
// identical numbers is exactly what the service kind exists to avoid.
//
// The accessor is the one Omarchy's own `omarchy.media` bar widget uses on
// its own service (shell/plugins/services/media/BarWidget.qml:10) —
// `bar?.shell?.firstPartyServiceFor(id)`, spelled here with its real name,
// `serviceFor` (shell.qml, 4.0.2-1: firstPartyServiceFor is a one-line
// alias for it). It is null until the service is up, and on a third-party
// bar that carries no `shell`: every cell then shows the blank/zero it
// shows before the first line arrives, which is the same reading the widget
// gives during the second between startup and the first sample.
//
// Every column has a FIXED width, measured once with TextMetrics from the
// widest value it can show, so the line never shifts as a speed goes from
// "0B/s" to "999.9MB/s" or a percentage from "3%" to "100%".
//
// Glyphs are the widget's own (the feeders emit numbers only): microchip
// (nf-fa-microchip U+F2DB), expansion card (nf-md-expansion_card U+F08AE),
// memory (nf-md-memory U+F061A) and the thermometer (nf-md-thermometer
// U+F050F — a solid Material Design glyph; the Weather-Icons one at U+E350
// is an outline that renders as a hairline at caption size, i.e. invisible).
// All four verified present in GeistMono Nerd Font
// (fc-list ':charset=…'), Omarchy's default bar font.
//
// Omarchy's Color singleton only exposes semantic roles (foreground, accent,
// urgent, muted, background) — not per-metric hues — so every segment
// renders in the bar's foreground, matching Omarchy's own text widgets.

import QtQuick
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "hyprconf.resources"

  // The one service instance behind every bar surface — see the header.
  // Literal id, not `moduleName`: the bar overwrites a widget's moduleName
  // from its slot id (Bar.qml's ModuleSlot.injectProps), and the service is
  // keyed by the manifest id, which is what this plugin is registered under.
  readonly property var feed: root.bar?.shell?.serviceFor("hyprconf.resources") ?? null

  readonly property int cpuPct: root.feed ? root.feed.cpuPct : 0
  readonly property string cpuTemp: root.feed ? root.feed.cpuTemp : ""
  readonly property string memText: root.feed ? root.feed.memText : ""
  readonly property string netDown: root.feed ? root.feed.netDown : "0B/s"
  readonly property string netUp: root.feed ? root.feed.netUp : "0B/s"

  readonly property bool gpuProduced: root.feed ? root.feed.gpuProduced : false
  readonly property int gpuUtil: root.feed ? root.feed.gpuUtil : 0
  readonly property string gpuTemp: root.feed ? root.feed.gpuTemp : ""
  readonly property string gpuVramUsed: root.feed ? root.feed.gpuVramUsed : ""
  readonly property string gpuVramTotal: root.feed ? root.feed.gpuVramTotal : ""
  readonly property string gpuTooltip: root.feed ? root.feed.gpuTooltip : ""

  readonly property string glyphCpu: "\u{F2DB}"
  readonly property string glyphGpu: "\u{F08AE}"
  readonly property string glyphMem: "\u{F061A}"
  readonly property string glyphThermo: "\u{F050F}"

  readonly property string fontFamily: root.bar ? root.bar.fontFamily : Style.fontFamily
  readonly property color textColor: root.bar ? root.bar.barForeground : Color.foreground

  // Two lines of text in a 26px bar only fit if the line box is the glyph box.
  // Qt's default proportional line height adds ~20% leading per line, which at
  // caption size overflows the bar and clips the second line.
  readonly property real lineHeightScale: 1.0

  implicitWidth: grid.implicitWidth
  // NEVER size this off `parent`. The bar's ModuleSlot takes its own height
  // from the widget's implicit size, so `parent.height` here closes a binding
  // loop — and QML breaks a loop by dropping the binding, leaving the widget
  // zero-height. It still loads, logs nothing at any verbosity, and paints
  // nothing: the bar simply has an invisible gap where the readout should be.
  implicitHeight: grid.implicitHeight

  function tempText(t) { return t !== "" ? root.glyphThermo + t + " " : "" }
  function vramText() {
    if (root.gpuVramTotal === "" || root.gpuVramTotal === "0") return "shared"
    return root.gpuVramUsed + "/" + root.gpuVramTotal + "G"
  }

  // Column widths: the widest thing each column can ever say, in the bar's
  // own font, so the grid never re-flows. Measured, not guessed — a font
  // change (omarchy font set) re-measures automatically.
  TextMetrics {
    id: loadCol
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    text: root.glyphGpu + " " + root.glyphThermo + "100° 100%"
  }
  TextMetrics {
    id: memCol
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    text: root.glyphMem + " 999.9/999.9G"
  }
  TextMetrics {
    id: netCol
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    text: "↓ 999.9MB/s"
  }

  component Cell: Text {
    // Feeder strings are untrusted-adjacent (device names, interface names):
    // never rich-text parsed — the same hardening stock 4.0.2 applies to
    // window titles.
    textFormat: Text.PlainText
    color: root.textColor
    font.pixelSize: Style.font.caption
    font.family: root.fontFamily
    lineHeight: root.lineHeightScale
    lineHeightMode: Text.ProportionalHeight
    horizontalAlignment: Text.AlignLeft
    elide: Text.ElideNone
  }

  // Row-major grid, three columns: load | memory | net. A vertical bar (side
  // rail) stacks all six cells in one column instead.
  Grid {
    id: grid
    anchors.verticalCenter: parent.verticalCenter
    columns: root.vertical ? 1 : 3
    rowSpacing: 0
    // 15 % of Omarchy's small spacing token — a hairline. The fixed-width
    // columns carry their own slack (a column is as wide as its widest value,
    // so "0B/s" sits in the room "999.9MB/s" needs); that slack, not this
    // gap, is what keeps the line from shifting.
    columnSpacing: Style.spacing.sm * 0.15
    flow: Grid.LeftToRight

    // ── line 1: CPU temp/util · RAM · upload ──────────────────────────────
    Cell {
      width: loadCol.width
      text: root.glyphCpu + " " + root.tempText(root.cpuTemp) + root.cpuPct + "%"

      MouseArea {
        anchors.fill: parent
        // Omarchy's own TUI launcher: it focuses an existing btop window
        // instead of stacking another and gives it the org.omarchy.btop
        // app-id its window rules key off.
        onClicked: if (root.bar) root.bar.run("omarchy-launch-or-focus-tui btop")
      }
    }
    Cell {
      width: memCol.width
      text: root.memText !== "" ? root.glyphMem + " " + root.memText : ""
    }
    Cell {
      width: netCol.width
      text: "↑ " + root.netUp
    }

    // ── line 2: GPU temp/util · VRAM · download ───────────────────────────
    // Empty (but still sized) cells when no GPU stream ever produced output,
    // so the download cell stays under the upload one.
    Cell {
      width: loadCol.width
      text: root.gpuProduced
        ? root.glyphGpu + " " + root.tempText(root.gpuTemp) + root.gpuUtil + "%"
        : ""

      MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onEntered: if (root.bar && root.gpuTooltip !== "") root.bar.showTooltip(root, root.gpuTooltip)
        onExited: if (root.bar) root.bar.hideTooltip(root)
      }
    }
    Cell {
      width: memCol.width
      text: root.gpuProduced ? root.glyphMem + " " + root.vramText() : ""
    }
    Cell {
      width: netCol.width
      text: "↓ " + root.netDown
    }
  }
}
