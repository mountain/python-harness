"""
Core module for integrating all evaluations and producing the final report.
"""

from typing import Any

from python_harness.hard_evaluator import HardEvaluator
from python_harness.qc_evaluator import QCEvaluator
from python_harness.soft_evaluator import SoftEvaluator


class Evaluator:
    """
    Main evaluator coordinating hard, QC, and soft assessments.
    """

    def __init__(self, target_path: str):
        self.target_path = target_path
        self.hard_evaluator = HardEvaluator(target_path)
        self.qc_evaluator = QCEvaluator(target_path)
        self.soft_evaluator = SoftEvaluator(target_path)

    def run(self) -> dict[str, Any]:
        """
        Run the complete evaluation process.
        """
        hard_results = self.hard_evaluator.evaluate()
        qc_results = self.qc_evaluator.evaluate()
        soft_results = self.soft_evaluator.evaluate()

        # Generate Final Synthesized Report with 3 Suggestions
        final_report = self.soft_evaluator.generate_final_report(
            hard_results, soft_results
        )

        return {
            "hard_evaluation": hard_results,
            "qc_evaluation": qc_results,
            "soft_evaluation": soft_results,
            "final_report": final_report,
            "overall_status": "success",
        }
