"""
Core module for integrating hard evaluation tools like ruff, mypy, and pytest.
"""

from pathlib import Path
from typing import Any

from python_harness.hard_eval_helpers import (
    apply_pytest_coverage_gate,
    collect_radon_metric_targets,
    compute_all_passed,
    run_mypy,
    run_pytest,
    run_radon_cc,
    run_radon_mi,
    run_ruff,
    run_ty,
)

PYTEST_TIMEOUT_SECONDS = 60

class HardEvaluator:
    """
    Evaluator for collecting structural code quality metrics.
    """

    def __init__(self, target_path: str):
        self.target_path = Path(target_path).resolve()

    def _radon_metric_targets(self) -> list[str]:
        return collect_radon_metric_targets(self.target_path)

    def run_ruff(self) -> dict[str, Any]:
        """
        Run Ruff linter and return results.
        """
        return run_ruff(self.target_path)

    def run_mypy(self) -> dict[str, Any]:
        """
        Run Mypy type checker and return results.
        """
        return run_mypy(self.target_path)

    def run_ty(self) -> dict[str, Any]:
        """
        Run ty language server checks.
        If ty is not installed, fail gracefully rather than crashing.
        """
        return run_ty(self.target_path)

    def run_radon_cc(self) -> dict[str, Any]:
        """
        Run Radon cyclomatic complexity check.
        Flag any function/method with CC > 15 as a failure.
        """
        return run_radon_cc(self.target_path)

    def run_radon_mi(self) -> dict[str, Any]:
        """
        Run Radon Maintainability Index (MI) check.
        This is a diagnostic metric, so it won't fail the build,
        but it contributes to the scorecard.
        """
        return run_radon_mi(self.target_path)

    def run_pytest(self) -> dict[str, Any]:
        """
        Run Pytest test suite and return coverage results.
        """
        return run_pytest(self.target_path, timeout_seconds=PYTEST_TIMEOUT_SECONDS)

    def evaluate(self) -> dict[str, Any]:
        """
        Execute all hard evaluation tools.
        Returns a dictionary with results and an overall success boolean.
        """
        ruff_res = self.run_ruff()
        mypy_res = self.run_mypy()
        ty_res = self.run_ty()
        radon_cc_res = self.run_radon_cc()
        radon_mi_res = self.run_radon_mi()
        pytest_res = apply_pytest_coverage_gate(self.run_pytest())

        all_passed = compute_all_passed(
            ruff_result=ruff_res,
            mypy_result=mypy_res,
            ty_result=ty_res,
            radon_cc_result=radon_cc_res,
            pytest_result=pytest_res,
        )

        return {
            "all_passed": all_passed,
            "ruff": ruff_res,
            "mypy": mypy_res,
            "ty": ty_res,
            "radon_cc": radon_cc_res,
            "radon_mi": radon_mi_res,
            "pytest": pytest_res,
        }
