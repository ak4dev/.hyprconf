// CPU / temp / memory / GPU / network readout, ported from hyprconf's
// quickshell bar (stow/quickshell/.config/quickshell/Bar.qml + Services.qml).
// Streams JSON off two long-lived background scripts rather than polling:
//   hyprconf-stats     — cpu%, mem, net down/up, cpu temp (one line/sec)
//   hyprconf-gpu-info  — nvidia-smi --loop or an AMD sysfs loop
// Both are installed onto PATH by omarchy/install.sh (same convention as
// hyprconf's own hyprconf-brightness) rather than bundled in this plugin
// directory — no first-party Omarchy plugin bundles its own scripts either;
// they all shell out to standalone tools by name.
//
// Omarchy's Color singleton only exposes semantic roles (foreground/accent/
// muted), not hyprconf's per-metric hues (green cpu, yellow mem, purple
// gpu) — so unlike hyprconf's bar, every segment here renders in the same
// foreground color, matching how Omarchy's own text-based widgets behave.

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
  implicitWidth: row.implicitWidth
  implicitHeight: parent ? parent.height : row.implicitHeight

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

  Row {
    id: row
    anchors.verticalCenter: parent ? parent.verticalCenter : undefined
    spacing: Style.spacing.sm

    Text {
      text: root.cpuPct + "%" + (root.cpuTemp !== "" ? " " + root.cpuTemp : "")
      color: Color.foreground
      font.pixelSize: Style.font.bodySmall
      font.family: Style.fontFamily

      MouseArea {
        anchors.fill: parent
        onClicked: if (root.bar) root.bar.run("kitty -e htop")
      }
    }

    Text {
      visible: root.memText !== ""
      text: root.memText
      color: Color.muted
      font.pixelSize: Style.font.bodySmall
      font.family: Style.fontFamily
    }

    Text {
      visible: root.gpuProduced && root.gpuText !== ""
      text: root.gpuText
      color: Color.muted
      font.pixelSize: Style.font.bodySmall
      font.family: Style.fontFamily
    }

    Text {
      visible: root.netDown !== "0B/s" || root.netUp !== "0B/s"
      text: "↓" + root.netDown + " ↑" + root.netUp
      color: Color.muted
      font.pixelSize: Style.font.bodySmall
      font.family: Style.fontFamily
    }
  }
}
