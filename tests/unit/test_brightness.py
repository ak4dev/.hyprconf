"""hyprconf-brightness — the backlight keys' wrapper.

The bare `brightnessctl set 5%-` binding these replaced had three failure modes
that only show up on real hardware: it walked the panel to 0% and left it dark,
it silently dimmed a keyboard LED on machines with no backlight at all (with no
backlight device, brightnessctl falls through to the first LED it finds), and
it gave no feedback. All three are covered here against a fake brightnessctl.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIGHTNESS = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf-brightness"

FAKE_BRIGHTNESSCTL = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{calls}"
# -m: the machine-readable line the wrapper parses for the new percentage.
for arg in "$@"; do
    if [[ "$arg" == "-m" ]]; then
        echo "intel_backlight,backlight,52428,{percent}%,96000"
        exit 0
    fi
done
exit 0
"""

FAKE_LAUNCH = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{calls}"
{body}
"""


def _run(
    tmp_path: Path,
    args: list[str],
    *,
    has_backlight: bool = True,
    percent: int = 55,
    launch_body: str = "exit 0",
    launch_executable: bool = True,
) -> tuple[int, str, list[str], list[str]]:
    """Run the script against fakes. Returns (rc, stdout, brightnessctl, osd)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    bctl_calls = tmp_path / "brightnessctl.calls"
    osd_calls = tmp_path / "osd.calls"

    bctl = bin_dir / "brightnessctl"
    bctl.write_text(FAKE_BRIGHTNESSCTL.format(calls=bctl_calls, percent=percent))
    bctl.chmod(0o755)

    launch = tmp_path / "launch.sh"
    launch.write_text(FAKE_LAUNCH.format(calls=osd_calls, body=launch_body))
    launch.chmod(0o755 if launch_executable else 0o644)

    backlight_root = tmp_path / "backlight"
    if has_backlight:
        device = backlight_root / "intel_backlight"
        device.mkdir(parents=True)
        (device / "brightness").write_text("52428\n")
    else:
        backlight_root.mkdir()

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["_HYPRCONF_BACKLIGHT_ROOT"] = str(backlight_root)
    env["_HYPRCONF_QS_LAUNCH"] = str(launch)
    env["_HYPRCONF_RUNTIME_DIR"] = str(tmp_path)

    result = subprocess.run(
        [shutil.which("bash") or "bash", str(BRIGHTNESS), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    def _lines(path: Path) -> list[str]:
        return [ln for ln in path.read_text().splitlines() if ln.strip()] if path.exists() else []

    return result.returncode, result.stdout, _lines(bctl_calls), _lines(osd_calls)


class TestSteps:
    def test_up_raises_and_down_lowers(self, tmp_path):
        _, _, up, _ = _run(tmp_path / "a", ["up"])
        _, _, down, _ = _run(tmp_path / "b", ["down"])
        assert any("set 5%+" in call for call in up), up
        assert any("set 5%-" in call for call in down), down

    def test_never_dims_to_zero(self, tmp_path):
        """A 5% step of zero is still zero, and the up key cannot always
        recover a dark panel — so the floor is passed on every call."""
        for direction in ("up", "down"):
            _, _, calls, _ = _run(tmp_path / direction, [direction])
            assert any("-n2" in call for call in calls), calls

    def test_steps_on_a_perceptual_curve(self, tmp_path):
        _, _, calls, _ = _run(tmp_path, ["up"])
        assert any("-e4" in call for call in calls), calls

    def test_stays_on_the_backlight_class(self, tmp_path):
        """Without -c, brightnessctl picks the first device of its default
        class; the keys must never reach a keyboard LED."""
        _, _, calls, _ = _run(tmp_path, ["up"])
        for call in calls:
            assert "-c backlight" in call, call


class TestNoBacklight:
    def test_desktop_is_a_no_op(self, tmp_path):
        """No backlight device: the key does nothing, quietly and successfully."""
        rc, _, calls, osd = _run(tmp_path, ["up"], has_backlight=False)
        assert rc == 0
        assert calls == [], "touched a brightness device on a machine with no backlight"
        assert osd == []


class TestOsdFeedback:
    def test_reports_the_resulting_level(self, tmp_path):
        _, _, _, osd = _run(tmp_path, ["up"], percent=42)
        assert osd == ["ipc call osd brightness 42"]

    def test_a_missing_bar_does_not_fail_the_keypress(self, tmp_path):
        """The backlight already changed; a shell that is not running (or is
        restarting) must not turn that into a failed keybind."""
        rc, _, calls, _ = _run(tmp_path, ["up"], launch_body="exit 1")
        assert rc == 0
        assert calls, "the brightness change itself must still have happened"

    def test_no_launcher_installed_is_fine(self, tmp_path):
        rc, _, calls, osd = _run(tmp_path, ["up"], launch_executable=False)
        assert rc == 0
        assert calls
        assert osd == []


class TestCli:
    def test_get_prints_the_percentage(self, tmp_path):
        rc, stdout, _, _ = _run(tmp_path, ["get"], percent=77)
        assert rc == 0
        assert stdout.strip() == "77"

    def test_unknown_argument_is_an_error(self, tmp_path):
        rc, _, calls, _ = _run(tmp_path, ["sideways"])
        assert rc != 0
        assert calls == []

    def test_no_argument_is_an_error(self, tmp_path):
        """`hyprconf-brightness` with no verb must not guess a direction."""
        rc, _, calls, _ = _run(tmp_path, [])
        assert rc != 0
        assert calls == []


class TestScriptShape:
    def test_ships_executable_with_a_bash_shebang(self):
        assert BRIGHTNESS.is_file()
        assert os.access(BRIGHTNESS, os.X_OK)
        assert BRIGHTNESS.read_text().splitlines()[0] == "#!/usr/bin/env bash"

    def test_overlapping_key_repeats_are_dropped(self):
        """Held keys fire faster than brightnessctl returns; queued presses
        would keep stepping after the key was released."""
        assert "flock -n" in BRIGHTNESS.read_text()


class TestOsdContract:
    """The other half of the feedback path: what the script calls must exist.

    `qs ipc call osd brightness <pct>` is the whole contract — if the handler
    is renamed or its argument stops being typed, the keys keep working and
    silently stop reporting.
    """

    QML_DIR = REPO_ROOT / "stow" / "quickshell" / ".config" / "quickshell"

    def test_shell_exposes_the_osd_ipc_target(self):
        shell = (self.QML_DIR / "shell.qml").read_text(encoding="utf-8")
        assert 'target: "osd"' in shell
        assert "function brightness(percent: int): string" in shell, (
            "IpcHandler arguments and returns must be typed"
        )

    def test_the_osd_clamps_what_it_is_handed(self):
        """Anything with access to the session can call an IpcHandler."""
        osd = (self.QML_DIR / "Osd.qml").read_text(encoding="utf-8")
        assert "function showBrightness" in osd
        assert "Math.max(0, Math.min(100," in osd

    def test_the_osd_still_shows_volume(self):
        """The pill is shared; a brightness mode that swallowed the volume path
        would silently drop the feedback the volume keys have always had."""
        osd = (self.QML_DIR / "Osd.qml").read_text(encoding="utf-8")
        assert "onVolumeChanged" in osd
        assert "onMutedChanged" in osd
