packer {
  required_plugins {
    qemu = {
      version = ">= 1.0.9"
      source  = "github.com/hashicorp/qemu"
    }
  }
}

# ── Variables ──────────────────────────────────────────────────────────────────

variable "iso_url" {
  description = "URL of the Arch Linux ISO to use for the install."
  type        = string
  default     = "https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso"
}

variable "ssh_password" {
  description = "Password for the hyprtest user created inside the image."
  type        = string
  default     = "hyprtest"
  sensitive   = true
}

variable "ssh_pubkey" {
  description = "Public key to inject into the test VM for passwordless SSH (content of ~/.ssh/hyprconf_vm_key.pub)."
  type        = string
  default     = ""
}

variable "disk_size" {
  description = "Size of the qcow2 disk image (e.g. '20G')."
  type        = string
  default     = "20G"
}

variable "memory" {
  description = "RAM in MB allocated to the build VM."
  type        = number
  default     = 4096
}

# ── Source ─────────────────────────────────────────────────────────────────────

source "qemu" "arch_hyprconf" {
  # ISO
  iso_url      = var.iso_url
  iso_checksum = "none"

  # VM identity
  vm_name          = "arch-hyprconf.qcow2"
  output_directory = "output-arch"

  # Hardware
  accelerator  = "kvm"
  machine_type = "q35"
  cpus         = 2
  memory       = var.memory
  disk_size    = var.disk_size
  net_device   = "virtio-net"

  # UEFI firmware — systemd-boot requires UEFI (OVMF).
  efi_firmware_code = "/usr/share/edk2/x64/OVMF_CODE.4m.fd"
  efi_firmware_vars = "/usr/share/edk2/x64/OVMF_VARS.4m.fd"

  # Storage
  format     = "qcow2"
  disk_image = false

  # Display — virtio-gpu-gl gives hardware-accelerated rendering for Hyprland.
  display  = "virtio-gpu-gl"
  headless = true

  # Boot: press Enter to start the Arch live environment, then set root
  # password and start sshd so Packer can SSH in.
  boot_wait = "5s"
  boot_command = [
    "<enter>",
    "<wait30>",
    "echo root:packer | chpasswd && systemctl start sshd<enter>",
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
  sources = ["source.qemu.arch_hyprconf"]

  # Upload the real hyprconf installer (tested end-to-end in CI mode)
  provisioner "file" {
    source      = "${path.root}/../../install/install.sh"
    destination = "/tmp/install.sh"
  }

  # Upload the current repo as a tar so install.sh doesn't need to clone from
  # GitHub inside the VM. build_image.sh creates this via 'git archive'.
  # This eliminates the QEMU network dependency and ensures the exact export-
  # ignored payload under test is installed — not whatever happens to be on
  # origin/stable at build time.
  provisioner "file" {
    source      = "/tmp/hyprconf-packer-repo.tar.gz"
    destination = "/tmp/hyprconf-repo.tar.gz"
  }

  # Run the real installer with HYPRCONF_CI=1 to bypass interactive prompts.
  # HYPRCONF_CI_DISK must match the QEMU disk device (/dev/vda for virtio).
  # HYPRCONF_CI_SSH_PUBKEY is injected into authorized_keys before unmount.
  # HYPRCONF_CI_REPO_TGZ tells install.sh to extract /tmp/hyprconf-repo.tar.gz
  # instead of cloning from GitHub.
  provisioner "shell" {
    environment_vars = [
      "HYPRCONF_CI=1",
      "HYPRCONF_CI_DISK=/dev/vda",
      "HYPRCONF_CI_USERNAME=hyprtest",
      "HYPRCONF_CI_PASSWORD=${var.ssh_password}",
      "HYPRCONF_CI_HOSTNAME=hyprconf-test",
      "HYPRCONF_CI_TIMEZONE=UTC",
      "HYPRCONF_CI_PART_MODE=full",
      "HYPRCONF_CI_COPY_NETCONF=0",
      "HYPRCONF_CI_SSH_PUBKEY=${var.ssh_pubkey}",
      "HYPRCONF_CI_REPO_TGZ=/tmp/hyprconf-repo.tar.gz",
    ]
    inline = [
      "chmod +x /tmp/install.sh",
      "bash /tmp/install.sh",
    ]
  }

  post-processor "manifest" {
    output     = "output-arch/manifest.json"
    strip_path = true
  }
}
