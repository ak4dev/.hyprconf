"""Tests for stow/hypr/.local/bin/autorotate."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parent.parent.parent
    / "stow" / "hypr" / ".local" / "bin" / "autorotate"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source_functions() -> str:
    """Return bash snippet that defines only the helper functions from autorotate.

    Stops before the main body (which starts with the retries loop) so sourcing
    in a test doesn't try to connect to a live Hyprland socket.
    """
    lines = SCRIPT.read_text().splitlines()
    func_lines: list[str] = []
    for line in lines:
        if line.startswith("# Wait until hyprctl") or line.startswith("retries="):
            break
        func_lines.append(line)
    return "\n".join(func_lines)


def _run_function(fn_call: str, extra_env: dict | None = None) -> tuple[int, str]:
    code = _source_functions() + "\n" + fn_call
    env = {**os.environ, **(extra_env or {})}
    result = subprocess.run(["bash", "-c", code], capture_output=True, text=True, env=env)
    return result.returncode, result.stdout.strip()


def _fake_hyprctl(tmp: Path, monitor_json: str, calls_file: Path) -> Path:
    """Create a fake hyprctl binary in *tmp* that records keyword calls."""
    fake = tmp / "hyprctl"
    fake.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "monitors" ]]; then
    echo '{monitor_json}'
elif [[ "$1" == "keyword" ]]; then
    echo "$2 $3" >> "{calls_file}"
fi
""")
    fake.chmod(0o755)
    return fake


# ---------------------------------------------------------------------------
# _transform_for — all orientations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("orientation,expected", [
    ("normal",    "0"),
    ("bottom-up", "2"),
    ("left-up",   "1"),
    ("right-up",  "3"),
    ("unknown",   "0"),
    ("",          "0"),
])
def test_transform_for_all_orientations(orientation: str, expected: str) -> None:
    rc, out = _run_function(f"_transform_for '{orientation}'")
    assert rc == 0
    assert out == expected


# ---------------------------------------------------------------------------
# _current_scale — reads scale from hyprctl monitors -j
# ---------------------------------------------------------------------------

def test_current_scale_returns_configured_scale(tmp_path: Path) -> None:
    monitor_json = json.dumps([{"name": "eDP-1", "scale": 1.5}])
    calls = tmp_path / "calls.txt"
    _fake_hyprctl(tmp_path, monitor_json, calls)
    env = {"PATH": str(tmp_path) + ":" + os.environ.get("PATH", "")}
    rc, out = _run_function("_current_scale eDP-1", env)
    assert rc == 0
    assert out == "1.5"


def test_current_scale_returns_auto_when_monitor_not_found(tmp_path: Path) -> None:
    monitor_json = json.dumps([{"name": "HDMI-1", "scale": 1.0}])
    calls = tmp_path / "calls.txt"
    _fake_hyprctl(tmp_path, monitor_json, calls)
    env = {"PATH": str(tmp_path) + ":" + os.environ.get("PATH", "")}
    rc, out = _run_function("_current_scale eDP-1", env)
    assert rc == 0
    assert out == "auto"


def test_current_scale_returns_auto_on_hyprctl_failure(tmp_path: Path) -> None:
    fake = tmp_path / "hyprctl"
    fake.write_text("#!/usr/bin/env bash\nexit 1\n")
    fake.chmod(0o755)
    env = {"PATH": str(tmp_path) + ":" + os.environ.get("PATH", "")}
    rc, out = _run_function("_current_scale eDP-1", env)
    assert rc == 0
    assert out == "auto"


# ---------------------------------------------------------------------------
# _apply_transform — full monitor keyword format
# ---------------------------------------------------------------------------

