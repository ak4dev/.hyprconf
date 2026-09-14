# modules/yubikey — notes for the integrator (delete this file)

Files: `install` (+x), `bin/hyprconf-yubikey` (+x, 739 lines — was 1,021), `README.md` (38),
`test_yubikey.py` (1,057, 41 test functions / 59 cases — was 1,217 / 44 / 60). Gates run green here:
`pytest modules/yubikey -q` (59 passed), `shellcheck --severity=warning` and
`shellcheck --include=SC2086` on both bash files, `bash -n`, `ruff check` + `ruff format --check`.

## Findings landed

- **yubikey.0#1** — the module. `install` links `bin/hyprconf-yubikey` into `~/.local/bin` (guarded by
  `readlink`, so a second run writes nothing; `ln -sfn` would give the link a new inode each time);
  `install undo` removes the link and nothing else. No sudo, no TTY, no marker, no package at install
  time — the tool is user-run and changes nothing until it is run.
- **yubikey.0#11 + .0#10** — the second proof layer is gone: `verify_boot_images`, `limine_setting`,
  `config_fingerprint` / `verified_state_path` / `record_verified_state` / `seed_verified_state`, their
  seeding calls in `write_dropin` / `remove_dropin`, the `.zz-hyprconf-fido2.conf.verified` file and its
  removal in `disable_boot_config`, and the five seams `_HYPRCONF_{LIMINE_ENTRY_CONF,LIMINE_USR_D,
  MACHINE_ID,MODULES_DIR,EFI_DIR}`. `rebuild_boot` keeps the exit-code check and the
  `mkinitcpio failed for kernel` / `failed to get kernel cmdline for` grep, and ends with one info line
  pointing at limine-mkinitcpio's own output as the record (the verifier's correction: without
  `limine_setting` nothing can name the ESP, so no `ls -l`). **Degraded verdicts, deliberately:** `disable`
  after a failed enroll, and a retried enroll after a failed rebuild, no longer distinguish "identical
  image, correctly not rewritten" from "never rebuilt" — neither is bricking (the passphrase slot and
  `cryptdevice=` are untouched, and the previous image still boots). ~230 test lines went with it.
