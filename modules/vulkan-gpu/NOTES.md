# modules/vulkan-gpu — notes for the integrator (delete this file)

Module = `install` (one symlink) + `bin/hyprconf-vulkan-gpu` + `README.md` + `test_vulkan_gpu.py`. 66 tests,
`pytest modules/vulkan-gpu -q` green; `shellcheck --severity=warning` and the SC2086 pass clean on both scripts;
`ruff check` / `format --check` clean. Payload was COPIED — `bin/hyprconf-vulkan-gpu` and
`tests/unit/test_vulkan_gpu.py` are still in place for you to delete.

## Findings landed

| id | how |
|---|---|
| `vulkan.0#8`, `vulkan.0#12` | **`toggle` gone**, `use <display\|other\|pci-address>` and `run <gpu> [--] <command>` kept. `cmd_toggle` (the grep-back of the pinned id, the `(cur+1) % n` step — the tool's only read of its own file's contents) is deleted and `use display` / `use other` is the two-GPU switch (`#12`'s own "do"); `run` stays because `#8`'s "do" keeps it by name — the only re-login-free switch, and the Steam launch option. `fix`, `status`, `alt`, `remove`, `help` stay, and so do `require_unique_id`, `nv_pair_for` and `warn_conflicts` — all three are on `fix`'s own path (the finding's inventory was wrong about that; the verifier note says so). ~25 tool lines and ~30 test lines. |
| `vulkan.0#10` | `resolve_gpu` now takes `display`, `other` and the **full PCI address** only. Dropped: the PCI-order index (`status` prints no ordinal), the short `04:00.0` form, and the `vendor:device` id — an id can be shared by two cards, which is the one thing `require_unique_id` exists to refuse. Pinned by `test_use_takes_neither_an_ordinal_nor_a_short_address_nor_an_id`. |
| `vulkan.0#2` | One home for the mechanism: `README.md` › What. The script header keeps two lines (symptom + pointer) plus the uwsm/`omarchy commands --json` provenance block **verbatim** (rules 1/2); `usage()` lost its six-line RandR paragraph; the NVIDIA-pair rule is stated once in code (`nv_pair_for`) and once in the README. |
| `vulkan.0#4` | The four `$HOME` seams (`_HYPRCONF_UWSM_ENV_D`, `_HYPRCONF_UWSM_ENV`, `_HYPRCONF_ENVIRONMENT_D`, `_HYPRCONF_STATE`) deleted — `$HOME` is relocated wholesale by the box fixture. `ENV_D`/`ENV_FILE` are plain `$HOME` paths, help prints the real paths, and the seam block is the three that read outside `$HOME`: `_HYPRCONF_SYS_PCI`, `_HYPRCONF_SYS_DRM`, `_HYPRCONF_VULKANINFO`. |
| `vulkan.0#5` | Probe kept (`vulkan-tools` stays uninstalled — rule 3). Cost trimmed instead: the probe-ordering prose is gone from `usage()`, one comment at `diagnose_vulkan` states the policy, and one test (`test_use_and_run_never_probe_vulkaninfo`) pins it in both directions — `run` sits on every game launch, so it must never wake a suspended GPU. |
| `vulkan.0#6` | One `env_hits <ere> [skip]` helper over the three files; `configured_in` = first hit of `FILTER\|PROTON`, `conflicts_elsewhere` = all hits of `FILTER\|SELECT\|PROTON` minus our own file. The two patterns stay different **on purpose** and a comment says why; new test `test_device_select_alone_is_not_configured_but_is_a_conflict`. The stale "so `use` and `toggle` name them" caller list is corrected to `fix` and `use`. No `head -1` pipeline (SIGPIPE + `pipefail` would kill the script): first line taken with `${all%%$'\n'*}`. |
| `vulkan.0#7` | `id_count` → predicate `id_shared`; both call sites asked `> 1`. The errexit-safe `if [[ ]]; then` body kept, no `grep -c` pipeline. |
| `vulkan.0#9` | `status --quiet` gone (no caller ever). `status` joined the no-argument arm of `main`, so `status --quiet` now exits 1 "status takes no arguments". |
| `vulkan.0#18` | `test_help_covers_every_subcommand`: one run, the subcommand list **derived from `main()`'s case arms** (`dispatched()`), `-h`/`--help` compared to it instead of three parametrized runs; the eight-seam block and the `RandR`/`OMARCHY_UPDATE_LOGGED` prose pins are gone. |
| `vulkan.0#1`, `vulkan.0#17`, `vulkan.0#15` | The module is the declaration: one file on PATH, no repo, no Omarchy command, no `@HYPRCONF_DIR@`, no marker. Test docstring is 14 lines (was 37), the hand-rolled `vulkaninfo` fake and the duplicate status-probe assert are gone, `test_unreadable_sysfs_is_an_error` stays at two runs. |
| `install-core.3#14`, `#16` | `stage_bin`'s share for this tool: `ln -sfn` behind a `readlink` guard (`ln -sfn` gives a correct link a **new inode**, which would make a re-run a write — `test_a_second_run_writes_nothing` compares inodes), no sed-render, no `.hyprconf-tmp`, no `@HYPRCONF_DIR@`, and no "not on PATH" warning (Omarchy appends `~/.local/bin` in `default/bash/env-bootstrap:37-40` and `envs:31-33`; `preflight` already refuses a box without Omarchy). |

