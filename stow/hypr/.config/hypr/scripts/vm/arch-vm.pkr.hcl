packer {
  required_plugins {
    qemu = {
      version = ">= 1.0.9"
      source  = "github.com/hashicorp/qemu"
    }
  }
}

# Builds a real, production Arch+hyprconf image for `gpu-passthrough.sh vm
# arch` (GPU passthrough VM launched via a plain `qemu-system-x86_64`, no
# Docker). Adapted from tests/install/arch.pkr.hcl, which builds the
# equivalent image for CI — the
# two differ only in where the repo comes from (a real 'git clone --branch
# stable' here vs. a worktree tar bundle there) and in the credentials/guest
# provisioning passed to install.sh. Kept as a separate template so this
# feature can never affect CI's build.

# ── Variables ──────────────────────────────────────────────────────────────────

variable "iso_url" {
  description = "URL of the Arch Linux ISO to use for the install."
  type        = string
  default     = "https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso"
}

variable "iso_checksum" {
  description = "ISO checksum — fetched and matched against the ISO filename so a corrupted or tampered download fails the build."
  type        = string
  default     = "file:https://geo.mirror.pkgbuild.com/iso/latest/sha256sums.txt"
}

variable "username" {
  description = "Username created inside the guest."
  type        = string
}

variable "password" {
  description = "Password for the guest user (also used for the guest's SSH/console login)."
  type        = string
  sensitive   = true
}

variable "hostname" {
  description = "Guest hostname."
  type        = string
  default     = "hyprconf-arch-vm"
}

variable "timezone" {
  description = "Guest timezone (e.g. 'UTC', 'America/New_York')."
  type        = string
  default     = "UTC"
}

variable "ssh_pubkey" {
  description = "Public key injected into the guest for passwordless SSH (content of ~/.ssh/hyprconf_arch_vm_key.pub)."
  type        = string
  default     = ""
}

variable "disk_size" {
  description = "Size of the qcow2 disk image (e.g. '64G') — this becomes the guest's real, permanent disk."
  type        = string
  default     = "64G"
}

variable "build_memory" {
  description = "RAM in MB allocated to the *build-time* VM only — unrelated to `vm arch launch`'s later launch-time RAM."
  type        = number
  default     = 4096
}

variable "output_directory" {
  description = "Where Packer writes the built qcow2 before build-arch-vm-image.sh moves it into place."
  type        = string
  default     = "output-arch-vm"
}

variable "install_script_path" {
  description = <<-EOT
    Absolute path to install/install.sh. This template lives at a symlinked,
    stowed location (stow/hypr/.config/hypr/scripts/vm/), so a relative path
    back to the repo's install/ directory isn't reliable — build-arch-vm-
    image.sh always resolves and passes this explicitly instead.
  EOT
  type        = string
}

# ── Source ─────────────────────────────────────────────────────────────────────

source "qemu" "arch_vm" {
  iso_url      = var.iso_url
  iso_checksum = var.iso_checksum

  vm_name          = "arch-hyprconf.qcow2"
  output_directory = var.output_directory

  accelerator  = "kvm"
  machine_type = "q35"
  cpus         = 2
  memory       = var.build_memory
  disk_size    = var.disk_size
  net_device   = "virtio-net"

  # UEFI firmware — systemd-boot requires UEFI (OVMF).
  efi_firmware_code = "/usr/share/edk2/x64/OVMF_CODE.4m.fd"
  efi_firmware_vars = "/usr/share/edk2/x64/OVMF_VARS.4m.fd"

  format     = "qcow2"
  disk_image = false

  # virtio-gpu-gl gives hardware-accelerated rendering during the build's own
  # setup.sh run — irrelevant at real launch time, where `vm arch launch` replaces
  # this with the passed-through physical GPU.
  display  = "virtio-gpu-gl"
  headless = true

  # Boot: press Enter to start the Arch live environment, set root password,
  # explicitly enable password auth + root login, then restart sshd.
  boot_wait = "5s"
  boot_command = [
    "<enter>",
    "<wait60>",
    "echo root:packer | chpasswd<enter>",
    "<wait2>",
    "echo PasswordAuthentication yes >> /etc/ssh/sshd_config<enter>",
    "<wait2>",
    "echo PermitRootLogin yes >> /etc/ssh/sshd_config<enter>",
    "<wait2>",
    "systemctl restart sshd<enter>",
    "<wait5>",
  ]

  # SSH (live-environment root access during provisioning)
  ssh_username           = "root"
  ssh_password           = "packer"
  ssh_timeout            = "20m"
  ssh_handshake_attempts = 30

  shutdown_command = "shutdown -h now"
}

# ── Build ──────────────────────────────────────────────────────────────────────

build {
  sources = ["source.qemu.arch_vm"]

  provisioner "file" {
    source      = var.install_script_path
    destination = "/tmp/install.sh"
  }

  # No repo-tar upload: install.sh takes its normal path and does a real
  # 'git clone --branch stable' from GitHub — this is a genuine install, not
  # a test fixture (see install/install.sh:22-140).
  provisioner "shell" {
    environment_vars = [
      "HYPRCONF_CI=1",
      "HYPRCONF_CI_DISK=/dev/vda",
      "HYPRCONF_CI_USERNAME=${var.username}",
      "HYPRCONF_CI_PASSWORD=${var.password}",
      "HYPRCONF_CI_HOSTNAME=${var.hostname}",
      "HYPRCONF_CI_TIMEZONE=${var.timezone}",
      "HYPRCONF_CI_PART_MODE=full",
      "HYPRCONF_CI_COPY_NETCONF=0",
      "HYPRCONF_CI_SSH_PUBKEY=${var.ssh_pubkey}",
      "HYPRCONF_CI_VM_GUEST=1",
    ]
    inline = [
      "chmod +x /tmp/install.sh",
      "bash /tmp/install.sh",
    ]
  }

  post-processor "manifest" {
    output     = "${var.output_directory}/manifest.json"
    strip_path = true
  }
}
