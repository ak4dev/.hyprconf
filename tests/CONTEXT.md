# Test Suite Context

## Status (as of session end)

**Tiers 1–3: ✅ FULLY PASSING — 0 failed, 0 skipped**

| Tier | Suite | Result |
|------|-------|--------|
| 1 | Unit (`tests/unit/`) | 242 passed |
| 2 | Integration (`tests/integration/`) | 20 passed |
| 3 | TUI (`tests/tui/`) | 8 passed |
| 4 | VM (`tests/vm/`) | 44 passed (requires running VM) |
| 5 | Install (`tests/install/`) | 9 passed (requires Packer image + VM) |

\* `test_publish_dry_run_succeeds` skips when working tree is not clean or not on `dev` branch; it passes on a clean `dev` checkout.

**Total tiers 1–3: 270 passed (previously 254 — +16 for new release-model tests).**

## New Test Files (Release Model Migration)

| File | Tier | What it tests |
|------|------|---------------|
| `tests/unit/test_release.py` | 1 | `.gitattributes` export-ignore rules, semver version, `setup.sh` branch constants, `scripts/publish` structural checks |
| `tests/integration/test_publish_pipeline.py` | 2 | `git archive` archive correctness (excluded + included paths, prefix), `scripts/publish --dry-run` end-to-end |
| `tests/vm/test_hyprland_integration.py` (+2) | 4 | `test_repo_has_stable_remote_ref`, `test_sync_migrates_mainline_to_stable` |

## How to Run

```bash
# Tiers 1–3 (no VM needed):
make test-unit test-integration test-tui

# Start VM first, then:
make test-vm      # Tier 4
make test-install # Tier 5

# Full test + deploy + publish to stable:
bash tests/vm/run_vm.sh
bash scripts/publish
```

## VM State

- Image: `arch-hyprconf.qcow2` — built Mar 19 16:31 with UEFI + luks_key_opt fix
- SSH: `ssh -i ~/.ssh/hyprconf_vm_key -p 2222 hyprtest@127.0.0.1`
- QEMU PID: check with `pgrep qemu`
- Run VM: `bash tests/vm/run_vm.sh`
- **`run_vm.sh --wait` auto-syncs the VM repo to `origin/dev`** AND now also bundles `origin/stable` so the mainline→stable migration test works.

### Manual patches applied to running VM (not baked into image)

1. Persistent CI NOPASSWD sudoers rule (`install.sh` fix)
2. `~/.zshenv` PATH setup (`setup.sh` fix)

**A fresh `make build-vm-image` will bake all of these in.**

## Branch model

- `dev` — all active development (tests, scripts, configs, CI)
- `stable` — release-ready source branch with normal shared history from `dev`
- `mainline` — temporary compatibility mirror of `stable` during migration
- `scripts/publish` runs all 5 tiers, deploys hyprconf.sh, builds a filtered release archive via `git archive`, promotes `dev` to `origin/stable`, and optionally mirrors `origin/mainline`
- `run_vm.sh` bundles both `dev` and `stable` so VM tests can exercise the mainline→stable migration path

## Fixes across sessions (key commits)

| Commit | Change |
|--------|--------|
| `f398be4` | `_read_persisted_value()` in hyprconf; packages fix; install/VM infra fixes |
| `4930423` | Eliminated 3 skipped VM tests; no live Hyprland required |
| `44b1a6c` | 11 new VM tests: theme/repair/show/mainmod/paper/deploy/configure/display |
| `f8898ea` | `scripts/publish` — legacy filtered dev → mainline workflow |
| `3b8885e` | `run_vm.sh --wait` auto-syncs VM repo to origin/dev before tests |
| *(current)* | Migrate tests to new dev→stable release model; add release/publish tests |

## Next Steps

- **Rebuild VM image** (`make build-vm-image`) to bake in all installer fixes.
- Coverage is complete. All commands have VM-level integration tests.

