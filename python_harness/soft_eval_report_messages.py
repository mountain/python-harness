import json
from typing import Any

from python_harness.soft_eval_report_shared import MI_PASS_THRESHOLD, QA_PASS_THRESHOLD


def build_final_report_messages(metrics: dict[str, Any]) -> list[dict[str, str]]:
    sys_prompt = (
        "You are an elite Python Codebase Evaluator. You have just analyzed "
        "a repository. Your task is to provide a final judgment and EXACTLY "
        "3 concrete, actionable improvement suggestions.\n"
        "If the codebase failed its Hard or QC evaluations (e.g. tests "
        "failed, coverage is low, or governance violated), your suggestions "
        "MUST prioritize fixing those issues.\n"
        "Otherwise, focus on refactoring/quality improvements without "
        "changing external functionality.\n\n"
        "Each suggestion MUST target exactly one concrete Python file in "
        "`target_file`; never use `all`, directories, or vague scope.\n"
        "Prefer local, mechanical, low-risk improvements over broad "
        "maintainability or architecture slogans.\n"
        "Avoid suggestions that mainly rewrite comments, docstrings, or "
        "formatting.\n\n"
        "Output MUST be in valid JSON matching this schema:\n"
        "{\n"
        '  "verdict": "Pass" or "Fail",\n'
        '  "summary": "One paragraph summary of codebase health and '
        'any critical failures",\n'
        '  "suggestions": [\n'
        '    {"title": "str", "description": "str", "target_file": "str"}\n'
        "  ]\n"
        "}\n"
        "Rule for Verdict: If there are Hard Failures or QC Failures, "
        "verdict MUST be Fail. Otherwise, Pass if Average Maintainability "
        f">= {MI_PASS_THRESHOLD:.0f} and QA Score > {QA_PASS_THRESHOLD:.0f} "
        "and no Critical CC issues (>15). Otherwise Fail."
    )
    user_content = (
        f"Metrics:\n"
        f"- Average Maintainability Index (MI): {metrics['avg_mi']:.1f}/100\n"
        f"- Number of functions with Cyclomatic Complexity > 15: "
        f"{len(metrics['cc_issues'])}\n"
        f"- Agent QA Readability Score: {metrics['qa_score']:.1f}/100\n\n"
        f"Failures (Prioritize these!):\n"
        f"- Hard Evaluation Errors: "
        f"{metrics['hard_errors'] if metrics['hard_errors'] else 'None'}\n"
        f"- QC/Governance Errors: "
        f"{metrics['qc_errors'] if metrics['qc_errors'] else 'None'}\n\n"
        f"QA Feedback Snippets:\n"
        + "\n".join(
            [f"  * {q['entity']}: {q['feedback']}" for q in metrics["qa_entities"]]
        )
    )
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_content},
    ]


def parse_final_report_response(raw_content: str) -> dict[str, Any]:
    parsed_json = json.loads(raw_content)
    if isinstance(parsed_json, dict):
        return parsed_json
    raise ValueError("JSON response is not a dictionary.")
