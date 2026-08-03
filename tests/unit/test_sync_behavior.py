"""
Tests for config-preservation sync behaviour introduced to protect user dotfiles.

Covers:
- migrate_user_conf() — converts stow-managed symlink to machine-local real file
- force_stow_package() — additive-only (stow) vs full-replace (restow) modes
- stow_all_packages() — passes mode through correctly
- --sync path — calls migrate_user_conf before git pull; uses additive mode on stable
- --sync --full flag — forces full restow on stable branch
- 99-hyprconf-local.conf not present in stow package (machine-local only)
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SETUP_SH = REPO_ROOT / "setup.sh"
CONF_D = REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "conf.d"


# ---------------------------------------------------------------------------
# Static analysis helpers
# ---------------------------------------------------------------------------


def _setup_text() -> str:
    return SETUP_SH.read_text()


def _extract_function(name: str) -> str:
    """Return the body of a bash function from setup.sh via awk."""
    result = subprocess.run(
        ["awk", f"/^{name}\\(\\)/,/^\\}}$/", str(SETUP_SH)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _run_bash_fragment(script: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run an arbitrary bash snippet and return the completed process."""
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=full_env,
    )


# ---------------------------------------------------------------------------
# 1. migrate_user_conf — function existence and static structure
# ---------------------------------------------------------------------------


class TestMigrateUserConf:
    def test_function_exists(self) -> None:
        assert "migrate_user_conf()" in _setup_text()

    def test_converts_symlink_to_real_file(self) -> None:
        body = _extract_function("migrate_user_conf")
        # Must detect symlinks (-L check)
        assert "-L" in body
        # Must resolve the symlink target with realpath
        assert "realpath" in body
        # Must remove the old symlink
        assert "rm" in body

    def test_removes_stow_copy(self) -> None:
        body = _extract_function("migrate_user_conf")
        # Must delete the stow package copy of the file
        assert "stow_file" in body or "STOW_DIR" in body

    def test_handles_broken_symlink(self) -> None:
        body = _extract_function("migrate_user_conf")
        # Must handle the case where realpath returns empty (broken symlink)
        assert "-z" in body or "broken" in body.lower() or "stale" in body.lower()

    def test_called_before_clone_in_sync(self) -> None:
        src = _setup_text()
        sync_idx = src.index('"--sync"')
        sync_block = src[sync_idx : sync_idx + 1500]
        mi_pos = sync_block.find("migrate_user_conf")
        cu_pos = sync_block.find("clone_or_update_repo")
        assert mi_pos != -1, "migrate_user_conf not found in --sync block"
        assert cu_pos != -1, "clone_or_update_repo not found in --sync block"
        assert mi_pos < cu_pos, (
            "migrate_user_conf must run BEFORE clone_or_update_repo so user "
            "settings are preserved even when git pull would delete the stow copy"
        )

    def test_migrate_working_symlink(self, tmp_path: Path) -> None:
        """migrate_user_conf preserves content when converting a working symlink."""
        # Set up a fake stow tree
        stow_conf_d = tmp_path / "stow" / "hypr" / ".config" / "hypr" / "conf.d"
        stow_conf_d.mkdir(parents=True)
        stow_file = stow_conf_d / "99-hyprconf-local.conf"
        stow_file.write_text("$mainMod = SUPER\n# user-value = 42\n")

        live_conf_d = tmp_path / ".config" / "hypr" / "conf.d"
        live_conf_d.mkdir(parents=True)
        live_file = live_conf_d / "99-hyprconf-local.conf"
        live_file.symlink_to(stow_file)

        fn_script = self._make_runner(tmp_path)
        result = subprocess.run(
            ["bash", fn_script],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(tmp_path),
                "HYPRCONF_DIR": str(tmp_path),
                "STOW_DIR": str(tmp_path / "stow"),
            },
        )
        assert result.returncode == 0, result.stderr
        # The live file must now be a REAL FILE (not a symlink)
        assert not live_file.is_symlink(), "live file should be a real file after migration"
        assert live_file.exists(), "live file should exist after migration"
        assert "user-value = 42" in live_file.read_text(), "user settings must be preserved"

    def test_migrate_working_symlink_local_lua(self, tmp_path: Path) -> None:
        """migrate_user_conf also handles the current local.lua filename, not just the legacy one."""
        stow_conf_d = tmp_path / "stow" / "hypr" / ".config" / "hypr" / "conf.d"
        stow_conf_d.mkdir(parents=True)
        stow_file = stow_conf_d / "local.lua"
        stow_file.write_text('local mainMod = "SUPER"\n-- user-value = 42\n')

        live_conf_d = tmp_path / ".config" / "hypr" / "conf.d"
        live_conf_d.mkdir(parents=True)
        live_file = live_conf_d / "local.lua"
        live_file.symlink_to(stow_file)

        fn_script = self._make_runner(tmp_path)
        result = subprocess.run(
            ["bash", fn_script],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(tmp_path),
                "HYPRCONF_DIR": str(tmp_path),
                "STOW_DIR": str(tmp_path / "stow"),
            },
        )
        assert result.returncode == 0, result.stderr
        assert not live_file.is_symlink(), "live file should be a real file after migration"
        assert live_file.exists(), "live file should exist after migration"
        assert "user-value = 42" in live_file.read_text(), "user settings must be preserved"

    def test_migrate_missing_file_is_noop(self, tmp_path: Path) -> None:
        """migrate_user_conf is a no-op when no file exists."""
        live_conf_d = tmp_path / ".config" / "hypr" / "conf.d"
        live_conf_d.mkdir(parents=True)
        fn_script = self._make_runner(tmp_path)
        result = subprocess.run(
            ["bash", fn_script],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(tmp_path),
                "HYPRCONF_DIR": str(tmp_path),
                "STOW_DIR": str(tmp_path / "stow"),
            },
        )
        assert result.returncode == 0

    def test_migrate_real_file_is_noop(self, tmp_path: Path) -> None:
        """migrate_user_conf does not touch an existing real file."""
        live_conf_d = tmp_path / ".config" / "hypr" / "conf.d"
        live_conf_d.mkdir(parents=True)
        live_file = live_conf_d / "99-hyprconf-local.conf"
        live_file.write_text("$mainMod = ALT\n# custom\n")

        fn_script = self._make_runner(tmp_path)
        subprocess.run(
            ["bash", fn_script],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(tmp_path),
                "HYPRCONF_DIR": str(tmp_path),
                "STOW_DIR": str(tmp_path / "stow"),
            },
        )
        # Content must be unchanged
        assert live_file.read_text() == "$mainMod = ALT\n# custom\n"

    def _make_runner(self, tmp_path: Path) -> str:
        """Write a temp script that sources migrate_user_conf and calls it."""
        fn_body = _extract_function("migrate_user_conf")
        script_path = tmp_path / "_test_migrate.sh"
        script_path.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            "log_ok() { :; }\n"
            "log_warn() { :; }\n" + fn_body + "\nmigrate_user_conf\n"
        )
        script_path.chmod(0o755)
        return str(script_path)


