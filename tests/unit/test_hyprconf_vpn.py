"""
Tests for hyprconf-vpn — the NetworkManager-backed VPN control helper
(stowed to ~/.local/bin) and its wiring into the main `hyprconf` CLI.

Two layers:
  • Static analysis — script is valid bash, stowed (not export-ignored), and
    wired into hyprconf's dispatcher + usage.
  • Behavioural — the script is executed against a fake `nmcli`/`protonvpn`/`nft`
    on PATH, so status parsing, profile resolution, import sniffing, and the
    kill-switch (both Proton-delegated and generic-nftables) are exercised
    without a live VPN, root, or real netfilter changes.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf-vpn"
HYPRCONF_BIN = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf"
PACKAGES = REPO_ROOT / "packages"
WAYBAR_JSONC = REPO_ROOT / "stow" / "waybar" / ".config" / "waybar" / "waybar.jsonc"

# Resolve the *real* nft now, before any fake shadows it on PATH (used only by
# the optional syntax-validation test).
_REAL_NFT = shutil.which("nft")


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _bin_text() -> str:
    return HYPRCONF_BIN.read_text(encoding="utf-8")


# ===========================================================================
# Static analysis: reachability + validity
# ===========================================================================

def test_script_exists_in_stowed_bin() -> None:
    assert SCRIPT.exists(), (
        "hyprconf-vpn must live under stow/hypr/.local/bin so it is stowed onto "
        "new systems and on PATH — scripts/ is export-ignored and absent from "
        "the installer's sparse-checkout paths."
    )


def test_script_is_executable() -> None:
    assert SCRIPT.stat().st_mode & stat.S_IXUSR, "hyprconf-vpn must be executable"


def test_script_shebang() -> None:
    assert _text().startswith("#!/usr/bin/env bash\n")


def test_script_bash_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_json_output_has_no_color_escapes() -> None:
    # --json runs non-TTY in waybar; colors must be gated on `[[ -t 1 ]]`.
    assert "[[ -t 1 ]]" in _text()


# ===========================================================================
# Static analysis: core-package + CLI wiring
# ===========================================================================

def test_core_packages_include_vpn_plugin() -> None:
    pkgs = PACKAGES.read_text(encoding="utf-8")
    active = [
        ln.strip() for ln in pkgs.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    assert "networkmanager-openvpn" in active, (
        "networkmanager-openvpn must be a core package — the user's existing "
        "ProtonVPN .ovpn profile depends on it."
    )
    assert "wireguard-tools" in active


def test_cli_dispatches_vpn() -> None:
    txt = _bin_text()
    assert "vpn)              cmd_vpn" in txt or "vpn)" in txt
    assert "cmd_vpn()" in txt
    assert 'VPN_SCRIPT="$HOME/.local/bin/hyprconf-vpn"' in txt


def test_cli_usage_lists_vpn() -> None:
    txt = _bin_text()
    assert "hyprconf vpn status" in txt
    assert "hyprconf vpn killswitch" in txt


def test_cli_vpn_handles_missing_helper() -> None:
    # cmd_vpn must guard on the helper existing (mirrors cmd_yubikey).
    assert 'if [[ ! -x "$VPN_SCRIPT" ]]' in _bin_text()


# ===========================================================================
# Static analysis: the `vpn` addon (ProtonVPN CLI)
# ===========================================================================

def test_vpn_addon_registered() -> None:
    # Resilient to other addons being added/reordered — just require `vpn` in
    # the _ADDON_NAMES array declaration.
    txt = _bin_text()
    m = re.search(r"_ADDON_NAMES=\(([^)]*)\)", txt)
    assert m, "_ADDON_NAMES array not found"
    assert "vpn" in m.group(1).split()


def test_vpn_addon_installs_proton_cli() -> None:
    txt = _bin_text()
    assert 'vpn)  printf "proton-vpn-cli"' in txt


def test_vpn_addon_is_installed_check() -> None:
    txt = _bin_text()
    assert "pacman -Qi proton-vpn-cli" in txt


def test_vpn_addon_post_install_is_non_interactive() -> None:
    # Must only *print* next steps — never auto-run `protonvpn signin` (which is
    # interactive and would block a batch addon install).
    txt = _bin_text()
    assert "protonvpn signin" in txt
    # Every line mentioning signin must be printed guidance, not an exec line.
    for line in txt.splitlines():
        if "protonvpn signin" in line:
            assert "printf" in line, "signin must be printed guidance, not executed"


# ===========================================================================
# Static analysis: waybar module + doctor integration
# ===========================================================================

def test_doctor_runs_vpn_check() -> None:
    txt = _bin_text()
    assert "_doctor_check_vpn()" in txt
    assert "_doctor_check_vpn" in txt.split("cmd_doctor()", 1)[1]


def test_waybar_module_wired() -> None:
    raw = WAYBAR_JSONC.read_text(encoding="utf-8")
    cfg = json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.M))
    assert "custom/vpn" in cfg["modules-right"]
    mod = cfg["custom/vpn"]
    assert "vpn status --json" in mod["exec"]
    assert mod["return-type"] == "json"
    assert "vpn toggle" in mod["on-click"]


# ===========================================================================
# Behavioural: fake nmcli / protonvpn / nft harness
# ===========================================================================

# Real system binaries the script genuinely needs. Everything else (nmcli,
# protonvpn, nft, wg, sudo, pacman) is faked — and because PATH is set to ONLY
# the fake dir, the host's real protonvpn/nmcli/nft can never leak in and block
# (real `protonvpn config list` hangs on its daemon).
_SYS_BINS = (
    "bash", "awk", "grep", "sort", "install", "tee", "rm", "dirname", "cat",
    "sed", "env", "mkdir", "head", "tail", "timeout",
)


def _make_fake_bin(dir_: Path, name: str, body: str) -> None:
    p = dir_ / name
    p.write_text("#!/usr/bin/env bash\n" + body)
    p.chmod(0o755)


def _link_system_bins(fake: Path) -> None:
    for name in _SYS_BINS:
        real = shutil.which(name)
        target = fake / name
        if real and not target.exists():
            target.symlink_to(real)


def _run_vpn(
    tmp: Path,
    args: list[str],
    *,
    active: str = "",          # lines for `-f NAME,TYPE connection show --active`
    active_dev: str = "",      # lines for `-f DEVICE,TYPE connection show --active`
    profiles: str = "",        # lines for `-f NAME,TYPE connection show`
    vpn_data: str = "",        # lines for `-f vpn.data connection show <name>`
    proton: bool = False,
    proton_ks: str = "off",    # value `protonvpn config list` reports
    with_nft: bool = False,
    nft_table_present: bool = False,
    up_rc: int = 0,
    import_rc: int = 0,
    have_pacman: bool = True,
) -> tuple[int, str, str, list[str]]:
    """Execute hyprconf-vpn with a controlled fake environment.

    Returns (rc, stdout, stderr, recorded_calls).
    """
    fake = tmp / "fakebin"
    fake.mkdir(exist_ok=True)
    _link_system_bins(fake)
    calls = tmp / "calls.log"

    # Fixture files the fake nmcli reads from.
    (tmp / "active.txt").write_text(active)
    (tmp / "active_dev.txt").write_text(active_dev)
    (tmp / "profiles.txt").write_text(profiles)
    (tmp / "vpndata.txt").write_text(vpn_data)

    _make_fake_bin(fake, "nmcli", f"""
