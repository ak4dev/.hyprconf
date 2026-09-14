"""modules/idle: the screensaver timeout, set once through Omarchy's own shell.json helper.

The module sources `omarchy-shell-config`, so the box's shared recording fake (whose body
is `exit 0`) would end the subshell before `commit` ever ran. Every test that expects a
write installs SOURCEABLE, a stand-in that mirrors the real helper's shape — source_file()
picking the user file or the shipped defaults, `jq -S -e` into a tmp, `mv`, then
`omarchy-shell shell reloadConfig` (bin/omarchy-shell-config:14-26,53-62, Omarchy 4.0.3-1).
Its own line is still recorded, so `box.commands` proves the module went through it.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"

# A sourceable stand-in for bin/omarchy-shell-config. Functions only — no `exit`, which
# would end the module's subshell (the real helper defines functions and one EXIT trap).
SOURCEABLE = """
CONFIG_FILE="$HOME/.config/omarchy/shell.json"
DEFAULTS_FILE="$OMARCHY_PATH/config/omarchy/shell.json"
fail() { echo "${0##*/}: $*" >&2; exit 1; }
refresh_shell_config() { omarchy-shell shell reloadConfig >/dev/null 2>&1 || true; }
source_file() {
  if [[ -s $CONFIG_FILE ]]; then printf '%s\\n' "$CONFIG_FILE"
  else printf '%s\\n' "$DEFAULTS_FILE"; fi
}
_SHELL_CONFIG_TMP=""
cleanup_shell_config_tmp() { if [[ -n $_SHELL_CONFIG_TMP ]]; then rm -f "$_SHELL_CONFIG_TMP"; fi; }
trap cleanup_shell_config_tmp EXIT
commit() {
  local program="$1"; shift
  mkdir -p "$(dirname "$CONFIG_FILE")"
  _SHELL_CONFIG_TMP=$(mktemp)
  jq -S -e "$@" "$program" "$(source_file)" >"$_SHELL_CONFIG_TMP" || fail "could not update shell config"
  mv "$_SHELL_CONFIG_TMP" "$CONFIG_FILE"
  _SHELL_CONFIG_TMP=""
  refresh_shell_config
}
"""

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")

# What `install` runs before it reaches the helper, plus what undo needs. A PATH of only
# these proves the `command -v omarchy-shell-config` guard without letting a run near the
# developer's real /usr/bin, where the live helper and shell would answer.
BARE_TOOLS = ("bash", "readlink", "dirname", "mkdir", "rm", "jq")


@pytest.fixture
def bare_path(tmp_path: Path) -> Path:
    """A PATH directory carrying the pure tools and no omarchy-* command at all."""
    bare = tmp_path / "bare"
    bare.mkdir()
    for name in BARE_TOOLS:
        found = shutil.which(name)
        if found is None:
            pytest.skip(f"{name} is not installed")
        (bare / name).symlink_to(found)
    return bare


def helper(box, body: str = SOURCEABLE) -> None:
    """Make `source omarchy-shell-config` work in this box, and `omarchy-shell` answer."""
    box.stub("omarchy-shell-config", body)
    box.stub("omarchy-shell")


def shell_json(box) -> dict:
    return json.loads((box.home / ".config/omarchy/shell.json").read_text())


def marker(box) -> Path:
    return box.home / ".local/state/hyprconf/idle-applied"


# -- applying -------------------------------------------------------------------


def test_screensaver_is_set_to_900_through_omarchys_own_helper(box):
    helper(box)
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert shell_json(box)["idle"]["screensaver"] == 900
    assert "omarchy-shell-config" in box.commands
    assert ["omarchy-shell", "shell", "reloadConfig"] in box.calls_of("omarchy-shell")
    assert marker(box).exists()


def test_the_lock_timeout_is_left_as_omarchy_has_it(box):
    """Only .idle.screensaver is ours; .idle.lock stays Omarchy's 300 s."""
    helper(box)
    box.run(INSTALL)
    assert shell_json(box)["idle"]["lock"] == 300


def test_an_existing_shell_json_is_edited_not_replaced(box):
    (box.home / ".config/omarchy").mkdir(parents=True)
    (box.home / ".config/omarchy/shell.json").write_text(
        json.dumps({"version": 1, "idle": {"lock": 60}, "bar": {"position": "bottom"}})
    )
    helper(box)
    box.run(INSTALL)
    config = shell_json(box)
    assert config["idle"] == {"lock": 60, "screensaver": 900}
    assert config["bar"]["position"] == "bottom"


def test_with_no_user_shell_json_the_shipped_defaults_are_the_source(box):
    """source_file() falls back to $OMARCHY_PATH/config/omarchy/shell.json (:20-26), so the
    first run materialises a user file carrying Omarchy's own keys plus ours."""
    helper(box)
    box.run(INSTALL)
    config = shell_json(box)
    assert config["version"] == 1
    assert config["bar"]["centerAnchor"] == "omarchy.clock"
    assert config["idle"]["screensaver"] == 900


# -- idempotence ----------------------------------------------------------------


def test_a_second_run_writes_nothing_and_calls_nothing(box):
    helper(box)
    box.run(INSTALL)
    before = {p: p.read_bytes() for p in box.files()}
    box.reset()

    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert box.commands == []
    assert {p: p.read_bytes() for p in box.files()} == before