- **yubikey.0#12 (+ #13)** — the 108-line `/etc/default/limine` parser is gone (`split_cmdline_line`,
  `limine_find_line`, `limine_read`, `L_LINES`/`L_IDX`/`L_VALUE`/`L_PLAIN`, and `mapper_name`'s
  line-reading half). The mapper now comes from `limine-entry-tool --get-cmdline default` — the cmdline
  limine actually assembles, the call Omarchy makes for the same reason
  (`bin/omarchy-upgrade-to-quattro:537-542`) — with `mapper_name`'s two-source agreement kept, plus a new
  `check_mapper` cross-check against the running system (`lsblk -rno NAME,TYPE -- <dev>` for the picked
  device's `crypt` child, `findmnt -no SOURCE --nofsroot /` for the live root; either may be silent,
  neither may disagree). After writing the cmdline drop-in, `verify_limine_dropin` asks limine again and
  refuses to write the hooks drop-in unless `rd.luks.name=<uuid>=<mapper>` is really on the assembled
  cmdline — so a failure leaves only the inert state.
  **One deliberate addition beyond the finding:** `limine_default_is_plain`, a single
  `grep -qE '^\s*KERNEL_CMDLINE\[default\]\s*='` on `/etc/default/limine`, kept in place of the L_PLAIN
  parser branch so that refusal still comes *before* anything changes (the tool's own contract: "nothing
  is touched before the confirmation"). The after-write proof is the general net behind it. Both are
  tested. `READ_SHAPES`/`REFUSED_LINES` (20 parametrized file-line shapes) collapsed to
  `CMDLINE_SHAPES`/`REFUSED_CMDLINES` (7 + 5) over the `limine-entry-tool` stub's output.
- **yubikey.0#2** — one home per fact: the header is provenance only and is 45 comment lines (was 113),
  ending in a pointer to `hyprconf-yubikey help` and to the module README; `usage()` is the one home for
  behaviour; `README.md` is the user contract. The shipped `/etc` drop-in's comment is down from ~20 lines
  to 12 (what it is, how to remove it, the `zz-` sort seam, the hook map).
- **yubikey.0#3** — `_HYPRCONF_FIDO2_DROPIN` is gone; `DROPIN=zz-hyprconf-fido2.conf` is a plain constant.
  The two directories it is joined to are still seamed, so hermeticity is unchanged.
- **yubikey.0#6** — `--device=X`, `-y`, `enrol` and `parse_flags`'s `-h|--help` are gone. `main`'s
  `help | -h | --help` stays (pinned). One spelling per flag, pinned by a new assertion in the help test.
- **yubikey.0#7** — the interactive numbered device menu is gone: several LUKS2 devices always die with
  the list and `--device`, on a terminal too. Usage line reworded to "required when there is more than
  one". The two menu tests are gone; `test_enroll_needs_device_flag_when_several` covers all three paths.
- **yubikey.0#8** — `wait_for_token`'s three-try retry loop is one `check_token`, the shape Omarchy's own
  `check_fido2_hardware` has (`bin/omarchy-setup-security-fido2:10-17`).
- **yubikey.0#9** — `_HYPRCONF_INITCPIO_INSTALL` no longer ships inside the `/etc` drop-in: the drop-in
  hardcodes `/usr/lib/initcpio/install/sd-btrfs-overlayfs`. Per the verifier, the **runtime** test stays
  (it is what keeps the hook set right at every rebuild, including after a limine-mkinitcpio-hook change);
  the test suite swaps that literal path for its fake dir before sourcing (`_source_dropin`), and a new
  assertion pins that no test seam ships into `/etc`. The seam itself stays for `cmd_status`.
- **yubikey.0#5** — part (b) (one `luksDump` per device, one `sudo -n` probe) was already landed in
  `e611192`; part (a), the `has_tty()` helper, is **moot**: its other two call sites were `pick_device`'s
  menu (#7) and `wait_for_token`'s retry (#8), both deleted, leaving one call site in `confirm`.
- **install-core.3#14 / #15 / #16** (core.json, `stage_bin`) — this module's half: the tool is a symlink,
  not a sed-render; it never carried `@HYPRCONF_DIR@` (grep is 0), so no derivation line was needed; the
  `~/.local/bin is not on PATH` warning is not carried into the module (Omarchy guarantees it,
  `default/bash/env-bootstrap:38-39`, `default/bash/envs:32-33`).

Already landed in the foundation phase and carried forward unchanged: **.0#13, .0#14, .0#15, .0#16**
(commit `e611192`) and **.0#17, .0#20, .0#21, .0#22, .0#24, .0#25** (commit `4b57e3f`).
Not this module's: **install-core.0#7** (`HERE_SED` / the `@HYPRCONF_DIR@` machinery) and
**test-install-a.2#4** (the hardcoded bin list) — both die with `stage_bin` itself.

## What to delete or rewire in the legacy tree

1. `bin/hyprconf-yubikey` — copied, not moved. Delete it. `tests/unit/test_yubikey.py` — moved and
   trimmed; **delete it before adding `modules` to `testpaths`**, or pytest's prepend import mode hits a
   basename collision with `modules/yubikey/test_yubikey.py` (no `__init__.py` anywhere).
2. `install.sh`: `stage_bin` (939-983) no longer installs this tool — `main()` calls
   `bash "$HERE/modules/yubikey/install"` instead. When the last `bin/hyprconf-*` has its own module,
   `stage_bin`, its `main()` call (:1505) and `HERE_SED` (:32-36) all go.
3. `Makefile:20` — `shellcheck --include=SC2086 install.sh bin/hyprconf-yubikey` names a path that will
   not exist. Derive the SC2086 list (`grep -l 'run_root\|sudo ' …` over the bash files) or name
   `modules/yubikey/bin/hyprconf-yubikey`; the file must keep an SC2086 pass (rule 8, root writes).
4. `README.md`: row 30 (feature table) → one line pointing at `modules/yubikey/README.md`; row 84 (the
   `bin` stage row) goes with `stage_bin`; line 98's `/etc` inventory — **drop the
   `.zz-hyprconf-fido2.conf.verified` clause, that file no longer exists**, keep the two drop-ins; line
   245's `libfido2` sentence; the whole `## YubiKey` section (288-300) → the module README; line 379's
   revert line — **drop "and the `.verified` record"**, keep the 4.0.0–4.2.0 inline-residue line.
5. `AGENTS.md`: line 19 (rule 6) — `hyprconf-yubikey`'s extras are now "its two drop-ins,
   `limine-mkinitcpio`, a LUKS slot" (no `.verified` record); line 38 (integration map) →
   `modules/yubikey`; lines 61 and 105 stay true (it still drops `-e`, and `confirm` is still the only
   prompt in the tree).
6. `docs/CONTRIBUTING.md`: line 26 (tree), 88 (test tree), 104 (the SC2086 sentence), 203 (security:
   "installed tools are rendered beside the target and `mv`'d" is no longer true of this one — it is a
   symlink; the `--` root-write pin still lives in this module's `test_restraint_scan`), and **line 143's
   seam list, which must shrink to `LIMINE_DEFAULT, LIMINE_CONF_D, MKINITCPIO_D, INITCPIO_INSTALL,
   VCONSOLE, ASSUME_TTY`** — `LIMINE_ENTRY_CONF`, `LIMINE_USR_D`, `FIDO2_DROPIN`, `MODULES_DIR`,
   `MACHINE_ID` and `EFI_DIR` are gone.
7. `.github/workflows/test.yml:26` — the comment names `tests/unit/test_yubikey.py` (why `shellcheck` is
   a CI dependency); repoint it at `modules/yubikey/test_yubikey.py`.
8. `web/index.html:265` — still accurate, no change needed.
9. `tests/unit/test_omarchy_install.py`: `SET_LINE` (:1419) keys on the basename, so it keeps working
   once `modules` is in `PAYLOAD`; the `USAGE_HEREDOC` comment (:1502) names `bin/hyprconf-yubikey` —
   repoint the path. Whatever pins the `bin/` tool set must lose `hyprconf-yubikey`.

## Cross-module facts

- Nothing else in the tree calls `hyprconf-yubikey`, and it calls nothing of hyprconf's: no shared
  helper, no `packages` line (it installs `libfido2` itself, on demand, through `omarchy-pkg-add`), no
  hotkey binds it. Order-free in the module loop.
- `vulkan-gpu` is the other link-only module; the two `install` scripts are the same four lines apart
  from the name. If a shared idiom is ever wanted, that is the pair — but per the contract a copy is
  correct (`a single directory must run`).
- New externals the shared fake set must cover once `tests/test_scans.py` derives them: **`findmnt`** and
  **`limine-entry-tool`** (this module stubs both itself; `findmnt` is not in the root conftest's
  `EXTRA_FAKES`, and it reaches the developer's real root when unstubbed — worth adding there).

## Live verification still owed (desktop only; no hardware here)

1. `hyprconf-yubikey status` on the desktop: the new one-line `kernel cmdline:` row, and the
   `set outside …` hint on this laptop, which carries the 4.x inline residue.
2. `enroll` on the desktop end to end — in particular `check_mapper` (the `lsblk`/`findmnt` cross-check)
   against a real two-LUKS-device box, and `verify_limine_dropin` seeing the drop-in land on
   `limine-entry-tool --get-cmdline default` after `write_limine_dropin`.
3. That dropping `verify_boot_images` costs nothing in practice: after `enroll`, confirm by hand that
   limine-mkinitcpio's own output names the images it wrote, and reboot.
4. This laptop: `/etc/default/limine` still has `rd.luks.*` inline from v4.x. `enroll` refuses it with the
   4.0.0–4.2.0 message; deleting those two parameters (keeping `cryptdevice=`) is a by-hand step the user
   owns, unchanged by this module.
