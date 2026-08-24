# hyprconf — Test Suite

## Quick Start

```bash
make test
```

Runs the unit and integration suites. No Hyprland session, no Omarchy shell,
no host tools — the suite is hermetic and runs in an `archlinux:latest`
container in CI.

## Suite Reference

| Suite | What it tests | Command | Requirements |
|-------|---------------|---------|--------------|
| Unit | `install.sh` (fake `omarchy-*` bins, throwaway `HOME`), `hypr/scripts/*`, `bin/` tools, `lib/hyprconf/firefox_theme.py`, the Firefox policy, the PII and release guards | `make test-unit` | `python-pytest`, `python-pytest-xdist` |
| Integration | Publish pipeline plumbing: `git archive` filtering, `scripts/publish --dry-run` | `make test-integration` | as above |

There are no VM or install suites. Behaviour that needs a live Omarchy session
is verified by hand and recorded in the commit message.

## Architecture

```
tests/
├── conftest.py                   # puts lib/ on sys.path
├── unit/
│   ├── test_omarchy_install.py   #   install.sh: every stage, restraint invariants, idempotency
│   ├── test_switch_monitor.py    #   hypr/scripts/switch_monitor.sh
│   ├── test_adjust_gaps.py       #   hypr/scripts/adjust-gaps
│   ├── test_stats_tools.py       #   bin/hyprconf-stats, bin/hyprconf-gpu-info
│   ├── test_firefox_theme.py     #   lib/hyprconf/firefox_theme.py (theme-set hook bridge)
│   ├── test_config_exec_targets.py  # every ~/-anchored path a shipped config references ships
│   ├── test_firefox.py           #   infra/firefox/policies.json
│   ├── test_release.py           #   .gitattributes export-ignore, semver, branch constants
│   └── test_no_pii.py            #   every tracked file, identities derived at runtime
└── integration/
    └── test_publish_pipeline.py
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

`.github/workflows/test.yml` runs Lint (`make shellcheck` + `make lint`) and
Unit + Integration (with coverage) on every push and pull request, each in an
`archlinux:latest` container.
