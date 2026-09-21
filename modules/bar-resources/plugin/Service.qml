// The plugin's data source: both feeders, and every value they produce, in ONE
// instance for the whole session.
//
// Why a service and not part of the widget: the bar is built once per monitor
// (`plugins/bar/Bar.qml`: `Variants { model: Quickshell.screens }`), so a
// Process the widget owns runs once per bar surface — two permanent streams,
// and on NVIDIA an NVML session, per screen for numbers identical on all of
// them. The service kind is that seam: shell.qml loads an enabled plugin's
// `entryPoints.service` once for the session, a third-party instance created
// unparented (shell.qml:923, Omarchy 4.0.3-1), and `omarchy plugin disable`
// destroys it with the bar entry — one id, one on/off switch.
//
// A stream that exits without ever producing a line means "no such hardware":
// it is left dead, and the GPU cells stay blank but sized. One that produced a
// line and then died IS restarted, on a backoff that gives up — 1 s, 2, 4, 8,
// 16, 32, then parked until the next shell restart, the ladder refilled by the
// next line. A feeder that dies instantly is the normal shape of dead hardware
// (nvidia-smi --loop exits at once when the driver stops answering), so a flat
// retry would never give up and would pay a failing NVML init every respawn.
// The "produced output" flag is latched, never cleared: it also decides what
// the GPU cells paint.

import QtQuick
import Quickshell.Io

Item {
  id: root

  // This plugin's own folder, trailing slash included: the shell loads an entry
  // point as a percent-encoded file:// URL, so this is the path the feeders are
  // run by — absolute, never a bare name on PATH (README › Host contract).
  readonly property string pluginDir: decodeURIComponent(String(Qt.resolvedUrl(".")).replace(/^file:\/\//, ""))

  property bool statsProduced: false
  property int cpuPct: 0
  property var cpuTemp: null       // °C, or null where there is no sensor
  property string memText: ""
  property string netDown: "0B/s"
  property string netUp: "0B/s"

  property bool gpuProduced: false
  property int gpuUtil: 0
  property var gpuTemp: null
  property string gpuVramUsed: ""
  property string gpuVramTotal: ""
  property string gpuTooltip: ""

  // The restart ladder of one feeder — see the header. `attempt` is the number
  // of restarts since the last line that parsed.
  component Restarter: Timer {
    id: restarter
    property var proc: null
    property int attempt: 0
    readonly property int maxAttempts: 6
    interval: 1000
    onTriggered: if (restarter.proc) restarter.proc.running = true
    function produced() { restarter.attempt = 0 }
    function died() {
      if (restarter.attempt >= restarter.maxAttempts) return
      restarter.interval = 1000 * (1 << restarter.attempt)
      restarter.attempt++
      restarter.start()
    }
  }

  Process {
    id: statsProc
    running: true
    command: [root.pluginDir + "bin/hyprconf-stats"]
    stdout: SplitParser {
      onRead: data => {
        try {
          const j = JSON.parse(data)
          root.statsProduced = true
          root.cpuPct = j.cpu
          root.cpuTemp = j.temp
          root.memText = j.mem
          root.netDown = j.down
          root.netUp = j.up
          statsRestartTimer.produced()
        } catch (e) {}
      }
    }
    onExited: if (root.statsProduced) statsRestartTimer.died()
  }

  Restarter {
    id: statsRestartTimer
    proc: statsProc
  }

  Process {
    id: gpuProc
    running: true
    command: [root.pluginDir + "bin/hyprconf-gpu-info"]
    stdout: SplitParser {
      onRead: data => {
        try {
          const j = JSON.parse(data)
          root.gpuProduced = true
          root.gpuUtil = j.util
          root.gpuTemp = j.temp
          root.gpuVramUsed = j.vram_used
          root.gpuVramTotal = j.vram_total
          root.gpuTooltip = j.tooltip
          gpuRestartTimer.produced()
        } catch (e) {}
      }
    }
    onExited: if (root.gpuProduced) gpuRestartTimer.died()
  }

  Restarter {
    id: gpuRestartTimer
    proc: gpuProc
  }
}
