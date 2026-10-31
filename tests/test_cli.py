import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
SUBCOMMANDS = ["analyze", "evaluate", "improve", "compare", "promote", "rollback", "resume"]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(SRC), os.environ.get("PYTHONPATH")]))}
    return subprocess.run(
        [sys.executable, "-m", "investigator.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_module_help_prints_usage_and_exits_successfully() -> None:
    # Runs the real `__main__` block, so hard-coded arguments there
    # (instead of reading sys.argv) make this fail.
    result = _run_cli("--help")

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage: investigator")
    for cmd in SUBCOMMANDS:
        assert cmd in result.stdout


@pytest.mark.parametrize("cmd", SUBCOMMANDS)
def test_subcommand_help_prints_usage(cmd: str) -> None:
    result = _run_cli(cmd, "--help")

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(f"usage: investigator {cmd}")


def test_no_arguments_is_a_usage_error() -> None:
    result = _run_cli()

    assert result.returncode == 2
    assert "usage: investigator" in result.stderr
