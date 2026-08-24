"""Tests for hyprconf.omarchy — the TUI's seams into Omarchy's theme,
background and idle machinery.

Everything runs against fake ``omarchy-*`` binaries on PATH (recording stubs,
as tests/unit/test_omarchy_install.py does) and a throwaway HOME /
OMARCHY_PATH tree, so the suite is hermetic in a bare archlinux container.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from hyprconf import omarchy

# A recording stub: appends its own name + args to the calls log, then runs an
# optional body.
STUB = """#!/usr/bin/env bash
printf '%s\\n' "${{0##*/}} $*" >> "{calls}"
{body}
"""

DEFAULT_SHELL_JSON = {
    "version": 1,
    "idle": {"screensaver": 150, "lock": 300},
    "bar": {"position": "top", "layout": {"left": [{"id": "omarchy.menu"}]}},
    "plugins": [],
}


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.home = tmp_path / "home"
        self.bins = tmp_path / "bins"
        self.omarchy_path = tmp_path / "omarchy"
        self.calls = tmp_path / "calls"
        for d in (self.home, self.bins, self.omarchy_path):
            d.mkdir(parents=True, exist_ok=True)
        self.calls.write_text("")

    def stub(self, name: str, body: str = "exit 0") -> None:
        p = self.bins / name
        p.write_text(STUB.format(calls=self.calls, body=body))
        p.chmod(0o755)

    def logged(self) -> list[str]:
        return self.calls.read_text().splitlines()

    @property
    def state(self) -> Path:
        return self.home / ".local" / "state" / "omarchy"

    @property
    def config(self) -> Path:
        return self.home / ".config" / "omarchy"

    def seed_theme(self, name: str = "tokyo-night") -> Path:
        cur = self.state / "current"
        cur.mkdir(parents=True, exist_ok=True)
        (cur / "theme.name").write_text(name + "\n")
        (cur / "theme").mkdir(exist_ok=True)
        return cur

    def seed_defaults(self, data: dict = DEFAULT_SHELL_JSON) -> Path:
        p = self.omarchy_path / "config" / "omarchy" / "shell.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2))
        return p


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    e = Env(tmp_path)
    monkeypatch.setenv("HOME", str(e.home))
    monkeypatch.setenv("OMARCHY_PATH", str(e.omarchy_path))
    # Stubs first; the rest of PATH stays so the stubs' `env bash` resolves.
    monkeypatch.setenv("PATH", str(e.bins) + os.pathsep + os.environ.get("PATH", "/usr/bin"))
    return e


# ---------------------------------------------------------------------------
# Paths derive from the environment at call time
# ---------------------------------------------------------------------------


def test_paths_follow_home_and_omarchy_path(env: Env) -> None:
    assert omarchy.home_dir() == env.home
    assert omarchy.state_dir() == env.home / ".local" / "state" / "omarchy"
    assert omarchy.config_dir() == env.home / ".config" / "omarchy"
    assert omarchy.omarchy_path() == env.omarchy_path
    assert omarchy.current_theme_dir() == env.state / "current" / "theme"


def test_omarchy_path_defaults_to_usr_share(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMARCHY_PATH")
    assert omarchy.omarchy_path() == Path("/usr/share/omarchy")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def test_run_command_missing_binary_is_a_failure(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(env.bins))  # nothing but our (empty) bins dir
    assert omarchy.run_command(["omarchy-theme-current"]) == (127, "")


def test_run_command_captures_stdout(env: Env) -> None:
    env.stub("omarchy-theme-current", 'echo "Tokyo Night"')
    assert omarchy.run_command(["omarchy-theme-current"]) == (0, "Tokyo Night\n")


def test_injected_runner_replaces_subprocess(env: Env) -> None:
    seen: list[list[str]] = []

    def fake(argv: list[str]) -> tuple[int, str]:
        seen.append(argv)
        return 0, "Gruvbox\nTokyo Night\n"

    assert omarchy.list_themes(run=fake) == ["Gruvbox", "Tokyo Night"]
    assert seen == [["omarchy-theme-list"]]
    assert env.logged() == []  # no real binary ran


# ---------------------------------------------------------------------------
# Theme — omarchy-theme-list / -current / -set
# ---------------------------------------------------------------------------


def test_list_themes_reads_omarchy_theme_list(env: Env) -> None:
    env.stub("omarchy-theme-list", 'printf "Catppuccin\\nTokyo Night\\n\\n"')
    assert omarchy.list_themes() == ["Catppuccin", "Tokyo Night"]
    assert env.logged() == ["omarchy-theme-list "]


def test_list_themes_empty_when_command_fails(env: Env) -> None:
    env.stub("omarchy-theme-list", "exit 1")
    assert omarchy.list_themes() == []


def test_current_theme_reads_omarchy_theme_current(env: Env) -> None:
    env.stub("omarchy-theme-current", 'echo "Tokyo Night"')
    assert omarchy.current_theme() == "Tokyo Night"


def test_current_theme_unknown_when_command_missing(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(env.bins))
    assert omarchy.current_theme() == "Unknown"


def test_set_theme_calls_omarchy_theme_set_with_the_display_name(env: Env) -> None:
    env.stub("omarchy-theme-set")
    assert omarchy.set_theme("Tokyo Night") is True
    assert env.logged() == ["omarchy-theme-set Tokyo Night"]


def test_set_theme_reports_failure(env: Env) -> None:
    env.stub("omarchy-theme-set", "exit 1")
    assert omarchy.set_theme("Nope") is False


# ---------------------------------------------------------------------------
# Background — the two dirs omarchy-theme-bg-next scans, the current symlink,
# omarchy-theme-bg-set
# ---------------------------------------------------------------------------


def _seed_backgrounds(env: Env) -> tuple[Path, Path]:
    cur = env.seed_theme("tokyo-night")
    theme_bgs = cur / "theme" / "backgrounds"
    theme_bgs.mkdir()
    (theme_bgs / "1-mountains.jpg").write_bytes(b"x")
    (theme_bgs / "2-city.PNG").write_bytes(b"x")
    (theme_bgs / "notes.txt").write_text("not an image")
    (theme_bgs / "nested").mkdir()
    (theme_bgs / "nested" / "deep.jpg").write_bytes(b"x")  # -maxdepth 1: not listed
    user_bgs = env.config / "backgrounds" / "tokyo-night"
    user_bgs.mkdir(parents=True)
    (user_bgs / "custom.webp").write_bytes(b"x")
    real = env.home / "Pictures" / "linked.jpeg"
    real.parent.mkdir()
    real.write_bytes(b"x")
    (user_bgs / "linked.jpeg").symlink_to(real)  # find -L: symlinked files count
    (user_bgs / "dangling.png").symlink_to(env.home / "gone.png")  # …but not dangling ones
    return theme_bgs, user_bgs


def test_background_dirs_are_exactly_the_two_omarchy_scans(env: Env) -> None:
    env.seed_theme("tokyo-night")
    assert omarchy.background_dirs() == [
        env.config / "backgrounds" / "tokyo-night",
        env.state / "current" / "theme" / "backgrounds",
    ]


def test_list_backgrounds_matches_omarchy_theme_bg_next(env: Env) -> None:
    theme_bgs, user_bgs = _seed_backgrounds(env)
    assert omarchy.list_backgrounds() == sorted(
        [
            user_bgs / "custom.webp",
            user_bgs / "linked.jpeg",
            theme_bgs / "1-mountains.jpg",
            theme_bgs / "2-city.PNG",
        ]
    )


def test_list_backgrounds_empty_without_dirs(env: Env) -> None:
    assert omarchy.list_backgrounds() == []


def test_current_background_is_the_symlink_target(env: Env) -> None:
    theme_bgs, _ = _seed_backgrounds(env)
    target = theme_bgs / "1-mountains.jpg"
    (env.state / "current" / "background").symlink_to(target)
    assert omarchy.current_background() == target
    assert omarchy.current_background() in omarchy.list_backgrounds()


def test_current_background_none_without_symlink(env: Env) -> None:
    env.seed_theme()
    assert omarchy.current_background() is None


def test_set_background_calls_omarchy_theme_bg_set(env: Env) -> None:
    env.stub("omarchy-theme-bg-set")
    assert omarchy.set_background(Path("/tmp/x/bg.png")) is True
    assert env.logged() == ["omarchy-theme-bg-set /tmp/x/bg.png"]


def test_set_background_reports_failure(env: Env) -> None:
    env.stub("omarchy-theme-bg-set", "exit 1")
    assert omarchy.set_background("/nope.png") is False


# ---------------------------------------------------------------------------
# Idle timeouts — shell.json, the way omarchy-shell-config's commit() edits it
# ---------------------------------------------------------------------------


def test_idle_timeouts_fall_back_to_omarchy_defaults_file(env: Env) -> None:
    env.seed_defaults()
    assert omarchy.idle_timeouts() == {"lock": 300, "screensaver": 150}


def test_idle_timeouts_prefer_the_user_file(env: Env) -> None:
    env.seed_defaults()
    env.config.mkdir(parents=True)
    (env.config / "shell.json").write_text(json.dumps({"idle": {"lock": 600}}))
    # A key the user file omits takes the shell's own fallback, not the
    # defaults file (Service.qml: secondsFromConfig(value, default)).
    assert omarchy.idle_timeouts() == {"lock": 600, "screensaver": 150}


def test_idle_timeouts_empty_user_file_means_defaults(env: Env) -> None:
    """omarchy-shell-config's source_file() tests -s: a 0-byte user file is ignored."""
    env.seed_defaults({"idle": {"lock": 420, "screensaver": 60}})
    env.config.mkdir(parents=True)
    (env.config / "shell.json").write_text("")
    assert omarchy.idle_timeouts() == {"lock": 420, "screensaver": 60}


