# Test Suite Context

## Status (as of session end)

**All 5 tiers: ✅ FULLY PASSING — 0 skipped**

| Tier | Suite | Result |
|------|-------|--------|
| 1 | Unit (`tests/unit/`) | 230 passed |
| 2 | Integration (`tests/integration/`) | 16 passed |
| 3 | TUI (`tests/tui/`) | 8 passed |
| 4 | VM (`tests/vm/`) | 42 passed, 0 skipped |
| 5 | Install (`tests/install/`) | 9 passed |

**Total: 305 passed, 0 skipped, 0 failed.**

## How to Run

```bash
# Tiers 1–3 (no VM needed):
make test-unit test-integration test-tui

# Start VM first, then:
make test-vm      # Tier 4
make test-install # Tier 5

# Full test + deploy + publish to mainline:
bash tests/vm/run_vm.sh
bash scripts/publish
```

## VM State

- Image: `arch-hyprconf.qcow2` — built Mar 19 16:31 with UEFI + luks_key_opt fix
- SSH: `ssh -i ~/.ssh/hyprconf_vm_key -p 2222 hyprtest@127.0.0.1`
- QEMU PID: check with `pgrep qemu`
- Run VM: `bash tests/vm/run_vm.sh`
- **`run_vm.sh --wait` now auto-syncs the VM repo to `origin/dev`** before tests run, so `hyprconf sync` (which calls `git restore .`) always restores to the current dev state.

### Manual patches applied to running VM (not baked into image)

1. Persistent CI NOPASSWD sudoers rule (`install.sh` fix)
2. `~/.zshenv` PATH setup (`setup.sh` fix)

**A fresh `make build-vm-image` will bake all of these in.**

## Branch model

- `dev` — all active development (tests, scripts, configs, CI)
- `mainline` — public-facing filtered snapshot; `tests/` `.github/` `AGENTS.md` `Makefile` `pyproject.toml` excluded
- `scripts/publish` produces the mainline snapshot: runs all 5 tiers, deploys hyprconf.sh, pushes filtered commit to `origin/mainline`
- Current mainline HEAD: `02c1476` (published Mar 19 2026)

## Fixes across sessions (key commits)

| Commit | Change |
|--------|--------|
| `f398be4` | `_read_persisted_value()` in hyprconf; packages fix; install/VM infra fixes |
| `4930423` | Eliminated 3 skipped VM tests; no live Hyprland required |
| `44b1a6c` | 11 new VM tests: theme/repair/show/mainmod/paper/deploy/configure/display |
| `f8898ea` | `scripts/publish` — test, deploy, push filtered dev → mainline |
| `3b8885e` | `run_vm.sh --wait` auto-syncs VM repo to origin/dev before tests |

## Next Steps

- **Rebuild VM image** (`make build-vm-image`) to bake in all installer fixes.
- Coverage is complete. All commands have VM-level integration tests.
