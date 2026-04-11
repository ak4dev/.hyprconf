# Contributing to hyprconf

## Repository Layout

```
.hyprconf/
├── packages                  # Arch packages to install (one per line, comments ok)
├── setup.sh                  # Local bootstrap + sync entry point
│
├── assets/                   # Shared project assets
│   ├── banner.sh             # print_banner() — glitch palette + logo
│   └── banner.svg            # README header banner
│
├── docs/
│   ├── CONTRIBUTING.md       # This file
│   └── hyprland-reference.md # Hyprland config syntax cheatsheet
│
├── infra/                    # AWS cloud infrastructure (S3 + CloudFront + ACM + Route53)
│   ├── env.sh.example        # Config template (copy → env.sh, never commit)
│   ├── deploy.sh             # Idempotent create/update
│   └── teardown.sh           # Destroy all resources (confirmation required)
│
├── install/
│   └── install.sh            # Self-contained installer (served from CloudFront)
│
├── scripts/
│   └── publish               # Run tests, deploy, promote dev → stable, build release archive
│
└── stow/                     # GNU Stow packages — symlinked into $HOME
    ├── hypr/
    │   ├── .config/hypr/
    │   │   ├── hyprland.conf           # Animations, layout, env vars
    │   │   ├── keybinds.conf           # All keybindings
    │   │   ├── gestures.conf
    │   │   ├── hyprpaper.conf
    │   │   ├── hyprlock.conf
    │   │   ├── hypridle.conf
    │   │   ├── laptopMonitors.conf
    │   │   ├── pcMonitors.conf / .bedroom / .kitchen
    │   │   ├── pcMonitorsK.conf        # Desktop alt preset (monitorv2 block syntax)
    │   │   ├── conf.d/
    │   │   │   ├── 00-hyprconf.conf        # Source guard (includes conf.d glob)
    │   │   │   └── 99-hyprconf-local.conf  # Machine-local overrides (hyprconf set)
    │   │   └── scripts/
    │   │       ├── hyprconf-tui/main.py    # Textual TUI
    │   │       ├── switch_monitor.sh
    │   │       ├── toggle-native-display   # Toggle built-in laptop screen (eDP-1)
    │   │       └── theme-switcher/
    │   │           ├── switch_theme.py
    │   │           └── themes/             # Theme JSON files
    │   └── .local/
    │       ├── bin/hyprconf               # CLI entry point → ~/.local/bin/
    │       └── lib/hyprconf/              # Shared Python library
    │           ├── schema.py              # OPTION_SCHEMA — all Hyprland keys + types + defaults
    │           ├── config.py              # Read/write 99-hyprconf-local.conf
    │           ├── hyprctl.py             # hyprctl IPC wrapper
    │           ├── autodetect.py          # First-run config migration
    │           ├── cli.py                 # Python CLI backend
    │           ├── file_edit.py           # Atomic file operations
    │           ├── block_conf.py          # Generic block-format config parser
    │           ├── keybinds.py            # Keybind read/write
    │           ├── rules.py               # Window/workspace rule read/write
    │           ├── monitors.py            # Monitor config read/write
    │           ├── hyprlock.py            # hyprlock block read/write
    │           ├── hypridle.py            # hypridle block read/write
    │           ├── hyprpaper.py           # hyprpaper read/write
    │           └── __init__.py
    ├── btop/   kitty/   dunst/   fastfetch/   code-oss/
    └── waybar/ wallpaper/
theme/                          # Vendor extension payloads (NOT under stow/)
    ├── firefox/extensions/
    └── .vscode-oss/extensions/
```

---

## Testing

hyprconf uses a **5-tier test architecture**. Tiers 1–3 require only Python and run without a Hyprland session; Tiers 4–5 are opt-in and require KVM.

```
tests/
├── conftest.py              # shared fixtures (isolated config dirs, mock hyprctl)
├── unit/                    # Tier 1 — pure Python, no Hyprland
├── integration/             # Tier 2 — Python CLI layer with mock hyprctl
├── tui/                     # Tier 3 — Textual Pilot (headless, no terminal needed)
├── vm/                      # Tier 4 — live Hyprland in QEMU/KVM (opt-in)
└── install/                 # Tier 5 — full Arch install smoke test (opt-in)
```