def test_idle_timeouts_without_any_file(env: Env) -> None:
    assert omarchy.idle_timeouts() == omarchy.IDLE_DEFAULTS


def test_idle_timeouts_ignore_garbage_values(env: Env) -> None:
    env.config.mkdir(parents=True)
    (env.config / "shell.json").write_text(json.dumps({"idle": {"lock": "soon", "screensaver": 5}}))
    assert omarchy.idle_timeouts() == {"lock": 300, "screensaver": 5}


def test_set_idle_timeouts_seeds_from_defaults_and_reloads_the_shell(env: Env) -> None:
    env.seed_defaults()
    env.stub("omarchy-shell")
    assert omarchy.set_idle_timeouts(lock=900) is True
    written = json.loads((env.config / "shell.json").read_text())
    assert written["idle"] == {"lock": 900, "screensaver": 150}
    assert written["bar"] == DEFAULT_SHELL_JSON["bar"]  # every other key preserved
    assert written["version"] == 1
    assert env.logged() == ["omarchy-shell shell reloadConfig"]
    assert not list(env.config.glob("*tmp*")), "temp file left behind"


def test_set_idle_timeouts_preserves_user_keys_and_writes_sorted(env: Env) -> None:
    env.stub("omarchy-shell")
    env.config.mkdir(parents=True)
    (env.config / "shell.json").write_text(
        json.dumps({"plugins": ["x"], "idle": {"lock": 300, "screensaver": 150, "extra": 1}})
    )
    assert omarchy.set_idle_timeouts(screensaver=45) is True
    text = (env.config / "shell.json").read_text()
    written = json.loads(text)
    assert written == {"plugins": ["x"], "idle": {"lock": 300, "screensaver": 45, "extra": 1}}
    assert text == json.dumps(written, indent=2, sort_keys=True) + "\n"  # jq -S shape
    assert omarchy.idle_timeouts() == {"lock": 300, "screensaver": 45}


