# Contributing to hyprconf

Read [`AGENTS.md`](../AGENTS.md) first — its rules bind every change;
`README.md` is the user contract. This file holds the tree, the tests, the
publish flow and the website upload.

## Repository Layout

```
.hyprconf/
├── install.sh                  # The only entry point: preflight, the module loop (or the modules named), the ~/.local/bin/hyprconf link, the hook, --undo; served by hyprconf.sh, clones itself on the curl path
│
├── hooks/10-hyprconf           # The post-update hook: execs ~/.local/bin/hyprconf --no-update --no-packages (installed with omarchy hook install, no path rendered in)
│
├── modules/                    # The seventeen self-contained modules (one directory each: `install`, `README.md`, `test_<name>.py`, optional `packages`, its payload), every one wired into install.sh's loop. Every tool the overlay puts on PATH ships under its module — modules/{hypr,vulkan-gpu,yubikey}/bin/ — and is symlinked into ~/.local/bin by that module
│
├── tests/                      # What is not a module's: the core, the tree-wide guards, the publish pipeline (see below)
├── VERSION                     # SemVer, bumped by hand; `scripts/publish` tags what it names
├── scripts/publish             # The three gates → tag → one atomic push of dev, stable and the tag
├── docs/                       # This file
├── .github/                    # CI workflow
├── web/, assets/               # index.html + favicon.svg (static landing page); banner.svg (the README's and the page's brand art)
├── Makefile, pyproject.toml    # Test/lint targets; pytest/ruff config
├── .gitignore                  # Python caches, `.vscode/`, editor swap files and Claude Code's local session state
├── .claude/settings.json       # Agent deny/ask rules — the layer bypass permission mode still honours
└── AGENTS.md, CLAUDE.md, README.md   # CLAUDE.md is a symlink to AGENTS.md — Claude Code reads CLAUDE.md, not AGENTS.md
```

What reaches a user's machine, and how, is `README.md` › Repository layout.
The `modules/hypr/*.lua` override files are **copied** into `~/.config/hypr/`
— `hyprconf hypr` after an edit (`AGENTS.md` › The Hyprland copies).

---

## Testing

One hermetic suite in two places — beside each module, and `tests/` for what
is not a module's (the contract is in `AGENTS.md` › Tests); CI runs it in an
`archlinux:latest` container, as an unprivileged user.

```
conftest.py                       # the `box` fixture every test builds on (repo root: it reaches both trees below)
modules/<name>/test_<name>.py     # one suite per module, beside its `install` — `testpaths` collects modules/ and tests/ in one pytest run
tests/                            # what is not a module's: install.sh and the tree-wide guards
├── test_core.py                  #   install.sh: the curl bootstrap, the flags and module selection, the ~/.local/bin/hyprconf link, the post-update hook end to end, --undo, a full run of every module byte-stable across two runs, and the restraint a whole run is held to (no sudo outside a module's gate, never a theme switch)
├── test_scans.py                 #   every shipped bash script, by shebang: the documented header, no pacman/AUR/removal/chsh on any path, no fetch-and-execute, `--` on every root write, the working hyprctl forms, plain names in every modules/*/packages
├── test_plugins_contract.py      #   every shipped plugin folder (modules/bar-*/plugin): omarchy-plugin-validate's checks ported to Python (CI has no Omarchy — each module runs the real validator too), the publishable shape (README, NOTICE, nothing of the overlay's, exec bits), the Text.PlainText and implicit-size rules, real qmllint, and every `bar.`/`bar.shell.` read against the installed PluginBarApi/PluginShellApi (pinned lists when Omarchy is absent)
├── test_no_pii.py                #   every file in the checkout (on-disk walk), identities derived at runtime
├── test_supply_chain.py          #   the published trust surface: web/ self-contained, https-only and stable-pinned bootstrap, every modules/*/install clone pinned and never pulled, sha-pinned least-privilege CI, the .claude guardrail entries
├── test_publish.py               #   scripts/publish: the gates, the tag, the atomic promotion and its refusals, against a throwaway bare origin
└── test_docs.py                  #   the docs contract, structure only: the README branding block byte for byte, one Modules row and one Reverting line per module
```