### Running tests

```bash
# Tier 1 — unit tests (fastest, no deps beyond pytest)
pytest tests/unit/

# Tier 2 — integration tests (mock hyprctl)
pytest tests/integration/

# Tier 3 — TUI tests (requires python-pytest-asyncio + python-textual)
pytest tests/tui/

# Tiers 1–3 together with coverage
pytest tests/unit/ tests/integration/ tests/tui/ --cov=stow/hypr/.local/lib/hyprconf

# Tier 4 — live Hyprland in QEMU (requires KVM; sudo modprobe kvm_amd first)
bash tests/vm/run_vm.sh           # start VM, wait for SSH
pytest tests/vm/ --run-vm -v

# Tier 5 — full Arch install smoke test
bash tests/install/build_image.sh   # first time only; ~20 min
bash tests/install/run_install_vm.sh
pytest tests/install/ --run-install -v

# Convenience via Makefile
make test            # Tiers 1–3
make test-vm         # Tier 4 (VM must be running)
make test-install    # Tier 5 (image must be built)
make build-vm-image  # runs build_image.sh
```

### Tier 5 install image

`build_image.sh` runs Packer to build a full Arch+hyprconf image (exercising `install.sh` end-to-end) and writes `tests/vm/arch-hyprconf.meta` with the build date and commit. The VM launches on port 2223 via `run_install_vm.sh` using a **COW overlay**, so the base image is never dirtied by test runs.

`scripts/publish` detects the image, shows its metadata, and prompts: _use existing_ (fast validation only) or _rebuild_ (re-runs `install.sh` via Packer, ~20 min).

### Key fixtures (`tests/conftest.py`)

- `hypr_dir` — isolated `~/.config/hypr` in a `tmp_path`, monkeypatches all 9 module-level path constants so each test gets a clean slate
- `mock_hyprctl` — patches `subprocess.run` with canned JSON responses; tests pass even without `HYPRLAND_INSTANCE_SIGNATURE`

### CI

`.github/workflows/test.yml` — Tiers 1–3 run on every push/PR via GitHub Actions. Tiers 4–5 require a self-hosted runner with KVM.

**Test packages** (`packages`): `python-pytest`, `python-pytest-asyncio`, `python-coverage`

---

## Branches

| Branch | Purpose |
|--------|---------|
| `dev` | All active development — tests, docs, scripts, configs |
| `stable` | Release-ready source branch with normal shared git history |

The model is `dev` → `stable` with shared history. User installs use a sparse checkout of `stable`; release archives are exported from the same commit via `git archive`.

---

## Publishing to stable

```bash
bash scripts/publish
```

`scripts/publish` handles the full pipeline automatically:

1. Verifies `dev` branch with a clean working tree
2. Starts the tier-4 test VM if not already running (stops it when done)
3. Runs all 5 test tiers (aborts on any failure)
4. **Tier 5 — install image detection**: checks for `tests/vm/arch-hyprconf.qcow2`; if found, displays its build date and commit, then prompts:
   - **Use existing** — skip `install.sh` re-execution, run post-install validation (~fast)
   - **Rebuild** — re-run Packer to exercise `install.sh` end-to-end (~20 min)
   - If no image exists, builds automatically (no prompt)
5. Starts the tier-5 VM on port 2223 via COW overlay; stops it on exit
6. Deploys to `hyprconf.sh` via `hyprconf deploy hyprconf.sh`
7. Builds a filtered release archive from `HEAD` using `git archive` + `.gitattributes`
8. Pushes `HEAD` to `origin/stable`
9. Creates and pushes the annotated tag `v<hyprconf.__version__>` unless it already points at `HEAD`

Files excluded from the release archive: `tests/` `scripts/` `.github/` `web/` `docs/` `AGENTS.md` `Makefile` `.editorconfig` `pyproject.toml` `__pycache__/` `*.pyc`

| Flag | Effect |
|------|--------|
| `--skip-deploy` | Skip the deploy step |
| `--skip-tag` | Skip annotated release-tag creation |
| `--dry-run` | Build the release archive locally but do not push branches/tags |
