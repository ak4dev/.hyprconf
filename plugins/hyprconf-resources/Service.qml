// The plugin's data source: BOTH feeders, and every value they produce, in
// ONE instance for the whole session.
//
// Why this is a service and not part of the widget. Omarchy builds the bar
// once per monitor (`plugins/bar/Bar.qml`: `Variants { model:
// Quickshell.screens }`), so a widget that owns its own Process pair runs
// that pair once per bar surface — two processes and ~12 MB per screen,
// linear, and on NVIDIA an independent NVML session per screen, all for
// numbers that are identical on every monitor. Omarchy has a seam for
// exactly this and AGENTS.md rule 1 says to use it: shell.qml's service
// host loads any ENABLED plugin that declares `kinds: ["service"]` with an
// `entryPoints.service` once into a hidden Item, first-party or not
// ("third-party services are enabled by adding the plugin id to
// shell.json" — shell.qml, `_syncServices` / `ensureService`, Omarchy
// 4.0.2-1). The stock `omarchy.media` plugin is the same shape: one
// manifest declaring both `service` and `bar-widget`, a Service.qml holding
// the state and a BarWidget.qml that reads it back through
// `bar?.shell?.firstPartyServiceFor(...)` — which is `serviceFor` under
// another name (shell.qml). `omarchy-plugin-validate` carries `service` in
// its kind → entry-point table, so the folder still validates as a
// standalone plugin.
//
// Enabling is unchanged by the extra kind: `PluginRegistry.setEnabled`
// takes the bar-widget branch (this plugin is one), so `omarchy plugin
// enable` still places it in `barWidget.defaultSection` and `omarchy plugin
// disable` still just drops the layout entry — after which
// `PluginRegistry.isEnabled` no longer finds the id anywhere in shell.json
// and `_syncServices` destroys this object. One id, one on/off switch.
//
// The two feeders ship INSIDE this plugin folder and are run by absolute
// path from it, the way Omarchy's clipboard plugin runs its bundled
// capture.sh (shell/plugins/clipboard/Clipboard.qml: `captureScript:
// root.omarchyPath + "/shell/plugins/clipboard/capture.sh"`, `command:
// [root.captureScript]`, Omarchy 4.0.2-1) — so the plugin needs nothing on
// PATH and works installed by `omarchy plugin add` as much as by hyprconf's
// install.sh. The folder is resolved from this file's own URL: the shell
// loads an entry point as a percent-encoded file:// URL
// (services/PluginRegistry.qml entryPointUrl → Commons/Util.qml fileUrl),
// so Qt.resolvedUrl(".") is that URL's directory and decodeURIComponent
// gives the filesystem path back — a space or a "%" in the path survives
// the round trip.
//
//   bin/hyprconf-stats     — cpu%, cpu temp, mem, net down/up (one line/sec)
//   bin/hyprconf-gpu-info  — the ACTIVE GPU's util/temp/VRAM (one line/2s):
//                            on a multi-GPU box the card with the most VRAM
//                            in use, re-picked every sample, so an idle
//                            second card never shadows the one doing the
//                            work. NVIDIA, AMD and Intel (xe: Panther Lake
//                            and the other Xe2/Xe3 parts), which reports no
//                            VRAM of its own — the cell then reads "shared"
//
// A stream that exits without ever producing output means "no such
// hardware" and is left alone: the widget's GPU cells then stay blank but
// sized, so the grid holds its shape. One that produced output and then
// died IS restarted (a driver hiccup, an OOM kill — Clipboard.qml restarts
// its watchers the same way), but on a backoff that gives up: 1 s, 2 s,
// 4 s, 8 s, 16 s, 32 s, then parked until the next shell restart, and the
// ladder is refilled the moment a fresh line arrives. A flat retry would
// never give up, because the "it produced output once" flag is latched — it
// also decides what the GPU cells paint, so it cannot be cleared — and a
// feeder that dies instantly is the normal shape of dead hardware:
// nvidia-smi --loop exits at once when the driver stops answering, the awk
// behind it exits with no input, and each respawn pays a failing NVML init
// for nothing. Upstream's Clipboard.qml has no backoff and no
// produced-output gate at all, so this is stricter than the pattern it
// follows, not looser.
//
// shell.qml's ensureService() offers `shell`, `manifest`, `omarchyPath`,
// `barWidgetRegistry` and `pluginRegistry` by property injection (each
// behind an `in` test). None is declared here: this service reads its own
// folder and nothing else.

import QtQuick
import Quickshell.Io

Item {
  id: root

  // This plugin's own directory, with its trailing slash — see the header.
  readonly property string pluginDir: decodeURIComponent(String(Qt.resolvedUrl(".")).replace(/^file:\/\//, ""))

  property bool statsProduced: false
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

  // The restart ladder of one feeder — see the header. `attempt` is the
  // number of restarts since the last line that parsed, so a stream that is
  // delivering data always starts again after a second and one that is only
  // dying walks 1 s → 32 s and then stops.
  component Restarter: Timer {
    id: restarter
    property var proc: null
    property int attempt: 0
    // 1 s, 2 s, 4 s, 8 s, 16 s, 32 s — a bit over a minute of trying.
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
          root.memText = j.mem
          root.netDown = j.down
          root.netUp = j.up
          root.cpuTemp = j.temp ?? ""
          statsRestartTimer.produced()
        } catch (e) {}
      }
    }
    onExited: function() {
      if (root.statsProduced) statsRestartTimer.died()
    }
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
          root.gpuUtil = Number(j.util ?? 0)
          root.gpuTemp = (j.temp === null || j.temp === undefined) ? "" : String(j.temp) + "°"
          root.gpuVramUsed = String(j.vram_used ?? "")
          root.gpuVramTotal = String(j.vram_total ?? "")
          root.gpuTooltip = String(j.tooltip ?? "")
          gpuRestartTimer.produced()
        } catch (e) {}
      }
    }
    onExited: function() {
      if (root.gpuProduced) gpuRestartTimer.died()
    }
  }

  Restarter {
    id: gpuRestartTimer
    proc: gpuProc
  }
}
