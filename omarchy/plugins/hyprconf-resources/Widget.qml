// CPU / temp / memory / GPU / network readout, ported from hyprconf's
// quickshell bar (stow/quickshell/.config/quickshell/Bar.qml + Services.qml).
// Streams JSON off two long-lived background scripts rather than polling:
//   hyprconf-stats     — cpu%, mem, net down/up, cpu temp (one line/sec)
//   hyprconf-gpu-info  — nvidia-smi --loop or an AMD sysfs loop
// Both are installed onto PATH by omarchy/install.sh (the same convention
// Omarchy's own plugins follow) rather than bundled in this plugin
// directory — no first-party Omarchy plugin bundles its own scripts either;
// they all shell out to standalone tools by name.
//
// Omarchy's Color singleton only exposes semantic roles (foreground, accent,
// urgent, muted, background) — not hyprconf's per-metric hues (green cpu,
// yellow mem, purple gpu), which no Omarchy theme is obliged to define. So
// every segment renders in the same foreground color, matching how Omarchy's
// own text-based widgets behave.
//
// Specifically NOT `muted`: that role is the theme's dimmed text, meant for
// secondary chrome, and it made four of the five readings look switched off
// next to the one drawn in foreground. A reading is a reading — they all
// carry equal weight, so they all get the same colour.

import QtQuick
import Quickshell
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

  property string gpuText: ""
  property bool gpuProduced: false

  visible: true
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
  // output means "no such hardware" and stays hidden, same as hyprconf's
  // Services singleton.
  Process {
    id: gpuProc
    running: true
    command: ["hyprconf-gpu-info"]
    stdout: SplitParser {
      onRead: data => {
        try {
          root.gpuProduced = true
          root.gpuText = String(JSON.parse(data).text ?? "")
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

  // Two stacked lines rather than one long row. Omarchy's bar is 26px tall and
  // a single line of caption text uses about half of it, so the second line is
  // free vertical space that was already being paid for — spending it halves
  // how much of the bar's width this widget eats.
  //
  // A Grid rather than nested Rows so the same declaration serves a vertical
  // bar: `columns: 1` stacks all four segments, which is the only sane shape
  // when the bar is a side rail. Column widths are the widest cell, so the two
  // lines align into tidy columns instead of drifting.
  Grid {
    id: grid
    anchors.verticalCenter: parent.verticalCenter
    columns: root.vertical ? 1 : 2
    rowSpacing: 0
    columnSpacing: Style.spacing.sm
    flow: Grid.LeftToRight

    // Line 1 — compute: CPU load and temperature, then the GPU readout
    // (hyprconf-gpu-info already packs util, temp and VRAM into one string).
    //
    // Each line is prefixed with a Nerd Font glyph — a microchip for CPU, a
    // memory stick for RAM — because stacking the numbers costs the reading
    // order that a single row gave for free: "3% 52°" over "7.4/54.6G" says
    // nothing about which is which.
    Text {
      text: "\u{F2DB} " + root.cpuPct + "%" + (root.cpuTemp !== "" ? " " + root.cpuTemp : "")
      color: Color.foreground
      font.pixelSize: Style.font.caption
      font.family: Style.fontFamily
      lineHeight: root.lineHeightScale
      lineHeightMode: Text.ProportionalHeight

      MouseArea {
        anchors.fill: parent
        // Omarchy's own TUI launcher: it focuses an existing btop window
        // instead of stacking another, gives it the org.omarchy.btop app-id its
        // window rules key off, and keeps the terminal open. `kitty -e htop`
        // opened a window that exited immediately — htop is not installed, and
        // nothing reported that.
        onClicked: if (root.bar) root.bar.run("omarchy-launch-or-focus-tui btop")
      }
    }

    Text {
      visible: root.gpuProduced && root.gpuText !== ""
      text: root.gpuText
      color: Color.foreground
      font.pixelSize: Style.font.caption
      font.family: Style.fontFamily
      lineHeight: root.lineHeightScale
      lineHeightMode: Text.ProportionalHeight
    }

    // Line 2 — memory and I/O.
    Text {
      visible: root.memText !== ""
      text: "\u{F061A} " + root.memText
      color: Color.foreground
      font.pixelSize: Style.font.caption
      font.family: Style.fontFamily
      lineHeight: root.lineHeightScale
      lineHeightMode: Text.ProportionalHeight
    }

    Text {
      visible: root.netDown !== "0B/s" || root.netUp !== "0B/s"
      text: "↓" + root.netDown + " ↑" + root.netUp
      color: Color.foreground
      font.pixelSize: Style.font.caption
      font.family: Style.fontFamily
      lineHeight: root.lineHeightScale
      lineHeightMode: Text.ProportionalHeight
    }
  }
}
