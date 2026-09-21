// CPU / RAM / net and GPU / VRAM readout. Two aligned lines:
//
//     <cpu>  <thermo>41°   3%   <mem> 12.7/94.2G   ↑ 12.3kB/s
//     <gpu>  <thermo>36°   7%   <mem>  2.3/32.6G   ↓ 1.2MB/s
//
// Layout only: every number comes from Service.qml, this plugin's other entry
// point, which the shell loads once for the session (its header has the seam
// and why).
//
// The accessor for an installed third-party widget is `bar.shell.serviceFor
// (<own id>)`: on Omarchy 4.0.3-1 `bar` is a Ui/PluginBarApi.qml facade
// (shell/plugins/bar/Bar.qml:2002-2003) and its `shell` a
// services/PluginShellApi.qml whose `serviceFor` answers only for ids this
// plugin owns (PluginShellApi.qml:30 → shell.qml:385-394). It is NOT
// `firstPartyServiceFor`, which on 4.0.3 is a narrow proxy over four
// `omarchy.*` ids (shell.qml:592-596) and is what the stock `omarchy.media`
// widget uses on itself (shell/plugins/services/media/BarWidget.qml:10). It
// is null until the service is up, and under a replacement bar, whose
// widgets get a service-less entry facade (Bar.qml:238-242); every cell
// then shows the blank/zero it shows before the first line arrives.
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
  readonly property var feed: root.bar?.shell?.serviceFor("hyprconf.resources")

  readonly property int cpuPct: root.feed ? root.feed.cpuPct : 0
  readonly property var cpuTemp: root.feed ? root.feed.cpuTemp : null
  readonly property string memText: root.feed ? root.feed.memText : ""
  readonly property string netDown: root.feed ? root.feed.netDown : "0B/s"
  readonly property string netUp: root.feed ? root.feed.netUp : "0B/s"

  readonly property bool gpuProduced: root.feed ? root.feed.gpuProduced : false
  readonly property int gpuUtil: root.feed ? root.feed.gpuUtil : 0
  readonly property var gpuTemp: root.feed ? root.feed.gpuTemp : null
  readonly property string gpuVramUsed: root.feed ? root.feed.gpuVramUsed : ""
  readonly property string gpuVramTotal: root.feed ? root.feed.gpuVramTotal : ""
  readonly property string gpuTooltip: root.feed ? root.feed.gpuTooltip : ""

  readonly property string glyphCpu: "\u{F2DB}"
  readonly property string glyphGpu: "\u{F08AE}"
  readonly property string glyphMem: "\u{F061A}"
  readonly property string glyphThermo: "\u{F050F}"

  readonly property string fontFamily: root.bar ? root.bar.fontFamily : Style.fontFamily
  readonly property color textColor: root.bar ? root.bar.barForeground : Color.foreground

  implicitWidth: grid.implicitWidth
  // NEVER size this off `parent`: the bar's ModuleSlot takes its height from
  // the widget's implicit size, so `parent.height` closes a binding loop that
  // QML resolves by dropping the binding — a zero-height, invisible widget.
  implicitHeight: grid.implicitHeight

  // The feeders emit a temperature as °C or null; the unit and the glyph are
  // the widget's, for both rows.
  function tempText(t) { return (t === null || t === undefined) ? "" : root.glyphThermo + t + "° " }
  function vramText() {
    if (root.gpuVramTotal === "" || root.gpuVramTotal === "0") return "shared"
    return root.gpuVramUsed + "/" + root.gpuVramTotal + "G"
  }

  // Column widths: the widest thing each column can ever say, in the bar's
  // own font, so the grid never re-flows. Measured, not guessed — a font
  // change (omarchy font set) re-measures automatically.
  component Col: TextMetrics {
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }

  Col { id: loadCol; text: root.glyphGpu + " " + root.glyphThermo + "100° 100%" }
  Col { id: memCol; text: root.glyphMem + " 999.9/999.9G" }
  Col { id: netCol; text: "↓ 999.9MB/s" }

  component Cell: Text {
    // Feeder strings are untrusted-adjacent (device names, interface names):
    // never rich-text parsed — the hardening the stock window-title widget
    // has (plugins/bar/widgets/ActiveWindow.qml:32, Omarchy 4.0.3-1).
    textFormat: Text.PlainText
    color: root.textColor
    font.pixelSize: Style.font.caption
    font.family: root.fontFamily
    // Text's default is NATURAL alignment, which flips whole under an RTL
    // layout direction; these cells are fixed-width columns of numbers.
    horizontalAlignment: Text.AlignLeft
  }

  // Row-major grid, three columns: load | memory | net. A vertical bar (side
  // rail) stacks all six cells in one column instead.
  Grid {
    id: grid
    anchors.verticalCenter: parent.verticalCenter
    columns: root.vertical ? 1 : 3
    // 15 % of Omarchy's small spacing token — a hairline. The fixed-width
    // columns carry their own slack (a column is as wide as its widest value,
    // so "0B/s" sits in the room "999.9MB/s" needs); that slack, not this
    // gap, is what keeps the line from shifting.
    columnSpacing: Style.spacing.sm * 0.15

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
