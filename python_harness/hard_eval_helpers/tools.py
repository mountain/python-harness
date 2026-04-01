"""
Subprocess-backed hard evaluation tool runners.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from python_harness.hard_eval_helpers.radon import (
    collect_radon_metric_targets,
    load_radon_json,
    parse_radon_cc_issues,
    parse_radon_mi_scores,
    radon_missing_result,
)


def run_ruff(target_path: Path) -> dict[str, Any]:
    """
    Run Ruff linter and return JSON issues when available.
    """
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                str(target_path),
                "--output-format",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        issues = json.loads(result.stdout) if result.stdout else []
        status = "success" if result.returncode == 0 else "failed"
        return {
            "status": status,
            "issues": issues,
            "return_code": result.returncode,
            "error_message": result.stderr.strip(),
        }
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)}


def run_mypy(target_path: Path) -> dict[str, Any]:
    """
    Run Mypy type checking on the target path.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mypy", str(target_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        status = "success" if result.returncode == 0 else "failed"
        return {
            "status": status,
            "output": result.stdout or result.stderr,
            "return_code": result.returncode,
        }
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)}


def run_ty(target_path: Path) -> dict[str, Any]:
    """
    Run ty checks and degrade gracefully when ty is unavailable.
    """
    try:
        result = subprocess.run(
            ["ty", "check", str(target_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        status = "success" if result.returncode == 0 else "failed"
        output = result.stdout if result.stdout else result.stderr
        return {
            "status": status,
            "output": output,
            "return_code": result.returncode,
        }
    except FileNotFoundError:
        return {
            "status": "warning",
            "error_message": "ty executable not found. Skipping ty checks.",
        }
    except Exception as exc:
        if "No such file or directory: 'ty'" in str(exc):
            return {
                "status": "warning",
                "error_message": "ty executable not found. Skipping ty checks.",
            }
        return {"status": "error", "error_message": str(exc)}


def run_radon_cc(target_path: Path) -> dict[str, Any]:
    """
    Run Radon cyclomatic complexity checks on discovered Python files.
    """
    try:
        targets = collect_radon_metric_targets(target_path)
        if not targets:
            return {
                "status": "success",
                "issues": [],
                "return_code": 0,
                "output": "",
            }
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "radon",
                "cc",
                "-j",
                "-a",
                *targets,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        issues = parse_radon_cc_issues(load_radon_json(result.stdout))
        status = "success"
        if result.returncode != 0 or issues:
            status = "failed"
        return {
            "status": status,
            "issues": issues,
            "return_code": result.returncode,
            "output": result.stdout,
            "error_message": result.stderr if result.returncode != 0 else "",
        }
    except FileNotFoundError:
        return radon_missing_result()
    except Exception as exc:
        if "No module named radon" in str(exc) or "radon" in str(exc):
            return radon_missing_result()
        return {"status": "error", "error_message": str(exc)}


def run_radon_mi(target_path: Path) -> dict[str, Any]:
    """
    Run Radon maintainability index checks on discovered Python files.
    """
    try:
        targets = collect_radon_metric_targets(target_path)
        if not targets:
            return {"status": "success", "mi_scores": {}, "return_code": 0}
        result = subprocess.run(
            [sys.executable, "-m", "radon", "mi", "-j", *targets],
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "status": "success",
            "mi_scores": parse_radon_mi_scores(load_radon_json(result.stdout)),
            "return_code": result.returncode,
        }
    except FileNotFoundError:
        return radon_missing_result(include_scores=True)
    except Exception as exc:
        if "No module named radon" in str(exc) or "radon" in str(exc):
            return radon_missing_result(include_scores=True)
        return {"status": "error", "error_message": str(exc)}


def run_pytest(target_path: Path, *, timeout_seconds: int) -> dict[str, Any]:
    """
    Run pytest with coverage JSON output and capture total coverage.
    """
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            coverage_report = Path(tmp_dir) / "coverage.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(target_path),
                    "--cov",
                    f"--cov-report=json:{coverage_report}",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
            coverage_percentage = None
            if coverage_report.exists():
                coverage_data = json.loads(coverage_report.read_text())
                coverage_percentage = coverage_data.get("totals", {}).get(
                    "percent_covered"
                )
        status = "success" if result.returncode == 0 else "failed"
        return {
            "status": status,
            "output": result.stdout,
            "return_code": result.returncode,
            "coverage_percentage": coverage_percentage,
            "error_message": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "error_message": (
                f"Pytest run timed out after {timeout_seconds} seconds."
            ),
        }
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)}