echo "nmcli $*" >> "{calls}"
args="$*"
case "$args" in
  *"-f NAME,TYPE connection show --active"*)   cat "{tmp}/active.txt" ;;
  *"-f DEVICE,TYPE connection show --active"*) cat "{tmp}/active_dev.txt" ;;
  *"-f vpn.data connection show"*)             cat "{tmp}/vpndata.txt" ;;
  *"-f NAME,TYPE connection show"*)            cat "{tmp}/profiles.txt" ;;
  *"connection up"*)     exit {up_rc} ;;
  *"connection down"*)   exit 0 ;;
  *"connection import"*) exit {import_rc} ;;
  *) exit 0 ;;
esac
""")

    if proton:
        _make_fake_bin(fake, "protonvpn", f"""
echo "protonvpn $*" >> "{calls}"
if [[ "$1 $2" == "config list" ]]; then
  echo "kill-switch: {proton_ks}"
  exit 0
fi
if [[ "$1 $2 $3" == "config set kill-switch" ]]; then
  exit 0
fi
exit 0
""")

    if with_nft:
        present = "0" if nft_table_present else "1"
        _make_fake_bin(fake, "nft", f"""
echo "nft $*" >> "{calls}"
if [[ "$1 $2" == "list table" ]]; then exit {present}; fi
exit 0
""")
        # sudo → run the rest directly (so real tee/install write to the tmp
        # KS file); fake nft/wg are picked up from PATH.
        _make_fake_bin(fake, "sudo", 'exec "$@"\n')
        _make_fake_bin(fake, "wg", "exit 0\n")

    if have_pacman:
        # Pretend the OpenVPN plugin is installed so import doesn't warn-skip.
        _make_fake_bin(fake, "pacman", 'exit 0\n')

    env = os.environ.copy()
    # Hermetic PATH — only the fake dir. The host's real protonvpn/nmcli/nft
    # must not be reachable, or the "no proton" branches would invoke the real
    # `protonvpn config list` and hang on its daemon.
    env["PATH"] = str(fake)
    env["HYPRCONF_KS_FILE"] = str(tmp / "killswitch.nft")

    result = subprocess.run(
        [str(fake / "bash"), str(SCRIPT), *args],
        env=env, capture_output=True, text=True,
    )
    recorded = []
    if calls.exists():
        recorded = [ln.strip() for ln in calls.read_text().splitlines() if ln.strip()]
    return result.returncode, result.stdout, result.stderr, recorded


# Fixture matching the real machine: an active OpenVPN profile + its tun device.
_ACTIVE = "myvpn:vpn\n"
_ACTIVE_DEV = "enp6s0:vpn\ntun0:tun\n"
_PROFILES = "myvpn:vpn\nWired connection 1:802-3-ethernet\n"


# --- status ---------------------------------------------------------------

def test_status_reports_active_vpn(tmp_path: Path) -> None:
    rc, out, _, _ = _run_vpn(
        tmp_path, ["status"], active=_ACTIVE, active_dev=_ACTIVE_DEV
    )
    assert rc == 0
    assert "myvpn" in out
    assert "tun0" in out


def test_status_reports_disconnected(tmp_path: Path) -> None:
    rc, out, _, _ = _run_vpn(tmp_path, ["status"], active="", active_dev="")
    assert rc == 0
    assert "Disconnected" in out


def test_status_json_is_valid_and_classed(tmp_path: Path) -> None:
    rc, out, _, _ = _run_vpn(
        tmp_path, ["status", "--json"], active=_ACTIVE, active_dev=_ACTIVE_DEV
    )
    assert rc == 0
    data = json.loads(out.strip())
    assert set(data) == {"text", "tooltip", "class"}
    # text is a bare on/off glyph (no profile name); the detail is in the tooltip.
    assert "myvpn" not in data["text"]
    assert data["text"].strip() != ""
    assert "myvpn" in data["tooltip"]
    assert data["class"].startswith("connected")


def test_status_json_disconnected_class(tmp_path: Path) -> None:
    rc, out, _, _ = _run_vpn(tmp_path, ["status", "--json"], active="")
    data = json.loads(out.strip())
    assert data["class"] == "disconnected"


# --- list -----------------------------------------------------------------

def test_list_shows_only_vpn_profiles(tmp_path: Path) -> None:
    rc, out, _, _ = _run_vpn(
        tmp_path, ["list"], profiles=_PROFILES, active=_ACTIVE
    )
    assert rc == 0
    assert "myvpn" in out
    assert "Wired connection 1" not in out  # 802-3-ethernet is not a VPN profile


def test_list_empty(tmp_path: Path) -> None:
    rc, out, _, _ = _run_vpn(tmp_path, ["list"], profiles="")
    assert rc == 0
    assert "No VPN profiles" in out


# --- connect / disconnect -------------------------------------------------

def test_connect_uses_sole_profile_by_default(tmp_path: Path) -> None:
    rc, _, _, calls = _run_vpn(
        tmp_path, ["connect"], profiles="myvpn:vpn\n"
    )
    assert rc == 0
    assert any("connection up myvpn" in c for c in calls)


def test_connect_requires_name_when_ambiguous(tmp_path: Path) -> None:
    rc, _, err, calls = _run_vpn(
        tmp_path, ["connect"],
        profiles="a:vpn\nb:wireguard\n",
    )
    assert rc == 1
    assert not any("connection up" in c for c in calls)
    assert "specify one" in err.lower()


def test_connect_forwards_explicit_name(tmp_path: Path) -> None:
    rc, _, _, calls = _run_vpn(tmp_path, ["connect", "myvpn"], profiles="")
    assert rc == 0
    assert any("connection up myvpn" in c for c in calls)


def test_connect_propagates_failure(tmp_path: Path) -> None:
    rc, _, _, _ = _run_vpn(
        tmp_path, ["connect", "myvpn"], profiles="", up_rc=1
    )
    assert rc == 1


def test_disconnect_defaults_to_active(tmp_path: Path) -> None:
    rc, _, _, calls = _run_vpn(
        tmp_path, ["disconnect"], active=_ACTIVE
    )
    assert rc == 0
    assert any("connection down myvpn" in c for c in calls)


def test_toggle_disconnects_when_active(tmp_path: Path) -> None:
    rc, _, _, calls = _run_vpn(tmp_path, ["toggle"], active=_ACTIVE)
    assert rc == 0
    assert any("connection down" in c for c in calls)
    assert not any("connection up" in c for c in calls)


def test_toggle_connects_when_inactive(tmp_path: Path) -> None:
    rc, _, _, calls = _run_vpn(
        tmp_path, ["toggle"], active="",
        profiles="myvpn:vpn\n",
    )
    assert rc == 0
    assert any("connection up myvpn" in c for c in calls)
    assert not any("connection down" in c for c in calls)


# --- import ---------------------------------------------------------------

def test_import_detects_openvpn(tmp_path: Path) -> None:
    f = tmp_path / "server.ovpn"
    f.write_text("client\nremote 1.2.3.4 1194\ndev tun\n")
    rc, _, _, calls = _run_vpn(tmp_path, ["import", str(f)])
    assert rc == 0
    assert any("connection import type openvpn" in c for c in calls)


def test_import_detects_wireguard(tmp_path: Path) -> None:
    f = tmp_path / "wg.conf"
    f.write_text("[Interface]\nPrivateKey = x\n[Peer]\nEndpoint = 1.2.3.4:51820\n")
    rc, _, _, calls = _run_vpn(tmp_path, ["import", str(f)])
    assert rc == 0
    assert any("connection import type wireguard" in c for c in calls)


def test_import_rejects_missing_file(tmp_path: Path) -> None:
    rc, _, err, _ = _run_vpn(tmp_path, ["import", str(tmp_path / "nope.ovpn")])
    assert rc == 1
    assert "not found" in err.lower()


def test_import_rejects_unrecognized(tmp_path: Path) -> None:
    f = tmp_path / "junk.conf"
    f.write_text("just some text\n")
    rc, _, err, _ = _run_vpn(tmp_path, ["import", str(f)])
    assert rc == 1
    assert "unrecognized" in err.lower()


# --- killswitch: Proton delegation ----------------------------------------

def test_killswitch_on_delegates_to_proton(tmp_path: Path) -> None:
    rc, _, _, calls = _run_vpn(
        tmp_path, ["killswitch", "on"], proton=True
    )
    assert rc == 0
    assert any("config set kill-switch standard" in c for c in calls)


def test_killswitch_off_delegates_to_proton(tmp_path: Path) -> None:
    rc, _, _, calls = _run_vpn(
        tmp_path, ["killswitch", "off"], proton=True
    )
    assert rc == 0
    assert any("config set kill-switch off" in c for c in calls)


def test_killswitch_status_reads_proton(tmp_path: Path) -> None:
    rc, out, _, _ = _run_vpn(
        tmp_path, ["killswitch", "status"], proton=True, proton_ks="standard"
    )
    assert rc == 0
    assert "ON" in out


# --- killswitch: generic nftables -----------------------------------------

def test_killswitch_on_generic_writes_and_applies(tmp_path: Path) -> None:
    rc, _, _, calls = _run_vpn(
        tmp_path, ["killswitch", "on"],
        active=_ACTIVE, active_dev=_ACTIVE_DEV,
        with_nft=True, proton=False,
    )
    assert rc == 0
    # Ruleset written to the (tmp) KS file and applied via nft -f.
    ks = tmp_path / "killswitch.nft"
    assert ks.exists()
    body = ks.read_text()
    assert "table inet hyprconf_killswitch" in body
    assert "policy drop" in body
    assert "tun0" in body                      # detected tunnel device
    assert "ct state established,related accept" in body
    assert any("nft -f" in c for c in calls)


def test_killswitch_off_generic_deletes_table(tmp_path: Path) -> None:
    rc, _, _, calls = _run_vpn(
        tmp_path, ["killswitch", "off"], with_nft=True, proton=False
    )
    assert rc == 0
    assert any("delete table inet hyprconf_killswitch" in c for c in calls)


def test_killswitch_status_generic_reports_table(tmp_path: Path) -> None:
    rc, out, _, _ = _run_vpn(
        tmp_path, ["killswitch", "status"],
        with_nft=True, nft_table_present=True, proton=False,
    )
    assert rc == 0
    assert "ON" in out


@pytest.mark.skipif(_REAL_NFT is None, reason="nft not installed")
def test_generic_killswitch_ruleset_is_valid_nft_syntax(tmp_path: Path) -> None:
    # Generate the real ruleset, then syntax-check it with the real nft.
    _run_vpn(
        tmp_path, ["killswitch", "on"],
        active=_ACTIVE, active_dev=_ACTIVE_DEV, with_nft=True, proton=False,
    )
    ks = tmp_path / "killswitch.nft"
    assert ks.exists()
    check = subprocess.run(
        [_REAL_NFT, "-c", "-f", str(ks)], capture_output=True, text=True
    )
    # `-c` is parse/dry-run, but unprivileged nft still initializes a netlink
    # cache against the live ruleset, which needs CAP_NET_ADMIN. Such failures
    # ("Operation not permitted" / "permission denied" / "cache initialization
    # failed") are environmental, not syntax errors — skip them. A genuine
    # syntax error reports a line/parse message instead.
    stderr = (check.stderr or "").lower()
    if check.returncode != 0 and any(
        s in stderr for s in ("permission", "not permitted", "cache initialization")
    ):
        pytest.skip("nft -c needs privileges in this environment")
    assert check.returncode == 0, check.stderr


# --- dispatch -------------------------------------------------------------

def test_unknown_subcommand_errors(tmp_path: Path) -> None:
    rc, _, err, _ = _run_vpn(tmp_path, ["bogus"])
    assert rc == 1
    assert "unknown subcommand" in err.lower()
