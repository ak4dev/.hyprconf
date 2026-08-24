# hyprconf — Test Suite

## Quick Start

```bash
make test
```

Runs tiers 1–3 (unit, integration, TUI). No Hyprland session, no Omarchy shell,
no host tools — the suite is hermetic and runs in an `archlinux:latest`
container in CI.

## Tier Reference

| Tier | What it tests | Command | Requirements |
|------|---------------|---------|--------------|
| 1 — Unit | `lib/hyprconf/` modules, `install.sh` (fake `omarchy-*` bins, throwaway `HOME`), `hypr/scripts/*`, `bin/hyprconf-stats` + `hyprconf-gpu-info`, the Firefox policy, the PII and release guards | `make test-unit` | `python-pytest`, `python-pytest-xdist` |
| 2 — Integration | Publish pipeline plumbing: `git archive` filtering, `scripts/publish --dry-run` | `make test-integration` | as above |
| 3 — TUI | Textual Pilot, fully headless | `make test-tui` | + `python-pytest-asyncio`, `python-textual` |

There are no VM or install tiers. Behaviour that needs a live Omarchy session is
verified by hand and recorded in the commit message.

## Architecture

```
tests/
├── conftest.py                   # hypr_dir: isolated ~/.config/hypr in tmp_path
├── unit/                         # Tier 1
│   ├── test_<module>.py          #   one per lib/hyprconf/<module>.py (schema, config,
│   │                             #   keybinds, rules, monitors, hyprctl, file_edit, …)
│   ├── test_omarchy_install.py   #   install.sh: every stage, restraint invariants, idempotency
│   ├── test_switch_monitor.py    #   hypr/scripts/switch_monitor.sh
│   ├── test_adjust_gaps.py       #   hypr/scripts/adjust-gaps
│   ├── test_stats_tools.py       #   bin/hyprconf-stats, bin/hyprconf-gpu-info
│   ├── test_config_exec_targets.py  # every ~/-anchored path a shipped config references ships
│   ├── test_firefox.py           #   infra/firefox/policies.json
│   ├── test_release.py           #   .gitattributes export-ignore, semver, branch constants
│   └── test_no_pii.py            #   every tracked file, identities derived at runtime
├── integration/                  # Tier 2
│   └── test_publish_pipeline.py
└── tui/                          # Tier 3
    └── test_tui_basic.py
```

## Rules

- Every system path a script reads must be env-overridable (`_HYPRCONF_*`,
  `HYPRCONF_STATS_*`, `HYPRCONF_GPU_*`) and pointed at `tmp_path`; never
  `readonly`.
- Every external command is a fake bin on `PATH` — `omarchy-*`, `hyprctl`, `git`,
  `jq`, `fc-list`, `sudo`. Never call a host binary, never invoke `pacman`.
- CI runs as root (DAC checks are bypassed) — reproduce permission-sensitive
  tests with `unshare -r python -m pytest <file>`.
- No PII in fixtures: `~`, `$HOME`, `testuser`.
- Never weaken a test to get green. An intended behaviour change updates the
  test to the new contract, in the same commit, and says so.

## Coverage

```bash
pytest tests/unit/ tests/integration/ \
  --cov=lib/hyprconf \
  --cov-report=term-missing
```

## CI (GitHub Actions)

`.github/workflows/test.yml` runs Lint (`make shellcheck` + `make lint`), tiers
1–2 (with coverage) and tier 3 on every push and pull request, each in an
`archlinux:latest` container.