def test_apply_transform_uses_full_monitor_spec(tmp_path: Path) -> None:
    """hyprctl keyword monitor must receive NAME,preferred,auto,SCALE,transform,N."""
    monitor_json = json.dumps([{"name": "eDP-1", "scale": 1.25}])
    calls = tmp_path / "calls.txt"
    _fake_hyprctl(tmp_path, monitor_json, calls)
    env = {"PATH": str(tmp_path) + ":" + os.environ.get("PATH", "")}

    _run_function("_apply_transform eDP-1 1", env)

    recorded = calls.read_text().strip()
    # Must have 5 comma-separated components: NAME,preferred,auto,SCALE,transform,N
    assert recorded.startswith("monitor eDP-1,preferred,auto,"), (
        f"Expected full monitor spec, got: {recorded!r}"
    )
    assert ",transform,1" in recorded


def test_apply_transform_preserves_scale(tmp_path: Path) -> None:
    monitor_json = json.dumps([{"name": "eDP-1", "scale": 2.0}])
    calls = tmp_path / "calls.txt"
    _fake_hyprctl(tmp_path, monitor_json, calls)
    env = {"PATH": str(tmp_path) + ":" + os.environ.get("PATH", "")}

    _run_function("_apply_transform eDP-1 2", env)

    recorded = calls.read_text().strip()
    assert "2.0,transform,2" in recorded


def test_apply_transform_falls_back_to_auto_scale(tmp_path: Path) -> None:
    """When hyprctl returns no monitor info, scale must fall back to 'auto'."""
    monitor_json = json.dumps([])
    calls = tmp_path / "calls.txt"
    _fake_hyprctl(tmp_path, monitor_json, calls)
    env = {"PATH": str(tmp_path) + ":" + os.environ.get("PATH", "")}

    _run_function("_apply_transform eDP-1 0", env)

    recorded = calls.read_text().strip()
    assert "eDP-1,preferred,auto,auto,transform,0" in recorded


def test_apply_transform_does_not_use_short_spec(tmp_path: Path) -> None:
    """Regression: the old broken format 'DISPLAY,transform,N' must not appear."""
    monitor_json = json.dumps([{"name": "eDP-1", "scale": 1.0}])
    calls = tmp_path / "calls.txt"
    _fake_hyprctl(tmp_path, monitor_json, calls)
    env = {"PATH": str(tmp_path) + ":" + os.environ.get("PATH", "")}

    _run_function("_apply_transform eDP-1 3", env)

    recorded = calls.read_text().strip()
    # Old broken format would be "monitor eDP-1,transform,3" — must NOT match
    assert recorded != "monitor eDP-1,transform,3", (
        "Old broken short monitor spec detected — hyprctl will silently ignore it"
    )


# ---------------------------------------------------------------------------
# End-to-end: orientation change triggers correct hyprctl call
# ---------------------------------------------------------------------------

def test_e2e_orientation_change_applies_correct_transform(tmp_path: Path) -> None:
    """Feed a monitor-sensor line through the script; verify hyprctl keyword call."""
    monitor_json = json.dumps([{"name": "eDP-1", "scale": 1.0}])
    calls = tmp_path / "calls.txt"

    # fake hyprctl: monitors returns JSON, keyword records calls, always exits 0
    fake_hc = tmp_path / "hyprctl"
    fake_hc.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "monitors" ]]; then
    echo '{monitor_json}'
elif [[ "$1" == "keyword" ]]; then
    echo "$2 $3" >> "{calls}"
fi
""")
    fake_hc.chmod(0o755)

    # fake monitor-sensor: emits one orientation line then exits
    fake_ms = tmp_path / "monitor-sensor"
    fake_ms.write_text(
        "#!/usr/bin/env bash\necho '    Accelerometer orientation changed: bottom-up'\n"
    )
    fake_ms.chmod(0o755)

    env = {**os.environ, "PATH": str(tmp_path) + ":" + os.environ.get("PATH", "")}

    # Run autorotate with a 5-second timeout; after monitor-sensor exits and
    # sleep 2 completes, the script will try monitor-sensor again (exits again),
    # sleep 2 again — timeout stops it before any harm.
    subprocess.run(
        ["timeout", "6", "bash", str(SCRIPT)],
        env=env, capture_output=True,
    )

    recorded = calls.read_text().strip()
    # bottom-up → transform 2; must include full spec
    assert "eDP-1,preferred,auto" in recorded
    assert ",transform,2" in recorded