# ---------------------------------------------------------------------------
# 2. force_stow_package — additive-only mode
# ---------------------------------------------------------------------------


class TestForceStowPackageMode:
    def test_accepts_mode_parameter(self) -> None:
        body = _extract_function("force_stow_package")
        assert "stow_mode" in body

    def test_uses_stow_mode_flag(self) -> None:
        body = _extract_function("force_stow_package")
        # The mode string must be passed to stow (--restow or --stow)
        assert (
            '"$stow_mode"' in body
            or "--$stow_mode" in body
            or '"--${stow_mode}"' in body
            or '--"$stow_mode"' in body
        )

    def test_additive_mode_skips_backup(self) -> None:
        body = _extract_function("force_stow_package")
        # In additive (stow) mode, conflicts should be skipped, not backed up
        assert "stow" in body and "restow" in body
        # Must have a branch that handles stow mode differently from restow
        assert '"stow"' in body or "== stow" in body or '== "stow"' in body

    def test_additive_mode_preserves_user_files(self) -> None:
        body = _extract_function("force_stow_package")
        # Must mention --full or preservation of user files in the warning
        assert "--full" in body or "user files preserved" in body or "preserved" in body


# ---------------------------------------------------------------------------
# 4. stow_all_packages — mode passthrough
# ---------------------------------------------------------------------------


class TestStowAllPackagesMode:
    def test_accepts_mode_parameter(self) -> None:
        body = _extract_function("stow_all_packages")
        assert "stow_mode" in body

    def test_passes_mode_to_force_stow_package(self) -> None:
        body = _extract_function("stow_all_packages")
        assert "force_stow_package" in body
        # mode variable passed in the call
        assert "stow_mode" in body


# ---------------------------------------------------------------------------
# 5. --sync path — branch-aware stow mode and --full flag
# ---------------------------------------------------------------------------