def test_a_later_hand_edit_is_never_re_asserted(box):
    """The marker is the whole point: past it the timeout is the user's (rule 5)."""
    helper(box)
    box.run(INSTALL)
    path = box.home / ".config/omarchy/shell.json"
    config = json.loads(path.read_text())
    config["idle"]["screensaver"] = 60
    path.write_text(json.dumps(config))
    box.reset()

    box.run(INSTALL)
    assert shell_json(box)["idle"]["screensaver"] == 60
    assert box.commands == []


def test_the_marker_follows_HYPRCONF_STATE(box):
    helper(box)
    state = box.tmp / "state"
    box.run(INSTALL, env={"HYPRCONF_STATE": str(state)})
    assert (state / "idle-applied").exists()
    assert not marker(box).exists()


# -- failing softly -------------------------------------------------------------


def test_a_failed_commit_leaves_no_marker_and_does_not_fail_the_run(box):
    """commit()'s fail() exits 1 inside the subshell; the module warns and retries next run."""
    helper(box, SOURCEABLE.replace('jq -S -e "$@"', 'false "$@"'))
    result = box.run(INSTALL)
    assert result.returncode == 0
    assert "retry" in result.stdout
    assert not marker(box).exists()


def test_a_helper_that_refuses_to_load_leaves_no_marker(box):
    """`source` returning non-zero short-circuits the && — the module warns and retries."""
    helper(box, "return 1\n")
    result = box.run(INSTALL)
    assert result.returncode == 0
    assert "retry" in result.stdout
    assert not marker(box).exists()
    assert box.files() == set(), "a failing run leaves nothing behind, not even the state dir"


def test_no_helper_on_PATH_is_a_warning_not_a_dead_install(box, bare_path):
    """`command -v omarchy-shell-config` fails: an Omarchy too old (or absent) to have the
    helper must not take the module loop down with it."""
    result = box.run(INSTALL, env={"PATH": str(bare_path)})
    assert result.returncode == 0
    assert "retry" in result.stdout
    assert not marker(box).exists()
    assert box.commands == []


def test_a_malformed_shell_json_is_a_warning_not_a_dead_install(box):
    (box.home / ".config/omarchy").mkdir(parents=True)
    (box.home / ".config/omarchy/shell.json").write_text("{ not json")
    helper(box)
    result = box.run(INSTALL)
    assert result.returncode == 0
    assert "retry" in result.stdout
    assert not marker(box).exists()


# -- undo -----------------------------------------------------------------------


def test_undo_drops_the_key_and_the_marker(box):
    helper(box)
    box.run(INSTALL)
    box.reset()

    result = box.undo("idle")
    assert result.returncode == 0, result.stderr
    config = shell_json(box)
    assert "screensaver" not in config["idle"]
    assert config["idle"]["lock"] == 300
    assert not marker(box).exists()
    assert "omarchy-shell-config" in box.commands


def test_undo_with_no_user_shell_json_creates_none(box):
    """Guarded, or commit()'s defaults fallback would materialise a file the user never had."""
    helper(box)
    result = box.undo("idle")
    assert result.returncode == 0, result.stderr
    assert not (box.home / ".config/omarchy/shell.json").exists()
    assert box.commands == []


def test_undo_leaves_a_shell_json_that_never_carried_the_key_alone(box):
    (box.home / ".config/omarchy").mkdir(parents=True)
    path = box.home / ".config/omarchy/shell.json"
    path.write_text('{"version": 1, "idle": {"lock": 300}}')
    helper(box)

    assert box.undo("idle").returncode == 0
    assert path.read_text() == '{"version": 1, "idle": {"lock": 300}}'
    assert box.commands == []


def test_undo_survives_a_malformed_shell_json(box):
    """The `.idle.screensaver != null` guard is jq's too: it fails on garbage, so undo
    falls through to removing the marker rather than rewriting the file."""
    (box.home / ".config/omarchy").mkdir(parents=True)
    path = box.home / ".config/omarchy/shell.json"
    path.write_text("{ not json")
    helper(box)
    marker(box).parent.mkdir(parents=True)
    marker(box).touch()

    assert box.undo("idle").returncode == 0
    assert path.read_text() == "{ not json"
    assert not marker(box).exists()


def test_undo_is_repeatable(box):
    helper(box)
    box.run(INSTALL)
    box.undo("idle")
    after = (box.home / ".config/omarchy/shell.json").read_bytes()
    box.reset()

    assert box.undo("idle").returncode == 0
    assert (box.home / ".config/omarchy/shell.json").read_bytes() == after
    assert box.commands == []


def test_install_after_undo_applies_again(box):
    helper(box)
    box.run(INSTALL)
    box.undo("idle")
    box.run(INSTALL)
    assert shell_json(box)["idle"]["screensaver"] == 900


# -- the module contract --------------------------------------------------------


def test_install_is_an_executable_strict_bash_script():
    text = INSTALL.read_text()
    assert INSTALL.stat().st_mode & 0o111, "modules/idle/install is not executable"
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "\nset -euo pipefail\n" in text
    assert "@HYPRCONF_DIR@" not in text, "a module carries no install-time substitution"
    assert "sudo" not in text, "idle needs no root, so it carries no sudo gate"


def test_every_omarchy_command_the_module_names_has_a_fake(box):
    """The box's PATH must answer for everything a run can reach (conftest › omarchy_fakes)."""
    names = set(re.findall(r"\bomarchy(?:-[a-z0-9]+)+\b", INSTALL.read_text()))
    assert names, "the scan is broken"
    assert names <= box.fakes
