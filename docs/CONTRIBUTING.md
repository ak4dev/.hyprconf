# Contributing to hyprconf

Read [`AGENTS.md`](../AGENTS.md) first — its rules bind every change.

## Repository layout

```
.hyprconf/
├── install.sh             # the core: flags, the curl bootstrap, the module loop, the ~/.local/bin/hyprconf link, the hook, --undo
├── hooks/10-hyprconf      # the post-update hook: exec ~/.local/bin/hyprconf --no-update --no-packages
├── modules/<name>/        # one self-contained module each: install (+ `install undo`), README.md, test_<name>.py,
│                          #   an optional packages file and its payload — tools under bin/, a bar plugin under plugin/
├── modules/bar-plugin.sh  # what the four bar-*/install share: link, rescan, enable, the shell.json fallback, undo — sourced, never run
├── conftest.py            # the `box` fixture (repo root, so it reaches modules/ and tests/)
├── tests/                 # what is not a module's: the core, the scans, the plugin contract, PII, the supply chain,
│                          #   the publish pipeline, the docs contract
├── VERSION                # SemVer, bumped by hand; scripts/publish tags it
├── scripts/publish        # the three gates → tag → one atomic push of dev, stable and the tag
├── docs/CONTRIBUTING.md   # this file
├── .github/workflows/     # CI: make check in archlinux:latest, unprivileged
├── web/, assets/          # the static landing page + favicon; the README banner
├── Makefile, pyproject.toml, .gitignore, .claude/settings.json
└── AGENTS.md, CLAUDE.md -> AGENTS.md, README.md
```