class TestSyncPath:
    def test_sync_always_uses_additive_stow_by_default(self) -> None:
        """Sync must use additive-only stow by default, regardless of branch.

        This prevents user-modified dotfiles from being overwritten on any branch.
        """
        src = _setup_text()
        sync_idx = src.index('"--sync"')
        sync_block = src[sync_idx : sync_idx + 3000]
        assert (
            '"stow"' in sync_block
            or '_stow_mode="stow"' in sync_block
            or "_stow_mode='stow'" in sync_block
        ), "--sync path must default to additive stow mode"

    def test_full_flag_forces_restow(self) -> None:
        src = _setup_text()
        sync_idx = src.index('"--sync"')
        sync_block = src[sync_idx : sync_idx + 3000]
        assert "--full" in sync_block, "--sync must support --full flag"
        assert "restow" in sync_block, "--full must select restow mode"

    def test_setup_hardware_features_in_sync(self) -> None:
        """setup_hardware_features (installs gtk-layer-shell/iio-sensor-proxy) must run on sync."""
        src = _setup_text()
        sync_idx = src.index('"--sync"')
        sync_block = src[sync_idx : sync_idx + 2000]
        assert "setup_hardware_features" in sync_block, (
            "setup_hardware_features must be called in sync path for install/sync parity"
        )

    def test_force_flag_triggers_hard_reset(self) -> None:
        """--force must trigger git reset --hard instead of --ff-only pull."""
        func = _extract_function("clone_or_update_repo")
        assert "reset --hard" in func, (
            "clone_or_update_repo must use git reset --hard when force is true"
        )

    def test_force_flag_accepted_in_sync_block(self) -> None:
        """The --sync arg parser must recognise --force."""
        src = _setup_text()
        sync_idx = src.index('"--sync"')
        sync_block = src[sync_idx : sync_idx + 1000]
        assert "--force" in sync_block, "--sync path must support --force flag"

    def test_force_passed_to_clone_or_update(self) -> None:
        """The sync block must pass the force flag to clone_or_update_repo."""
        src = _setup_text()
        sync_idx = src.index('"--sync"')
        sync_block = src[sync_idx : sync_idx + 2000]
        assert "clone_or_update_repo" in sync_block
        # Must be called with the force variable, not bare
        clone_line = [l for l in sync_block.splitlines() if "clone_or_update_repo" in l][0]
        assert "_sync_force" in clone_line, (
            "clone_or_update_repo must receive the _sync_force argument"
        )

    def test_clone_or_update_repo_accepts_force_param(self) -> None:
        """clone_or_update_repo must accept a force parameter."""
        func = _extract_function("clone_or_update_repo")
        assert "_force" in func, "clone_or_update_repo must have a _force parameter"

    def test_default_pull_uses_autostash(self) -> None:
        """The non-force pull must use --autostash.

        Theme writes leave tracked stow files chronically dirty; a plain
        `git pull --ff-only` aborts on those local changes and silently strands
        newly-added files (e.g. yubikey-fido2-setup).  --autostash shelves the
        dirty files so the fast-forward — and the new files — still land.
        """
        func = _extract_function("clone_or_update_repo")
        assert "--autostash" in func, (
            "Default (non-force) pull must use 'git pull --ff-only --autostash' so "
            "a chronically-dirty working tree (theme writes) cannot block updates"
        )

    def test_autostash_conflict_is_resolved(self) -> None:
        """A conflicted autostash re-apply must be resolved, not left in the tree.

        Otherwise the unmerged index + conflict markers would break the next sync.
        """
        func = _extract_function("clone_or_update_repo")
        assert "--diff-filter=U" in func, (
            "Must enumerate conflicted paths after a failed autostash re-apply"
        )
        assert "checkout HEAD --" in func, (
            "Conflicted paths must be reset to the upstream version (checkout HEAD)"
        )
        assert "stash drop" in func, (
            "The leftover autostash entry must be dropped so stashes don't accumulate"
        )

    def test_active_theme_preserved_across_pull(self) -> None:
        """The user's active theme selection must survive the pull/regenerate."""
        func = _extract_function("clone_or_update_repo")
        assert ".current-theme" in func, (
            "clone_or_update_repo must preserve .current-theme so reapply_current_theme "
            "regenerates colors for the user's selected theme, not the repo default"
        )

    def test_force_and_full_combinable(self) -> None:
        """--force and --full must be combinable (loop-based parsing, not positional)."""
        src = _setup_text()
        sync_idx = src.index('"--sync"')
        sync_block = src[sync_idx : sync_idx + 500]
        assert "for _arg" in sync_block or "for arg" in sync_block, (
            "Sync arg parsing must use a loop so flags are combinable in any order"
        )


# ---------------------------------------------------------------------------
# 7. sync_services wifi backend fix — sync-patchable networking
# ---------------------------------------------------------------------------


