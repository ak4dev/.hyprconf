# Web TUI via textual-serve — Implementation Spec

## Overview

Serve the hyprconf TUI (`main.py`) in the browser using
[textual-serve](https://github.com/Textualize/textual-serve), giving users a
fully interactive configuration experience without installing anything locally.
Generated config files can be downloaded and dropped into any Hyprland setup.

## Architecture

```
Browser (xterm.js)
   │
   │  WebSocket (wss://tui.hyprconf.sh)
   ▼
┌──────────────────────────────┐
│  EC2 t3.micro / Fargate      │
│  ┌────────────────────────┐  │
│  │  nginx (TLS termination)│  │
│  └────────┬───────────────┘  │
│           │ :8000             │
│  ┌────────▼───────────────┐  │
│  │  textual-serve          │  │
│  │  → spawns main.py per   │  │
│  │    session (file-only    │  │
│  │    mode, no hyprctl)     │  │
│  └────────────────────────┘  │
└──────────────────────────────┘
```

### Components

| Component | Role | Notes |
|---|---|---|
| **textual-serve** | Serves the Textual app over WebSocket | Each session is an isolated subprocess |
| **nginx** | TLS termination + reverse proxy | Uses ACM cert or Let's Encrypt |
| **main.py** (unchanged) | The actual TUI | Runs in file-only mode (`HYPRLAND_INSTANCE_SIGNATURE` unset) |
| **hyprconf Python library** | Schema, validation, config generation | Installed in container/instance |

### Key Insight: File-Only Mode

When `HYPRLAND_INSTANCE_SIGNATURE` is not set, the TUI already falls back to
file-only mode (main.py L1565-1569). In this mode it can:

- Browse all 28 config sections and 150+ options with descriptions/defaults
- Edit values, stage pending changes
- Save to `~/.config/hypr/conf.d/99-hyprconf-local.conf`
- Browse themes (68 available), keybinds (53), window/workspace rules
- Edit hyprlock, hypridle, hyprpaper configs

It **cannot** (and gracefully skips):

- Apply changes at runtime (`hyprctl keyword`)
- Detect hardware (`/sys/class/input/`, `/sys/bus/iio/`)
- Toggle daemons (OSK, autorotate)
- Set wallpaper via IPC

This is the correct behavior for a web deployment.

---

## What Users Get

1. Visit hyprconf.sh → click "Launch TUI"
2. Full interactive TUI opens in browser (xterm.js rendering)
3. Browse sections, tweak options, edit keybinds/rules
4. Press `s` to save → config files written to session sandbox
5. Download generated config as a tarball
6. Place in `~/.config/hypr/conf.d/` on their machine → `hyprctl reload`

**No hyprconf installation required for basic config.** The generated file is
standard Hyprland conf syntax.

### Config Export Options

```bash
# Option A: Download tarball from browser (textual-serve file download API)
# User clicks "Export" in TUI → browser downloads hyprconf-config.tar.gz

# Option B: curl one-liner (requires a small sidecar endpoint)
curl -sL hyprconf.sh/c/SESSION_ID | tar xzf - -C ~/.config/hypr/

# Option C: Full install for theme/monitor/hardware features
curl -sL hyprconf.sh | bash
```

---

## Infrastructure (CDK additions)

Add to the existing `HyprconfStack` or create a separate `HyprconfTuiStack`.

### Option 1: EC2 (cheapest — ~$0 free tier, ~$3-7/month after)

```typescript
// New CDK constructs needed:
// 1. EC2 instance (t3.micro for free tier, or t4g.nano for ARM)
// 2. Security group (allow 443 inbound)
// 3. IAM instance profile (minimal — just SSM for management)
// 4. Route53 A record: tui.hyprconf.sh → EC2 EIP
// 5. Elastic IP (so DNS doesn't change on restart)
// 6. UserData script to install textual-serve + hyprconf deps
```

### Option 2: ECS Fargate (fully managed — ~$26/month)

```typescript
// 1. ECS Cluster
// 2. Fargate Service (1 task, 0.25 vCPU, 0.5 GB)
// 3. ALB with WebSocket sticky sessions
// 4. ACM certificate for tui.hyprconf.sh
// 5. Route53 A record: tui.hyprconf.sh → ALB
// 6. ECR repository for Docker image
```

### Cost Comparison

| Option | Monthly Cost | Free Tier | Management |
|---|---|---|---|
| EC2 t3.micro | $0 (12 months) / $7.50 | Yes | Manual updates |
| EC2 t4g.nano | $3.07 | No | Manual updates |
| Fargate + ALB | ~$26 | No | Fully managed |
| Fargate Spot + ALB | ~$18 | No | May be interrupted |

---

## Docker Image

```dockerfile
FROM python:3.12-slim

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
RUN pip install --no-cache-dir textual textual-serve

# Copy hyprconf library
COPY stow/hypr/.local/lib/hyprconf/ /usr/local/lib/python3.12/site-packages/hyprconf/

# Copy TUI script
COPY stow/hypr/.config/hypr/scripts/hyprconf-tui/main.py /app/main.py

# Copy theme data (needed for theme section)
COPY stow/hypr/.config/hypr/scripts/theme-switcher/themes/ /app/themes/

# Copy default config files (template for new sessions)
COPY stow/hypr/.config/hypr/hyprland.conf /app/defaults/hyprland.conf
COPY stow/hypr/.config/hypr/keybinds.conf /app/defaults/keybinds.conf
COPY stow/hypr/.config/hypr/hyprlock.conf /app/defaults/hyprlock.conf
COPY stow/hypr/.config/hypr/hypridle.conf /app/defaults/hypridle.conf
COPY stow/hypr/.config/hypr/hyprpaper.conf /app/defaults/hyprpaper.conf

# Copy serve config
COPY infra/tui/serve.toml /app/serve.toml

# Session sandbox: each session gets a temp HOME with default configs
COPY infra/tui/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
```

### serve.toml

```toml
[app]
command = "python3 /app/main.py"
title = "hyprconf TUI"

[server]
host = "0.0.0.0"
port = 8000
```

### entrypoint.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

# Each session gets an isolated HOME with default configs
# textual-serve handles session isolation via subprocesses
# We just need the default config templates in place

export TEXTUAL_SERVE_HOME="/app"
exec textual-serve --config /app/serve.toml
```

---

## TUI Modifications Needed (minimal)

### 1. Session Sandbox (main.py)

Add an environment variable check to use a session-local config directory
instead of `~/.config/hypr/`:

```python
# At top of main.py, after imports:
_WEB_MODE = os.environ.get("HYPRCONF_WEB_MODE") == "1"
if _WEB_MODE:
    _CONFIG_DIR = Path(os.environ.get("HYPRCONF_SESSION_DIR", "/tmp/hyprconf-session"))
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Copy default configs into session dir on first access
```

### 2. Export/Download Action

Add a new keybind (`e` for export) that bundles the session's config files
into a tarball and triggers a textual-serve file download:

```python
# In HyprconfApp BINDINGS:
Binding("e", "export_config", "Export config"),

async def action_export_config(self) -> None:
    """Bundle session configs into a downloadable tarball."""
    import tarfile
    import tempfile
    export_path = Path(tempfile.mktemp(suffix=".tar.gz"))
    with tarfile.open(export_path, "w:gz") as tar:
        for conf in self._session_config_dir.glob("**/*.conf"):
            arcname = str(conf.relative_to(self._session_config_dir))
            tar.add(conf, arcname=arcname)
    # textual-serve file download API
    self.save_file(export_path)
    self.notify(f"Config exported → {export_path.name}")
```

### 3. Welcome Banner

Show a brief welcome message for web sessions explaining the workflow:

```python
if _WEB_MODE:
    self.notify(
        "Welcome to hyprconf TUI (web mode). "
        "Browse and edit options, then press [e] to export your config.",
        title="Web Mode",
        timeout=8,
    )
```

### 4. Suppress Hyprland Warning

In web mode, don't show the "Hyprland session not detected" warning since
it's expected:

```python
# In on_mount(), change:
if not _hyprctl_active:
    if not _WEB_MODE:
        self.notify("Hyprland session not detected — file-only mode", ...)
```

---

## Frontend Integration

### Option A: Subdomain (tui.hyprconf.sh)

Add a "Launch TUI" button on the React site that opens `tui.hyprconf.sh` in
a new tab or embedded iframe.

```tsx
// In Landing.tsx or a new TUI page:
<a href="https://tui.hyprconf.sh" target="_blank" rel="noopener">
  Launch TUI in Browser
</a>
```

### Option B: Embedded iframe

```tsx
// New page: web/src/pages/TUI.tsx
export default function TUI() {
  return (
    <div className={styles.tuiContainer}>
      <iframe
        src="https://tui.hyprconf.sh"
        className={styles.tuiFrame}
        title="hyprconf TUI"
        allow="clipboard-write"
      />
    </div>
  );
}
```

### Route Addition

```typescript
// In routes.ts:
{ path: '/tui', label: 'Try TUI', icon: Terminal, component: lazy(() => import('./pages/TUI')) }
```

---

## Config Files That Work Without hyprconf

| File | What It Contains | Standalone? |
|---|---|---|
| `conf.d/99-hyprconf-local.conf` | All general/decoration/input/etc. options | ✅ Yes — standard Hyprland syntax |
| `keybinds.conf` | Custom keybindings | ✅ Yes — needs `source` line in hyprland.conf |
| `theme-colors.conf` | Active theme border colors | ✅ Yes — needs `source` line |
| `hyprlock.conf` | Lock screen config | ✅ Yes — standalone |
| `hypridle.conf` | Idle timeout config | ✅ Yes — standalone |
| `hyprpaper.conf` | Wallpaper config | ✅ Yes — standalone |
| Theme switching | Cascades across kitty/waybar/vscode/firefox | ❌ Requires hyprconf |
| Monitor detection | Live `hyprctl monitors -j` | ❌ Requires local Hyprland |
| Hardware toggles | OSK/autorotate daemon management | ❌ Requires local system |

**~70% of TUI value works standalone.** The remaining 30% (themes, monitors,
hardware) serves as an upgrade path to full hyprconf installation.

---

## Testing Plan

### Unit Tests

```python
# tests/unit/test_tui_web_mode.py
def test_web_mode_env_sets_session_dir():
    """HYPRCONF_WEB_MODE=1 uses session-local config dir."""

def test_export_creates_valid_tarball():
    """Export action produces a .tar.gz with all session configs."""

def test_welcome_banner_shown_in_web_mode():
    """Web mode shows welcome notification."""

def test_hyprland_warning_suppressed_in_web_mode():
    """No 'session not detected' warning in web mode."""
```

### Integration Tests

```python
# tests/integration/test_tui_serve.py
def test_textual_serve_starts():
    """textual-serve process starts and binds to port."""

def test_websocket_connection():
    """WebSocket connection to textual-serve succeeds."""

def test_session_isolation():
    """Two concurrent sessions have independent config dirs."""
```

### CDK Tests

```typescript
// infra/cdk/test/tui-stack.test.ts
test('EC2 instance created with correct type', () => { ... });
test('Security group allows 443 inbound', () => { ... });
test('Route53 record points to EIP', () => { ... });
test('UserData installs textual-serve', () => { ... });
```

---

## Deployment Steps

1. Build Docker image → push to ECR (or install directly on EC2 via UserData)
2. CDK deploy with TUI stack enabled
3. Verify `tui.hyprconf.sh` serves the TUI
4. Add "Launch TUI" to React frontend → redeploy web

### Deploy Command

```bash
# Add to hyprconf deploy:
hyprconf deploy tui.hyprconf.sh

# Or via CDK directly:
cd infra/cdk && npx cdk deploy HyprconfTuiStack
```

---

## Dependencies

```
# Python (in Docker image or EC2)
textual>=1.0.0
textual-serve>=1.0.0

# System
python3.12+
nginx (for TLS termination on EC2 option)
```

---

## Decision Log

| Decision | Chosen | Rationale |
|---|---|---|
| Compute | EC2 or Fargate (TBD) | Lambda is wrong for stateful TUI sessions |
| TUI framework | textual-serve | Purpose-built by Textual authors, stable beta |
| Config export | Tarball download | Standard format, no special tooling needed |
| Subdomain | tui.hyprconf.sh (TBD) | Clean separation from main site |
| TUI changes | Minimal (~30 lines) | Web mode env var, export action, welcome banner |
| Separate CDK stack | Yes | Independent lifecycle from main site |

## Status

**ON HOLD** — Evaluating usefulness before committing to implementation.
