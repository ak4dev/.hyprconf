# Test Suite Context

## Status (as of session end)

**All 5 tiers: ✅ FULLY PASSING**

| Tier | Suite | Result |
|------|-------|--------|
| 1 | Unit (`tests/unit/`) | 230 passed |
| 2 | Integration (`tests/integration/`) | 16 passed |
| 3 | TUI (`tests/tui/`) | 8 passed |
| 4 | VM (`tests/vm/`) | 28 passed, 3 skipped (Hyprland not running — correct) |
| 5 | Install (`tests/install/`) | 9 passed |

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

### Manual patches applied to running VM (not baked into image yet)

The current image was patched directly on the running VM for:
1. Persistent CI NOPASSWD sudoers rule (via `install.sh` changes)
2. `~/.zshenv` PATH setup (via `setup.sh` changes)

**These patches ARE committed to `install.sh` and `setup.sh`** — a fresh `make build-vm-image` will bake them in automatically.

## Fixes Committed (this session)

1. **`stow/hypr/.local/bin/hyprconf`**: `_read_persisted_value()` helper + fallback in `cmd_get` — `hyprconf get` now shows the persisted config file value when Hyprland is not running.

2. **`packages`**: `nerd-fonts` (meta-group) → `ttf-jetbrains-mono-nerd` (the specific font used everywhere).

3. **`install/install.sh`**: Pre-compute `luks_key_opt` before heredoc; add persistent `zz-ci-nopasswd` sudoers when `HYPRCONF_CI=1`; add `update_zshenv()` call sites.

4. **`setup.sh`**: `update_zshenv()` writes `~/.zshenv` so `~/.local/bin` is in PATH for non-interactive SSH sessions.

5. **`tests/vm/run_vm.sh`**: Fixed SSH user (`user`→`hyprtest`); added UEFI OVMF firmware + `-machine q35`.

6. **`tests/install/arch.pkr.hcl`**: Explicit `efi_firmware_code`/`efi_firmware_vars` for OVMF.

7. **`tests/vm/test_hyprland_integration.py`**: `hyprland_running` fixture for hyprctl-dependent tests; fixed `monitor set/delete` → `monitor config set/delete`.

8. **`.gitignore`**: Added `*.qcow2`, `OVMF_VARS.4m.fd`, `output-arch/`.

## Next Steps

- **Rebuild VM image** (`make build-vm-image`) to bake in all installer fixes.