Each module's README is the home for what it does and how it is undone; the mechanism with its Omarchy citations is
the header of its `install`; a test file's docstring says what it pins (`awk 'FNR==1,/"""$/' modules/*/test_*.py tests/*.py`).

## Testing

The contract is `AGENTS.md` › Tests; collection (`testpaths`, unique basenames) is commented in `pyproject.toml`.

### Running tests

```bash
make check      # the three commit gates: lint + shellcheck + test — what scripts/publish and CI run
make test       # the suite alone (pytest -q -n auto -rs); make lint / make shellcheck / make fmt are the others
```

The gates need `ruff`, `shellcheck`, `python-pytest` and `python-pytest-xdist`, the official packages CI installs:
`omarchy pkg add ruff shellcheck python-pytest python-pytest-xdist`. CI and the skip budget are `AGENTS.md` › Gates
and CI; the package list with the reason for each entry is `.github/workflows/test.yml`. Reproduce a container-only
failure with:

```bash
docker run --rm -v "$PWD":/src:ro archlinux:latest bash -c \
  'pacman -Syu --noconfirm --needed git make ruff python python-pytest python-pytest-xdist jq shellcheck diffutils lua qt6-declarative zsh &&
   cp -r /src /repo && useradd -m ci && chown -R ci: /repo && cd /repo && su ci -s /bin/bash -c "make check"'
```

### Writing hermetic tests

- Start from `box`, the fixture in the repo-root `conftest.py`: a throwaway machine per test — a tmp `$HOME`, a tmp
  `/etc`, a tmp `$OMARCHY_PATH` tree (`OMARCHY_TREE` holds what the scripts read from it) and a fakes directory
  FIRST on PATH, then only `/usr/bin` and `/bin`, with an environment built from scratch so nothing of the
  developer's session reaches a run. `box.stub(name, body)` gives a fake something to do; `box.run(script, *args,
  tty=, env=, stdin=)` runs a script against the box (`box.core()` the installer, `box.undo(module)` a module's
  undo branch); `box.calls`, `box.commands`, `box.calls_of(name)` and `box.reset()` read back what ran;
  `box.files()` is every file under its HOME and `box.snapshot(*roots)` the mode, inode, mtime and
  bytes-or-link-target of every path under them (HOME and `/etc` by default), so `before == after` is "a second run
  wrote nothing"; `box.omarchy_write(rel, text)` adds to the Omarchy tree. It also exports the session's git
  identity (`GIT_AUTHOR_*` / `GIT_COMMITTER_*`, CI's identity-less container included), so no test passes
  `-c user.*` itself.
- The fakes: a recording stub for every `omarchy-*` name the shipped scripts and payload carry — derived from them
  at session start, so a new call cannot slip past — plus the handful that would otherwise reach the real machine,
  `EXTRA_FAKES` in `conftest.py`, each with its reason beside it; `bar_shell(box, anchor, layout)` writes a
  `shell.json` and installs the four that model the running shell (`omarchy-plugin-{list,enable,disable}`,
  `omarchy-bar`). `box.fakes` is the set a suite's "every external the tool names has a fake" self-check compares
  against. `/usr/bin` carries every `omarchy-*` command, so fakes-then-`/usr/bin` keeps none of them out: the
  derivation does. Real when present: conftest's `PURE_TOOLS`, and the installed Omarchy's own files
  (`omarchy-plugin-validate`, the stock clock, `default/firefox/policies.json` — for which `OMARCHY_TREE` is the
  fixture stand-in). A probe of that tree goes through conftest's `OMARCHY` and skips with `reason=NEEDS_OMARCHY`
  to the letter, since the budget matches on the reason. Never invoke `pacman`: the container has one.
- Every path a script reads is under `$HOME` (relocated wholesale) or behind an env seam declared in a
  `: "${_HYPRCONF_X:=…}"` line at the top of its own script, never `readonly` — `OMARCHY_PATH` (Omarchy's own) for
  the tree, `HYPRCONF_STATE` for the marker directory, `HYPRCONF_STATS_*` / `HYPRCONF_GPU_*` for the feeders. Grep
  the seams rather than trust a list:
  `grep -oh '_HYPRCONF_[A-Z_]*\|HYPRCONF_STATS_[A-Z_]*\|HYPRCONF_GPU_[A-Z_]*' install.sh modules/*/install modules/*/bin/* modules/*/plugin/bin/* | sort -u`.
- Every module suite covers the mandatory cases (the four bar modules' live once, per plugin folder, in
  `tests/test_plugins_contract.py`): a second run writes nothing and calls nothing that mutates;
  `install undo` restores stock after an install and is a no-op on a box that never installed; the sudo and TTY
  gates where the module has them.

## Security

The overlay is published: strangers clone `stable` and run `install.sh` with their own sudo. Three trust boundaries, each held by mechanical pins (`AGENTS.md` rule 8):

1. **Unprivileged → root, on the local box.** `install.sh` asks for no sudo; the only privileged paths are the modules that declare them (rule 6). `tests/test_scans.py::test_every_root_write_carries_the_end_of_options_marker` over every shipped script, against the `SUDO_CALLERS` literal that names the whole root surface, `::test_every_packages_file_holds_plain_package_names`, `::test_nothing_shipped_switches_the_active_theme` and `::test_no_pacman_aur_wrapper_removal_or_chsh_on_any_path`; every tool on PATH is a symlink into the checkout.
2. **Untrusted content → local execution.** Window titles and feeder strings render as plain text (`tests/test_plugins_contract.py::test_plugin_text_never_renders_runtime_strings_as_rich_text`); nothing shipped fetches-and-executes (`tests/test_scans.py::test_nothing_shipped_fetches_and_executes`, its allowed exceptions written inside it — a new one is added there verbatim, with its why, or the change does not land).
3. **Publish pipeline → strangers' boxes.** `tests/test_supply_chain.py`: the https-only one-liners and the pinned bootstrap defaults, the pinned and never-pulled powerlevel10k clone (every `modules/*/install` clone, `test_every_module_clone_is_pinned_to_a_reviewed_commit`), sha-pinned least-privilege CI, a self-contained web page, the `.claude/settings.json` guardrail entries; `tests/test_no_pii.py::test_no_secret_material_anywhere`; `install.sh` refuses to run as root.

One deliberate exception to the https-only one-liners: the landing page's command drops the scheme and the `--proto` pin, so it reads as one short line and rides `hyprconf.sh`'s `301` from http. That first hop is plaintext and an on-path attacker answers it, which is the cost the author accepted for the page — every command a reader copies out of `README.md`, `install.sh` or this file still names https. The page's command is therefore frozen as `WEB_ONE_LINER` rather than left unpinned, and that constant is the only home for the literal: quoting it in prose trips the scan that holds the rest.

The checklist for any change: does it add a network touch, execute anything it did not ship with, widen a root path or a udev match, or move bytes from an untrusted source toward a shell, QML or root sink? Then the matching pin above changes in the same commit, its reasoning beside it. A pin loosened without its why is a finding, not a diff.

## Publishing to stable

```bash
bash scripts/publish            # from a clean `dev` checkout in sync with origin/dev
```

Only `scripts/publish` writes `stable`: it dies naming `ruff`, `shellcheck` or `pytest` when one is not on PATH,
before any git or network work, then verifies the branch and a clean tree, runs the three gates, tags `v$(<VERSION)`
at HEAD (reusing an identical tag, refusing one on another commit) and moves `dev`, `stable` and the tag in one
`git push --atomic` — all three or none, so `stable` carries the exact sha the gates went green on and a run that
dies is simply rerun. The push is never forced: a `stable` that moved outside the script is a refusal, since every
user clone pulls it `--ff-only`. It takes no options and bumps nothing: `VERSION` moves by hand in the commit that
earns it. `tests/test_publish.py` runs the script end to end against a throwaway bare origin. **When the user
asks for a deploy, right after: the website upload below** — until then `hyprconf.sh` keeps serving the previous
release's `install.sh` to curl.

## Publishing a plugin

`omarchy plugin add <url>` clones a repository and expects `manifest.json` at its root (`bin/omarchy-plugin-add`,
Omarchy 4.0.4-1), so the monorepo cannot be added as it is. Each `modules/bar-*/plugin` folder is the whole plugin
and splits out with git's own tool, history and modes included:

```bash
git subtree split --prefix=modules/bar-clock/plugin -b plugins/hyprconf-clock
git push git@github.com:ak4dev/omarchy-hyprconf-clock.git plugins/hyprconf-clock:main
```

Never run here: a push is the user's, on request. `tests/test_plugins_contract.py` pins the splittable shape and
the validator's own checks over every folder, and runs Omarchy's real validator against a link to each; the
manifest `version` stays `1.0.0` — nothing reads it. Until that push each plugin README gives Omarchy's by-hand
install (`/usr/share/omarchy/shell/README.md` › Installing by hand) and names
`omarchy plugin add <url> --enable --yes` as the form that applies once the repository exists — `--yes` because
the bar-section prompt would move a `clonedFrom` widget out of the stock slot it just took.

## Updating the website

`hyprconf.sh` is the `hyprconf-sh` S3 bucket behind a CloudFront distribution that routes on the User-Agent —
`curl` and `wget` get the `install.sh` object, browsers `index.html` — managed by hand outside this repo (`aws` from
`omarchy-pkg-add aws-cli-v2`, an official `extra` package). The `install.sh` object must be **`origin/stable`'s**: upload
after `scripts/publish`, only when the user asks for a deploy. Always `origin/stable`, never the local `stable`
branch — `scripts/publish` deliberately never moves that one (its comment says why), so on a working checkout it
sits at whatever release last touched it and `git show stable:install.sh` would put a months-old installer in the
bucket. The page stays self-contained (`test_web_page_is_self_contained`).

```bash
git show origin/stable:install.sh | aws s3 cp - s3://hyprconf-sh/install.sh \
  --content-type 'text/plain; charset=utf-8' --cache-control 'no-cache, no-store'
# max-age=300: without one browsers keep the previous page for days
aws s3 cp web/index.html        s3://hyprconf-sh/index.html     --content-type 'text/html; charset=utf-8' --cache-control 'public, max-age=300'
aws s3 cp web/favicon.svg       s3://hyprconf-sh/favicon.svg    --content-type image/svg+xml --cache-control 'public, max-age=31536000, immutable'

DIST=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?contains(Aliases.Items,'hyprconf.sh')].Id" --output text)
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*"
```

Verify both routes once the invalidation has completed — the curl UA must get `origin/stable`'s installer, a browser
UA the page:

```bash
curl -fsSL https://hyprconf.sh | cmp - <(git show origin/stable:install.sh) && echo installer-ok
curl -fsSL -A 'Mozilla/5.0' https://hyprconf.sh | cmp - web/index.html && echo page-ok
```
