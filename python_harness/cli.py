"""
Command-line interface for python-harness.
"""

import os
import sys
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv
from rich.console import Console

from python_harness.evaluator import Evaluator
from python_harness.refine_engine import run_refine

# Try to find .env file explicitly before anything else executes
env_path = os.path.join(os.getcwd(), '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv() # Fallback to default search

app = typer.Typer(help="Agentic harness tool for universal Python codebase evaluation.")
console = Console()
MI_HEALTHY_THRESHOLD = 70.0
MI_WARNING_THRESHOLD = 40.0


def _print_detail_block(title: str, details: str, color: str) -> None:
    normalized_details = [
        line.rstrip() for line in details.splitlines() if line.strip()
    ]
    console.print(f"[{color}]{title}:[/{color}]")
    for line in normalized_details:
        console.print(f"  {line}")
    console.print()


def _print_ruff_issues(
    issues: list[dict[str, Any]],
    error_message: str = "",
) -> None:
    console.print("[red]Ruff issues found:[/red]")
    for issue in issues:
        file = issue.get("filename", "unknown")
        line = issue.get("location", {}).get("row", "?")
        msg = issue.get("message", "unknown issue")
        console.print(f"  - {file}:{line} {msg}")
    if not issues and error_message:
        console.print(f"  {error_message}")
    console.print()


def _print_ty_result(ty_results: dict[str, Any]) -> None:
    status = ty_results.get("status")
    if status == "warning":
        msg = str(ty_results.get("error_message", "ty not found"))
        _print_detail_block("Ty warning", msg, "yellow")
        return
    if status == "success":
        return

    output = str(ty_results.get("output", ""))
    error_msg = str(ty_results.get("error_message", ""))
    if output:
        _print_detail_block("Ty issues found", output, "red")
    elif error_msg:
        _print_detail_block("Ty error", error_msg, "red")
    else:
        console.print("[red]Ty failed, but no standard output was captured.[/red]")


def _print_radon_cc_result(radon_results: dict[str, Any]) -> None:
    status = radon_results.get("status")
    if status == "warning":
        err_msg = str(radon_results.get("error_message", ""))
        _print_detail_block("Radon CC warning", err_msg, "yellow")
        return
    if status != "failed":
        return

    issues = radon_results.get("issues", [])
    if issues:
        console.print(
            f"[red]Cyclomatic Complexity too high "
            f"({len(issues)} functions > 15):[/red]"
        )
        for issue in issues:
            console.print(
                f"  - {issue['file']}: {issue['type']} '{issue['name']}' "
                f"has CC {issue['complexity']}"
            )
        console.print()
        return

    err_msg = str(radon_results.get("error_message", ""))
    if err_msg:
        _print_detail_block("Radon CC error", err_msg, "red")
        return
    console.print("[red]Radon CC failed but no specific issues were parsed.[/red]")
    console.print()


def _print_hard_failure_details(hard_results: dict[str, Any]) -> None:
    console.print("[bold red]Hard Evaluation Failed![/bold red]")
    console.print()

    ruff_issues = hard_results.get("ruff", {}).get("issues", [])
    if hard_results.get("ruff", {}).get("status") != "success":
        _print_ruff_issues(
            ruff_issues,
            str(hard_results.get("ruff", {}).get("error_message", "")),
        )

    if hard_results.get("mypy", {}).get("status") != "success":
        output = str(hard_results.get("mypy", {}).get("output", ""))
        _print_detail_block("Mypy issues found", output, "red")

    _print_ty_result(hard_results.get("ty", {}))
    _print_radon_cc_result(hard_results.get("radon_cc", {}))

    if hard_results.get("pytest", {}).get("status") == "failed":
        error_msg = str(hard_results.get("pytest", {}).get("error_message", ""))
        _print_detail_block("Pytest/Coverage issues found", error_msg, "red")

    console.print(
        "[yellow]Continuing to soft evaluation to generate "
        "suggestions despite hard failures...[/yellow]"
    )


def _print_hard_evaluation_summary(hard_results: dict[str, Any]) -> None:
    if hard_results["all_passed"]:
        console.print("[bold green]Hard Evaluation Passed![/bold green]")
        return
    _print_hard_failure_details(hard_results)


def _mi_scorecard_color(avg_mi: float) -> str:
    if avg_mi >= MI_HEALTHY_THRESHOLD:
        return "green"
    if avg_mi >= MI_WARNING_THRESHOLD:
        return "yellow"
    return "red"


def _print_mi_scorecard(hard_results: dict[str, Any]) -> None:
    mi_scores = hard_results.get("radon_mi", {}).get("mi_scores", {})
    if not mi_scores:
        return

    avg_mi = sum(mi_scores.values()) / len(mi_scores)
    color = _mi_scorecard_color(avg_mi)
    console.print(f"[{color}]Average Maintainability Index: {avg_mi:.1f}/100[/{color}]")


def _print_qc_summary(qc_results: dict[str, Any]) -> None:
    console.print()
    console.print("[bold blue]Running Governance QC (Second Fence)...[/bold blue]")

    if qc_results["all_passed"]:
        console.print(
            "[bold green]Governance QC Passed! (Change is admissible)[/bold green]"
        )
        console.print()
        return

    console.print("[bold red]Governance QC Failed![/bold red]")
    console.print()
    console.print(
        "[red]The proposed changes violate governance constraints "
        "or lack sufficient evidence.[/red]"
    )
    for failure in qc_results["failures"]:
        console.print(f"[red]- {failure}[/red]")
    console.print()
    console.print(
        "[yellow]Continuing to soft evaluation to generate "
        "suggestions despite QC failures...[/yellow]"
    )
    console.print()


def _print_soft_evaluation_start() -> None:
    console.print(
        "[bold blue]Running Soft Evaluation "
        "(Readability & Understandability)...[/bold blue]"
    )


def _print_soft_summary(soft_results: dict[str, Any]) -> None:
    pkg_summary = soft_results["package_summary"]
    console.print(
        f"[green]Analyzed {pkg_summary['total_files']} files with a total of "
        f"{pkg_summary['total_tokens']} tokens.[/green]"
    )
    console.print(
        f"[magenta]Agent's Understanding of the Package:[/magenta]\n"
        f"{pkg_summary['package_understanding']}"
    )

    console.print()
    console.print(
        f"[cyan]Overall Understandability Score:[/cyan] "
        f"{soft_results['understandability_score']:.1f}/100"
    )

    qa_results = soft_results.get("qa_results", {}).get("sampled_entities", [])
    if qa_results:
        console.print()
        console.print("[bold yellow]Blind QA Sampling Results:[/bold yellow]")
        for qa in qa_results:
            color = "green" if qa["score"] >= 80 else "red"
            console.print(f"  - [{color}]{qa['entity']}: Score {qa['score']}[/{color}]")
            console.print(f"    [dim]Feedback: {qa['feedback']}[/dim]")

    console.print()
    console.print("[yellow]Evaluation completed. Generating report...[/yellow]")
    console.print()


def _print_final_report(final_report: dict[str, Any]) -> None:
    verdict = str(final_report.get("verdict", "Unknown"))
    verdict_color = "bold green" if "Pass" in verdict else "bold red"

    console.print(
        f"[{verdict_color}]=== FINAL VERDICT: {verdict} ===[/{verdict_color}]"
    )
    console.print(f"[bold]Summary:[/bold] {final_report.get('summary', '')}")
    console.print()

    suggestions = final_report.get("suggestions", [])
    if suggestions:
        console.print("[bold cyan]Top 3 Improvement Suggestions:[/bold cyan]")
        for i, sug in enumerate(suggestions[:3], 1):
            console.print(
                f"  {i}. [bold]{sug.get('title', 'Suggestion')}[/bold] "
                f"(Target: [yellow]{sug.get('target_file', 'unknown')}[/yellow])"
            )
            console.print(f"     [dim]{sug.get('description', '')}[/dim]")


@app.command()
def refine(
    path: str = typer.Argument(".", help="The path to evaluate and evolve"),
    max_retries: int = typer.Option(3, help="Maximum retries per candidate"),
    loop: bool = typer.Option(False, help="Keep refining winners across rounds"),
    max_rounds: int = typer.Option(3, help="Maximum refine rounds when looping"),
) -> None:
    """
    Refine the codebase through a fixed two-level search and optional loop.
    """
    console.print(
        f"[bold magenta]Starting refine for path:[/bold magenta] {path} "
        f"[dim](loop={loop}, max_rounds={max_rounds}, "
        f"max_retries={max_retries})[/dim]"
    )
    target_path = Path(path).resolve()

    result = run_refine(
        target_path=target_path,
        max_retries=max_retries,
        loop=loop,
        max_rounds=max_rounds,
    )
    console.print(f"[green]winner_id:[/green] {result['winner_id']}")
    console.print(f"[cyan]rounds_completed:[/cyan] {result['rounds_completed']}")
    console.print(f"[yellow]stop_reason:[/yellow] {result['stop_reason']}")
@app.command()
def measure(path: str = typer.Argument(".", help="The path to evaluate")) -> None:
    """
    Measure the codebase against hard, soft, and governance constraints.
    Outputs a final report with scores and actionable improvement suggestions.
    """
    console.print(
        f"[bold green]Starting harness measurement for path:[/bold green] {path}"
    )
    
    evaluator = Evaluator(path)
    console.print("[bold blue]Running Hard Evaluation (ruff, mypy)...[/bold blue]")
    hard_results = evaluator.hard_evaluator.evaluate()
    _print_hard_evaluation_summary(hard_results)
    _print_mi_scorecard(hard_results)

    qc_results = evaluator.qc_evaluator.evaluate()
    _print_qc_summary(qc_results)

    _print_soft_evaluation_start()
    soft_results = evaluator.soft_evaluator.evaluate()
    _print_soft_summary(soft_results)

    final_report = evaluator.soft_evaluator.generate_final_report(
        hard_results, qc_results, soft_results
    )
    if not final_report:
        return

    _print_final_report(final_report)
    if "Fail" in str(final_report.get("verdict", "Unknown")):
        sys.exit(1)


if __name__ == "__main__":
    app()
