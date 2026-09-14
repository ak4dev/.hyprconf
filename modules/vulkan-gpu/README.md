# vulkan-gpu

## What

`bin/hyprconf-vulkan-gpu`, symlinked into `~/.local/bin` — on the session PATH (`default/bash/env-bootstrap:37-40`, and again for rc shells in `default/bash/envs:31-33`). That link is the whole install: the tool is run by hand, on a dual-GPU box, and decides nothing by itself. Omarchy has no command for any of this — the survey that says so, with its citations, is the script's own header.

**Why a dual-GPU box needs it.** Xwayland exposes no RandR providers, so Wine binds every monitor to Vulkan physical device 0 — the first GPU in PCI order, not the one the displays are on. A Proton game whose
adapter has no output dies at `CreateSwapChainForHwnd` (`E_INVALIDARG`, "No display detected for current GPU") while the launcher works. Reordering (`VK_LOADER_DEVICE_SELECT`) is not enough: the other GPU must
leave Vulkan enumeration, which is `VK_LOADER_DEVICE_ID_FILTER` (vulkan-icd-loader ≥ 1.4.3xx; Mesa 25 dropped `MESA_VK_DEVICE_SELECT`). NVIDIA's driver also presents to Xwayland only from its own GPU 0 unless
PRIME offload is on, so `__NV_PRIME_RENDER_OFFLOAD=1` and `__VK_LAYER_NV_optimus=NVIDIA_only` are written together — and only when another NVIDIA GPU sits ahead of the target in PCI order, where there is
something to offload from. The filter hides a GPU from *Vulkan* only: the compositor (KMS/EGL) still drives the monitors on it, and Vulkan compute no longer sees it.

**Where it writes.** `~/.config/uwsm/env.d/50-hyprconf-vulkan-gpu`, `export VAR=value` lines uwsm sources at login (`/usr/lib/uwsm/prepare-env.sh:80-82`) in the directory Omarchy names for session overrides (`/usr/share/uwsm/env.d/10-omarchy:6-7`), so every launcher and game inherits them.

- `status` (the default) — the GPUs, the display GPU, Vulkan device 0 (from `vulkaninfo --summary` when `vulkan-tools` is installed, else assumed PCI order and said so) and what already configures it. Exit **0** nothing to do, **3** at risk and unconfigured, **1** error.
- `fix` — that file for the display GPU. `use display|other|<pci-address>` — for a GPU you name instead, which pays for every frame copied back across PCIe to the card that scans out, so measure first. `run <gpu> [--] <command>` — the same variables for one command only, writing nothing: the one switch that needs no re-login (anything started through uwsm inherits the compositor's environment, which `systemctl --user set-environment` does not reach), and as a Steam launch option `… run <gpu> -- %command%` picks a GPU for one game.
- `alt` — `PROTON_ENABLE_WAYLAND=1` alone, for a Wayland-capable Proton: the answer when two cards share a `vendor:device` id, which the loader's filter cannot separate. `remove` — delete the file. Every write takes effect at the next login.

## Requires

A uwsm Omarchy session and coreutils; `vulkaninfo` is optional and never installed here. No package, no `sudo`, no TTY, no marker — the link target is all a re-run looks at.

## Install alone

```sh
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/vulkan-gpu && bash ~/.hyprconf/modules/vulkan-gpu/install
```

Or copy `bin/hyprconf-vulkan-gpu` onto your own PATH: it needs no checkout, no repo and no Omarchy command.

## Settings

`hyprconf-vulkan-gpu fix` once per box (`use <gpu>` pins another), then re-login; re-run it after changing cards. Anything setting the same variables elsewhere — `~/.config/environment.d/*.conf`, `~/.config/uwsm/env` — is named on every write, since whichever the session sources last wins.

## Undo

`bash modules/vulkan-gpu/install undo` removes the `~/.local/bin` link and nothing else; the pin is yours, and `hyprconf-vulkan-gpu remove` deletes it.

## Verified against Omarchy 4.0.3-1
