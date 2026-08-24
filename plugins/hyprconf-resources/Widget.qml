// CPU / RAM / net and GPU / VRAM readout, ported from hyprconf's retired
// quickshell bar. Two aligned lines:
//
//     <cpu>  <thermo>41°   3%   <mem> 12.7/94.2G   ↑ 12.3kB/s
//     <gpu>  <thermo>36°   7%   <mem>  2.3/32.6G   ↓ 1.2MB/s
//
// Streams JSON off two long-lived background scripts rather than polling:
//   hyprconf-stats     — cpu%, cpu temp, mem, net down/up (one line/sec)
//   hyprconf-gpu-info  — the ACTIVE GPU's util/temp/VRAM (one line/2s): on a
//                        multi-GPU box the card with the most VRAM in use,
//                        re-picked every sample, so an idle second card
//                        never shadows the one doing the work
// Both are installed onto PATH by install.sh (the convention Omarchy's own
// plugins follow — none bundles its scripts; they shell out by name). The bar
// is built per monitor (Bar.qml's `Variants { model: Quickshell.screens }`),
// so each bar surface runs its own pair of feeders — the same per-instance
// Process pattern Omarchy's KeyboardLayout.qml and SystemUpdate.qml use.
//
// Every column has a FIXED width, measured once with TextMetrics from the
// widest value it can show, so the line never shifts as a speed goes from
// "0B/s" to "999.9MB/s" or a percentage from "3%" to "100%".
//
// Glyphs are the widget's own (the feeders emit numbers only): microchip
// (nf-fa-microchip U+F2DB), expansion card (nf-md-expansion_card U+F08AE),
// memory (nf-md-memory U+F061A) and the thermometer (nf-md-thermometer
// U+F050F — a solid Material Design glyph; the Weather-Icons one at U+E350
// the old feeder used is an outline that renders as a hairline at caption
// size, i.e. invisible). All four verified present in GeistMono Nerd Font
// (fc-list ':charset=…'), Omarchy's default bar font.
//
// Omarchy's Color singleton only exposes semantic roles (foreground, accent,
// urgent, muted, background) — not per-metric hues — so every segment
// renders in the bar's foreground, matching Omarchy's own text widgets.

import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "hyprconf.resources"

  property int cpuPct: 0
  property string cpuTemp: ""
  property string memText: ""
  property string netDown: "0B/s"
  property string netUp: "0B/s"

  property bool gpuProduced: false
  property int gpuUtil: 0
  property string gpuTemp: ""
  property string gpuVramUsed: ""
  property string gpuVramTotal: ""
  property string gpuTooltip: ""

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

  Process {
    id: statsProc
    running: true
    command: ["hyprconf-stats"]
    stdout: SplitParser {
      onRead: data => {
        try {
          const j = JSON.parse(data)
          root.cpuPct = j.cpu
          root.memText = j.mem
          root.netDown = j.down
          root.netUp = j.up
          root.cpuTemp = j.temp ?? ""
        } catch (e) {}
      }
    }
  }

  // A stream that produced output and then died is restarted (driver
  // hiccup / transient error); one that exits without ever producing
  // output means "no such hardware" and is left alone — the GPU cells
  // below stay blank (but sized, so the grid holds its shape).
  Process {
    id: gpuProc
    running: true
    command: ["hyprconf-gpu-info"]
    stdout: SplitParser {
      onRead: data => {
        try {
          const j = JSON.parse(data)
          root.gpuProduced = true
          root.gpuUtil = Number(j.util ?? 0)
          root.gpuTemp = (j.temp === null || j.temp === undefined) ? "" : String(j.temp) + "°"
          root.gpuVramUsed = String(j.vram_used ?? "")
          root.gpuVramTotal = String(j.vram_total ?? "")
          root.gpuTooltip = String(j.tooltip ?? "")
        } catch (e) {}
      }
    }
    onExited: function() {
      if (root.gpuProduced) restartTimer.start()
    }
  }

  Timer {
    id: restartTimer
    interval: 1000
    onTriggered: gpuProc.running = true
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
