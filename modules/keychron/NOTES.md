# modules/keychron — integrator notes (delete this file)

## Findings landed

- **install-core.2#10** (stage_keychron is already a module) — done: `modules/keychron/{install,
  70-keychron.rules,README.md,test_keychron.py}`, standalone, seam default inlined
  (`: "${_HYPRCONF_UDEV_RULES:=/etc/udev/rules.d}"`, never `readonly`), tests on the root
  `conftest.py` `box` fixture only, no `_setup`/`_run` harness left.
- **install-core.2#5, half (1) — the required half** — both root calls now carry `--`:
  `sudo install -Dm644 -- "$src" "$dst"` and `sudo rm -f -- "$dst"`. The end-of-options pin is
  carried inside the module by `test_every_root_call_carries_the_end_of_options_marker`
  (scans the module's own `install`; `sudo udevadm …` is exempt — it takes no path). If you
  land a tree-wide `--` scan in `tests/test_scans.py`, that module test is redundant and can go.
  Half (2) — an `install_root_file` helper mirroring Omarchy's — deliberately **not** taken:
  the finding's own verifier says a shared install.sh-level helper works against the module
  split, and Omarchy's version is a private in-script function (bin/omarchy-hibernation-setup:33-49
  == bin/omarchy-toggle-hybrid-gpu:6-22), not a callable command, so rule 1 does not bite.
- **install-system.0#1** (the reasoning written out three or four times) — one home, and per the
  task's direction that home is `modules/keychron/README.md`. The rule file keeps a 9-line header:
  what the tag does, then a pointer to the README beside it; the `install` header keeps only the
  rule-1 citation (`omarchy commands --json` has no udev route — re-verified on 4.0.3-1, `grep -ci
  udev` over its JSON is 0) plus the qmk-hid.sh shape and the write-only-when-bytes-differ note.
  The test docstring is one line. **Deviation from the finding's `do`**, which kept the rule
  file's header as the home: in the module layout README.md ships in the same directory, so a
  taker reads both — and the user-facing half (symptom, cause, the security price of the
  vendor-only match, the Bluetooth caveat, the undo) belongs in the README, not in a udev file.
  If you disagree, the swap is mechanical: the README's What section is the old header verbatim
  plus the symptom/cause paragraph.

## Not landed here

Nothing else in `keychron.json`; it holds only install-system.0#1. `core.json`'s other
keychron-touching findings are cross-cutting and belong to the integrator or to other steps:
install-core.0#10 / 2#8 (the no-terminal sudo gate copy-pasted three times) — after the split
each module carries its own gate by contract, so there is nothing left to deduplicate;
install-core.0#4/0#5/5#9 (install.sh coupling and comment bulk) — the core rewrite;
test-install-a.1#19 (the 25-line rule test that re-asserts what equality implies) — folded in:
the payload test here is 11 lines and asserts the three properties only, once.

## Delete from the legacy tree when you wire this in

- `install.sh`: the `stage_keychron` comment block + function, **lines 587-628**; the
  `_HYPRCONF_UDEV_RULES` seam declaration, **lines 58-61**; `stage_keychron` in the `main()`
  sudo-stage line **1492** and the sentence about it in the comment at **1490-1491** ("stage_keychron
  runs last of the four so the first `sudo install` of a run is still the Firefox policy's" — that
  ordering claim dies with the fixed stage order; module order is alphabetical and order-free).
  Also the Keychron clauses in the `--no-packages` help text (**106**) and the header (**22**, **495**).
- `infra/udev/70-keychron.rules` — and `infra/udev/` itself, now empty (`infra/firefox/` stays
  until the firefox module lands).
- `tests/unit/test_omarchy_install.py`: `KEYCHRON_RULE` (**1668**),
  `test_keychron_rule_is_installed_via_sudo_when_interactive` (**1671-1699**),
  `test_keychron_rule_is_vendor_only_and_sorts_before_seat_late` (**1702-1712**), the
  `env["udev_rules"]` harness key (**276**) and its env entry (**294**), the udevadm comment at
  **206**, the CI-container note at **293**, the keychron assertion inside
  `test_every_sudo_stage_bows_out_without_a_terminal` (**1622**) and the three-line rule copy inside
  `test_a_failed_firefox_install_leaves_no_policy_behind` (**1650-1652**, only there to prove the
  Firefox failure path does not reach keychron — drop it, the module's own tests cover the gate).
- `README.md`: the whole `## Keychron / Lemokey HID access` section (**347-380**); the `keychron`
  stage-table row (**73**); the Keychron clauses in **32**, **39**, **61**, **63**, **98**, **117**; the
  `sudo rm /etc/udev/rules.d/70-keychron.rules …` undo line (**401**). Replace with one row in the
  module table pointing at `modules/keychron/README.md`.
- `docs/CONTRIBUTING.md`: tree row **48**; the `_HYPRCONF_UDEV_RULES` entry in the seam list around
  **155-160** now points at `modules/keychron/install`, not `install.sh`.
- `AGENTS.md`: rule 6's "the Keychron udev rule" in the root-write inventory and its
  "`packages`/`firefox`/`editor`/`keychron` stages" list (**19**) become the module list; the
  `Keyboard/mouse HID` integration-map row (**39**) becomes `modules/keychron` → its README.
- `hooks/post-update.d/10-hyprconf`: the Keychron mention at **34** (the hook shrinks to 4 lines
  anyway).

## Cross-module facts

- This module is the only one besides `firefox` that writes outside `$HOME`; both gate on
  `HYPRCONF_NO_SUDO` + a TTY and both exit 0 when they bow out, so the core's `failed=()` never
  sees them. Whichever runs first pays for the sudo timestamp; nothing depends on the order.
- No marker under `$HYPRCONF_STATE`: the rule is not a user choice, it is a file kept in sync, so
  it is `cmp`-gated and repaired on every run instead. `box.files() == set()` is asserted — the
  module writes nothing into `$HOME` at all.
- The `box` fixture already stubs `sudo` and `udevadm`; nothing new was added to `conftest.py`.

## Live verification (not done here — no sudo on this box)

1. `bash ~/.hyprconf/modules/keychron/install` from a terminal on a machine that has the old
   `/etc/udev/rules.d/70-keychron.rules`: the header shrank, so **the bytes differ** and the first
   post-split run rewrites the file once, then reloads and triggers. Expected and harmless — the
   two rule lines are unchanged — but it means one sudo prompt on the first run after the split.
2. `udevadm info /dev/hidrawN` for a plugged-in Keychron shows `TAGS=…:uaccess:…` and `getfacl`
   on the node shows `user:<you>:rw-`; launcher.keychron.com lists the board after a tab reload.
3. `bash ~/.hyprconf/modules/keychron/install undo` removes the file and reloads; a re-plugged
   board is invisible to the launcher again.
