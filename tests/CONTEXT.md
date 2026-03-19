# Test Suite Context

## Status (as of session end)

**All 5 tiers: ✅ FULLY PASSING — 0 skipped**

| Tier | Suite | Result |
|------|-------|--------|
| 1 | Unit (`tests/unit/`) | 230 passed |
| 2 | Integration (`tests/integration/`) | 16 passed |
| 3 | TUI (`tests/tui/`) | 8 passed |
| 4 | VM (`tests/vm/`) | 31 passed, 0 skipped |
| 5 | Install (`tests/install/`) | 9 passed |

**Total: 294 passed, 0 skipped, 0 failed.**

## How to Run

```bash
# Tiers 1–3 (no VM needed):
make test-unit test-integration test-tui

# Start VM first, then:
make test-vm      # Tier 4
make test-install # Tier 5
```

## VM State

- Image: `arch-hyprconf.qcow2` — built Mar 19 16:31 with UEFI + luks_key_opt fix
- SSH: `ssh -i ~/.ssh/hyprconf_vm_key -p 2222 hyprtest@127.0.0.1`
- QEMU PID: check with `pgrep qemu`
- Run VM: `bash tests/vm/run_vm.sh`

### Manual patches applied to running VM (not baked into image)

1. Persistent CI NOPASSWD sudoers rule (`install.sh` fix)
2. `~/.zshenv` PATH setup (`setup.sh` fix)
3. `hyprconf` bash script updates (persisted-value fallback, `packages` fix)

**A fresh `make build-vm-image` will bake all of these in.**

## Fixes in this session (commits f398be4, 4930423)

1. **`stow/hypr/.local/bin/hyprconf`**: `_read_persisted_value()` + fallback in `cmd_get`
2. **`packages`**: `nerd-fonts` → `ttf-jetbrains-mono-nerd`
3. **`install/install.sh`**: `luks_key_opt` pre-compute; CI NOPASSWD sudoers; zshenv calls
4. **`setup.sh`**: `update_zshenv()` for SSH non-interactive PATH
5. **`tests/vm/run_vm.sh`**: SSH user fix; UEFI OVMF firmware
6. **`tests/install/arch.pkr.hcl`**: OVMF firmware
7. **`tests/vm/test_hyprland_integration.py`**: Removed `hyprland_running` skip fixture; redesigned 3 previously-skipped tests to run without live Hyprland
8. **`.gitignore`**: VM artefacts

## Next Steps

- **Rebuild VM image** (`make build-vm-image`) to bake in all installer fixes.