def test_set_idle_timeouts_clamps_to_bounds(env: Env) -> None:
    env.stub("omarchy-shell")
    assert omarchy.set_idle_timeouts(lock=-5, screensaver=10**9) is True
    assert omarchy.idle_timeouts() == {"lock": 0, "screensaver": omarchy.IDLE_MAX_S}


def test_set_idle_timeouts_falls_back_to_rescan_when_reload_fails(env: Env) -> None:
    env.stub("omarchy-shell", '[[ "$*" == "shell reloadConfig" ]] && exit 1; exit 0')
    assert omarchy.set_idle_timeouts(lock=120) is True
    assert env.logged() == [
        "omarchy-shell shell reloadConfig",
        "omarchy-shell -q shell rescanPlugins",
    ]


def test_set_idle_timeouts_without_shell_still_writes(env: Env, monkeypatch) -> None:
    monkeypatch.setenv("PATH", str(env.bins))  # no omarchy-shell at all
    assert omarchy.set_idle_timeouts(lock=120) is True
    assert omarchy.idle_timeouts()["lock"] == 120


# ---------------------------------------------------------------------------
# Stay awake — omarchy-toggle-idle
# ---------------------------------------------------------------------------


def test_stay_awake_reads_status_json(env: Env) -> None:
    env.stub(
        "omarchy-toggle-idle",
        'printf \'{"enabled":true,"class":"enabled","tooltip":"Allow Idle Lock & Screensaver"}\\n\'',
    )
    assert omarchy.stay_awake() is True
    assert env.logged() == ["omarchy-toggle-idle --status"]