### Running tests

```bash
make check               # the three commit gates: lint + shellcheck + test

make test                # the whole suite, one invocation, in parallel (pytest -n auto)

# Lint gates
make lint                # ruff check + ruff format --check
make shellcheck          # every bash script (selected by shebang), severity=warning; plus SC2086 (info-level) on
                         #   the root-writing files — modules/yubikey/bin/hyprconf-yubikey, modules/firefox/install
                         #   and modules/keychron/install (the two module installs that call sudo)
make fmt                 # ruff format + safe fixes
```

The gates need `ruff`, `shellcheck`, `python-pytest` and `python-pytest-xdist`
— official repos, the same Arch packages CI installs, so the versions match:
`omarchy pkg add ruff shellcheck python-pytest python-pytest-xdist`. `jq`,
`luac`, `qmllint` and `zsh` are used real by the tests that need them and
skipped when absent; `git` is required. CI's own package list, with the
reason each entry is there, lives in `.github/workflows/test.yml`; the tests that
skip in CI, and the recipe for reproducing a container-only failure, are in
`AGENTS.md` › Gates and CI.

### Writing hermetic tests

- Start from the `box` fixture in the repo-root `conftest.py`: a throwaway
  machine per test — a tmp `$HOME`, a tmp `/etc`, a tmp `$OMARCHY_PATH` tree
  (`OMARCHY_TREE` there holds what the scripts read out of it) and a fakes
  directory FIRST on PATH with a recording stub for every `omarchy-*` name the
  shipped scripts and payload carry — derived from them, so a new call cannot
  slip past the fakes — plus `omarchy`, `sudo`, `hyprctl`, `udevadm`,
  `fc-list`, `findmnt`, `git`, `limine-entry-tool`, `nvidia-smi` and
  `vulkaninfo`. PATH is those fakes, then
  only `/usr/bin` and `/bin`, and the environment is built from scratch, so
  nothing of the developer's session reaches a run. `box.stub(name, body)`
  gives one fake something to do (a `sudo` that execs its arguments) ahead of
  the shared ones; `box.run(script, *args, tty=, env=, stdin=)` runs a script
  against the box (`box.core()` the installer, `box.undo(module)` a module's
  undo branch); `box.calls`, `box.commands`, `box.calls_of(name)` and
  `box.reset()` read back what ran; `box.files()` is every file under its
  HOME; `box.fakes` is what a suite's "every external the tool names has a
  fake" self-check holds the script to. Its git identity
  (`GIT_AUTHOR_*`/`GIT_COMMITTER_*`, `os.environ.setdefault` at import) covers
  the whole session, CI's identity-less container included.

- Every path a script reads is under `$HOME` (relocated wholesale by the
  suite) or behind an env seam — in `install.sh` only `OMARCHY_PATH` (Omarchy's
  own variable, not `_HYPRCONF_*`), whose `default/` tree the preflight tests
  for; in the modules (derive this list rather than trusting it:
  `grep -oh '_HYPRCONF_[A-Z_]*' modules/*/install modules/*/bin/* | sort -u`)
  `_HYPRCONF_FIREFOX_POLICIES` and `_HYPRCONF_UDEV_RULES` —
  the two root-owned destinations a module writes — with `_HYPRCONF_ASSUME_TTY`
  in `modules/firefox/install` and `modules/keychron/install`; `_HYPRCONF_*` in
  `modules/yubikey/bin/hyprconf-yubikey` for the boot files it reads and
  writes (`MKINITCPIO_D`, `LIMINE_DEFAULT`, `LIMINE_CONF_D`,
  `INITCPIO_INSTALL`, `VCONSOLE`) plus `ASSUME_TTY` for its one prompt;
  `_HYPRCONF_*` in `modules/vulkan-gpu/bin/hyprconf-vulkan-gpu` for the three
  trees it reads outside `$HOME` (`SYS_PCI`, `SYS_DRM`, `VULKANINFO`),
  `HYPRCONF_STATS_*` in `modules/bar-resources/plugin/bin/hyprconf-stats`
  (`NET_ROOT`, `PROC_STAT`, `PROC_MEMINFO`, `PROC_ROUTE`, `HWMON_ROOT`,
  `INTERVAL`, `ITERATIONS`, and `SLEEP_BUILTIN` — the loadable sleep's path,
  pointed at a file that is not there so a PATH `sleep` fake runs between
  ticks) and `HYPRCONF_GPU_*` in its sibling `hyprconf-gpu-info` (`INTERVAL`,
  `DRM_ROOT`, `ITERATIONS`, `PCI_IDS`) — pointed at `tmp_path`. Never make
  such a variable `readonly`.
