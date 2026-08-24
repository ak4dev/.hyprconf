# hyprconf — Test Suite

## Quick Start

```bash
make test
```

Runs the unit and integration suites. No Hyprland session, no Omarchy shell,
no host tool that touches the desktop — the suite is hermetic and runs in an `archlinux:latest`
container in CI.

## Suite Reference

| Suite | What it tests | Command | Requirements |
|-------|---------------|---------|--------------|
| Unit | `install.sh` (fake `omarchy-*` bins, throwaway `HOME`), `hypr/scripts/*`, `hypr/*.lua` deltas, `bin/` tools (`hyprconf-stats`, `hyprconf-gpu-info`, `hyprconf-yubikey`), `lib/hyprconf/firefox_theme.py`, the Firefox policy, the PII and release guards | `make test-unit` | `python-pytest`, `python-pytest-xdist`; `jq`, `luac`, `shellcheck`, `git` for the tests that use the real ones (skipped otherwise) |
| Integration | `scripts/publish --help` and `--dry-run` in a throwaway clone | `make test-integration` | as above, plus `git` |

There are no VM or install suites. Behaviour that needs a live Omarchy session
is verified by hand and recorded in the commit message.

## Architecture

```
tests/
├── conftest.py                   # puts lib/ on sys.path
├── unit/
│   ├── test_omarchy_install.py   #   install.sh: every stage, restraint invariants, idempotency
│   ├── test_switch_monitor.py    #   hypr/scripts/switch_monitor.sh
│   ├── test_adjust_gaps.py       #   hypr/scripts/adjust-gaps (fake hyprctl, real jq)
│   ├── test_hypr_overrides.py    #   hypr/*.lua state the deltas the README promises (Steam tiled …)
│   ├── test_stats_tools.py       #   bin/hyprconf-stats, bin/hyprconf-gpu-info
│   ├── test_yubikey.py           #   bin/hyprconf-yubikey (fake sudo/cryptenroll/limine-update; real shellcheck on the drop-in)
│   ├── test_firefox_theme.py     #   lib/hyprconf/firefox_theme.py (theme-set hook bridge, --status)
│   ├── test_config_exec_targets.py  # every ~/-anchored path a shipped config references ships
│   ├── test_firefox.py           #   infra/firefox/policies.json
│   ├── test_release.py           #   install payload roots, semver, scripts/publish constants
│   └── test_no_pii.py            #   every tracked file, identities derived at runtime
└── integration/
    └── test_publish_pipeline.py
```

## Rules

- Every system path a script reads must be env-overridable (`_HYPRCONF_*`,
  `HYPRCONF_STATS_*`, `HYPRCONF_GPU_*`) and pointed at `tmp_path`; never
  `readonly`.
- Every command that could touch the desktop or the system — `omarchy-*`,
  `hyprctl`, `sudo`, `chsh`, `fc-list`, `systemd-cryptenroll`, `limine-update`,
  `git clone`/`pull` … — is **always** a fake bin first on `PATH`; a test must
  never reach a real binary that changes the desktop (the suite once put a
  notification on the owner's desktop). Pure tools are real when present and
  the test skips otherwise: `jq`, `luac`, `cp`, `python3`, `shellcheck`, and
  `git` `init`/`add`/`commit`/`checkout` inside a throwaway clone under
  `tmp_path` — never the repository the suite runs from. Never invoke `pacman`.
- CI runs as root (DAC checks are bypassed) — reproduce permission-sensitive
  tests with `unshare -r python -m pytest <file>`.
- No PII in fixtures: `~`, `$HOME`, `testuser`.
- Never weaken a test to get green. An intended behaviour change updates the
  test to the new contract, in the same commit, and says so.

## Coverage (optional, local)

Needs `python-pytest-cov`; the source/omit config is in `pyproject.toml`. CI
does not run it.

```bash
pytest tests/unit/ tests/integration/ \
  --cov=hyprconf \
  --cov-report=term-missing
```

## CI (GitHub Actions)

`.github/workflows/test.yml` runs Lint (`make shellcheck` + `make lint`) and
Unit + Integration (`make test`, with `jq` and `shellcheck` installed so the
tests that use the real ones do not skip) on every push and pull request, each
in an `archlinux:latest` container.
