"""
Core module for integrating hard evaluation tools like ruff, mypy, and pytest.
"""

import json
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()

class HardEvaluator:
    """
    Evaluator for collecting structural code quality metrics.
    """

    def __init__(self, target_path: str):
        self.target_path = Path(target_path).resolve()

    def run_ruff(self) -> dict[str, Any]:
        """
        Run Ruff linter and return results.
        """
        try:
            result = subprocess.run(
                ["ruff", "check", str(self.target_path), "--output-format", "json"],
                capture_output=True,
                text=True,
                check=False
            )
            issues = json.loads(result.stdout) if result.stdout else []
            status = "success" if result.returncode == 0 else "failed"
            return {
                "status": status,
                "issues": issues,
                "return_code": result.returncode,
            }
        except Exception as e:
            return {"status": "error", "error_message": str(e)}

    def run_mypy(self) -> dict[str, Any]:
        """
        Run Mypy type checker and return results.
        """
        try:
            result = subprocess.run(
                ["mypy", str(self.target_path)],
                capture_output=True,
                text=True,
                check=False
            )
            status = "success" if result.returncode == 0 else "failed"
            return {
                "status": status,
                "output": result.stdout,
                "return_code": result.returncode,
            }
        except Exception as e:
            return {"status": "error", "error_message": str(e)}

    def run_ty(self) -> dict[str, Any]:
        """
        Run ty language server checks.
        """
        try:
            result = subprocess.run(
                ["ty", "check", str(self.target_path)],
                capture_output=True,
                text=True,
                check=False
            )
            status = "success" if result.returncode == 0 else "failed"
            # ty might print to stderr
            output = result.stdout if result.stdout else result.stderr
            return {
                "status": status,
                "output": output,
                "return_code": result.returncode,
            }
        except Exception as e:
            return {"status": "error", "error_message": str(e)}

    def run_radon_cc(self) -> dict[str, Any]:
        """
        Run Radon cyclomatic complexity check.
        Flag any function/method with CC > 15 as a failure.
        """
        try:
            result = subprocess.run(
                ["radon", "cc", "-j", "-a", str(self.target_path)],
                capture_output=True,
                text=True,
                check=False
            )
            
            issues = []
            status = "success"
            
            if result.stdout:
                data = json.loads(result.stdout)
                for file_path, blocks in data.items():
                    if isinstance(blocks, list):
                        for block in blocks:
                            if block.get('complexity', 0) > 15:
                                issues.append({
                                    "file": file_path,
                                    "name": block.get('name'),
                                    "type": block.get('type'),
                                    "complexity": block.get('complexity')
                                })
            
            if issues:
                status = "failed"
                
            return {
                "status": status,
                "issues": issues,
                "return_code": result.returncode,
                "output": result.stdout
            }
        except Exception as e:
            return {"status": "error", "error_message": str(e)}

    def run_radon_mi(self) -> dict[str, Any]:
        """
        Run Radon Maintainability Index (MI) check.
        This is a diagnostic metric, so it won't fail the build,
        but it contributes to the scorecard.
        """
        try:
            result = subprocess.run(
                ["radon", "mi", "-j", str(self.target_path)],
                capture_output=True,
                text=True,
                check=False
            )
            
            mi_scores = {}
            if result.stdout:
                data = json.loads(result.stdout)
                for file_path, info in data.items():
                    mi_scores[file_path] = info.get('mi', 100.0)
                    
            return {
                "status": "success",
                "mi_scores": mi_scores,
                "return_code": result.returncode,
            }
        except Exception as e:
            return {"status": "error", "error_message": str(e)}

    def run_pytest(self) -> dict[str, Any]:
        """
        Run Pytest test suite and return coverage results.
        """
        try:
            # When pytest is run within pytest, it can cause issues or hang.
            # Here we just run it as a subprocess to gather results.
            result = subprocess.run(
                ["pytest", str(self.target_path), "--cov", "--cov-report=json"],
                capture_output=True,
                text=True,
                check=False
            )
            status = "success" if result.returncode == 0 else "failed"
            return {
                "status": status,
                "output": result.stdout,
                "return_code": result.returncode,
            }
        except Exception as e:
             return {"status": "error", "error_message": str(e)}

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
        # pytest_res = self.run_pytest() # Better handled as a separate stage
        
        all_passed = (
            ruff_res.get("status") == "success" and 
            mypy_res.get("status") == "success" and
            ty_res.get("status") == "success" and
            radon_cc_res.get("status") == "success"
        )

        return {
            "all_passed": all_passed,
            "ruff": ruff_res,
            "mypy": mypy_res,
            "ty": ty_res,
            "radon_cc": radon_cc_res,
            "radon_mi": radon_mi_res
        }