- The fake bins (`AGENTS.md` › Tests): `omarchy-*`, `hyprctl`, `sudo`,
  `systemd-cryptenroll`, `limine-mkinitcpio`, `limine-entry-tool` (the fake
  assembles `--get-cmdline` from the box's own limine config files), `findmnt`
  (the real one answers for the developer's own root), `udevadm`
  (the real one would re-apply rules on the developer's own machine),
  `vulkaninfo` (it would answer for the host's GPUs), `nvidia-smi` (likewise),
  `sleep` (the feeders' hook between ticks: it advances the fake counters and
  mutates the fake trees, then runs the real sleep), `git` (the shared fake
  exits 0; `tests/test_core.py`'s `live` box gives it a body — a clone of a
  local directory runs the real git, which is how the curl path is exercised,
  a clone of a URL makes the directory with the pinned revision as its HEAD,
  and a pull is a no-op; the real git otherwise runs only inside a throwaway
  checkout under `tmp_path`, never the repository the suite runs from).
  `/usr/bin` carries every `omarchy-*` command (`pacman -Ql omarchy
  omarchy-settings omarchy-nvim | grep -c /usr/bin/omarchy-`), so a PATH of
  fakes plus `/usr/bin` keeps none of them out: the `box` fixture derives a
  fake for every `omarchy-*` name the shipped scripts and payload carry, so
  a new call is covered the moment it is written. Real when present, skipped
  otherwise: `jq`, `luac`,
  `qmllint`, `shellcheck`, `sh`, `zsh`,
  `/usr/share/omarchy/bin/omarchy-plugin-validate`
  (reads a manifest, changes nothing), the installed clock plugin's files
  (`modules/bar-clock/test_bar_clock.py` reads them for parity).
  A test that reads a file of the installed Omarchy falls back to a
  fixture instead of skipping (`conftest.OMARCHY_TREE`'s
  `default/firefox/policies.json` stands in for Omarchy's policy everywhere,
  and `modules/firefox/test_firefox.py` checks it against the real file where
  there is one). Never invoke `pacman` (it exists in the container).

### CI

`.github/workflows/test.yml` runs one job on every push to any branch:
`make check` — the target `scripts/publish` gates on — inside
`archlinux:latest`, as a `ci` user the job creates and hands the checkout to.
There are no pull requests in this flow (`dev` → `stable` is a push by
`scripts/publish`), so `push` is the only trigger. It must be green before a
publish; the recipe for reproducing a container-only failure is in
`AGENTS.md` › Gates and CI.

---

## Security

The overlay is published: strangers clone `stable` and run `install.sh` with their own sudo. Three trust boundaries, each held by mechanical pins (AGENTS.md hard rule 8):

1. **Unprivileged → root, on the local box.** `install.sh` itself asks for no sudo at all: the modules that declare it (`modules/firefox`'s system policy, `modules/keychron`'s udev rule, the package installs in `modules/{terminal-kitty,shell-zsh,font,vscode}`) and `modules/yubikey`'s `run_root` surface (rule 6 names them) are the only privileged paths. Root coreutils calls keep the `--` end-of-options shape (`tests/test_scans.py::test_every_root_write_carries_the_end_of_options_marker`, over every shipped script, beside the per-file pins in `modules/{yubikey,firefox,keychron}/test_*.py`); every tool on PATH is a module's, a symlink into the checkout — `install.sh` copies none; every module's `packages` file holds plain package names only (`test_every_packages_file_holds_plain_package_names`). A new root write or sudo call names itself in the module's README (rule 6) and lands with a pin.
2. **Untrusted content → local execution.** Window titles and feeder strings render as plain text (`textFormat: Text.PlainText`, stock parity); nothing shipped fetches-and-executes — `tests/test_scans.py::test_nothing_shipped_fetches_and_executes` forbids curl/wget/pipe-to-shell/`base64 -d`/`eval` in every shipped script and the zsh payload, with the allowed exceptions written down in full inside the test. A new exception is added there verbatim, with its why, or the change does not land.
3. **Publish pipeline → strangers' boxes.** The bootstrap is https-only (`--proto '=https'`; `test_published_one_liners_are_https_only`, `test_bootstrap_defaults_are_pinned_https_and_stable` — schemeless, curl's first request is plaintext port 80 and an on-path attacker answers it before the redirect exists). powerlevel10k — the one third-party repository left, and code that runs in every interactive zsh — is cloned at a reviewed commit by `modules/shell-zsh` and never pulled; bumping the pin is a deliberate commit through the publish gates (`test_every_module_clone_is_pinned_to_a_reviewed_commit`, which holds every `modules/*/install` to the same rule). Oh My Zsh is gone with its in-tree updater. CI actions are sha-pinned under a read-only token (`test_ci_workflow_is_least_privilege`); `web/` stays self-contained (`test_web_page_is_self_contained`); secret-shaped material anywhere in the tree fails `test_no_secret_material_anywhere`; `install.sh` refuses to run as root (the curl|bash sudo-prefix habit half-installs into /root).

The checklist for any change: does it add a network touch, execute anything it did not ship with, widen a root path or a udev match, or move bytes from an untrusted source toward a shell, QML or root sink? Then the matching pin above changes in the same commit, its reasoning beside it. A pin loosened without its why is a finding, not a diff.

## Branches

| Branch | Purpose |
|--------|---------|
| `dev` | All active development |
| `stable` | What users clone; written only by `scripts/publish` |

## Publishing to stable

```bash
bash scripts/publish            # from a clean, pushed `dev` checkout
```

1. Verifies the working branch, a clean tree, and that local `dev` matches its remote
2. Lint gates: `make lint` + `make shellcheck`
3. Test suites: `make test`
4. Creates the annotated tag `v<VERSION>` at HEAD (reusing one already there)
5. Moves `dev`, `stable` and the tag in one `git push --atomic
   --force-with-lease` — all three or none, so `stable` carries the exact sha
   the gates went green on and a run that dies is simply rerun
6. **When the user asks for a deploy, right after: upload `stable`'s
   `install.sh` and invalidate CloudFront** (the objects under "Updating the
   website" below). `scripts/publish` deploys nothing, so until that upload
   `hyprconf.sh` keeps serving the previous release's `install.sh` to curl —
   whatever that file does.

Nothing is packaged: users `git clone -b stable`, so the promoted branch is the release.

The script takes no options. `VERSION` is bumped by hand, in the commit that
earns it; a publish whose tag already exists on another commit is refused
naming it. The local `stable` branch is never moved — `git branch -f` exits
128 while `stable` is checked out in another worktree, and nothing reads it.

`tests/test_publish.py` runs the script end to end
against a throwaway bare origin (a recording `make` stub stands in for the
gates): the real promotion and its rerun, a rejected push moving no ref at
all, the tag-on-another-commit refusal, and the argument / dirty-tree /
off-branch refusals.

## Publishing a plugin

`omarchy plugin add <url>` clones a repository and expects `manifest.json` at
its root — `bin/omarchy-plugin-add` (Omarchy 4.0.2-1): `git clone`,
`omarchy-plugin-validate`, then a move to `~/.config/omarchy/plugins/<id>/`
— so the monorepo cannot be added as it is. Each bar module's `plugin/` folder
is published as a repository of its own, split out of `dev`'s history with git's
own tool (history and the `100755` modes travel with it):

```bash
git subtree split --prefix=modules/bar-clock/plugin -b plugins/hyprconf-clock
git push git@github.com:ak4dev/omarchy-hyprconf-clock.git plugins/hyprconf-clock:main
```

Never run here: a push is the user's, on request, like every other. The
folder is the whole plugin — everything a split needs lives inside it:
`manifest.json`, `README.md` (the install line, dependencies, settings, what
`omarchy plugin disable` / `remove` do to it), `NOTICE` where the code is
Omarchy's (MIT requires its notice on every copy), and any script the widget
runs, under `bin/`, resolved from the plugin's own directory and never from
`PATH`. `tests/test_plugins_contract.py` pins that shape and the validator's
own checks over every folder, and each bar module runs Omarchy's real
validator against its installed link. The manifest's `version` stays at
`1.0.0` — nothing reads it (the validator checks the key's presence,
`omarchy plugin update` is a git fast-forward) and Omarchy's own plugin
manifests have never moved off it. A published plugin is listed on the
community directory, <https://omarchyplugins.com>. Until that push each
plugin README gives Omarchy's own by-hand install instead
(`/usr/share/omarchy/shell/README.md` › Installing by hand) and names
`omarchy plugin add <url> --enable --yes` as the
form that applies once the repository is there — `--yes` because
`omarchy-plugin-add` otherwise asks for a bar section
(`select_bar_widget_placement`, `bin/omarchy-plugin-add:161-162`) and the
answer moves a `clonedFrom` widget out of the stock slot it just took. Each
bar module links the same folder from the checkout, and leaves a folder that is a git checkout (`omarchy
plugin add`'s) to `omarchy plugin update`.

## Updating the website

`hyprconf.sh` is the `hyprconf-sh` S3 bucket behind a CloudFront distribution
that routes on the User-Agent: browsers get the `index.html` object, `curl` and
`wget` get the `install.sh` object — which is what makes
`bash <(curl -fsSL --proto '=https' https://hyprconf.sh)` work. That router is existing infrastructure
outside this repo, managed by hand; there is no deploy tooling (`aws` comes
from `omarchy-pkg-add aws-cli-v2`, an official `extra` package), and the upload
happens only when the user asks for a deploy. Four objects, and the `install.sh`
one must be the **`stable`** branch's — upload it after `scripts/publish`, never
the `dev` copy. The page itself is fixed in shape: the `assets/banner.svg` art
as the brand (inline SVG, never scrolls), a tiling glyph and a `user@omarchy`
prompt on the install block, one centred GitHub button, compact, no JS and no
external requests:

| Key | Source | Content-Type |
|---|---|---|
| `install.sh` | `git show stable:install.sh` | `text/plain; charset=utf-8`, `Cache-Control: no-cache, no-store` |
| `index.html` | `web/index.html` | `text/html; charset=utf-8`, `Cache-Control: public, max-age=300` — without a max-age browsers keep the previous page for days (heuristic freshness) |
| `favicon.svg` | `web/favicon.svg` | `image/svg+xml`, `Cache-Control: public, max-age=31536000, immutable` |

```bash
git show stable:install.sh | aws s3 cp - s3://hyprconf-sh/install.sh \
  --content-type 'text/plain; charset=utf-8' --cache-control 'no-cache, no-store'
aws s3 cp web/index.html        s3://hyprconf-sh/index.html     --content-type 'text/html; charset=utf-8' --cache-control 'public, max-age=300'
aws s3 cp web/favicon.svg       s3://hyprconf-sh/favicon.svg    --content-type image/svg+xml --cache-control 'public, max-age=31536000, immutable'

DIST=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?contains(Aliases.Items,'hyprconf.sh')].Id" --output text)
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*"
```

Verify both routes once the invalidation has completed — the curl UA must get
`stable`'s installer, a browser UA the page:

```bash
curl -fsSL https://hyprconf.sh | cmp - <(git show stable:install.sh) && echo installer-ok
curl -fsSL -A 'Mozilla/5.0' https://hyprconf.sh | cmp - web/index.html && echo page-ok
```