class TestSyncServicesWifi:
    def test_sync_services_writes_nm_wifi_backend_conf(self) -> None:
        """sync_services must write the NM wifi-backend.conf to use iwd."""
        func = _extract_function("sync_services")
        assert "wifi.backend=iwd" in func, (
            "sync_services must write wifi.backend=iwd to the NM conf.d directory "
            "so existing installs pick up the iwd backend fix via setup.sh --sync"
        )

    def test_sync_services_enables_iwd(self) -> None:
        """sync_services must enable iwd.service (guarded by iwctl presence)."""
        func = _extract_function("sync_services")
        assert "enable" in func and "iwd" in func, (
            "sync_services must enable iwd.service — required for NM iwd backend"
        )

    def test_sync_services_iwd_guarded(self) -> None:
        """iwd enablement must be guarded behind a check for iwctl."""
        func = _extract_function("sync_services")
        assert "iwctl" in func, (
            "sync_services must check for iwctl before enabling iwd "
            "so systems without iwd don't fail"
        )

    def test_sync_services_nm_conf_is_idempotent(self) -> None:
        """sync_services must guard the NM conf write to avoid overwriting on repeat runs."""
        func = _extract_function("sync_services")
        # Must check if conf already exists (grep -qs or similar) before writing
        assert "grep" in func or "if " in func, (
            "sync_services must check for the existing NM conf before writing "
            "so repeated syncs are idempotent"
        )
        assert "_nm_wifi_conf" in func or "wifi-backend.conf" in func, (
            "sync_services must reference the wifi-backend.conf path"
        )

    def test_sync_services_warns_when_no_wifi_profiles(self) -> None:
        """sync_services must warn when no NM wifi profiles are configured."""
        func = _extract_function("sync_services")
        assert "nmcli" in func, (
            "sync_services must check for wifi profiles via nmcli and warn if none exist"
        )
        assert "nmtui" in func, (
            "sync_services warning must direct the user to nmtui to configure wifi"
        )

    def test_wifi_profile_warning_only_on_live_system(self) -> None:
        """The no-profiles warning must only fire outside of a chroot."""
        func = _extract_function("sync_services")
        # nmtui reference must be in the non-chroot else branch, not inside _in_chroot block
        chroot_block_end = func.find("else\n")
        nmcli_pos = func.find("nmcli")
        assert nmcli_pos > chroot_block_end, (
            "nmcli wifi profile check must only run on a live system (not in chroot)"
        )


# ---------------------------------------------------------------------------
# 6. local.lua (and the pre-migration 99-hyprconf-local.conf) must NOT be
#    tracked in the stow package
# ---------------------------------------------------------------------------


class TestUserConfNotStowed:
    def test_local_lua_not_in_stow_package(self) -> None:
        local_conf = CONF_D / "local.lua"
        assert not local_conf.exists(), (
            "local.lua must not exist in the stow package — "
            "it is machine-local and must not be managed by stow or committed to git"
        )

    def test_99_conf_not_in_stow_package(self) -> None:
        local_conf = CONF_D / "99-hyprconf-local.conf"
        assert not local_conf.exists(), (
            "99-hyprconf-local.conf must not exist in the stow package — "
            "it is machine-local and must not be managed by stow or committed to git"
        )

    def test_gitignore_excludes_local_lua(self) -> None:
        gitignore = CONF_D / ".gitignore"
        assert gitignore.exists(), (
            "conf.d/.gitignore must exist to prevent committing machine-local user configs"
        )
        assert "local.lua" in gitignore.read_text()

    def test_gitignore_excludes_99_conf(self) -> None:
        gitignore = CONF_D / ".gitignore"
        assert gitignore.exists(), (
            "conf.d/.gitignore must exist to prevent committing machine-local user configs"
        )
        assert "99-hyprconf-local.conf" in gitignore.read_text()

    def test_create_directories_creates_user_conf_as_real_file(self) -> None:
        """create_directories must create local.lua as a real file."""
        src = _setup_text()
        # The function must create the file (cat > or similar)
        cd_idx = src.index("create_directories()")
        cd_body = src[cd_idx : cd_idx + 800]
        assert "local.lua" in cd_body, "create_directories must handle local.lua"

    def test_create_directories_still_recognises_legacy_name(self) -> None:
        """create_directories must not blank-slate a not-yet-migrated legacy file."""
        src = _setup_text()
        cd_idx = src.index("create_directories()")
        cd_body = src[cd_idx : cd_idx + 800]
        assert "99-hyprconf-local.conf" in cd_body, (
            "create_directories must still check for the legacy filename so it "
            "doesn't create a blank local.lua that would make hyprconf's Python "
            "migration skip converting the user's old overrides"
        )
