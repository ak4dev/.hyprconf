# hyprconf — Test Suite

## Quick Start

```bash
make test
```

Runs Tiers 1–3 (unit, integration, TUI). No Hyprland session required.

---

## Full Suite (All 5 Tiers)

### TL;DR — Run Everything From Scratch

```bash
make build-vm-image          # build VM image (~20 min, one-time)
bash tests/vm/run_vm.sh      # start VM (blocks until SSH-ready)
make test test-vm test-install
```

### One-Time Setup

```bash
# Enable KVM (AMD CPU — use kvm_intel for Intel)
sudo modprobe kvm_amd

# Install required tooling
sudo pacman -S qemu-full packer python-pytest-asyncio

# Build the VM image (~20 min)
make build-vm-image
```

### Running All Tiers

```bash
# Tiers 1–3: unit, integration, TUI
make test

# Tier 4: live Hyprland in QEMU (start VM first)
bash tests/vm/run_vm.sh
make test-vm

# Tier 5: full Arch install smoke test
make test-install
```

---

## Tier Reference

| Tier | What It Tests | Command | Requirements |
|------|--------------|---------|--------------|
| 1 — Unit | All Python config parsers/writers (1,122 tests) | `make test-unit` | None |
| 2 — Integration | CLI layer with mock hyprctl | `make test-integration` | None |
| 3 — TUI | Textual Pilot headless UI tests | `make test-tui` | `python-pytest-asyncio` |
| 4 — VM | Every CLI subcommand against live Hyprland | `make test-vm` | KVM + `qemu-full` + running VM |
| 5 — Install | Full `install/install.sh` end-to-end | `make test-install` | KVM + `packer` + built image |

---

## Architecture

```
tests/
├── conftest.py               # Shared fixtures: hypr_dir
├── unit/                     # Tier 1 — pure Python, zero Hyprland dependency
│   ├── test_config.py
│   ├── test_schema.py
│   ├── test_file_edit.py
│   ├── test_block_conf.py
│   ├── test_keybinds.py
│   ├── test_rules.py
│   ├── test_monitors.py
│   ├── test_hyprlock.py
│   ├── test_hypridle.py
│   └── test_hyprpaper.py
├── integration/              # Tier 2 — CLI layer, subprocess mocked
│   └── test_cli_get_set.py
├── tui/                      # Tier 3 — Textual Pilot, fully headless
│   └── test_tui_basic.py
├── vm/                       # Tier 4 — SSH into live QEMU/Hyprland VM
│   ├── run_vm.sh             #   Launch/stop the test VM
│   └── test_hyprland_integration.py
└── install/                  # Tier 5 — Packer builds fresh Arch VM, tests result
    ├── arch.pkr.hcl          #   Packer template (uses real install/install.sh)
    ├── build_image.sh        #   Convenience wrapper around packer build
    └── test_full_install.py
```

---

## VM Management

```bash
bash tests/vm/run_vm.sh         # Start VM (blocks until SSH is ready)
bash tests/vm/run_vm.sh --stop  # Stop VM
bash tests/vm/run_vm.sh --wait  # Wait for SSH without starting
```

The VM uses `virtio-gpu-gl` (software OpenGL) so Hyprland's DRM requirement
is satisfied without a physical GPU. SSH is forwarded to `localhost:2222`.

---

## Installer CI Mode

`install/install.sh` supports non-interactive execution for Tier 5:

```bash
HYPRCONF_CI=1 \
HYPRCONF_CI_DISK=/dev/vda \
HYPRCONF_CI_USERNAME=hyprtest \
HYPRCONF_CI_PASSWORD=hyprtest \
HYPRCONF_CI_HOSTNAME=hyprconf-test \
HYPRCONF_CI_TIMEZONE=UTC \
HYPRCONF_CI_PART_MODE=full \
bash install/install.sh
```

| Variable | Default | Description |
|----------|---------|-------------|
| `HYPRCONF_CI` | `0` | Set to `1` to enable non-interactive mode |
| `HYPRCONF_CI_DISK` | *(required)* | Target block device, e.g. `/dev/vda` |
| `HYPRCONF_CI_USERNAME` | `hyprtest` | User account name |
| `HYPRCONF_CI_PASSWORD` | `hyprtest` | Account + LUKS password |
| `HYPRCONF_CI_HOSTNAME` | `hyprconf-test` | System hostname |
| `HYPRCONF_CI_TIMEZONE` | `UTC` | Timezone (from `/usr/share/zoneinfo`) |
| `HYPRCONF_CI_PART_MODE` | `full` | `full` (wipe disk) or `unallocated` |
| `HYPRCONF_CI_COPY_NETCONF` | `0` | Copy network config from live ISO |

---

## Coverage

```bash
pytest tests/unit/ tests/integration/ \
  --cov=stow/hypr/.local/lib/hyprconf \
  --cov-report=term-missing
```

---

## CI (GitHub Actions)

Tiers 1–3 run automatically on every push and pull request via
`.github/workflows/test.yml`. Tiers 4–5 require a self-hosted runner
with KVM access.
