import subprocess
import sys
from pathlib import Path


def run_command(path: Path, args: list[str]) -> tuple[bool, str]:
    command_cwd = path if path.is_dir() else path.parent
    completed = subprocess.run(
        args,
        cwd=command_cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, output


def default_self_check_runner(path: Path) -> tuple[bool, str]:
    checks = [
        [sys.executable, "-m", "ruff", "check", str(path)],
        [sys.executable, "-m", "mypy", str(path)],
        [sys.executable, "-m", "pytest", str(path)],
    ]
    for args in checks:
        ok, output = run_command(path, args)
        if not ok:
            return False, output
    return True, ""