## Deviations from the finding text — deliberate, put them in the commit body

1. **`use` kept alongside `run`** — finding `#8`'s "do" drops `use` and keeps `run`; `#12` (confirmed, independent)
   deletes `toggle` and keeps `use display` / `use other` as the two-GPU switch, which `#8` cannot also delete
   without leaving `#12` unsatisfiable. So both stay: `use` writes the persistent pin the desktop record documents
   (legacy `README.md:343-355`, "99% on the pinned card"), `run` lends a GPU to one command with no re-login. Nothing
   user-visible is lost; `toggle` is the one subcommand removed here.
2. **`alt` kept** — finding `#8`'s verifier keeps it, and it is the only answer when two cards share a
   `vendor:device` id (`require_unique_id`'s die points at it).
3. `feat(vulkan)!` + a `BREAKING CHANGE:` footer: removed subcommand `toggle`, the `status --quiet` flag, and the
   `use` selector forms that went with `vulkan.0#10` (ordinal, short address, `vendor:device`).

## Findings not landed here

- `vulkan.0#3` — no-op by design: the `Omarchy 4.0.0-1` date in the header is that fact's provenance (AGENTS.md:8)
  and stays as written. Re-verified today against installed 4.0.3-1: `/usr/bin/omarchy-hw-vulkan` still only globs
  `/usr/share/vulkan/icd.d`, and nothing under `/usr/share/omarchy` mentions `VK_LOADER*`, `PROTON_ENABLE_WAYLAND`
  or writes `~/.config/uwsm/env.d` (the one writer is `omarchy-upgrade-to-quattro:1675`, a migration).
- `vulkan.0#19` — the repo-wide script-hygiene meta test belongs to `tests/test_scans.py`, not to a module (a shared
  test module iterating `bin/` is the opposite of a module that tests alone). The `"MESA_VK_DEVICE_SELECT=" not in
  text` pin is gone by construction: the module ships no hygiene test. Make sure `test_scans.py` covers
  `modules/*/install` and `modules/*/bin/*` for shebang / `set -euo pipefail` / no `readonly` / exec bit.
- `vulkan.0#14`, `install-core.3#17`, `install-core.3#18` — already landed in the foundation phase (`prompt`,
  `ignore`, the marker, `_HYPRCONF_ASSUME_TTY` and `stage_vulkan_gpu` were gone before this module started).
- `test-install-a.3#5`, `test-install-a.2#4` — `tests/unit/test_omarchy_install.py`'s business, below.

## What to delete / rewire in the legacy tree

- `install.sh`: `stage_bin` **cannot go with this module alone** — it still installs `hyprconf-gaps` and
  `hyprconf-monitor-preset` (hypr) and `hyprconf-yubikey` (yubikey). (`hyprconf-firefox-theme` is already gone:
  modules/firefox-theme replaced it with a self-contained bash hook.) Delete `stage_bin` once those three are
  modules; nothing else in `install.sh` names vulkan any more.
- Payload: `bin/hyprconf-vulkan-gpu` (copied — take the module's version, it is not a byte copy).
- `tests/unit/test_vulkan_gpu.py` — delete; `modules/vulkan-gpu/test_vulkan_gpu.py` replaces it whole.
- `tests/unit/test_omarchy_install.py`: `test_every_shipped_tool_lands_on_path` (1883-1893) asserts **copied bytes
  with `@HYPRCONF_DIR@` substituted** — it must become a symlink assertion, or go with `stage_bin`; the `"bin"`
  `PAYLOAD` entry (:326) goes when `bin/` does; the comment at :1502 naming `bin/hyprconf-vulkan-gpu` as a heredoc
  the fetch-and-execute scan must keep needs re-pointing at `modules/vulkan-gpu/bin/hyprconf-vulkan-gpu`.
- `README.md`: row 31 (Dual-GPU gaming — mentions `use`/`toggle`/`run`), the `bin` stage row 84, the bow-out bullet
  102, the whole `## Dual-GPU Vulkan (Proton) fix` section 310-345 (317 `[--quiet]`, 319 the five selector forms,
  320-321 the `toggle` line, 343-345 the `use`/`toggle`/`run` prose) and the revert line 381. The module table row +
  `modules/vulkan-gpu/README.md` replace all of it; the desktop record at 343-345 ("99% on the pinned card") is
  worth keeping in one sentence somewhere, recast as `use display` / `use other` (`run` is unchanged).
- `docs/CONTRIBUTING.md`: tree line 27 (the subcommand list `status/fix/use/toggle/run/alt/remove` → `status/fix/use/
  run/alt/remove`), tree line 87 (the test file moved), and the seam sentence at 147 — only the two sysfs seams and
  `_HYPRCONF_VULKANINFO` remain, the uwsm/environment.d ones are gone.
- `AGENTS.md`: the "Session environment" integration-map row (:37) points at `bin/hyprconf-vulkan-gpu` → point it at
  `modules/vulkan-gpu/README.md`.

## Cross-module facts

- `~/.local/bin` is written by this module, `yubikey` and `hypr` (its two hotkey tools). Same directory, different
  names, `mkdir -p` in each — order-free, no conflict. All of them should use the same `readlink`-guarded `ln -sfn`.
- Nothing else in the tree writes `~/.config/uwsm/env.d/`; nothing binds this tool from `hypr/bindings.lua`, a menu
  row or a hook (checked: `grep -rn hyprconf-vulkan-gpu` finds only README/CONTRIBUTING/AGENTS prose).
- The conftest fakes scan reads comments too, so `omarchy-hw-nvidia` (named in the script header's provenance
  block) gets a stub. Harmless — a stub too many is one file in a tmp dir.
- `vulkan-tools` is deliberately **not** in any module's `packages`: the probe is optional and says so when absent.

## Live verification (desktop, two NVIDIA GPUs — not doable hermetically)

1. **Before shipping:** any script, alias or Steam launch option calling `toggle` or `status --quiet` breaks —
   `use display` / `use other` replaces the first, plain `status` the second. A launch option of the form
   `hyprconf-vulkan-gpu run <gpu> -- %command%` is unchanged and must still start the game (check one).
2. `bash modules/vulkan-gpu/install` on the desktop, then `ls -l ~/.local/bin/hyprconf-vulkan-gpu` — the legacy
   copied file must have become a link into the checkout; run it once more, nothing changes.
3. `hyprconf-vulkan-gpu status` on the desktop (the laptop's single AMD iGPU exits 0 "nothing to do — 1 GPU"), then
   `fix` if AT RISK, re-login, and confirm a Proton game renders on the pinned card. The box has no `vulkan-tools`,
   so device 0 should read "assumed PCI order; vulkaninfo not found".
4. `use other`, re-login, then `use display` and re-login — the switch that replaces `toggle`. Then, without
   re-logging in, `hyprconf-vulkan-gpu run other -- vulkaninfo --summary` (or a game): GPU0 must be the card named,
   and `~/.config/uwsm/env.d/50-hyprconf-vulkan-gpu` must be untouched by that run.
5. `bash modules/vulkan-gpu/install undo` — the link goes, `~/.config/uwsm/env.d/50-hyprconf-vulkan-gpu` stays.
