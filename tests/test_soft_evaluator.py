"""
Tests for soft evaluation logic.
"""

import os
from pathlib import Path

from python_harness.soft_evaluator import SoftEvaluator


def test_soft_evaluator_methods() -> None:
    """
    Test methods of SoftEvaluator.
    """
    # Create a dummy file to test the token complexity calculation
    dummy_file = Path("dummy_soft.py")
    with open(dummy_file, "w") as f:
        f.write("def foo():\n    pass\n")

    # Create an empty .env file or just temporarily remove LLM_API_KEY from env
    # so we don't accidentally spend tokens during tests unless explicitly intended.
    old_key = os.environ.pop("LLM_API_KEY", None)

    try:
        evaluator = SoftEvaluator(".")
        
        file_summary = evaluator.summarize_file(dummy_file)
        assert "tokens" in file_summary
        assert "summary" in file_summary
        
        pkg_summary = evaluator.summarize_package()
        assert "total_tokens" in pkg_summary
        assert "file_level_summaries" in pkg_summary
        
        eval_result = evaluator.evaluate()
        assert eval_result["status"] == "success"
        assert "understandability_score" in eval_result
    finally:
        if os.path.exists(dummy_file):
            os.remove(dummy_file)
        if old_key is not None:
            os.environ["LLM_API_KEY"] = old_key