def test_stay_awake_false_when_disabled_or_failing(env: Env) -> None:
    env.stub("omarchy-toggle-idle", 'printf \'{"enabled":false,"class":"disabled"}\\n\'')
    assert omarchy.stay_awake() is False
    env.stub("omarchy-toggle-idle", "exit 1")
    assert omarchy.stay_awake() is False
    env.stub("omarchy-toggle-idle", "echo not-json")
    assert omarchy.stay_awake() is False


def test_toggle_stay_awake_returns_new_state(env: Env) -> None:
    # omarchy-toggle-idle prints the resulting *idle* state.
    env.stub("omarchy-toggle-idle", "echo disabled")
    assert omarchy.toggle_stay_awake() is True
    env.stub("omarchy-toggle-idle", "echo enabled")
    assert omarchy.toggle_stay_awake() is False
    assert env.logged() == ["omarchy-toggle-idle ", "omarchy-toggle-idle "]


def test_toggle_stay_awake_none_on_failure(env: Env) -> None:
    env.stub("omarchy-toggle-idle", "exit 1")
    assert omarchy.toggle_stay_awake() is None


# ---------------------------------------------------------------------------
# Theme palette — current/theme/colors.toml
# ---------------------------------------------------------------------------


def test_theme_colors_reads_colors_toml(env: Env) -> None:
    cur = env.seed_theme()
    (cur / "theme" / "colors.toml").write_text(
        'mode = "dark"\naccent = "#8bc9eb"\nmuted = "#304860"\n'
        'background = "#16242d"\nforeground = "#d6e2ee"\nred = "#4d86b0"\n'
    )
    assert omarchy.theme_colors() == {
        "background": "#16242d",
        "foreground": "#d6e2ee",
        "accent": "#8bc9eb",
        "comment": "#304860",
    }


def test_theme_colors_skips_missing_or_malformed_values(env: Env) -> None:
    cur = env.seed_theme()
    (cur / "theme" / "colors.toml").write_text('background = "#16242d"\naccent = "blue"\n')
    assert omarchy.theme_colors() == {"background": "#16242d"}


def test_theme_colors_empty_without_file_or_on_bad_toml(env: Env) -> None:
    assert omarchy.theme_colors() == {}
    cur = env.seed_theme()
    (cur / "theme" / "colors.toml").write_text("this is = = not toml")
    assert omarchy.theme_colors() == {}
